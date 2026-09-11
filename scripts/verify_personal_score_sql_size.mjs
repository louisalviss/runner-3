import {
  PERSONAL_MODEL_VERSION,
  PERSONAL_POLICY_VERSION,
  PERSONAL_SCORE_READ_PAGE,
  PERSONAL_SCORE_WRITE_BATCH,
  recomputePersonalScores,
} from '../cloudflare/runner3-core/src/content-personalization.js';
import { INTEREST_ONTOLOGY_VERSION } from '../cloudflare/runner3-core/src/content-interest-ontology.js';

const preparedSql = [];
const batchSizes = [];
const written = new Map();
const profileRows = [
  { feature_type:'family',feature_key:'ai-economics',weight:2,confidence:1 },
  { feature_type:'topic',feature_key:'ai-economics',weight:1,confidence:1 },
];
const featureRows = [
  { item_id:'i1',feature_type:'topic',feature_key:'ai_economics',weight:1,confidence:1,published_at:new Date().toISOString() },
  { item_id:'i1',feature_type:'concept',feature_key:'ai-capex',weight:1,confidence:1,published_at:new Date().toISOString() },
  { item_id:'i2',feature_type:'topic',feature_key:'rare-earths',weight:1,confidence:1,published_at:new Date().toISOString() },
  { item_id:'i3',feature_type:'topic',feature_key:'ai-economics',weight:1,confidence:1,published_at:new Date().toISOString() },
];

function statement(sql) {
  preparedSql.push(sql);
  const q = {
    sql,
    args:[],
    bind(...args) { q.args=args; return q; },
    async run() { return { meta:{ changes:0 } }; },
    async all() {
      if (sql.includes('FROM interest_profile')) return { results:profileRows };
      if (sql.includes('FROM content_features')) {
        const offset=Number(q.args[1] || 0);
        return { results:offset === 0 ? featureRows : [] };
      }
      if (sql.includes("SELECT item_id FROM content_scores")) {
        return { results:[...written.keys()].map((item_id)=>({ item_id })) };
      }
      return { results:[] };
    },
    async first() { return null; },
  };
  return q;
}

const DB = {
  prepare:statement,
  async batch(statements) {
    batchSizes.push(statements.length);
    return statements.map((s) => {
      if (s.sql.includes('INSERT INTO content_scores')) written.set(String(s.args[0]),s.args);
      if (s.sql.includes('DELETE FROM content_scores')) written.delete(String(s.args[0]));
      return { meta:{ changes:1 } };
    });
  },
};

const result = await recomputePersonalScores({ DB }, PERSONAL_MODEL_VERSION);
if (!result.ok || result.scored_items !== 3) throw new Error(`unexpected scorer result: ${JSON.stringify(result)}`);
if (result.read_features !== featureRows.length) throw new Error(`read feature count mismatch: ${result.read_features}`);
if (PERSONAL_SCORE_READ_PAGE > 1000) throw new Error('read page exceeds bounded budget');
if (PERSONAL_SCORE_WRITE_BATCH > 50) throw new Error('write batch exceeds bounded budget');
if (batchSizes.some((n)=>n > PERSONAL_SCORE_WRITE_BATCH)) throw new Error(`oversized D1 batch: ${batchSizes}`);
if (written.size !== 3) throw new Error(`expected 3 score rows, got ${written.size}`);
const i1 = written.get('i1');
const reason = JSON.parse(i1[3]);
if (reason.profile_policy !== PERSONAL_POLICY_VERSION) throw new Error('profile policy proof missing');
if (reason.ontology_version !== INTEREST_ONTOLOGY_VERSION) throw new Error('ontology proof missing');
if (reason.matched_families !== 1) throw new Error(`family rollup mismatch: ${reason.matched_families}`);
if (!(reason.relevance_signal > 3 && reason.relevance_signal < 3.1)) {
  throw new Error(`family diminishing return mismatch: ${reason.relevance_signal}`);
}
const maxSql = Math.max(...preparedSql.map((sql)=>sql.length));
if (maxSql > 5000) throw new Error(`unexpected large SQL statement remains: ${maxSql}`);
console.log(JSON.stringify({
  ok:true,
  model_version:PERSONAL_MODEL_VERSION,
  scored_items:result.scored_items,
  read_features:result.read_features,
  max_sql_bytes:maxSql,
  max_batch:Math.max(...batchSizes),
  family_signal:reason.relevance_signal,
}));
