export const PERSONAL_MODEL_VERSION = "personal-v3";
export const PROFILE_STATE_KEY = "content-intelligence-profile";
export const RECOMPUTE_DEBOUNCE_MS = 60_000;
export const PERSONAL_POLICY_VERSION = "compressed-profile-bounded-rank-v3";
export const EVENT_WEIGHTS = {
  shown: 0,
  selected: 1,
  deep_read: 2,
  saved: 3,
  interest_saved: 3.5,
  liked: 5,
  disliked: -5,
};

const AUTO_FEATURE_MODELS = new Set(["semantic-bridge-v3", "reader-bridge-v2", "rules-v1"]);

export function isSupportedContentEvent(eventType) {
  return Object.prototype.hasOwnProperty.call(EVENT_WEIGHTS, String(eventType || ""));
}

export async function markProfileDirty(env, reason = "content_intelligence_event") {
  if (!env?.DB) return;
  await env.DB.prepare(`
    INSERT INTO workflow_state(source,status,detail,updated_at)
    VALUES(?, 'dirty', ?, CURRENT_TIMESTAMP)
    ON CONFLICT(source) DO UPDATE SET status='dirty', detail=excluded.detail, updated_at=CURRENT_TIMESTAMP
  `).bind(PROFILE_STATE_KEY, JSON.stringify({ reason })).run();
}

async function profileState(env) {
  return env.DB.prepare("SELECT status,detail,updated_at FROM workflow_state WHERE source=?").bind(PROFILE_STATE_KEY).first();
}

const ITEM_SIGNAL_CTE = `
  WITH event_rollup AS (
    SELECT item_id,
      MAX(CASE WHEN event_type='liked' THEN event_at END) AS liked_at,
      MAX(CASE WHEN event_type='disliked' THEN event_at END) AS disliked_at,
      MAX(CASE WHEN event_type='interest_saved' THEN 1 ELSE 0 END) AS interest_saved,
      MAX(CASE WHEN event_type='saved' THEN 1 ELSE 0 END) AS saved,
      MAX(CASE WHEN event_type='deep_read' THEN 1 ELSE 0 END) AS deep_read,
      MAX(CASE WHEN event_type='selected' THEN 1 ELSE 0 END) AS selected,
      MAX(event_at) AS last_event_at
    FROM user_content_events
    WHERE event_type <> 'shown'
    GROUP BY item_id
  ), item_signal AS (
    SELECT item_id,
      CASE
        WHEN disliked_at IS NOT NULL AND (liked_at IS NULL OR disliked_at >= liked_at) THEN -5.0
        WHEN liked_at IS NOT NULL THEN 5.0
        WHEN interest_saved=1 THEN 3.5
        WHEN saved=1 THEN 3.0
        WHEN deep_read=1 THEN 2.0
        WHEN selected=1 THEN 1.0
        ELSE 0.0
      END AS signal,
      CASE
        WHEN last_event_at IS NULL THEN 0.30
        WHEN julianday('now') - julianday(last_event_at) <= 7 THEN 1.00
        WHEN julianday('now') - julianday(last_event_at) <= 30 THEN 0.90
        WHEN julianday('now') - julianday(last_event_at) <= 90 THEN 0.75
        WHEN julianday('now') - julianday(last_event_at) <= 180 THEN 0.60
        WHEN julianday('now') - julianday(last_event_at) <= 365 THEN 0.45
        ELSE 0.30
      END AS recency_factor
    FROM event_rollup
  )
`;

function autoModelSql() {
  return [...AUTO_FEATURE_MODELS].map((x) => `'${x.replaceAll("'", "''")}'`).join(",");
}

export async function recomputeInterestProfile(env, modelVersion = PERSONAL_MODEL_VERSION) {
  if (!env?.DB) return { ok: false, model_version: modelVersion, profile_features: 0 };
  await env.DB.prepare("DELETE FROM interest_profile").run();
  const autoModels = autoModelSql();
  await env.DB.prepare(`${ITEM_SIGNAL_CTE}, feature_evidence AS (
    SELECT f.feature_type,f.feature_key,
      COUNT(*) AS evidence_count,
      SUM(CASE WHEN s.signal>0 THEN 1 ELSE 0 END) AS positive_count,
      SUM(CASE WHEN s.signal<0 THEN 1 ELSE 0 END) AS negative_count,
      SUM(s.signal*s.recency_factor*f.weight*f.confidence) AS raw_weight,
      AVG(f.confidence) AS avg_feature_confidence,
      MAX(CASE WHEN COALESCE(f.model_version,'') IN (${autoModels}) THEN 0 ELSE 1 END) AS has_explicit_feature
    FROM item_signal s
    JOIN content_features f ON f.item_id=s.item_id
    WHERE s.signal<>0
    GROUP BY f.feature_type,f.feature_key
  ), eligible AS (
    SELECT *,
      CASE
        WHEN evidence_count>=4 THEN 1.00
        WHEN evidence_count=3 THEN 0.82
        WHEN evidence_count=2 THEN 0.62
        WHEN has_explicit_feature=1 THEN 0.45
        WHEN feature_type IN ('topic','mechanism') THEN 0.35
        WHEN feature_type='concept' AND avg_feature_confidence>=0.80 THEN 0.30
        ELSE 0.18
      END AS evidence_factor
    FROM feature_evidence
    WHERE
      NOT (has_explicit_feature=0 AND feature_type IN ('keyword','domain','language'))
      AND (
        evidence_count>=2
        OR has_explicit_feature=1
        OR feature_type IN ('topic','mechanism')
        OR (feature_type='concept' AND avg_feature_confidence>=0.80)
      )
  )
  INSERT INTO interest_profile(
    feature_type,feature_key,weight,evidence_count,positive_count,negative_count,confidence,updated_at
  )
  SELECT feature_type,feature_key,
    (raw_weight/MAX(1.0,SQRT(evidence_count)))*evidence_factor,
    evidence_count,positive_count,negative_count,
    MIN(1.0,(evidence_count/(evidence_count+2.0))*MAX(0.35,avg_feature_confidence)),CURRENT_TIMESTAMP
  FROM eligible
  WHERE ABS((raw_weight/MAX(1.0,SQRT(evidence_count)))*evidence_factor)>=0.05
  `).run();
  const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM interest_profile").first();
  const evidence = await env.DB.prepare(`SELECT
      SUM(CASE WHEN evidence_count=1 THEN 1 ELSE 0 END) AS singleton_features,
      SUM(CASE WHEN evidence_count>=2 THEN 1 ELSE 0 END) AS repeated_features,
      AVG(confidence) AS avg_confidence
    FROM interest_profile`).first();
  return {
    ok: true,
    model_version: modelVersion,
    policy_version: PERSONAL_POLICY_VERSION,
    profile_features: Number(row?.n || 0),
    singleton_features: Number(evidence?.singleton_features || 0),
    repeated_features: Number(evidence?.repeated_features || 0),
    avg_confidence: Number(evidence?.avg_confidence || 0),
  };
}

export async function recomputePersonalScores(env, modelVersion = PERSONAL_MODEL_VERSION) {
  if (!env?.DB) return { ok: false, model_version: modelVersion, scored_items: 0 };
  await env.DB.prepare("DELETE FROM content_scores WHERE score_type='personal_relevance'").run();
  await env.DB.prepare(`
    WITH per_type AS (
      SELECT i.item_id,f.feature_type,
        COALESCE(SUM(p.weight*f.weight*f.confidence),0) AS type_signal,
        SUM(CASE WHEN p.feature_key IS NOT NULL THEN 1 ELSE 0 END) AS matched_features,
        SUM(CASE WHEN p.feature_key IS NOT NULL AND f.feature_type IN ('topic','concept','entity','mechanism') THEN 1 ELSE 0 END) AS semantic_matches,
        COALESCE(SUM(CASE WHEN f.feature_type IN ('topic','concept','entity','mechanism') THEN f.weight*f.confidence ELSE 0 END),0) AS semantic_weight,
        COALESCE(SUM(CASE WHEN f.feature_type IN ('topic','concept','entity','mechanism') AND (p.feature_key IS NULL OR p.evidence_count<=1) THEN f.weight*f.confidence ELSE 0 END),0) AS novel_semantic_weight,
        COALESCE(MAX(p.confidence),0) AS profile_confidence
      FROM content_items i
      LEFT JOIN content_features f ON f.item_id=i.item_id
      LEFT JOIN interest_profile p ON p.feature_type=f.feature_type AND p.feature_key=f.feature_key
      GROUP BY i.item_id,f.feature_type
    ), feature_rollup AS (
      SELECT item_id,
        SUM(CASE
          WHEN feature_type IN ('topic','mechanism') THEN MAX(-5.0,MIN(5.0,type_signal))
          WHEN feature_type='concept' THEN MAX(-4.0,MIN(4.0,type_signal))
          WHEN feature_type='entity' THEN MAX(-2.0,MIN(2.0,type_signal))
          WHEN feature_type='source' THEN MAX(-1.5,MIN(1.5,type_signal))
          ELSE MAX(-2.0,MIN(2.0,type_signal))
        END) AS relevance_signal,
        SUM(matched_features) AS matched_features,
        SUM(semantic_matches) AS semantic_matches,
        SUM(semantic_weight) AS semantic_weight,
        SUM(novel_semantic_weight) AS novel_semantic_weight,
        MAX(profile_confidence) AS profile_confidence
      FROM per_type
      GROUP BY item_id
    ), components AS (
      SELECT i.item_id,r.relevance_signal,r.matched_features,r.semantic_matches,r.profile_confidence,
        CASE
          WHEN i.published_at IS NULL OR julianday(i.published_at) IS NULL THEN 0.0
          WHEN julianday('now')-julianday(i.published_at) < 0 THEN 0.0
          WHEN julianday('now')-julianday(i.published_at) <= 2 THEN 5.0
          WHEN julianday('now')-julianday(i.published_at) <= 7 THEN 3.5
          WHEN julianday('now')-julianday(i.published_at) <= 30 THEN 1.5
          WHEN julianday('now')-julianday(i.published_at) <= 90 THEN 0.5
          WHEN julianday('now')-julianday(i.published_at) > 365 THEN -2.0
          WHEN julianday('now')-julianday(i.published_at) > 180 THEN -1.0
          ELSE 0.0
        END AS freshness_bonus,
        CASE
          WHEN r.semantic_matches>0 AND r.semantic_weight>0
            THEN MIN(2.0,2.0*r.novel_semantic_weight/r.semantic_weight)
          ELSE 0.0
        END AS novelty_bonus
      FROM content_items i JOIN feature_rollup r ON r.item_id=i.item_id
    ), base_scores AS (
      SELECT *,
        50.0 + (38.0*relevance_signal/(6.0+ABS(relevance_signal))) + freshness_bonus + novelty_bonus AS base_score
      FROM components
    ), ranked AS (
      SELECT *, PERCENT_RANK() OVER (ORDER BY base_score) AS rank_percentile
      FROM base_scores
    )
    INSERT INTO content_scores(item_id,score_type,score,confidence,reason_json,model_version,scored_at)
    SELECT item_id,'personal_relevance',
      MIN(99.5,MAX(0.5,0.82*base_score+18.0*rank_percentile)),
      MIN(1.0,MAX(profile_confidence,CASE WHEN semantic_matches>0 THEN 0.30 ELSE 0.0 END)),
      json_object(
        'relevance_signal',ROUND(relevance_signal,4),
        'base_score',ROUND(base_score,3),
        'rank_percentile',ROUND(rank_percentile,4),
        'matched_features',matched_features,
        'semantic_matches',semantic_matches,
        'freshness_bonus',freshness_bonus,
        'novelty_bonus',ROUND(novelty_bonus,3),
        'signal_policy','latest-explicit-wins',
        'profile_policy',?,
        'model',?
      ),?,CURRENT_TIMESTAMP
    FROM ranked
  `).bind(PERSONAL_POLICY_VERSION, modelVersion, modelVersion).run();
  const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM content_scores WHERE score_type='personal_relevance' AND model_version=?").bind(modelVersion).first();
  const dist = await env.DB.prepare(`SELECT
      MIN(score) AS min_score,
      MAX(score) AS max_score,
      AVG(score) AS avg_score,
      SUM(CASE WHEN score>=99 THEN 1 ELSE 0 END) AS score_99_plus,
      SUM(CASE WHEN score>=95 THEN 1 ELSE 0 END) AS score_95_plus
    FROM content_scores WHERE score_type='personal_relevance' AND model_version=?`).bind(modelVersion).first();
  return {
    ok: true,
    model_version: modelVersion,
    policy_version: PERSONAL_POLICY_VERSION,
    scored_items: Number(row?.n || 0),
    distribution: {
      min: Number(dist?.min_score || 0),
      max: Number(dist?.max_score || 0),
      avg: Number(dist?.avg_score || 0),
      score_99_plus: Number(dist?.score_99_plus || 0),
      score_95_plus: Number(dist?.score_95_plus || 0),
    },
  };
}

function clampTopK(value) {
  const n = Number.parseInt(String(value ?? 10), 10);
  return Math.min(50, Math.max(1, Number.isFinite(n) ? n : 10));
}

function numberOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function parseContextNumber(contextJson) {
  if (!contextJson) return null;
  try {
    const obj = JSON.parse(contextJson);
    return numberOrNull(obj?.number);
  } catch {
    return null;
  }
}

function scoreDistribution(rows) {
  const values = rows.map((r) => Number(r.score)).filter(Number.isFinite).sort((a,b) => a-b);
  const quantile = (q) => {
    if (!values.length) return null;
    const idx = Math.min(values.length - 1, Math.max(0, Math.round((values.length - 1) * q)));
    return values[idx];
  };
  return {
    count: values.length,
    min: values[0] ?? null,
    p50: quantile(0.50),
    p90: quantile(0.90),
    p99: quantile(0.99),
    max: values[values.length - 1] ?? null,
    score_99_plus: values.filter((x) => x >= 99).length,
  };
}

export async function snapshotRecommendationRun(env, renderId, { topK = 10, modelVersion = PERSONAL_MODEL_VERSION } = {}) {
  if (!env?.DB) return { ok:false,error:"D1_NOT_BOUND" };
  const rid = String(renderId || "").trim();
  if (!rid) return { ok:false,error:"render_id_required" };
  const k = clampTopK(topK);
  await maybeRecomputePersonal(env, { force:true, modelVersion });
  const result = await env.DB.prepare(`
    SELECT e.item_id,e.context_json,i.title,i.canonical_url,i.source_name,i.published_at,
      s.score,s.confidence,s.reason_json
    FROM user_content_events e
    JOIN content_items i ON i.item_id=e.item_id
    LEFT JOIN content_scores s ON s.item_id=e.item_id
      AND s.score_type='personal_relevance' AND s.model_version=?
    WHERE e.render_id=? AND e.event_type='shown'
    ORDER BY e.id ASC
  `).bind(modelVersion,rid).all();
  const dedup = new Map();
  for (const row of result.results || []) {
    if (dedup.has(row.item_id)) continue;
    dedup.set(row.item_id,{...row,manifest_number:parseContextNumber(row.context_json)});
  }
  const rows = [...dedup.values()];
  if (!rows.length) return { ok:false,error:"render_not_found_or_no_shown_items",render_id:rid };
  const baseline = [...rows].sort((a,b) => {
    const an = a.manifest_number ?? Number.MAX_SAFE_INTEGER;
    const bn = b.manifest_number ?? Number.MAX_SAFE_INTEGER;
    return an-bn || String(a.item_id).localeCompare(String(b.item_id));
  }).slice(0,k).map((r,index) => ({ item_id:r.item_id,rank:index+1,manifest_number:r.manifest_number }));
  const personalized = [...rows].sort((a,b) => {
    const as = Number.isFinite(Number(a.score)) ? Number(a.score) : -1;
    const bs = Number.isFinite(Number(b.score)) ? Number(b.score) : -1;
    const an = a.manifest_number ?? Number.MAX_SAFE_INTEGER;
    const bn = b.manifest_number ?? Number.MAX_SAFE_INTEGER;
    return bs-as || an-bn || String(a.item_id).localeCompare(String(b.item_id));
  }).slice(0,k).map((r,index) => ({ item_id:r.item_id,rank:index+1,score:numberOrNull(r.score),manifest_number:r.manifest_number }));
  const metadata = {
    schema_version:1,
    policy_version:PERSONAL_POLICY_VERSION,
    top_k:k,
    baseline_policy:"canonical-manifest-order",
    personalized_policy:"personal-relevance-score",
    baseline,
    personalized,
    score_distribution:scoreDistribution(rows),
    created_at:new Date().toISOString(),
  };
  await env.DB.prepare(`
    INSERT INTO recommendation_runs(render_id,source_scope,item_count,recommended_count,exploration_ratio,model_version,created_at,metadata_json)
    VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP,?)
    ON CONFLICT(render_id) DO UPDATE SET
      source_scope=excluded.source_scope,item_count=excluded.item_count,recommended_count=excluded.recommended_count,
      exploration_ratio=excluded.exploration_ratio,model_version=excluded.model_version,created_at=CURRENT_TIMESTAMP,metadata_json=excluded.metadata_json
  `).bind(rid,"rss",rows.length,k,0,modelVersion,JSON.stringify(metadata)).run();
  return { ok:true,render_id:rid,model_version:modelVersion,item_count:rows.length,top_k:k,...metadata };
}

function gradeEvents(events) {
  let latestExplicit = null;
  let positive = 0;
  for (const event of events) {
    if (event.event_type === "liked" || event.event_type === "disliked") latestExplicit = event.event_type;
    if (event.event_type === "interest_saved" || event.event_type === "saved") positive = Math.max(positive,3);
    else if (event.event_type === "deep_read") positive = Math.max(positive,2);
    else if (event.event_type === "selected") positive = Math.max(positive,1);
  }
  if (latestExplicit === "disliked") return 0;
  if (latestExplicit === "liked") return 3;
  return positive;
}

function rankingMetrics(list, grades, allPositiveCount, topK) {
  const k = Math.min(topK,list.length);
  let hits = 0;
  let dcg = 0;
  for (let i=0;i<k;i+=1) {
    const grade = Number(grades.get(list[i].item_id) || 0);
    if (grade>0) hits += 1;
    dcg += (Math.pow(2,grade)-1)/Math.log2(i+2);
  }
  const idealGrades = [...grades.values()].filter((x) => x>0).sort((a,b) => b-a).slice(0,k);
  const idcg = idealGrades.reduce((sum,grade,index) => sum + (Math.pow(2,grade)-1)/Math.log2(index+2),0);
  return {
    precision_at_k:k ? hits/k : null,
    recall_at_k:allPositiveCount ? hits/allPositiveCount : null,
    ndcg_at_k:idcg ? dcg/idcg : null,
    hits_at_k:hits,
  };
}

export async function evaluateRecommendationRun(env, renderId) {
  if (!env?.DB) return { ok:false,error:"D1_NOT_BOUND" };
  const rid = String(renderId || "").trim();
  if (!rid) return { ok:false,error:"render_id_required" };
  const run = await env.DB.prepare("SELECT * FROM recommendation_runs WHERE render_id=?").bind(rid).first();
  if (!run) return { ok:false,error:"recommendation_snapshot_not_found",render_id:rid };
  let metadata;
  try { metadata = JSON.parse(run.metadata_json || "{}"); } catch { metadata = {}; }
  const baseline = Array.isArray(metadata.baseline) ? metadata.baseline : [];
  const personalized = Array.isArray(metadata.personalized) ? metadata.personalized : [];
  const shown = await env.DB.prepare("SELECT DISTINCT item_id FROM user_content_events WHERE render_id=? AND event_type='shown'").bind(rid).all();
  const shownIds = (shown.results || []).map((r) => String(r.item_id));
  if (!shownIds.length) return { ok:false,error:"render_not_found_or_no_shown_items",render_id:rid };
  const placeholders = shownIds.map(() => "?").join(",");
  const events = await env.DB.prepare(`
    SELECT item_id,event_type,event_at,id FROM user_content_events
    WHERE item_id IN (${placeholders}) AND event_type IN ('selected','deep_read','saved','interest_saved','liked','disliked')
      AND event_at>=?
    ORDER BY event_at ASC,id ASC
  `).bind(...shownIds,run.created_at).all();
  const byItem = new Map(shownIds.map((id) => [id,[]]));
  for (const event of events.results || []) {
    if (!byItem.has(String(event.item_id))) continue;
    byItem.get(String(event.item_id)).push(event);
  }
  const grades = new Map();
  for (const [itemId,itemEvents] of byItem.entries()) grades.set(itemId,gradeEvents(itemEvents));
  const positiveCount = [...grades.values()].filter((x) => x>0).length;
  const topK = clampTopK(metadata.top_k || run.recommended_count || 10);
  const baselineMetrics = rankingMetrics(baseline,grades,positiveCount,topK);
  const personalizedMetrics = rankingMetrics(personalized,grades,positiveCount,topK);
  const lift = (a,b) => (a==null || b==null) ? null : a-b;
  return {
    ok:true,
    render_id:rid,
    model_version:run.model_version,
    policy_version:metadata.policy_version || null,
    top_k:topK,
    judged_positive_count:positiveCount,
    feedback_event_count:(events.results || []).length,
    evaluable:positiveCount>0,
    baseline:baselineMetrics,
    personalized:personalizedMetrics,
    lift:{
      precision_at_k:lift(personalizedMetrics.precision_at_k,baselineMetrics.precision_at_k),
      recall_at_k:lift(personalizedMetrics.recall_at_k,baselineMetrics.recall_at_k),
      ndcg_at_k:lift(personalizedMetrics.ndcg_at_k,baselineMetrics.ndcg_at_k),
    },
    snapshot_created_at:run.created_at,
    evaluated_at:new Date().toISOString(),
  };
}

export async function recomputePersonalization(env, modelVersion = PERSONAL_MODEL_VERSION) {
  const profile = await recomputeInterestProfile(env, modelVersion);
  const scores = await recomputePersonalScores(env, modelVersion);
  await env.DB.prepare(`
    INSERT INTO workflow_state(source,status,detail,updated_at)
    VALUES(?, 'clean', ?, CURRENT_TIMESTAMP)
    ON CONFLICT(source) DO UPDATE SET status='clean',detail=excluded.detail,updated_at=CURRENT_TIMESTAMP
  `).bind(PROFILE_STATE_KEY, JSON.stringify({ recomputed_at: new Date().toISOString(), model: modelVersion, policy: PERSONAL_POLICY_VERSION })).run();
  return { ok: true, model_version: modelVersion, policy_version: PERSONAL_POLICY_VERSION, profile_features: profile.profile_features, scored_items: scores.scored_items, profile, scores };
}

export async function maybeRecomputePersonal(env, { force = false, modelVersion = PERSONAL_MODEL_VERSION } = {}) {
  if (!env?.DB) return { ok: false, recomputed: false };
  const state = await profileState(env);
  if (!state || state.status !== "dirty") {
    if (force) {
      const result = await recomputePersonalization(env, modelVersion);
      return { ...result, recomputed: true, status: "clean" };
    }
    return { ok: true, recomputed: false, status: state?.status || "missing" };
  }
  const last = Date.parse(state.updated_at || 0);
  const due = force || !Number.isFinite(last) || Date.now() - last >= RECOMPUTE_DEBOUNCE_MS;
  if (!due) return { ok: true, recomputed: false, status: "dirty_debounced" };
  const result = await recomputePersonalization(env, modelVersion);
  return { ...result, recomputed: true, status: "clean" };
}
