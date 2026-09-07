#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "cloudflare/runner3-core/src/content-personalization.js"
I = ROOT / "cloudflare/runner3-core/src/content-intelligence.js"
C = ROOT / "scripts/content_intelligence_client.py"
T = ROOT / ".github/workflows/content-intelligence-v2-test.yml"


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {text.count(old)}")
    return text.replace(old, new, 1)


def regex_once(text, pattern, replacement, label):
    out, n = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"{label}: expected one regex match, got {n}")
    return out


p = P.read_text(encoding="utf-8")
p = replace_once(p, 'export const PERSONAL_MODEL_VERSION = "personal-v2";', 'export const PERSONAL_MODEL_VERSION = "personal-v3";', "model version")
p = replace_once(
    p,
    'export const RECOMPUTE_RETRY_MS = 60 * 60 * 1000;\n',
    'export const RECOMPUTE_RETRY_MS = 60 * 60 * 1000;\nexport const PERSONAL_POLICY_VERSION = "compressed-profile-bounded-rank-v3";\n',
    "policy marker",
)
p = replace_once(
    p,
    'export function isSupportedContentEvent(eventType) {',
    'const AUTO_FEATURE_MODELS = new Set(["semantic-bridge-v3", "reader-bridge-v2", "rules-v1"]);\n\nexport function isSupportedContentEvent(eventType) {',
    "auto model marker",
)

PROFILE_BLOCK = r'''function autoModelSql() {
  return [...AUTO_FEATURE_MODELS].map((x) => `'${x.replaceAll("'", "''")}'`).join(",");
}

function profileProjectionCte() {
  const autoModels = autoModelSql();
  return `${ITEM_SIGNAL_CTE}, feature_evidence AS (
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
    SELECT *, CASE
      WHEN evidence_count>=4 THEN 1.00
      WHEN evidence_count=3 THEN 0.82
      WHEN evidence_count=2 THEN 0.62
      WHEN has_explicit_feature=1 THEN 0.40
      WHEN feature_type IN ('topic','mechanism') THEN 0.30
      WHEN feature_type='concept' AND avg_feature_confidence>=0.80 THEN 0.25
      ELSE 0.15
    END AS evidence_factor
    FROM feature_evidence
    WHERE (evidence_count>=2 OR has_explicit_feature=1 OR feature_type IN ('topic','mechanism') OR (feature_type='concept' AND avg_feature_confidence>=0.80))
      AND NOT (has_explicit_feature=0 AND feature_type IN ('keyword','domain','language'))
      AND NOT (has_explicit_feature=0 AND feature_type='entity' AND evidence_count<2)
      AND NOT (has_explicit_feature=0 AND feature_type='source' AND evidence_count<3)
  ), scored AS (
    SELECT *,
      (raw_weight/MAX(1.0,SQRT(evidence_count)))*evidence_factor AS projected_weight,
      MIN(1.0,(evidence_count/(evidence_count+2.0))*MAX(0.35,avg_feature_confidence)) AS projected_confidence
    FROM eligible
  ), ranked AS (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY feature_type
      ORDER BY evidence_count DESC, ABS(projected_weight) DESC, feature_key
    ) AS type_rank
    FROM scored
    WHERE ABS(projected_weight)>=0.05
  ), projected AS (
    SELECT * FROM ranked WHERE type_rank <= CASE
      WHEN feature_type='topic' THEN 60
      WHEN feature_type='mechanism' THEN 60
      WHEN feature_type='concept' THEN 100
      WHEN feature_type='entity' THEN 40
      WHEN feature_type='source' THEN 20
      ELSE 20 END
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
'''
p = regex_once(
    p,
    r'export async function recomputeInterestProfile\(.*?\n\}\n\n(?=export async function recomputePersonalScores)',
    PROFILE_BLOCK + "\n",
    "profile recompute",
)

SCORE_AND_EVAL_BLOCK = r'''export async function recomputePersonalScores(env, modelVersion = PERSONAL_MODEL_VERSION) {
  if (!env?.DB) return { ok:false,model_version:modelVersion,scored_items:0,changed:0 };
  const stale = await env.DB.prepare("DELETE FROM content_scores WHERE score_type='personal_relevance' AND model_version<>?").bind(modelVersion).run();
  const upsert = await env.DB.prepare(`
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
          ELSE MAX(-2.0,MIN(2.0,type_signal)) END) AS relevance_signal,
        SUM(matched_features) AS matched_features,SUM(semantic_matches) AS semantic_matches,
        SUM(semantic_weight) AS semantic_weight,SUM(novel_semantic_weight) AS novel_semantic_weight,
        MAX(profile_confidence) AS profile_confidence
      FROM per_type GROUP BY item_id
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
        'freshness_bonus',freshness_bonus,'novelty_bonus',ROUND(novelty_bonus,3),'signal_policy','latest-explicit-wins',
        'profile_policy',?,'model',?),?,CURRENT_TIMESTAMP
    FROM ranked WHERE 1=1
    ON CONFLICT(item_id,score_type,model_version) DO UPDATE SET
      score=excluded.score,confidence=excluded.confidence,reason_json=excluded.reason_json,scored_at=CURRENT_TIMESTAMP
    WHERE content_scores.score IS NOT excluded.score OR content_scores.confidence IS NOT excluded.confidence OR content_scores.reason_json IS NOT excluded.reason_json
  `).bind(PERSONAL_POLICY_VERSION,modelVersion,modelVersion).run();
  const dist = await env.DB.prepare(`SELECT COUNT(*) AS n,MIN(score) AS min_score,MAX(score) AS max_score,AVG(score) AS avg_score,
    SUM(CASE WHEN score>=99 THEN 1 ELSE 0 END) AS score_99_plus,SUM(CASE WHEN score>=95 THEN 1 ELSE 0 END) AS score_95_plus
    FROM content_scores WHERE score_type='personal_relevance' AND model_version=?`).bind(modelVersion).first();
  return {ok:true,model_version:modelVersion,policy_version:PERSONAL_POLICY_VERSION,scored_items:Number(dist?.n||0),
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
  const features=await env.DB.prepare(`SELECT f.item_id,f.feature_type,f.weight AS feature_weight,f.confidence AS feature_confidence,
    p.weight AS profile_weight,p.evidence_count,p.confidence AS profile_confidence
    FROM content_features f LEFT JOIN interest_profile p ON p.feature_type=f.feature_type AND p.feature_key=f.feature_key
    WHERE f.item_id IN (${placeholders})`).bind(...ids).all();
  const byItem=new Map(rows.map(x=>[x.item_id,[]])); for(const f of features.results||[])if(byItem.has(f.item_id))byItem.get(f.item_id).push(f);
  for(const row of rows){
    const perType=new Map();let semanticWeight=0,novelWeight=0,semanticMatches=0,matched=0,profileConfidence=0;
    for(const f of byItem.get(row.item_id)||[]){const fw=Number(f.feature_weight||0),fc=Number(f.feature_confidence||0),pw=numberOrNull(f.profile_weight);const t=String(f.feature_type||'other');
      if(pw!=null){perType.set(t,(perType.get(t)||0)+pw*fw*fc);matched+=1;profileConfidence=Math.max(profileConfidence,Number(f.profile_confidence||0));}
      if(['topic','concept','entity','mechanism'].includes(t)){const sw=fw*fc;semanticWeight+=sw;if(pw!=null)semanticMatches+=1;if(pw==null||Number(f.evidence_count||0)<=1)novelWeight+=sw;}
    }
    const relevance=[...perType.entries()].reduce((s,[t,v])=>s+typeCap(t,v),0);const novelty=semanticMatches>0&&semanticWeight>0?Math.min(2,2*novelWeight/semanticWeight):0;
    row.relevance_signal=relevance;row.freshness_bonus=freshnessBonus(row.published_at);row.novelty_bonus=novelty;row.profile_confidence=profileConfidence;
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
  const state=await profileState(env);const metadata={schema_version:2,policy_version:PERSONAL_POLICY_VERSION,source_render_id:rid,top_k:k,baseline_policy:'canonical-manifest-order',personalized_policy:'bounded-personal-relevance-live',baseline,personalized,score_distribution:scoreDistribution(rows),profile_state:state?.status||'missing',created_at:new Date().toISOString()};
  await env.DB.prepare(`INSERT INTO recommendation_runs(render_id,source_scope,item_count,recommended_count,exploration_ratio,model_version,created_at,metadata_json) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP,?)`).bind(sid,'rss',rows.length,k,0,modelVersion,JSON.stringify(metadata)).run();
  return {ok:true,idempotent:false,snapshot_id:sid,model_version:modelVersion,item_count:rows.length,...metadata};
}

function gradeEvents(events){let latest=null,positive=0;for(const e of events){if(e.event_type==='liked'||e.event_type==='disliked')latest=e.event_type;if(e.event_type==='interest_saved'||e.event_type==='saved')positive=Math.max(positive,3);else if(e.event_type==='deep_read')positive=Math.max(positive,2);else if(e.event_type==='selected')positive=Math.max(positive,1);}if(latest==='disliked')return 0;if(latest==='liked')return 3;return positive;}
function rankingMetrics(list,grades,positives,k){const n=Math.min(k,list.length);let hits=0,dcg=0;for(let i=0;i<n;i++){const g=Number(grades.get(list[i].item_id)||0);if(g>0)hits++;dcg+=(Math.pow(2,g)-1)/Math.log2(i+2);}const ideal=[...grades.values()].filter(x=>x>0).sort((a,b)=>b-a).slice(0,n);const idcg=ideal.reduce((s,g,i)=>s+(Math.pow(2,g)-1)/Math.log2(i+2),0);return {precision_at_k:n?hits/n:null,recall_at_k:positives?hits/positives:null,ndcg_at_k:idcg?dcg/idcg:null,hits_at_k:hits};}
export async function evaluateRecommendationRun(env,snapshotId){if(!env?.DB)return {ok:false,error:'D1_NOT_BOUND'};const sid=String(snapshotId||'').trim();if(!sid)return {ok:false,error:'snapshot_id_required'};const run=await env.DB.prepare('SELECT * FROM recommendation_runs WHERE render_id=?').bind(sid).first();if(!run)return {ok:false,error:'recommendation_snapshot_not_found',snapshot_id:sid};let meta={};try{meta=JSON.parse(run.metadata_json||'{}');}catch{}const baseline=Array.isArray(meta.baseline)?meta.baseline:[],personalized=Array.isArray(meta.personalized)?meta.personalized:[],rid=String(meta.source_render_id||'');const shown=await env.DB.prepare("SELECT DISTINCT item_id FROM user_content_events WHERE render_id=? AND event_type='shown'").bind(rid).all();const ids=(shown.results||[]).map(r=>String(r.item_id));if(!ids.length)return {ok:false,error:'source_render_not_found',source_render_id:rid};const ph=ids.map(()=>'?').join(',');const events=await env.DB.prepare(`SELECT item_id,event_type,event_at,id FROM user_content_events WHERE item_id IN (${ph}) AND event_type IN ('selected','deep_read','saved','interest_saved','liked','disliked') AND event_at>=? ORDER BY event_at,id`).bind(...ids,run.created_at).all();const by=new Map(ids.map(id=>[id,[]]));for(const e of events.results||[])if(by.has(String(e.item_id)))by.get(String(e.item_id)).push(e);const grades=new Map();for(const [id,es] of by)grades.set(id,gradeEvents(es));const positives=[...grades.values()].filter(x=>x>0).length,k=clampTopK(meta.top_k||run.recommended_count||10),b=rankingMetrics(baseline,grades,positives,k),p=rankingMetrics(personalized,grades,positives,k),lift=(x,y)=>(x==null||y==null)?null:x-y;return {ok:true,snapshot_id:sid,source_render_id:rid,model_version:run.model_version,policy_version:meta.policy_version||null,top_k:k,judged_positive_count:positives,feedback_event_count:(events.results||[]).length,evaluable:positives>0,baseline:b,personalized:p,lift:{precision_at_k:lift(p.precision_at_k,b.precision_at_k),recall_at_k:lift(p.recall_at_k,b.recall_at_k),ndcg_at_k:lift(p.ndcg_at_k,b.ndcg_at_k)},snapshot_created_at:run.created_at,evaluated_at:new Date().toISOString()};}
'''
p = regex_once(
    p,
    r'export async function recomputePersonalScores\(.*?\n\}\n\n(?=export async function recomputePersonalization)',
    SCORE_AND_EVAL_BLOCK + "\n",
    "score recompute and evaluation",
)
p = replace_once(
    p,
    '    model_version: modelVersion,\n    profile_features: profile.profile_features,',
    '    model_version: modelVersion,\n    policy_version: PERSONAL_POLICY_VERSION,\n    profile_features: profile.profile_features,',
    "personalization result policy",
)
P.write_text(p, encoding="utf-8")

# Add quota-safe recommendation endpoints without changing guarded recompute behavior.
i = I.read_text(encoding="utf-8")
i = replace_once(
    i,
    '  RECOMPUTE_DEBOUNCE_MS,\n  isSupportedContentEvent,',
    '  RECOMPUTE_DEBOUNCE_MS,\n  PERSONAL_POLICY_VERSION,\n  snapshotRecommendationRun,\n  evaluateRecommendationRun,\n  isSupportedContentEvent,',
    "intelligence imports",
)
handler_anchor = 'async function handleProfileRecompute(request,env){ return handleGuardedRecompute(request,env); }\n'
handlers = '''async function handleRecommendationSnapshot(request,env){\n  const e=requireDb(env)||requireAuth(request,env);if(e)return e;if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});\n  const body=await request.json().catch(()=>({}));\n  const result=await snapshotRecommendationRun(env,text(body.snapshot_id,300)||text(body.render_id,300),{sourceRenderId:text(body.render_id,300),topK:body.top_k,modelVersion:PERSONAL_MODEL_VERSION});\n  return Response.json(result,{status:result.ok?200:400});\n}\nasync function handleRecommendationEvaluation(request,env,url){\n  const e=requireDb(env)||requireAuth(request,env);if(e)return e;if(request.method!=="GET")return Response.json({ok:false,error:"method_not_allowed"},{status:405});\n  const result=await evaluateRecommendationRun(env,text(url.searchParams.get("snapshot_id"),300));\n  return Response.json(result,{status:result.ok?200:404});\n}\n'''
i = replace_once(i, handler_anchor, handler_anchor + handlers, "recommendation handlers")
i = replace_once(
    i,
    'return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,rows:result.results||[]}); }',
    'return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,policy_version:PERSONAL_POLICY_VERSION,rows:result.results||[]}); }',
    "profile response policy",
)
i = replace_once(
    i,
    '  if(url.pathname==="/content-intelligence/scores/top")return handleTopScores(request,env,url);\n',
    '  if(url.pathname==="/content-intelligence/scores/top")return handleTopScores(request,env,url);\n  if(url.pathname==="/content-intelligence/recommendations/snapshot")return handleRecommendationSnapshot(request,env);\n  if(url.pathname==="/content-intelligence/recommendations/evaluate")return handleRecommendationEvaluation(request,env,url);\n',
    "recommendation routes",
)
I.write_text(i, encoding="utf-8")

# Client commands used by RSS daily workflow in phase 2.
c = C.read_text(encoding="utf-8")
client_funcs = '''\ndef cmd_recommendation_snapshot(args: argparse.Namespace) -> int:\n    payload = {"render_id": args.render_id, "snapshot_id": args.snapshot_id, "top_k": args.top_k}\n    result = request_json("POST", "/content-intelligence/recommendations/snapshot", payload, core_url=args.core_url)\n    text = json.dumps(result, ensure_ascii=False, sort_keys=True)\n    if args.out:\n        with open(args.out, "w", encoding="utf-8") as fh: fh.write(json.dumps(result, ensure_ascii=False, indent=2) + "\\n")\n    print(text)\n    return 0 if result.get("ok") else 1\n\ndef cmd_recommendation_evaluate(args: argparse.Namespace) -> int:\n    from urllib.parse import quote\n    result = request_json("GET", f"/content-intelligence/recommendations/evaluate?snapshot_id={quote(args.snapshot_id, safe='')}", core_url=args.core_url)\n    if args.out:\n        with open(args.out, "w", encoding="utf-8") as fh: fh.write(json.dumps(result, ensure_ascii=False, indent=2) + "\\n")\n    print(json.dumps(result, ensure_ascii=False, sort_keys=True))\n    return 0 if result.get("ok") else 1\n\n'''
c = replace_once(c, '\ndef build_parser() -> argparse.ArgumentParser:\n', client_funcs + '\ndef build_parser() -> argparse.ArgumentParser:\n', "client functions")
parser_anchor = '    g.set_defaults(func=cmd_profile)\n    return p\n'
parser_new = '''    g.set_defaults(func=cmd_profile)\n    rs = sub.add_parser("recommendation-snapshot")\n    rs.add_argument("--render-id", required=True)\n    rs.add_argument("--snapshot-id", required=True)\n    rs.add_argument("--top-k", type=int, default=10)\n    rs.add_argument("--out")\n    rs.set_defaults(func=cmd_recommendation_snapshot)\n    reval = sub.add_parser("recommendation-evaluate")\n    reval.add_argument("--snapshot-id", required=True)\n    reval.add_argument("--out")\n    reval.set_defaults(func=cmd_recommendation_evaluate)\n    return p\n'''
c = replace_once(c, parser_anchor, parser_new, "client parser")
C.write_text(c, encoding="utf-8")

# Regression contract: v3 markers + quota guard + anti-saturation/evaluation endpoints.
t = T.read_text(encoding="utf-8")
t = t.replace('name: Content Intelligence v2 Regression', 'name: Content Intelligence v3 Regression', 1)
t = replace_once(t, "if (PERSONAL_MODEL_VERSION !== 'personal-v2')", "if (PERSONAL_MODEL_VERSION !== 'personal-v3')", "test model marker")
t = replace_once(
    t,
    "import { EVENT_WEIGHTS, PERSONAL_MODEL_VERSION, isSupportedContentEvent } from './cloudflare/runner3-core/src/content-personalization.js';",
    "import { EVENT_WEIGHTS, PERSONAL_MODEL_VERSION, PERSONAL_POLICY_VERSION, isSupportedContentEvent } from './cloudflare/runner3-core/src/content-personalization.js';",
    "test import policy",
)
t = replace_once(
    t,
    "if (!isSupportedContentEvent('interest_saved') || EVENT_WEIGHTS.interest_saved <= EVENT_WEIGHTS.deep_read) throw new Error('interest_saved priority incorrect');",
    "if (PERSONAL_POLICY_VERSION !== 'compressed-profile-bounded-rank-v3') throw new Error('personal policy marker mismatch');\n          if (!isSupportedContentEvent('interest_saved') || EVENT_WEIGHTS.interest_saved <= EVENT_WEIGHTS.deep_read) throw new Error('interest_saved priority incorrect');",
    "test policy marker",
)
t = replace_once(
    t,
    "          grep -q 'novelty_bonus' cloudflare/runner3-core/src/content-personalization.js\n",
    "          grep -q 'novelty_bonus' cloudflare/runner3-core/src/content-personalization.js\n          grep -q 'PERCENT_RANK()' cloudflare/runner3-core/src/content-personalization.js\n          grep -q 'type_rank' cloudflare/runner3-core/src/content-personalization.js\n          grep -q '/content-intelligence/recommendations/snapshot' cloudflare/runner3-core/src/content-intelligence.js\n          grep -q '/content-intelligence/recommendations/evaluate' cloudflare/runner3-core/src/content-intelligence.js\n",
    "test v3 greps",
)
T.write_text(t, encoding="utf-8")

print("CONTENT_INTELLIGENCE_V3_UPGRADE_APPLIED")
