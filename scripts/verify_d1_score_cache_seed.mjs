import fs from "node:fs";
import {
  hasCommittedScoreCacheProof, maybeRecomputePersonal, refreshPersonalScoresDaily,
  PERSONAL_MODEL_VERSION, PERSONAL_POLICY_VERSION,
  CONTENT_INTELLIGENCE_CONTRACT_VERSION,
} from "../cloudflare/runner3-core/src/content-personalization.js";
import { DAILY_SCORE_CACHE_VERSION } from "../cloudflare/runner3-core/src/personal-score-daily-cache.js";
import { INTEREST_ONTOLOGY_VERSION } from "../cloudflare/runner3-core/src/content-interest-ontology.js";

const receipt = {
  model:PERSONAL_MODEL_VERSION,policy_version:PERSONAL_POLICY_VERSION,
  contract_version:CONTENT_INTELLIGENCE_CONTRACT_VERSION,ontology_version:INTEREST_ONTOLOGY_VERSION,
  recomputed_at:"2026-11-03T03:17:00.000Z",
};
const state = detail => ({status:"clean",detail:JSON.stringify(detail)});
const assert=(v,msg)=>{if(!v)throw new Error(msg);};
assert(hasCommittedScoreCacheProof(state({...receipt,score_cache_version:DAILY_SCORE_CACHE_VERSION})),"proof missing");
assert(!hasCommittedScoreCacheProof(state(receipt)),"legacy proof must not pass");
assert(!hasCommittedScoreCacheProof({...state({...receipt,score_cache_version:DAILY_SCORE_CACHE_VERSION}),status:"dirty"}),"dirty proof must fail");

function fakeDb(detail=receipt,{lease=true,features=1,items=1}={}) {
  let leased=false,restored=null;
  const queries=[];
  return {
    queries,get restored(){return restored;},
    DB:{
      prepare(sql){
        queries.push(sql);
        const stmt={args:[],bind(...a){stmt.args=a;return stmt;},
          async first(){
            if(sql.includes("FROM workflow_state"))return state(detail);
            if(sql.includes("FROM content_scores"))return {ok:1};
            if(sql.includes("COUNT(*) AS n FROM (SELECT 1 FROM content_features"))return {n:features};
            if(sql.includes("COUNT(*) AS n FROM (SELECT 1 FROM content_items"))return {n:items};
            throw new Error("unexpected read "+sql);
          },
          async run(){
            if(sql.includes("SET status='recomputing'")) {
              if(!lease||leased)return {meta:{changes:0}};
              leased=true;return {meta:{changes:1}};
            }
            if(sql.includes("SET status='clean'")) {
              assert(leased,"restore without lease");
              assert(sql.includes("status='recomputing' AND run_id=?"),"restore must be CAS");
              restored=JSON.parse(stmt.args[0]);return {meta:{changes:1}};
            }
            throw new Error("unexpected write "+sql);
          }};
        return stmt;
      },
    },
  };
}
const untouched=fakeDb();
const ordinary=await maybeRecomputePersonal({DB:untouched.DB});
assert(ordinary.ok && ordinary.status==="clean","normal refresh should not seed");
assert(untouched.queries.length===1,"clean profile should be a single indexed read");
const declined=fakeDb(receipt,{lease:false});
const debounced=await maybeRecomputePersonal({DB:declined.DB},{seedScoreCacheIfMissing:true,quotaPreflightVerified:true});
assert(debounced.status==="score_cache_seed_debounced","6h/racing lease guard");
assert(!declined.queries.some(q=>q.includes("COUNT(*) AS n")),"lease denied but full scan attempted");
for(const [features,items,label] of [[50001,1,"features"],[1,15001,"items"]]){
  const db=fakeDb(receipt,{features,items});
  let thrown=false;
  try {await maybeRecomputePersonal({DB:db.DB},{seedScoreCacheIfMissing:true,quotaPreflightVerified:true});}
  catch(err){thrown=String(err.message).includes("SCORE_CACHE_SEED_");}
  assert(thrown,"seed cap did not fail closed: "+label);
  assert(db.restored?.score_cache_seed_failed_at,"failed seed did not restore clean: "+label);
  assert(!db.queries.some(q=>q.includes("JOIN content_items i ON i.item_id=f.item_id")),"full feature score scan before cap");
}
const failed=fakeDb({...receipt,score_cache_seed_failed_at:"2026-11-03T00:00:00Z"});
const failedResult=await maybeRecomputePersonal({DB:failed.DB},{seedScoreCacheIfMissing:true,quotaPreflightVerified:true});
assert(failedResult.status==="score_cache_seed_failed_requires_review","failed seed auto-retried");
assert(failed.queries.length===1,"failed seed caused extra queries");
// An incomplete seed leaves the profile clean but may leave partial score rows.
// The daily Worker must never scan or serve that uncommitted cache.
for (const detail of [receipt,
  {...receipt,score_cache_seed_failed_at:"2026-11-03T00:00:00Z"}]) {
  const db=fakeDb(detail);
  const result=await refreshPersonalScoresDaily({DB:db.DB});
  assert(result.ok===false && result.status==="daily_score_cache_seed_required",
    "daily Worker accepted uncommitted score-cache rows");
  assert(db.queries.length===1 && !db.queries.some(q=>q.includes("FROM content_scores")),
    "uncommitted score cache triggered an unnecessary D1 read");
}
// The optimized path must still operate for successfully committed cache rows.
let cacheRead=false;
const valid={...receipt,score_cache_version:DAILY_SCORE_CACHE_VERSION};
const committedDB={
  prepare(sql){
    if(sql.includes("FROM workflow_state"))return {
      bind(){return this;},async first(){return state(valid);},
    };
    if(sql.includes("FROM content_scores s LEFT JOIN content_items")){
      cacheRead=true;
      return {bind(){return this;},async all(){return {results:[]};}};
    }
    throw new Error("unexpected committed-cache SQL: "+sql);
  },
};
await refreshPersonalScoresDaily({DB:committedDB});
assert(cacheRead,"committed cache no longer enters daily freshness read path");
const job=fs.readFileSync(".github/workflows/content-intelligence-v4-guarded-materialize.yml","utf8");
assert(job.indexOf("d1_account_quota_preflight.py")>0 && job.indexOf("--seed-score-cache-if-missing")>job.indexOf("d1_account_quota_preflight.py"),"seed bypasses quota preflight");
assert(job.includes("id-token: write") && job.includes("--preflight-receipt-file"),"signed preflight workflow wiring missing");
assert(job.includes("D1_READ_SAFE_CEILING: '4000000'") && job.includes("D1_SAFE_CEILING: '70000'"),"preflight ceilings changed");
const audio=fs.readFileSync("cloudflare/runner3-core/audio-entry.js","utf8");
assert(!audio.includes("seedScoreCacheIfMissing:true"),"daily worker may seed");
console.log("D1_SCORE_CACHE_SEED_GUARD_PASS");
