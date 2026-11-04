import fs from "node:fs";
import { maybeRecomputePersonal, PERSONAL_MODEL_VERSION } from "../cloudflare/runner3-core/src/content-personalization.js";
import { handleContentIntelligence } from "../cloudflare/runner3-core/src/content-intelligence.js";
const assert=(x,msg)=>{if(!x)throw Error(msg);};
let cases=0;
for(const status of ["dirty","recomputing","clean"]){
  let reads=0,writes=0;
  const db={
    prepare(sql){
      reads++;
      return {bind(){return this;},async first(){
        if(sql.includes("FROM workflow_state"))return {
          status,run_id:null,detail:status==="dirty"?'{"reason":"content_items_or_features_changed"}':"{}"};
        throw Error("UNGUARDED_QUERY:"+sql);
      },async run(){writes++;throw Error("UNGUARDED_WRITE:"+sql);}};
    },
  };
  for(const opts of [{},{seedScoreCacheIfMissing:true},{priorityExplicit:true}]){
    const prev=reads;
    const result=await maybeRecomputePersonal({DB:db},opts);
    assert(result.recomputed===false,"unguarded materialization occurred");
    assert(reads===prev+1,"unguarded path scanned more than one D1 row");
    assert(writes===0,"unguarded path wrote D1");
    cases++;
  }
}
for(const path of ["/content-intelligence/profile/recompute",
                   "/content-intelligence/scores/recompute"]){
  for(const body of [
    {model_version:PERSONAL_MODEL_VERSION},
    {model_version:PERSONAL_MODEL_VERSION,seed_score_cache_if_missing:true},
    {model_version:PERSONAL_MODEL_VERSION,quotaPreflightVerified:true}]){
    const req=new Request("https://runner3-core.invalid"+path,{
      method:"POST",headers:{Authorization:"Bearer fixture-token",
        "Content-Type":"application/json"},body:JSON.stringify(body)});
    const env={RUNNER3_CORE_TOKEN:"fixture-token",DB:{
      prepare(){throw Error("bearer-only recompute accessed D1");}}};
    const response=await handleContentIntelligence(req,env,new URL(req.url));
    const doc=await response.json();
    assert(response.status===403 && doc.error==="PERSONAL_RECOMPUTE_PREFLIGHT_UNAUTHORIZED",
      "unguarded API recompute allowed "+path);
    cases++;
  }
}
const cron=fs.readFileSync("cloudflare/runner3-core/audio-entry.js","utf8");
assert(!cron.includes("learning.maybeRecomputePersonal("),"cron still invokes full recompute");
assert(cron.includes("if (!dailyWindow) return;"),"hourly cron still touches D1");
const client=fs.readFileSync("scripts/content_intelligence_client.py","utf8");
assert(client.includes("DIRECT_RECOMPUTE_DISABLED_USE_GUARDED_PREFLIGHT"),"legacy double-recompute client enabled");
assert(client.includes('"status":"deferred_to_quota_guard"'),"recommendation snapshot still recomputes");
const personal=fs.readFileSync("cloudflare/runner3-core/src/content-personalization.js","utf8");
assert(personal.includes("await assertScoreCacheSeedBounds(env);"),"dirty recompute unbounded");
console.log("D1_ALL_RECOMPUTE_PATHS_PREFLIGHT_PASS "+cases+" live-no-network cases");
