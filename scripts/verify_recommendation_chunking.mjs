import assert from 'node:assert/strict';
import { snapshotRecommendationRun, evaluateRecommendationRun } from '../cloudflare/runner3-core/src/content-personalization.js';

const ids = Array.from({length: 103}, (_, i) => `item-${String(i+1).padStart(3,'0')}`);
const shownRows = ids.map((item_id, i) => ({
  item_id,
  id: i + 1,
  context_json: JSON.stringify({number:i+1}),
  title: `Item ${i+1}`,
  canonical_url: `https://example.test/${i+1}`,
  source_name: 'test',
  published_at: '2026-09-16T00:00:00Z',
}));

function mockDb({ evaluation=false }={}) {
  const bindSizes=[];
  return {
    bindSizes,
    prepare(sql) {
      return {
        bind(...args) {
          bindSizes.push({sql:String(sql), n:args.length});
          if (args.length > 60) throw new Error(`too_many_sql_variables_simulated:${args.length}`);
          return {
            async all() {
              const q=String(sql);
              if (q.includes("FROM user_content_events e JOIN content_items i") && q.includes("event_type='shown'")) return {results: shownRows};
              if (q.includes('FROM content_features f LEFT JOIN interest_profile p')) return {results: []};
              if (q.includes('SELECT family_key,weight,evidence_count,confidence FROM interest_family_profile')) return {results: []};
              if (q.includes('SELECT DISTINCT item_id FROM user_content_events')) return {results: ids.map(item_id=>({item_id}))};
              if (q.includes('SELECT item_id,event_type,event_at,id FROM user_content_events WHERE item_id IN')) return {results: []};
              return {results: []};
            },
            async first() {
              const q=String(sql);
              if (q.includes('SELECT metadata_json,created_at FROM recommendation_runs')) return null;
              if (q.includes('SELECT * FROM recommendation_runs WHERE render_id=?')) {
                return evaluation ? {
                  render_id:'snap-1', model_version:'personal-relevance-v3', recommended_count:10,
                  created_at:'2026-09-16T00:00:00Z',
                  metadata_json: JSON.stringify({source_render_id:'render-1',top_k:10,baseline:ids.slice(0,10).map((item_id,i)=>({item_id,rank:i+1})),personalized:ids.slice(0,10).map((item_id,i)=>({item_id,rank:i+1}))}),
                } : null;
              }
              if (q.includes('FROM workflow_state WHERE source=?')) return {status:'clean',run_id:null,detail:'{}',updated_at:'2026-09-16T00:00:00Z'};
              return null;
            },
            async run() { return {meta:{changes:1}}; },
          };
        },
        async all(){ return {results:[]}; },
        async first(){ return null; },
        async run(){ return {meta:{changes:1}}; },
      };
    },
  };
}

const snapDb=mockDb();
const snap=await snapshotRecommendationRun({DB:snapDb},'snap-1',{sourceRenderId:'render-1',topK:10});
assert.equal(snap.ok,true);
assert.equal(snap.item_count,103);
const featureBinds=snapDb.bindSizes.filter(x=>x.sql.includes('FROM content_features f LEFT JOIN interest_profile p')).map(x=>x.n);
assert.deepEqual(featureBinds,[50,50,3]);

const evalDb=mockDb({evaluation:true});
const evaluated=await evaluateRecommendationRun({DB:evalDb},'snap-1');
assert.equal(evaluated.ok,true);
const eventBinds=evalDb.bindSizes.filter(x=>x.sql.includes('SELECT item_id,event_type,event_at,id FROM user_content_events WHERE item_id IN')).map(x=>x.n);
assert.deepEqual(eventBinds,[51,51,4]);
console.log('RECOMMENDATION_CHUNKING_PASS', JSON.stringify({featureBinds,eventBinds}));
