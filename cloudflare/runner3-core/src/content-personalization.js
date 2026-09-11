import { canonicalInterestKey, canonicalInterestKeySql, familyDiminishingWeight, familySignalCap, interestFamily, interestFamilySql, INTEREST_ONTOLOGY_VERSION } from "./content-interest-ontology.js";

export const PERSONAL_MODEL_VERSION = "personal-v4";
export const PROFILE_STATE_KEY = "content-intelligence-profile";
export const PROFILE_RECOMPUTE_CLOCK_KEY = "content-intelligence-profile-last-recompute";
export const RECOMPUTE_DEBOUNCE_MS = 4 * 60 * 60 * 1000;
export const RECOMPUTE_LEASE_MS = 15 * 60 * 1000;
export const RECOMPUTE_RETRY_MS = 60 * 60 * 1000;
export const PERSONAL_POLICY_VERSION = "canonical-interest-ontology-v7-family-aware";
export const EVENT_WEIGHTS = {
  shown: 0,
  selected: 1,
  deep_read: 2,
  follow_up: 0.5,
  saved: 3,
  interest_saved: 3.5,
  liked: 5,
  disliked: -5,
};

export function isSupportedContentEvent(eventType) {
  return Object.prototype.hasOwnProperty.call(EVENT_WEIGHTS, String(eventType || ""));
}

export async function markProfileDirty(env, reason = "content_intelligence_event") {
  if (!env?.DB) return 0;
  const result = await env.DB.prepare(`
    INSERT INTO workflow_state(source,status,run_id,detail,updated_at)
    VALUES(?, 'dirty', NULL, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(source) DO UPDATE SET
      status='dirty', run_id=NULL, detail=excluded.detail, updated_at=CURRENT_TIMESTAMP
    WHERE workflow_state.status IS NOT 'dirty'
  `).bind(PROFILE_STATE_KEY, JSON.stringify({ reason })).run();
  return Number(result.meta?.changes || 0);
}

async function profileState(env) {
  return env.DB.prepare("SELECT status,run_id,detail,updated_at FROM workflow_state WHERE source=?").bind(PROFILE_STATE_KEY).first();
}

function leaseToken() {
  return typeof globalThis.crypto?.randomUUID === "function" ? globalThis.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function agoModifier(ms) {
  return `-${Math.max(0, Math.floor(ms / 1000))} seconds`;
}

async function acquireRecomputeLease(env, modelVersion, priorityExplicit = false) {
  const token = leaseToken();
  const detail = JSON.stringify({ model: modelVersion, policy_version: PERSONAL_POLICY_VERSION, ontology_version: INTEREST_ONTOLOGY_VERSION, lease_acquired_at: new Date().toISOString() });
  const result = await env.DB.prepare(`
    UPDATE workflow_state
    SET status='recomputing', run_id=?, detail=?, updated_at=CURRENT_TIMESTAMP
    WHERE source=? AND (
      (status='dirty' AND (
        ?=1
        OR NOT EXISTS(SELECT 1 FROM workflow_state WHERE source=?)
        OR EXISTS(SELECT 1 FROM workflow_state WHERE source=? AND updated_at <= datetime('now',?))
        OR NOT EXISTS(SELECT 1 FROM content_scores WHERE score_type='personal_relevance' AND model_version=?)
      ))
      OR (status='recomputing' AND updated_at <= datetime('now',?))
    )
  `).bind(
    token, detail, PROFILE_STATE_KEY, priorityExplicit ? 1 : 0,
    PROFILE_RECOMPUTE_CLOCK_KEY, PROFILE_RECOMPUTE_CLOCK_KEY, agoModifier(RECOMPUTE_DEBOUNCE_MS), modelVersion,
    agoModifier(RECOMPUTE_LEASE_MS),
  ).run();
  return Number(result.meta?.changes || 0) === 1 ? token : null;
}

async function finishRecomputeLease(env, token, modelVersion) {
  const recomputedAt = new Date().toISOString();
  const detail = JSON.stringify({ recomputed_at: recomputedAt, model: modelVersion, policy_version: PERSONAL_POLICY_VERSION, ontology_version: INTEREST_ONTOLOGY_VERSION });
  const result = await env.DB.prepare(`
    UPDATE workflow_state
    SET status='clean', run_id=NULL, detail=?, updated_at=CURRENT_TIMESTAMP
    WHERE source=? AND status='recomputing' AND run_id=?
  `).bind(detail, PROFILE_STATE_KEY, token).run();
  const committed = Number(result.meta?.changes || 0) === 1;
  if (committed) {
    await env.DB.prepare(`
      INSERT INTO workflow_state(source,status,run_id,detail,updated_at)
      VALUES(?, 'clean', NULL, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(source) DO UPDATE SET status='clean',run_id=NULL,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP
    `).bind(PROFILE_RECOMPUTE_CLOCK_KEY, detail).run();
  }
  return committed;
}

async function failRecomputeLease(env, token, error) {
  await env.DB.prepare(`
    UPDATE workflow_state
    SET status='dirty', run_id=NULL, detail=?, updated_at=datetime('now',?)
    WHERE source=? AND status='recomputing' AND run_id=?
  `).bind(
    JSON.stringify({ retryable_error: String(error?.message || error) }),
    agoModifier(RECOMPUTE_DEBOUNCE_MS - RECOMPUTE_RETRY_MS),
    PROFILE_STATE_KEY,
    token,
  ).run();
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
      SUM(CASE WHEN event_type='follow_up' THEN 1 ELSE 0 END) AS follow_up_count,
      MAX(event_at) AS last_event_at
    FROM user_content_events
    WHERE event_type <> 'shown'
    GROUP BY item_id
  ), item_signal AS (
    SELECT item_id,
      CASE
        WHEN disliked_at IS NOT NULL AND (liked_at IS NULL OR disliked_at >= liked_at) THEN -5.0
        WHEN liked_at IS NOT NULL THEN 5.0
        WHEN interest_saved=1 OR saved=1 OR deep_read=1 OR selected=1 THEN
          MIN(3.5,
            CASE
              WHEN interest_saved=1 THEN 3.5
              WHEN saved=1 THEN 3.0
              WHEN deep_read=1 THEN 2.0
              ELSE 1.0
            END + MIN(1.5, 0.5 * follow_up_count)
          )
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

function profileProjectionCte() {
  const canonicalKey = canonicalInterestKeySql("f.feature_type", "f.feature_key");
  const familyId = interestFamilySql("f.feature_type", "f.feature_key");
  return `${ITEM_SIGNAL_CTE}, normalized_features AS (
    SELECT f.item_id,f.feature_type,${canonicalKey} AS feature_key,
      MAX(f.weight) AS weight,MAX(f.confidence) AS confidence
    FROM content_features f
    WHERE f.feature_type IN ('topic','mechanism','concept')
    GROUP BY f.item_id,f.feature_type,${canonicalKey}
  ), feature_evidence AS (
    SELECT f.feature_type,f.feature_key,
      COUNT(*) AS evidence_count,
      SUM(CASE WHEN s.signal>0 THEN 1 ELSE 0 END) AS positive_count,
      SUM(CASE WHEN s.signal<0 THEN 1 ELSE 0 END) AS negative_count,
      SUM(s.signal*s.recency_factor*f.weight*f.confidence) AS raw_weight,
      AVG(f.confidence) AS avg_feature_confidence
    FROM item_signal s JOIN normalized_features f ON f.item_id=s.item_id
    WHERE s.signal<>0
    GROUP BY f.feature_type,f.feature_key
  ), eligible AS (
    SELECT *,CASE WHEN evidence_count>=4 THEN 1.00 WHEN evidence_count=3 THEN 0.82 ELSE 0.62 END AS evidence_factor
    FROM feature_evidence WHERE evidence_count>=2
  ), scored AS (
    SELECT *,(raw_weight/MAX(1.0,SQRT(evidence_count)))*evidence_factor AS projected_weight,
      MIN(1.0,(evidence_count/(evidence_count+2.0))*MAX(0.35,avg_feature_confidence)) AS projected_confidence
    FROM eligible
  ), ranked AS (
    SELECT *,ROW_NUMBER() OVER (PARTITION BY feature_type ORDER BY evidence_count DESC,ABS(projected_weight) DESC,feature_key) AS type_rank
    FROM scored WHERE ABS(projected_weight)>=0.05
  ), leaf_projected AS (
    SELECT feature_type,feature_key,evidence_count,positive_count,negative_count,projected_weight,projected_confidence
    FROM ranked WHERE type_rank<=CASE WHEN feature_type='topic' THEN 40 WHEN feature_type='mechanism' THEN 30 WHEN feature_type='concept' THEN 40 ELSE 20 END
  ), family_item_ranked AS (
    SELECT s.item_id,${familyId} AS family_key,s.signal,s.recency_factor,f.weight,f.confidence,
      ROW_NUMBER() OVER (PARTITION BY s.item_id,${familyId} ORDER BY f.weight*f.confidence DESC,f.feature_type,f.feature_key) AS family_rank
    FROM item_signal s JOIN normalized_features f ON f.item_id=s.item_id
    WHERE s.signal<>0
  ), family_item AS (
    SELECT item_id,family_key,MAX(signal) AS signal,
      SUM(signal*recency_factor*weight*confidence*CASE WHEN family_rank=1 THEN 1.0 WHEN family_rank=2 THEN 0.35 ELSE 0.15 END) AS item_raw_weight,
      MAX(confidence) AS family_confidence
    FROM family_item_ranked GROUP BY item_id,family_key
  ), family_evidence AS (
    SELECT 'family' AS feature_type,family_key AS feature_key,COUNT(*) AS evidence_count,
      SUM(CASE WHEN signal>0 THEN 1 ELSE 0 END) AS positive_count,
      SUM(CASE WHEN signal<0 THEN 1 ELSE 0 END) AS negative_count,
      SUM(item_raw_weight) AS raw_weight,AVG(family_confidence) AS avg_feature_confidence
    FROM family_item GROUP BY family_key
  ), family_eligible AS (
    SELECT *,CASE WHEN evidence_count>=4 THEN 1.00 WHEN evidence_count=3 THEN 0.82 ELSE 0.62 END AS evidence_factor
    FROM family_evidence WHERE evidence_count>=2 AND instr(feature_key, ':')=0
  ), family_scored AS (
    SELECT feature_type,feature_key,evidence_count,positive_count,negative_count,
      (raw_weight/MAX(1.0,SQRT(evidence_count)))*evidence_factor AS projected_weight,
      MIN(1.0,(evidence_count/(evidence_count+2.0))*MAX(0.35,avg_feature_confidence)) AS projected_confidence
    FROM family_eligible
  ), projected AS (
    SELECT * FROM leaf_projected
    UNION ALL
    SELECT * FROM family_scored WHERE ABS(projected_weight)>=0.05
  )`;
}

export async function recomputeInterestProfile(env, modelVersion = PERSONAL_MODEL_VERSION) {
  if (!env?.DB) return { ok:false,model_version:modelVersion,profile_features:0,changed:0 };
  const projection = profileProjectionCte();
  const upsert = await env.DB.prepare(`${projection}
    INSERT INTO interest_profile(feature_type,feature_key,weight,evidence_count,positive_count,negative_count,confidence,updated_at)
    SELECT feature_type,feature_key,projected_weight,evidence_count,positive_count,negative_count,projected_confidence,CURRENT_TIMESTAMP
    FROM projected WHERE 1=1
    ON CONFLICT(feature_type,feature_key) DO UPDATE SET
      weight=excluded.weight,evidence_count=excluded.evidence_count,positive_count=excluded.positive_count,
      negative_count=excluded.negative_count,confidence=excluded.confidence,updated_at=CURRENT_TIMESTAMP
    WHERE interest_profile.weight IS NOT excluded.weight
       OR interest_profile.evidence_count IS NOT excluded.evidence_count
       OR interest_profile.positive_count IS NOT excluded.positive_count
       OR interest_profile.negative_count IS NOT excluded.negative_count
       OR interest_profile.confidence IS NOT excluded.confidence
  `).run();
  const removed = await env.DB.prepare(`${projection}
    DELETE FROM interest_profile
    WHERE NOT EXISTS (
      SELECT 1 FROM projected p
      WHERE p.feature_type=interest_profile.feature_type AND p.feature_key=interest_profile.feature_key
    )
  `).run();
  const stats = await env.DB.prepare(`SELECT COUNT(*) AS n,
    SUM(CASE WHEN evidence_count=1 THEN 1 ELSE 0 END) AS singleton_features,
    SUM(CASE WHEN evidence_count>=2 THEN 1 ELSE 0 END) AS repeated_features,
    AVG(confidence) AS avg_confidence FROM interest_profile`).first();
  return {
    ok:true,model_version:modelVersion,policy_version:PERSONAL_POLICY_VERSION,
    profile_features:Number(stats?.n||0),singleton_features:Number(stats?.singleton_features||0),
    repeated_features:Number(stats?.repeated_features||0),avg_confidence:Number(stats?.avg_confidence||0),
    changed:Number(upsert.meta?.changes||0)+Number(removed.meta?.changes||0),
  };
}

export async function recomputePersonalScores(env, modelVersion = PERSONAL_MODEL_VERSION) {
  if (!env?.DB) return { ok:false,model_version:modelVersion,scored_items:0,changed:0 };
  const stale = await env.DB.prepare("DELETE FROM content_scores WHERE score_type='personal_relevance' AND model_version<>?").bind(modelVersion).run();
  const canonicalKey = canonicalInterestKeySql("f.feature_type", "f.feature_key");
  const familyId = interestFamilySql("nf.feature_type", "nf.feature_key");
  const upsert = await env.DB.prepare(`
    WITH normalized_features AS (
      SELECT f.item_id,f.feature_type,${canonicalKey} AS feature_key,
        MAX(f.weight) AS weight,MAX(f.confidence) AS confidence
      FROM content_features f
      WHERE f.feature_type IN ('topic','mechanism','concept')
      GROUP BY f.item_id,f.feature_type,${canonicalKey}
    ), item_family_ranked AS (
      SELECT nf.*,${familyId} AS family_id,
        ROW_NUMBER() OVER (PARTITION BY nf.item_id,${familyId} ORDER BY nf.weight*nf.confidence DESC,nf.feature_type,nf.feature_key) AS family_rank
      FROM normalized_features nf
    ), item_family AS (
      SELECT item_id,family_id,
        SUM(weight*confidence*CASE WHEN family_rank=1 THEN 1.0 WHEN family_rank=2 THEN 0.35 ELSE 0.15 END) AS family_feature_strength
      FROM item_family_ranked
      WHERE instr(family_id,':')=0
      GROUP BY item_id,family_id
    ), leaf_matches AS (
      SELECT nf.item_id,nf.feature_type,nf.feature_key,${familyId} AS family_id,
        COALESCE(p.weight*nf.weight*nf.confidence,0) AS contribution,
        CASE WHEN p.feature_key IS NOT NULL THEN 1 ELSE 0 END AS matched_feature,
        CASE WHEN p.feature_key IS NOT NULL THEN 1 ELSE 0 END AS semantic_match,
        nf.weight*nf.confidence AS semantic_weight,
        CASE WHEN p.feature_key IS NULL AND pf.feature_key IS NULL THEN nf.weight*nf.confidence ELSE 0 END AS novel_semantic_weight,
        MAX(COALESCE(p.confidence,0),COALESCE(pf.confidence,0)) AS profile_confidence
      FROM normalized_features nf
      LEFT JOIN interest_profile p ON p.feature_type=nf.feature_type AND p.feature_key=nf.feature_key
      LEFT JOIN interest_profile pf ON pf.feature_type='family' AND pf.feature_key=${familyId}
    ), family_matches AS (
      SELECT x.item_id,'family' AS feature_type,x.family_id AS feature_key,x.family_id,
        COALESCE(p.weight*x.family_feature_strength,0) AS contribution,
        CASE WHEN p.feature_key IS NOT NULL THEN 1 ELSE 0 END AS matched_feature,
        CASE WHEN p.feature_key IS NOT NULL THEN 1 ELSE 0 END AS semantic_match,
        0.0 AS semantic_weight,0.0 AS novel_semantic_weight,COALESCE(p.confidence,0) AS profile_confidence
      FROM item_family x
      LEFT JOIN interest_profile p ON p.feature_type='family' AND p.feature_key=x.family_id
    ), combined_matches AS (
      SELECT * FROM leaf_matches
      UNION ALL
      SELECT * FROM family_matches
    ), ranked_matches AS (
      SELECT *,ROW_NUMBER() OVER (
        PARTITION BY item_id,family_id
        ORDER BY ABS(contribution) DESC,feature_type,feature_key
      ) AS family_rank
      FROM combined_matches
    ), family_rollup AS (
      SELECT item_id,family_id,
        SUM(contribution*CASE WHEN family_rank=1 THEN 1.0 WHEN family_rank=2 THEN 0.35 ELSE 0.15 END) AS family_signal,
        SUM(matched_feature) AS matched_features,SUM(semantic_match) AS semantic_matches,
        SUM(semantic_weight) AS semantic_weight,SUM(novel_semantic_weight) AS novel_semantic_weight,
        MAX(profile_confidence) AS profile_confidence
      FROM ranked_matches GROUP BY item_id,family_id
    ), feature_rollup AS (
      SELECT item_id,
        SUM(CASE WHEN family_id='analysis-style' THEN MAX(-3.0,MIN(3.0,family_signal)) ELSE MAX(-5.0,MIN(5.0,family_signal)) END) AS relevance_signal,
        SUM(matched_features) AS matched_features,SUM(semantic_matches) AS semantic_matches,
        SUM(semantic_weight) AS semantic_weight,SUM(novel_semantic_weight) AS novel_semantic_weight,
        MAX(profile_confidence) AS profile_confidence,
        SUM(CASE WHEN ABS(family_signal)>0.0001 THEN 1 ELSE 0 END) AS matched_families
      FROM family_rollup GROUP BY item_id
    ), components AS (
      SELECT i.item_id,r.*,
        CASE
          WHEN i.published_at IS NULL OR julianday(i.published_at) IS NULL THEN 0.0
          WHEN julianday('now')-julianday(i.published_at)<0 THEN 0.0
          WHEN julianday('now')-julianday(i.published_at)<=2 THEN 5.0
          WHEN julianday('now')-julianday(i.published_at)<=7 THEN 3.5
          WHEN julianday('now')-julianday(i.published_at)<=30 THEN 1.5
          WHEN julianday('now')-julianday(i.published_at)<=90 THEN 0.5
          WHEN julianday('now')-julianday(i.published_at)>365 THEN -2.0
          WHEN julianday('now')-julianday(i.published_at)>180 THEN -1.0 ELSE 0.0 END AS freshness_bonus,
        CASE WHEN r.semantic_matches>0 AND r.semantic_weight>0 THEN MIN(2.0,2.0*r.novel_semantic_weight/r.semantic_weight) ELSE 0.0 END AS novelty_bonus
      FROM content_items i JOIN feature_rollup r ON r.item_id=i.item_id
    ), base_scores AS (
      SELECT *,50.0+(38.0*relevance_signal/(6.0+ABS(relevance_signal)))+freshness_bonus+novelty_bonus AS base_score FROM components
    ), ranked AS (
      SELECT *,PERCENT_RANK() OVER (ORDER BY base_score) AS rank_percentile FROM base_scores
    )
    INSERT INTO content_scores(item_id,score_type,score,confidence,reason_json,model_version,scored_at)
    SELECT item_id,'personal_relevance',MIN(99.5,MAX(0.5,0.82*base_score+18.0*rank_percentile)),
      MIN(1.0,MAX(profile_confidence,CASE WHEN semantic_matches>0 THEN 0.30 ELSE 0.0 END)),
      json_object('relevance_signal',ROUND(relevance_signal,4),'base_score',ROUND(base_score,3),
        'rank_percentile',ROUND(rank_percentile,4),'matched_features',matched_features,'semantic_matches',semantic_matches,
        'matched_families',matched_families,'freshness_bonus',freshness_bonus,'novelty_bonus',ROUND(novelty_bonus,3),
        'signal_policy','latest-explicit-wins','profile_policy',?,'ontology_version',?,'model',?),?,CURRENT_TIMESTAMP
    FROM ranked WHERE 1=1
    ON CONFLICT(item_id,score_type,model_version) DO UPDATE SET
      score=excluded.score,confidence=excluded.confidence,reason_json=excluded.reason_json,scored_at=CURRENT_TIMESTAMP
    WHERE content_scores.score IS NOT excluded.score OR content_scores.confidence IS NOT excluded.confidence OR content_scores.reason_json IS NOT excluded.reason_json
  `).bind(PERSONAL_POLICY_VERSION,INTEREST_ONTOLOGY_VERSION,modelVersion,modelVersion).run();
  const dist = await env.DB.prepare(`SELECT COUNT(*) AS n,MIN(score) AS min_score,MAX(score) AS max_score,AVG(score) AS avg_score,
    SUM(CASE WHEN score>=99 THEN 1 ELSE 0 END) AS score_99_plus,SUM(CASE WHEN score>=95 THEN 1 ELSE 0 END) AS score_95_plus
    FROM content_scores WHERE score_type='personal_relevance' AND model_version=?`).bind(modelVersion).first();
  return {ok:true,model_version:modelVersion,policy_version:PERSONAL_POLICY_VERSION,ontology_version:INTEREST_ONTOLOGY_VERSION,scored_items:Number(dist?.n||0),
    changed:Number(stale.meta?.changes||0)+Number(upsert.meta?.changes||0),distribution:{min:Number(dist?.min_score||0),max:Number(dist?.max_score||0),
    avg:Number(dist?.avg_score||0),score_99_plus:Number(dist?.score_99_plus||0),score_95_plus:Number(dist?.score_95_plus||0)}};
}

function clamp(value,min,max){ return Math.min(max,Math.max(min,value)); }
function clampTopK(value){ const n=Number.parseInt(String(value??10),10); return Math.min(50,Math.max(1,Number.isFinite(n)?n:10)); }
function numberOrNull(value){ const n=Number(value); return Number.isFinite(n)?n:null; }
function parseContextNumber(value){ try{return numberOrNull(JSON.parse(value||"{}").number);}catch{return null;} }
function typeCap(type,signal){ const caps={topic:5,mechanism:5,concept:4,entity:2,source:1.5}; const cap=caps[type]??2; return clamp(signal,-cap,cap); }
function freshnessBonus(value){ const ts=Date.parse(value||""); if(!Number.isFinite(ts))return 0; const days=(Date.now()-ts)/86400000; if(days<0)return 0;if(days<=2)return 5;if(days<=7)return 3.5;if(days<=30)return 1.5;if(days<=90)return .5;if(days>365)return -2;if(days>180)return -1;return 0; }
function scoreDistribution(rows){ const v=rows.map(x=>x.score).filter(Number.isFinite).sort((a,b)=>a-b); const q=x=>v.length?v[Math.min(v.length-1,Math.max(0,Math.round((v.length-1)*x)))]:null; return {count:v.length,min:v[0]??null,p50:q(.5),p90:q(.9),p99:q(.99),max:v[v.length-1]??null,score_99_plus:v.filter(x=>x>=99).length}; }

async function scoreShownItems(env, sourceRenderId){
  const shown = await env.DB.prepare(`SELECT e.item_id,e.id,e.context_json,i.title,i.canonical_url,i.source_name,i.published_at
    FROM user_content_events e JOIN content_items i ON i.item_id=e.item_id
    WHERE e.render_id=? AND e.event_type='shown' ORDER BY e.id ASC`).bind(sourceRenderId).all();
  const dedup=new Map(); for(const row of shown.results||[]){if(!dedup.has(row.item_id))dedup.set(row.item_id,{...row,manifest_number:parseContextNumber(row.context_json)});} const rows=[...dedup.values()];
  if(!rows.length)return [];
  const ids=rows.map(x=>x.item_id), placeholders=ids.map(()=>'?').join(',');
  const canonicalKeySql=canonicalInterestKeySql('f.feature_type','f.feature_key');
  const features=await env.DB.prepare(`SELECT f.item_id,f.feature_type,${canonicalKeySql} AS feature_key,f.weight AS feature_weight,f.confidence AS feature_confidence,
    p.weight AS profile_weight,p.evidence_count,p.confidence AS profile_confidence
    FROM content_features f LEFT JOIN interest_profile p ON p.feature_type=f.feature_type AND p.feature_key=${canonicalKeySql}
    WHERE f.item_id IN (${placeholders}) AND f.feature_type IN ('topic','concept','mechanism')`).bind(...ids).all();
  const families=await env.DB.prepare("SELECT feature_key,weight,evidence_count,confidence FROM interest_profile WHERE feature_type='family'").all();
  const familyProfile=new Map((families.results||[]).map(x=>[String(x.feature_key),x]));
  const byItem=new Map(rows.map(x=>[x.item_id,new Map()]));
  for(const f of features.results||[]){if(!byItem.has(f.item_id))continue;const key=`${f.feature_type}::${canonicalInterestKey(f.feature_type,f.feature_key)}`;const prior=byItem.get(f.item_id).get(key);const strength=Number(f.feature_weight||0)*Number(f.feature_confidence||0);if(!prior||strength>prior.__strength)byItem.get(f.item_id).set(key,{...f,__strength:strength});}
  for(const row of rows){
    const perFamily=new Map(),familyStrengths=new Map();let semanticWeight=0,novelWeight=0,semanticMatches=0,matched=0,profileConfidence=0;
    for(const f of byItem.get(row.item_id)?.values()||[]){
      const fw=Number(f.feature_weight||0),fc=Number(f.feature_confidence||0),pw=numberOrNull(f.profile_weight),t=String(f.feature_type||'other'),family=interestFamily(t,f.feature_key),sw=fw*fc,pf=familyProfile.get(family);
      if(!perFamily.has(family))perFamily.set(family,[]);if(!familyStrengths.has(family))familyStrengths.set(family,[]);familyStrengths.get(family).push(sw);
      if(pw!=null){perFamily.get(family).push(pw*sw);matched+=1;semanticMatches+=1;profileConfidence=Math.max(profileConfidence,Number(f.profile_confidence||0));}
      if(pf)profileConfidence=Math.max(profileConfidence,Number(pf.confidence||0));
      semanticWeight+=sw;if(pw==null&&!pf)novelWeight+=sw;
    }
    for(const [family,strengths] of familyStrengths){const pf=familyProfile.get(family);if(!pf)continue;strengths.sort((a,b)=>b-a);const familyFeatureStrength=strengths.reduce((sum,value,index)=>sum+value*familyDiminishingWeight(index+1),0);perFamily.get(family).push(Number(pf.weight||0)*familyFeatureStrength);matched+=1;semanticMatches+=1;}
    let relevance=0,matchedFamilies=0;
    for(const [family,contributions] of perFamily){if(!contributions.length)continue;contributions.sort((a,b)=>Math.abs(b)-Math.abs(a));const familyRaw=contributions.reduce((sum,value,index)=>sum+value*familyDiminishingWeight(index+1),0);const cap=familySignalCap(family);relevance+=clamp(familyRaw,-cap,cap);matchedFamilies+=1;}
    const novelty=semanticMatches>0&&semanticWeight>0?Math.min(2,2*novelWeight/semanticWeight):0;
    row.relevance_signal=relevance;row.matched_families=matchedFamilies;row.matched_features=matched;row.semantic_matches=semanticMatches;row.freshness_bonus=freshnessBonus(row.published_at);row.novelty_bonus=novelty;row.profile_confidence=profileConfidence;
    row.base_score=50+(38*relevance/(6+Math.abs(relevance)))+row.freshness_bonus+novelty;
  }
  const values=rows.map(r=>r.base_score).sort((a,b)=>a-b), first=new Map();values.forEach((v,i)=>{if(!first.has(v))first.set(v,i);});
  for(const row of rows){const pct=rows.length>1?(first.get(row.base_score)||0)/(rows.length-1):0;row.rank_percentile=pct;row.score=clamp(.82*row.base_score+18*pct,.5,99.5);}
  return rows;
}

export async function snapshotRecommendationRun(env, snapshotId, {sourceRenderId=null,topK=10,modelVersion=PERSONAL_MODEL_VERSION}={}){
  if(!env?.DB)return {ok:false,error:'D1_NOT_BOUND'};const sid=String(snapshotId||'').trim(),rid=String(sourceRenderId||snapshotId||'').trim();if(!sid||!rid)return {ok:false,error:'snapshot_id_and_source_render_id_required'};
  const existing=await env.DB.prepare('SELECT metadata_json,created_at FROM recommendation_runs WHERE render_id=?').bind(sid).first();if(existing){let meta={};try{meta=JSON.parse(existing.metadata_json||'{}');}catch{}return {ok:true,idempotent:true,snapshot_id:sid,source_render_id:meta.source_render_id||rid,created_at:existing.created_at,...meta};}
  const k=clampTopK(topK),rows=await scoreShownItems(env,rid);if(!rows.length)return {ok:false,error:'render_not_found_or_no_shown_items',source_render_id:rid};
  const baseline=[...rows].sort((a,b)=>(a.manifest_number??1e12)-(b.manifest_number??1e12)||a.id-b.id).slice(0,k).map((r,i)=>({item_id:r.item_id,rank:i+1,manifest_number:r.manifest_number}));
  const personalized=[...rows].sort((a,b)=>b.score-a.score||(a.manifest_number??1e12)-(b.manifest_number??1e12)).slice(0,k).map((r,i)=>({item_id:r.item_id,rank:i+1,score:Number(r.score.toFixed(4)),manifest_number:r.manifest_number}));
  const state=await profileState(env);const metadata={schema_version:3,policy_version:PERSONAL_POLICY_VERSION,ontology_version:INTEREST_ONTOLOGY_VERSION,source_render_id:rid,top_k:k,baseline_policy:'canonical-manifest-order',personalized_policy:'bounded-personal-relevance-live',baseline,personalized,score_distribution:scoreDistribution(rows),profile_state:state?.status||'missing',created_at:new Date().toISOString()};
  await env.DB.prepare(`INSERT INTO recommendation_runs(render_id,source_scope,item_count,recommended_count,exploration_ratio,model_version,created_at,metadata_json) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP,?)`).bind(sid,'rss',rows.length,k,0,modelVersion,JSON.stringify(metadata)).run();
  return {ok:true,idempotent:false,snapshot_id:sid,model_version:modelVersion,item_count:rows.length,...metadata};
}

function gradeEvents(events){let latest=null,positive=0,followUps=0;for(const e of events){if(e.event_type==='liked'||e.event_type==='disliked')latest=e.event_type;if(e.event_type==='interest_saved'||e.event_type==='saved')positive=Math.max(positive,3);else if(e.event_type==='deep_read')positive=Math.max(positive,2);else if(e.event_type==='selected')positive=Math.max(positive,1);else if(e.event_type==='follow_up')followUps+=1;}if(latest==='disliked')return 0;if(latest==='liked')return 3;return Math.min(3,positive+(positive>0?Math.min(1,0.5*followUps):0));}
function rankingMetrics(list,grades,positives,k){const n=Math.min(k,list.length);let hits=0,dcg=0;for(let i=0;i<n;i++){const g=Number(grades.get(list[i].item_id)||0);if(g>0)hits++;dcg+=(Math.pow(2,g)-1)/Math.log2(i+2);}const ideal=[...grades.values()].filter(x=>x>0).sort((a,b)=>b-a).slice(0,n);const idcg=ideal.reduce((s,g,i)=>s+(Math.pow(2,g)-1)/Math.log2(i+2),0);return {precision_at_k:n?hits/n:null,recall_at_k:positives?hits/positives:null,ndcg_at_k:idcg?dcg/idcg:null,hits_at_k:hits};}
export async function evaluateRecommendationRun(env,snapshotId){if(!env?.DB)return {ok:false,error:'D1_NOT_BOUND'};const sid=String(snapshotId||'').trim();if(!sid)return {ok:false,error:'snapshot_id_required'};const run=await env.DB.prepare('SELECT * FROM recommendation_runs WHERE render_id=?').bind(sid).first();if(!run)return {ok:false,error:'recommendation_snapshot_not_found',snapshot_id:sid};let meta={};try{meta=JSON.parse(run.metadata_json||'{}');}catch{}const baseline=Array.isArray(meta.baseline)?meta.baseline:[],personalized=Array.isArray(meta.personalized)?meta.personalized:[],rid=String(meta.source_render_id||'');const shown=await env.DB.prepare("SELECT DISTINCT item_id FROM user_content_events WHERE render_id=? AND event_type='shown'").bind(rid).all();const ids=(shown.results||[]).map(r=>String(r.item_id));if(!ids.length)return {ok:false,error:'source_render_not_found',source_render_id:rid};const ph=ids.map(()=>'?').join(',');const events=await env.DB.prepare(`SELECT item_id,event_type,event_at,id FROM user_content_events WHERE item_id IN (${ph}) AND event_type IN ('selected','deep_read','follow_up','saved','interest_saved','liked','disliked') AND event_at>=? ORDER BY event_at,id`).bind(...ids,run.created_at).all();const by=new Map(ids.map(id=>[id,[]]));for(const e of events.results||[])if(by.has(String(e.item_id)))by.get(String(e.item_id)).push(e);const grades=new Map();for(const [id,es] of by)grades.set(id,gradeEvents(es));const positives=[...grades.values()].filter(x=>x>0).length,k=clampTopK(meta.top_k||run.recommended_count||10),b=rankingMetrics(baseline,grades,positives,k),p=rankingMetrics(personalized,grades,positives,k),lift=(x,y)=>(x==null||y==null)?null:x-y;return {ok:true,snapshot_id:sid,source_render_id:rid,model_version:run.model_version,policy_version:meta.policy_version||null,top_k:k,judged_positive_count:positives,feedback_event_count:(events.results||[]).length,evaluable:positives>0,baseline:b,personalized:p,lift:{precision_at_k:lift(p.precision_at_k,b.precision_at_k),recall_at_k:lift(p.recall_at_k,b.recall_at_k),ndcg_at_k:lift(p.ndcg_at_k,b.ndcg_at_k)},snapshot_created_at:run.created_at,evaluated_at:new Date().toISOString()};}

export async function recomputePersonalization(env, modelVersion = PERSONAL_MODEL_VERSION) {
  const profile = await recomputeInterestProfile(env, modelVersion);
  const scores = await recomputePersonalScores(env, modelVersion);
  return {
    ok: true,
    model_version: modelVersion,
    policy_version: PERSONAL_POLICY_VERSION,
    profile_features: profile.profile_features,
    scored_items: scores.scored_items,
    changed: Number(profile.changed || 0) + Number(scores.changed || 0),
  };
}

export async function maybeRecomputePersonal(env, { modelVersion = PERSONAL_MODEL_VERSION, priorityExplicit = false } = {}) {
  if (!env?.DB) return { ok: false, recomputed: false };
  const before = await profileState(env);
  if (!before) return { ok: true, recomputed: false, status: "missing" };
  let materializationMismatch = false;
  if (before.status === "clean") {
    const materialized = await env.DB.prepare(
      "SELECT 1 AS ok FROM content_scores WHERE score_type='personal_relevance' AND model_version=? AND json_extract(reason_json,'$.profile_policy')=? AND json_extract(reason_json,'$.ontology_version')=? LIMIT 1"
    ).bind(modelVersion, PERSONAL_POLICY_VERSION, INTEREST_ONTOLOGY_VERSION).first();
    if (materialized?.ok) return { ok: true, recomputed: false, status: "clean" };
    materializationMismatch = true;
    await env.DB.prepare(`
      UPDATE workflow_state
      SET status='dirty', run_id=NULL, detail=?, updated_at=CURRENT_TIMESTAMP
      WHERE source=? AND status='clean'
    `).bind(JSON.stringify({ reason: "materialization_identity_mismatch", model: modelVersion, policy_version: PERSONAL_POLICY_VERSION, ontology_version: INTEREST_ONTOLOGY_VERSION }), PROFILE_STATE_KEY).run();
  }

  const token = await acquireRecomputeLease(env, modelVersion, priorityExplicit || materializationMismatch);
  if (!token) {
    const current = await profileState(env);
    if (current?.status === "dirty") return { ok: true, recomputed: false, status: "dirty_debounced" };
    if (current?.status === "recomputing") return { ok: true, recomputed: false, status: "recompute_in_progress" };
    return { ok: true, recomputed: false, status: current?.status || "missing" };
  }

  try {
    const result = await recomputePersonalization(env, modelVersion);
    const committed = await finishRecomputeLease(env, token, modelVersion);
    return {
      ...result,
      recomputed: true,
      lease_committed: committed,
      status: committed ? "clean" : "dirty_after_recompute",
    };
  } catch (error) {
    await failRecomputeLease(env, token, error);
    throw error;
  }
}

export async function refreshPersonalScoresDaily(env, { modelVersion = PERSONAL_MODEL_VERSION } = {}) {
  if (!env?.DB) return { ok: false, refreshed: false };
  const state = await profileState(env);
  if (!state) return { ok: true, refreshed: false, status: "profile_missing" };
  if (state.status === "dirty" || state.status === "recomputing") {
    return { ok: true, refreshed: false, status: `profile_${state.status}` };
  }
  const result = await recomputePersonalScores(env, modelVersion);
  return { ...result, refreshed: true, status: "score_refreshed" };
}
