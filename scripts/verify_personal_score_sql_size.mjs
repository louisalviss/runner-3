import { PERSONAL_MODEL_VERSION, recomputePersonalScores } from '../cloudflare/runner3-core/src/content-personalization.js';

const statements = [];
const DB = {
  prepare(sql) {
    let args = [];
    const q = {
      bind(...next) { args = next; return q; },
      async run() { statements.push({ sql, args, kind: 'run' }); return { meta: { changes: 0 } }; },
      async first() {
        statements.push({ sql, args, kind: 'first' });
        return { n: 0, min_score: 0, max_score: 0, avg_score: 0, score_99_plus: 0, score_95_plus: 0 };
      },
    };
    return q;
  },
};

await recomputePersonalScores({ DB }, PERSONAL_MODEL_VERSION);
const stageUpsert = statements.find((x) => x.kind === 'run' && x.sql.includes('INSERT INTO personal_score_stage'));
const scoreUpsert = statements.find((x) => x.kind === 'run' && x.sql.includes('INSERT INTO content_scores'));
if (!stageUpsert) throw new Error('personal score stage SQL not captured');
if (!scoreUpsert) throw new Error('personal score final SQL not captured');
const hardBudget = 60000;
for (const [name, stmt] of [['stage', stageUpsert], ['final', scoreUpsert]]) {
  if (stmt.sql.length > hardBudget) {
    throw new Error(`${name} personal score SQL too large: ${stmt.sql.length} > ${hardBudget}`);
  }
}
if (!stageUpsert.sql.includes('normalized_features AS') || !stageUpsert.sql.includes('nf.family_id')) {
  throw new Error('family_id must be materialized once and reused in stage SQL');
}
if (!scoreUpsert.sql.includes('FROM personal_score_stage') || scoreUpsert.sql.includes('normalized_features AS')) {
  throw new Error('final scoring SQL must rank only staged components');
}
console.log(JSON.stringify({
  ok: true,
  model_version: PERSONAL_MODEL_VERSION,
  stage_sql_bytes: stageUpsert.sql.length,
  final_sql_bytes: scoreUpsert.sql.length,
  hard_budget: hardBudget,
}));
