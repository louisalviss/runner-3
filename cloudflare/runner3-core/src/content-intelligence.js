import { FEATURE_MODEL_VERSION, replaceAutoSemanticFeatures } from "./content-feature-enrichment.js";
import {
  PERSONAL_MODEL_VERSION,
  isSupportedContentEvent,
  markProfileDirty,
  maybeRecomputePersonal,
  recomputeInterestProfile,
  recomputePersonalScores,
} from "./content-personalization.js";

const MAX_ROWS = 100;
const MAX_JSON = 200000;

function requireDb(env) { if (!env.DB) return Response.json({ ok:false, error:"D1_NOT_BOUND" }, { status:503 }); return null; }
function requireAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return Response.json({ ok:false, error:"WRITE_AUTH_NOT_CONFIGURED" }, { status:503 });
  const auth=request.headers.get("Authorization")||""; const supplied=auth.startsWith("Bearer ")?auth.slice(7).trim():"";
  if (!supplied || supplied!==expected) return Response.json({ ok:false, error:"UNAUTHORIZED" }, { status:401 }); return null;
}
function text(value,max=4096){ if(value==null)return null; const out=typeof value==="string"?value:String(value); if(out.length>max)throw new Error(`text_too_large:${out.length}:${max}`); return out; }
function jsonText(value){ if(value==null)return null; const out=JSON.stringify(value); if(out.length>MAX_JSON)throw new Error(`json_too_large:${out.length}:${MAX_JSON}`); return out; }
function rows(body){ if(!Array.isArray(body?.rows))throw new Error("rows_must_be_array"); if(body.rows.length<1||body.rows.length>MAX_ROWS)throw new Error(`rows_must_contain_1_to_${MAX_ROWS}`); return body.rows; }
function normalizedItem(row={}){
  const canonicalUrl=text(row.canonical_url,4096)?.trim();
  const itemId=text(row.item_id || canonicalUrl,4096)?.trim();
  const sourceType=text(row.source_type || "web",100)?.trim();
  if(!itemId||!canonicalUrl||!sourceType)throw new Error("item_id_canonical_url_source_type_required");
  return {...row,item_id:itemId,canonical_url:canonicalUrl,source_type:sourceType};
}

function itemStatement(env,row){
  const r=normalizedItem(row);
  return env.DB.prepare(`INSERT INTO content_items(item_id,canonical_url,source_type,source_name,source_key,title,published_at,captured_at,language,raw_ref,content_hash,metadata_json,first_seen_at,last_seen_at)
    VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
    ON CONFLICT(item_id) DO UPDATE SET canonical_url=excluded.canonical_url,source_type=excluded.source_type,source_name=COALESCE(excluded.source_name,content_items.source_name),source_key=COALESCE(excluded.source_key,content_items.source_key),title=COALESCE(excluded.title,content_items.title),published_at=COALESCE(excluded.published_at,content_items.published_at),language=COALESCE(excluded.language,content_items.language),raw_ref=COALESCE(excluded.raw_ref,content_items.raw_ref),content_hash=COALESCE(excluded.content_hash,content_items.content_hash),metadata_json=COALESCE(excluded.metadata_json,content_items.metadata_json),last_seen_at=CURRENT_TIMESTAMP`)
    .bind(r.item_id,r.canonical_url,r.source_type,text(r.source_name,300),text(r.source_key,200),text(r.title,4000),text(r.published_at,100),text(r.language,50),text(r.raw_ref,2000),text(r.content_hash,200),jsonText(r.metadata));
}
async function enrichItem(env,row){
  const r=normalizedItem(row);
  return replaceAutoSemanticFeatures(env,r.item_id,r);
}
async function handleItems(request,env){
  const e=requireDb(env)||requireAuth(request,env); if(e)return e;
  if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  try{
    const list=rows(await request.json()).map(normalizedItem);
    await env.DB.batch(list.map(r=>itemStatement(env,r)));
    let semanticFeatures=0;
    for(const r of list) semanticFeatures+=(await enrichItem(env,r)).applied;
    await markProfileDirty(env,"content_items_or_features_changed");
    return Response.json({ok:true,applied:list.length,semantic_features:semanticFeatures,feature_model:FEATURE_MODEL_VERSION,materialization_status:"dirty"});
  }catch(err){return Response.json({ok:false,error:String(err?.message||err)},{status:400});}
}

function featureStatement(env,row){
  const itemId=text(row.item_id,4096)?.trim(),type=text(row.feature_type,100)?.trim(),key=text(row.feature_key,300)?.trim(); if(!itemId||!type||!key)throw new Error("item_id_feature_type_feature_key_required");
  return env.DB.prepare(`INSERT INTO content_features(item_id,feature_type,feature_key,feature_value,weight,confidence,model_version,updated_at) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(item_id,feature_type,feature_key) DO UPDATE SET feature_value=excluded.feature_value,weight=excluded.weight,confidence=excluded.confidence,model_version=excluded.model_version,updated_at=CURRENT_TIMESTAMP
    WHERE content_features.feature_value IS NOT excluded.feature_value
       OR content_features.weight IS NOT excluded.weight
       OR content_features.confidence IS NOT excluded.confidence
       OR content_features.model_version IS NOT excluded.model_version`)
    .bind(itemId,type,key,text(row.feature_value,4000),Number(row.weight??1),Number(row.confidence??1),text(row.model_version,200));
}
async function handleFeatures(request,env){
  const e=requireDb(env)||requireAuth(request,env); if(e)return e;
  if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  try{
    const list=rows(await request.json());
    const results=await env.DB.batch(list.map(r=>featureStatement(env,r)));
    const changed=results.reduce((n,r)=>n+Number(r.meta?.changes||0),0);
    if(changed) await markProfileDirty(env,"content_features_changed");
    return Response.json({ok:true,applied:list.length,changed,materialization_status:changed?"dirty":"unchanged"});
  }catch(err){return Response.json({ok:false,error:String(err?.message||err)},{status:400});}
}

function eventStatement(env,row){
  const itemId=text(row.item_id,4096)?.trim(),eventType=text(row.event_type,100)?.trim(); if(!itemId||!eventType)throw new Error("item_id_event_type_required"); if(!isSupportedContentEvent(eventType))throw new Error("unsupported_event_type");
  return env.DB.prepare(`INSERT INTO user_content_events(item_id,render_id,event_type,assistant_recommended,assistant_rank,explicit_feedback,context_json,event_at)
    SELECT ?,?,?,?,?,?,?,CURRENT_TIMESTAMP WHERE EXISTS(SELECT 1 FROM content_items WHERE item_id=?)`)
    .bind(itemId,text(row.render_id,300),eventType,row.assistant_recommended?1:0,Number.isFinite(Number(row.assistant_rank))?Number(row.assistant_rank):null,text(row.explicit_feedback,1000),jsonText(row.context),itemId);
}
async function handleEvent(request,env){
  const e=requireDb(env)||requireAuth(request,env); if(e)return e;
  if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  try{
    const body=await request.json(); const result=await eventStatement(env,body).run();
    if((result.meta?.changes??0)<1)return Response.json({ok:false,error:"CONTENT_ITEM_NOT_FOUND_OR_DUPLICATE"},{status:404});
    await markProfileDirty(env,`event_${text(body.event_type,100)}`);
    return Response.json({ok:true,durable:true,id:result.meta?.last_row_id??null,event_applied:1,materialization_status:"dirty"});
  }catch(err){return Response.json({ok:false,error:String(err?.message||err)},{status:400});}
}
async function handleEventBatch(request,env){
  const e=requireDb(env)||requireAuth(request,env); if(e)return e;
  if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  try{
    const list=rows(await request.json()); const results=await env.DB.batch(list.map(r=>eventStatement(env,r))); const applied=results.reduce((n,r)=>n+(r.meta?.changes??0),0);
    if(applied) await markProfileDirty(env,"event_batch");
    return Response.json({ok:true,durable:true,applied,requested:list.length,missing_or_duplicate:list.length-applied,materialization_status:applied?"dirty":"unchanged"});
  }catch(err){return Response.json({ok:false,error:String(err?.message||err)},{status:400});}
}

async function handleInterestIngest(request,env){
  const e=requireDb(env)||requireAuth(request,env); if(e)return e;
  if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  try{
    const body=await request.json(); const item=normalizedItem(body.item||body);
    await itemStatement(env,item).run();
    if(Array.isArray(body.features)&&body.features.length){
      if(body.features.length>MAX_ROWS)throw new Error(`features_must_contain_at_most_${MAX_ROWS}`);
      await env.DB.batch(body.features.map(f=>featureStatement(env,{...f,item_id:item.item_id})));
    }
    const renderId=text(body.render_id,300)?.trim()||`interest-save:${item.item_id}`;
    const event={item_id:item.item_id,event_type:"interest_saved",render_id:renderId,explicit_feedback:"interest_saved",context:{source:"explicit_interest_ingest",...(body.context||{})}};
    const result=await eventStatement(env,event).run();
    await markProfileDirty(env,"explicit_interest_ingested");
    return Response.json({
      ok:true,
      durable:true,
      item_id:item.item_id,
      event_applied:Number(result.meta?.changes||0),
      event_id:result.meta?.last_row_id??null,
      feature_model:FEATURE_MODEL_VERSION,
      model_version:PERSONAL_MODEL_VERSION,
      semantic_enrichment:"deferred",
      materialization_status:"dirty"
    });
  }catch(err){return Response.json({ok:false,error:String(err?.message||err)},{status:400});}
}

// Compatibility endpoint. New callers should use /interests/ingest; this route
// retains the historical eager enrichment/recompute behavior until consumers migrate.
async function handleInterestSave(request,env){
  const e=requireDb(env)||requireAuth(request,env); if(e)return e;
  if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  try{
    const body=await request.json(); const item=normalizedItem(body.item||body);
    await itemStatement(env,item).run();
    const semantic=await enrichItem(env,item);
    if(Array.isArray(body.features)&&body.features.length){
      if(body.features.length>MAX_ROWS)throw new Error(`features_must_contain_at_most_${MAX_ROWS}`);
      await env.DB.batch(body.features.map(f=>featureStatement(env,{...f,item_id:item.item_id})));
    }
    const renderId=text(body.render_id,300)?.trim()||`interest-save:${item.item_id}`;
    const event={item_id:item.item_id,event_type:"interest_saved",render_id:renderId,explicit_feedback:"interest_saved",context:{source:"explicit_interest_save",...(body.context||{})}};
    const result=await eventStatement(env,event).run();
    await markProfileDirty(env,"explicit_interest_saved");
    const recompute=await maybeRecomputePersonal(env);
    return Response.json({ok:true,item_id:item.item_id,event_applied:Number(result.meta?.changes||0),semantic_features:semantic.applied,feature_model:FEATURE_MODEL_VERSION,model_version:PERSONAL_MODEL_VERSION,profile_recomputed:Boolean(recompute.recomputed)});
  }catch(err){return Response.json({ok:false,error:String(err?.message||err)},{status:400});}
}

async function handleProfileRecompute(request,env){
  const e=requireDb(env)||requireAuth(request,env);if(e)return e;if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  const body=await request.json().catch(()=>({})); return Response.json(await recomputeInterestProfile(env,text(body.model_version,200)||PERSONAL_MODEL_VERSION));
}
async function handleScoresRecompute(request,env){
  const e=requireDb(env)||requireAuth(request,env);if(e)return e;if(request.method!=="POST")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  const body=await request.json().catch(()=>({})); return Response.json(await recomputePersonalScores(env,text(body.model_version,200)||PERSONAL_MODEL_VERSION));
}
async function handleProfile(request,env,url){ const e=requireDb(env)||requireAuth(request,env);if(e)return e;if(request.method!=="GET")return Response.json({ok:false,error:"method_not_allowed"},{status:405});const limit=Math.min(500,Math.max(1,Number.parseInt(url.searchParams.get("limit")||"100",10)||100));const result=await env.DB.prepare(`SELECT feature_type,feature_key,weight,evidence_count,positive_count,negative_count,confidence,updated_at FROM interest_profile ORDER BY ABS(weight) DESC,confidence DESC,evidence_count DESC LIMIT ?`).bind(limit).all();return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,rows:result.results||[]}); }
async function handleTopScores(request,env,url){ const e=requireDb(env)||requireAuth(request,env);if(e)return e;if(request.method!=="GET")return Response.json({ok:false,error:"method_not_allowed"},{status:405});const limit=Math.min(200,Math.max(1,Number.parseInt(url.searchParams.get("limit")||"30",10)||30));const result=await env.DB.prepare(`SELECT s.item_id,s.score,s.confidence,s.reason_json,s.model_version,i.canonical_url,i.title,i.source_type,i.source_name,i.published_at FROM content_scores s JOIN content_items i ON i.item_id=s.item_id WHERE s.score_type='personal_relevance' AND s.model_version=? ORDER BY s.score DESC,i.published_at DESC LIMIT ?`).bind(PERSONAL_MODEL_VERSION,limit).all();return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,rows:result.results||[]}); }

async function handleSynthesis(request,env,url){
  const e=requireDb(env)||requireAuth(request,env); if(e)return e;
  if(request.method!=="GET")return Response.json({ok:false,error:"method_not_allowed"},{status:405});
  const profileLimit=Math.min(100,Math.max(5,Number.parseInt(url.searchParams.get("profile_limit")||"30",10)||30));
  const scoreLimit=Math.min(100,Math.max(5,Number.parseInt(url.searchParams.get("score_limit")||"20",10)||20));
  const [counts,eventTypes,profile,topScores,recentFeedback,recentEvents]=await Promise.all([
    env.DB.prepare(`SELECT (SELECT COUNT(*) FROM content_items) AS items,(SELECT COUNT(*) FROM user_content_events) AS events,(SELECT COUNT(*) FROM content_scores WHERE score_type='personal_relevance' AND model_version=?) AS scored_items,(SELECT COUNT(*) FROM interest_profile) AS profile_features,(SELECT MAX(event_at) FROM user_content_events) AS last_event_at`).bind(PERSONAL_MODEL_VERSION).first(),
    env.DB.prepare(`SELECT event_type,COUNT(*) AS count FROM user_content_events GROUP BY event_type ORDER BY count DESC`).all(),
    env.DB.prepare(`SELECT feature_type,feature_key,weight,evidence_count,positive_count,negative_count,confidence,updated_at FROM interest_profile ORDER BY ABS(weight) DESC,confidence DESC,evidence_count DESC LIMIT ?`).bind(profileLimit).all(),
    env.DB.prepare(`SELECT s.item_id,s.score,s.confidence,s.reason_json,s.model_version,i.canonical_url,i.title,i.source_type,i.source_name,i.source_key,i.published_at FROM content_scores s JOIN content_items i ON i.item_id=s.item_id WHERE s.score_type='personal_relevance' AND s.model_version=? ORDER BY s.score DESC,i.published_at DESC LIMIT ?`).bind(PERSONAL_MODEL_VERSION,scoreLimit).all(),
    env.DB.prepare(`SELECT e.id,e.item_id,e.event_type,e.explicit_feedback,e.event_at,i.title,i.canonical_url,i.source_type,i.source_name FROM user_content_events e JOIN content_items i ON i.item_id=e.item_id WHERE e.explicit_feedback IS NOT NULL AND TRIM(e.explicit_feedback)<>'' ORDER BY e.event_at DESC LIMIT 20`).all(),
    env.DB.prepare(`SELECT e.id,e.item_id,e.event_type,e.event_at,e.render_id,i.title,i.canonical_url,i.source_type,i.source_name FROM user_content_events e JOIN content_items i ON i.item_id=e.item_id WHERE e.event_type<>'shown' ORDER BY e.event_at DESC LIMIT 30`).all()
  ]);
  return Response.json({
    ok:true,generated_at:new Date().toISOString(),model_version:PERSONAL_MODEL_VERSION,feature_model:FEATURE_MODEL_VERSION,
    signal_policy:"latest-explicit-wins + interaction-recency-decay",
    scoring_policy:"semantic relevance + freshness + bounded novelty",
    counts:{items:Number(counts?.items||0),events:Number(counts?.events||0),scored_items:Number(counts?.scored_items||0),profile_features:Number(counts?.profile_features||0),last_event_at:counts?.last_event_at||null},
    event_types:eventTypes.results||[],profile:profile.results||[],top_scores:topScores.results||[],recent_feedback:recentFeedback.results||[],recent_interest_events:recentEvents.results||[]
  });
}

export async function handleContentIntelligence(request,env,url){
  if(url.pathname==="/content-intelligence/items")return handleItems(request,env);
  if(url.pathname==="/content-intelligence/features")return handleFeatures(request,env);
  if(url.pathname==="/content-intelligence/events")return handleEvent(request,env);
  if(url.pathname==="/content-intelligence/events/batch")return handleEventBatch(request,env);
  if(url.pathname==="/content-intelligence/interests/ingest")return handleInterestIngest(request,env);
  if(url.pathname==="/content-intelligence/interests/save")return handleInterestSave(request,env);
  if(url.pathname==="/content-intelligence/profile")return handleProfile(request,env,url);
  if(url.pathname==="/content-intelligence/profile/recompute")return handleProfileRecompute(request,env);
  if(url.pathname==="/content-intelligence/scores/recompute")return handleScoresRecompute(request,env);
  if(url.pathname==="/content-intelligence/scores/top")return handleTopScores(request,env,url);
  if(url.pathname==="/content-intelligence/synthesis")return handleSynthesis(request,env,url);
  return null;
}
