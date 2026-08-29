export const PERSONAL_MODEL_VERSION = "personal-v2";
export const PROFILE_STATE_KEY = "content-intelligence-profile";
export const RECOMPUTE_DEBOUNCE_MS = 60_000;
export const EVENT_WEIGHTS = {
  shown: 0,
  selected: 1,
  deep_read: 2,
  saved: 3,
  interest_saved: 3.5,
  liked: 5,
  disliked: -5,
};

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

export async function recomputeInterestProfile(env, modelVersion = PERSONAL_MODEL_VERSION) {
  if (!env?.DB) return { ok: false, model_version: modelVersion, profile_features: 0 };
  await env.DB.prepare("DELETE FROM interest_profile").run();
  await env.DB.prepare(`${ITEM_SIGNAL_CTE}
    INSERT INTO interest_profile(
      feature_type,feature_key,weight,evidence_count,positive_count,negative_count,confidence,updated_at
    )
    SELECT f.feature_type,f.feature_key,
      SUM(s.signal*s.recency_factor*f.weight*f.confidence)/MAX(1.0,SQRT(COUNT(*))),
      COUNT(*),
      SUM(CASE WHEN s.signal>0 THEN 1 ELSE 0 END),
      SUM(CASE WHEN s.signal<0 THEN 1 ELSE 0 END),
      MIN(1.0,COUNT(*)/5.0),CURRENT_TIMESTAMP
    FROM item_signal s
    JOIN content_features f ON f.item_id=s.item_id
    WHERE s.signal<>0
    GROUP BY f.feature_type,f.feature_key
  `).run();
  const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM interest_profile").first();
  return { ok: true, model_version: modelVersion, profile_features: Number(row?.n || 0) };
}

export async function recomputePersonalScores(env, modelVersion = PERSONAL_MODEL_VERSION) {
  if (!env?.DB) return { ok: false, model_version: modelVersion, scored_items: 0 };
  await env.DB.prepare("DELETE FROM content_scores WHERE score_type='personal_relevance'").run();
  await env.DB.prepare(`
    WITH feature_rollup AS (
      SELECT i.item_id,
        COALESCE(SUM(p.weight*f.weight*f.confidence),0) AS relevance_signal,
        SUM(CASE WHEN p.feature_key IS NOT NULL THEN 1 ELSE 0 END) AS matched_features,
        SUM(CASE WHEN p.feature_key IS NOT NULL AND f.feature_type IN ('topic','concept','entity') THEN 1 ELSE 0 END) AS semantic_matches,
        COALESCE(SUM(CASE WHEN f.feature_type IN ('topic','concept','entity') THEN f.weight*f.confidence ELSE 0 END),0) AS semantic_weight,
        COALESCE(SUM(CASE WHEN f.feature_type IN ('topic','concept','entity') AND (p.feature_key IS NULL OR p.evidence_count<=1) THEN f.weight*f.confidence ELSE 0 END),0) AS novel_semantic_weight,
        COALESCE(MAX(p.confidence),0) AS profile_confidence
      FROM content_items i
      LEFT JOIN content_features f ON f.item_id=i.item_id
      LEFT JOIN interest_profile p ON p.feature_type=f.feature_type AND p.feature_key=f.feature_key
      GROUP BY i.item_id
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
            THEN MIN(3.0,3.0*r.novel_semantic_weight/r.semantic_weight)
          ELSE 0.0
        END AS novelty_bonus
      FROM content_items i JOIN feature_rollup r ON r.item_id=i.item_id
    )
    INSERT INTO content_scores(item_id,score_type,score,confidence,reason_json,model_version,scored_at)
    SELECT item_id,'personal_relevance',
      MIN(100.0,MAX(0.0,50.0+8.0*relevance_signal+freshness_bonus+novelty_bonus)),
      MIN(1.0,MAX(profile_confidence,CASE WHEN semantic_matches>0 THEN 0.35 ELSE 0.0 END)),
      json_object(
        'relevance_signal',ROUND(relevance_signal,4),
        'matched_features',matched_features,
        'semantic_matches',semantic_matches,
        'freshness_bonus',freshness_bonus,
        'novelty_bonus',ROUND(novelty_bonus,3),
        'signal_policy','latest-explicit-wins',
        'model',?
      ),?,CURRENT_TIMESTAMP
    FROM components
  `).bind(modelVersion, modelVersion).run();
  const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM content_scores WHERE score_type='personal_relevance' AND model_version=?").bind(modelVersion).first();
  return { ok: true, model_version: modelVersion, scored_items: Number(row?.n || 0) };
}

export async function recomputePersonalization(env, modelVersion = PERSONAL_MODEL_VERSION) {
  const profile = await recomputeInterestProfile(env, modelVersion);
  const scores = await recomputePersonalScores(env, modelVersion);
  await env.DB.prepare(`
    INSERT INTO workflow_state(source,status,detail,updated_at)
    VALUES(?, 'clean', ?, CURRENT_TIMESTAMP)
    ON CONFLICT(source) DO UPDATE SET status='clean',detail=excluded.detail,updated_at=CURRENT_TIMESTAMP
  `).bind(PROFILE_STATE_KEY, JSON.stringify({ recomputed_at: new Date().toISOString(), model: modelVersion })).run();
  return { ok: true, model_version: modelVersion, profile_features: profile.profile_features, scored_items: scores.scored_items };
}

export async function maybeRecomputePersonal(env, { force = false, modelVersion = PERSONAL_MODEL_VERSION } = {}) {
  if (!env?.DB) return { ok: false, recomputed: false };
  const state = await profileState(env);
  if (!state || state.status !== "dirty") return { ok: true, recomputed: false, status: state?.status || "missing" };
  const last = Date.parse(state.updated_at || 0);
  const due = force || !Number.isFinite(last) || Date.now() - last >= RECOMPUTE_DEBOUNCE_MS;
  if (!due) return { ok: true, recomputed: false, status: "dirty_debounced" };
  const result = await recomputePersonalization(env, modelVersion);
  return { ...result, recomputed: true, status: "clean" };
}
