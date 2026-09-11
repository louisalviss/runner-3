import {
  PERSONAL_MODEL_VERSION,
  PERSONAL_POLICY_VERSION,
  eventAffectsProfile,
  dirtyReasonAllowsPriorityMaterialization,
  maybeRecomputePersonal,
} from '../cloudflare/runner3-core/src/content-personalization.js';
import { INTEREST_ONTOLOGY_VERSION } from '../cloudflare/runner3-core/src/content-interest-ontology.js';

if (eventAffectsProfile('shown')) throw new Error('shown must remain zero-weight and non-invalidating');
if (!dirtyReasonAllowsPriorityMaterialization('content_items_or_features_changed') || !dirtyReasonAllowsPriorityMaterialization('content_features_changed')) throw new Error('semantic dirty reasons must get guarded priority repair');
if (dirtyReasonAllowsPriorityMaterialization('event_batch')) throw new Error('generic event dirty must not bypass debounce');
for (const t of ['selected','deep_read','follow_up','saved','interest_saved','liked','disliked']) {
  if (!eventAffectsProfile(t)) throw new Error(`${t} must affect the profile`);
}

let cleanWrites = 0;
let expensiveQueries = 0;
const DB = {
  prepare(sql) {
    let args=[];
    const q={
      bind(...next){args=next;return q;},
      async first(){
        if (sql.includes('SELECT status,run_id,detail,updated_at FROM workflow_state')) {
          return {status:'dirty',run_id:null,detail:JSON.stringify({reason:'event_batch'}),updated_at:'2026-09-11 16:45:32'};
        }
        if (sql.includes("FROM content_scores WHERE score_type='personal_relevance'")) {
          return {ok:1};
        }
        if (sql.includes('SELECT COUNT(*) AS n FROM user_content_events')) {
          if (!sql.includes("event_type IN")) throw new Error('meaningful-event query missing event filter');
          return {n:0};
        }
        expensiveQueries += 1;
        throw new Error(`unexpected first SQL: ${sql.slice(0,120)}`);
      },
      async run(){
        if (sql.includes("SET status='clean',run_id=NULL,detail=?")) {
          cleanWrites += 1;
          const detail=JSON.parse(String(args[0]||'{}'));
          if (detail.reason !== 'zero_weight_event_dirty_repaired') throw new Error('repair proof reason missing');
          if (detail.model !== PERSONAL_MODEL_VERSION) throw new Error('repair model proof mismatch');
          if (detail.policy_version !== PERSONAL_POLICY_VERSION) throw new Error('repair policy proof mismatch');
          if (detail.ontology_version !== INTEREST_ONTOLOGY_VERSION) throw new Error('repair ontology proof mismatch');
          return {meta:{changes:1}};
        }
        expensiveQueries += 1;
        throw new Error(`unexpected run SQL: ${sql.slice(0,120)}`);
      },
    };
    return q;
  },
};

const result=await maybeRecomputePersonal({DB},{modelVersion:PERSONAL_MODEL_VERSION});
if (!result.ok || result.status !== 'clean' || result.recomputed !== false || result.zero_weight_dirty_repaired !== true) {
  throw new Error(`zero-weight repair failed: ${JSON.stringify(result)}`);
}
if (cleanWrites !== 1 || expensiveQueries !== 0) throw new Error(`repair was not bounded: clean=${cleanWrites} expensive=${expensiveQueries}`);
console.log(JSON.stringify({ok:true,shown_affects_profile:false,repair_status:result.status,zero_weight_dirty_repaired:true}));
