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
const scoreUpsert = statements.find((x) => x.kind === 'run' && x.sql.includes('INSERT INTO content_scores'));
if (!scoreUpsert) throw new Error('personal score upsert SQL not captured');
const hardBudget = 60000;
if (scoreUpsert.sql.length > hardBudget) {
  throw new Error("personal score SQL too large: " + scoreUpsert.sql.length + " > " + hardBudget);
}
if (!scoreUpsert.sql.includes('normalized_features AS') || !scoreUpsert.sql.includes('nf.family_id')) {
  throw new Error('family_id must be materialized once and reused downstream');
}
console.log(JSON.stringify({ ok: true, model_version: PERSONAL_MODEL_VERSION, score_sql_bytes: scoreUpsert.sql.length, hard_budget: hardBudget }));
