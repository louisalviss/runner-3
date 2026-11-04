import { DAILY_SCORE_CACHE_VERSION, refreshCachedPersonalScores } from '../cloudflare/runner3-core/src/personal-score-daily-cache.js';
import { refreshPersonalScoresDaily, PERSONAL_MODEL_VERSION } from '../cloudflare/runner3-core/src/content-personalization.js';

const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const settings={
  modelVersion:'personal-v4',contractVersion:'content-intelligence-v4',
  policyVersion:'canonical-interest-ontology-v7-family-aware',
  ontologyVersion:'interest-family-v1',
  freshnessBonus:(date)=>({a:1.5,b:3.5,c:0}[date]),
  clamp,readPage:2,writeBatch:2,maxRows:10,maxWrites:10,
};
const inputs=[
  {item_id:'a',published_at:'a',r:0.8,n:0.17,oldFresh:5,newFresh:1.5},
  {item_id:'b',published_at:'b',r:2.12,n:0.1,oldFresh:5,newFresh:3.5},
  {item_id:'c',published_at:'c',r:-0.5,n:0,oldFresh:0,newFresh:0},
];
const rawBase=(x,f)=>50+(38*x.r/(6+Math.abs(x.r)))+f+x.n;
function ranked(freshKey) {
  const out=inputs.map(x=>({...x,base:rawBase(x,x[freshKey])}));
  const sorted=[...out].sort((a,b)=>a.base-b.base||a.item_id.localeCompare(b.item_id));
  let rank=1;
  sorted.forEach((x,i)=>{
    if(i>0&&x.base!==sorted[i-1].base)rank=i+1;
    x.pct=sorted.length<=1?0:(rank-1)/(sorted.length-1);
    x.score=clamp(.82*x.base+18*x.pct,.5,99.5);
  });
  return out;
}
const old=ranked('oldFresh'), expected=ranked('newFresh');
const fixture=old.map(x=>{
  const reason=JSON.stringify({
    relevance_signal:Number(x.r.toFixed(4)),base_score:Number(x.base.toFixed(3)),
    ranking_cache_version:DAILY_SCORE_CACHE_VERSION,
    relevance_signal_exact:x.r,novelty_bonus_exact:x.n,
    rank_percentile:Number(x.pct.toFixed(4)),freshness_bonus:x.oldFresh,
    novelty_bonus:Number(x.n.toFixed(3)),
    model:settings.modelVersion,contract_version:settings.contractVersion,
    profile_policy:settings.policyVersion,ontology_version:settings.ontologyVersion,
  });
  return {item_id:x.item_id,content_item_id:x.item_id,published_at:x.published_at,score:x.score,reason_json:reason};
});
function fakeDB(original) {
  const data=new Map(original.map(x=>[x.item_id,{...x}]));
  const queries=[];const batches=[];let writes=0;
  const DB={
    prepare(sql) {
      queries.push(sql);
      const st={
        sql,args:[],
        bind(...args){this.args=args;return this;},
        async all(){
          if(!sql.includes('FROM content_scores s LEFT JOIN content_items'))throw Error('feature full scan forbidden');
          const args=st.args;
          const cursor=args.length===3?args[1]:null;
          const size=args.at(-1);
          const rows=[...data.values()].sort((a,b)=>a.item_id.localeCompare(b.item_id))
            .filter(x=>cursor==null||x.item_id>cursor).slice(0,size);
          return {results:rows};
        },
      };
      return st;
    },
    async batch(statements){
      batches.push(statements.length);
      return statements.map(st=>{
        if(!st.sql.includes('UPDATE content_scores'))throw Error('wrong SQL');
        const [score,reason,id,model,prior]=st.args;
        const old=data.get(id);
        if(model!==settings.modelVersion||!old||old.reason_json!==prior)return {meta:{changes:0}};
        data.set(id,{...old,score,reason_json:reason});writes++;
        return {meta:{changes:1}};
      });
    },
  };
  return {DB,data,queries,batches,writes:()=>writes};
}
function withOpts(db,extras={}){return refreshCachedPersonalScores({DB:db.DB},{...settings,...extras});}
const db=fakeDB(fixture);
const actual=await withOpts(db);
if(!actual.ok||!actual.refreshed||actual.status!=='daily_freshness_cached')throw Error('daily cache did not refresh');
if(db.queries.some(x=>x.includes('FROM content_features')||x.includes('FROM interest_profile')))throw Error('unbounded features scan');
if(db.batches.some(x=>x>settings.writeBatch))throw Error('write batching exceeded');
for(const x of expected){
  const actualRow=db.data.get(x.item_id);
  if(Math.abs(actualRow.score-x.score)>1e-10)throw Error('score ranking parity '+x.item_id);
  const reason=JSON.parse(actualRow.reason_json);
  if(reason.base_score!==Number(x.base.toFixed(3))||
     reason.rank_percentile!==Number(x.pct.toFixed(4))||
     reason.freshness_bonus!==x.newFresh)throw Error('reason parity '+x.item_id);
}
const same=await withOpts(db);
if(same.refreshed||same.changed!==0||db.writes()!==actual.changed)throw Error('unchanged freshness must write zero rows');
const legacy=fakeDB(fixture.map((x,i)=>i===0?{...x,reason_json:JSON.stringify({model:'personal-v4'})}:x));
if(await withOpts(legacy)!==null||legacy.writes())throw Error('legacy cache must fall back to full scoring');
const overflow=fakeDB(fixture);
const overflowResult=await withOpts(overflow,{maxRows:2});
if(overflowResult.status!=='daily_score_cache_row_cap'||overflow.writes())throw Error('read cap did not fail closed');
const writeCap=fakeDB(fixture);
const capped=await withOpts(writeCap,{maxWrites:1});
if(capped.status!=='daily_score_write_cap'||writeCap.writes())throw Error('write cap did not fail before mutation');
// Integration: a clean legacy score must not enter the expensive feature-join
// scorer from the unbudgeted 03:17 UTC Worker cron.
const legacyFixture=fakeDB(fixture.map((x,i)=>i===0?{...x,reason_json:JSON.stringify({model:'personal-v4'})}:x));
const legacyWorkerDB={
  prepare(sql){
    if(sql.includes('FROM workflow_state')){
      return {bind(){return this;},async first(){return {status:'clean',detail:'{}'};}};
    }
    return legacyFixture.DB.prepare(sql);
  },
  async batch(stmts){return legacyFixture.DB.batch(stmts);},
};
const workerResult=await refreshPersonalScoresDaily({DB:legacyWorkerDB},{modelVersion:PERSONAL_MODEL_VERSION});
if(workerResult.status!=='daily_score_cache_seed_required'||workerResult.refreshed||
    workerResult.ok!==false||legacyFixture.writes()||
    legacyFixture.queries.some(q=>q.includes('FROM content_features'))) {
  throw Error('legacy cron must fail closed, never rescan content features');
}
console.log('D1_DAILY_SCORE_FRESHNESS_CACHE_PASS',{cases:6,read_queries:db.queries.length,written:db.writes(),max_batch:Math.max(...db.batches)});
