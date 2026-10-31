import {
  hasCommittedProfileMaterializationProof,
  maybeRecomputePersonal,
  PERSONAL_MODEL_VERSION,
  PERSONAL_POLICY_VERSION,
  CONTENT_INTELLIGENCE_CONTRACT_VERSION,
} from '../cloudflare/runner3-core/src/content-personalization.js';
import { INTEREST_ONTOLOGY_VERSION } from '../cloudflare/runner3-core/src/content-interest-ontology.js';

const completed = {
  status: 'clean',
  detail: JSON.stringify({
    model: PERSONAL_MODEL_VERSION,
    contract_version: CONTENT_INTELLIGENCE_CONTRACT_VERSION,
    policy_version: PERSONAL_POLICY_VERSION,
    ontology_version: INTEREST_ONTOLOGY_VERSION,
    recomputed_at: '2026-10-30T03:17:00.000Z',
  }),
};
const cases = [
  [completed, true],
  [{ ...completed, status: 'dirty' }, false],
  [{ ...completed, detail: '{broken' }, false],
  [{ ...completed, detail: JSON.stringify({ ...JSON.parse(completed.detail), model: 'other' }) }, false],
  [{ ...completed, detail: JSON.stringify({ ...JSON.parse(completed.detail), policy_version: 'other' }) }, false],
  [{ ...completed, detail: JSON.stringify({ ...JSON.parse(completed.detail), ontology_version: 'other' }) }, false],
  [{ ...completed, detail: JSON.stringify({ ...JSON.parse(completed.detail), contract_version: 'other' }) }, false],
  [{ ...completed, detail: JSON.stringify({ ...JSON.parse(completed.detail), recomputed_at: undefined }) }, false],
  [{ ...completed, detail: JSON.stringify({ ...JSON.parse(completed.detail), recomputed_at: 'not-a-date' }) }, false],
  [null, false],
];
for (const [state, expected] of cases) {
  if (hasCommittedProfileMaterializationProof(state) !== expected) {
    throw new Error('completion-proof validation mismatch');
  }
}

function database(state, existingScore) {
  const queries = [];
  let dirtyWrites = 0;
  const DB = {
    prepare(sql) {
      queries.push(sql);
      const stmt = {
        bind(...args) { stmt.args = args; return stmt; },
        async first() {
          if (sql.includes('FROM workflow_state')) return state;
          if (sql.includes('FROM content_scores')) return existingScore ? {ok: 1} : null;
          return null;
        },
        async run() { dirtyWrites++; return { meta: { changes: 0 } }; },
      };
      return stmt;
    },
  };
  return { DB, queries, getDirtyWrites: () => dirtyWrites };
}

const clean = database(completed, true);
const cleanResult = await maybeRecomputePersonal({DB: clean.DB});
if (!cleanResult.ok || cleanResult.recomputed || cleanResult.status !== 'clean') throw new Error('clean result mismatch');
if (clean.queries.length !== 1 || clean.queries.some(q => q.includes('FROM content_scores')) || clean.getDirtyWrites()) {
  throw new Error('clean proof should make exactly one indexed D1 read and no writes');
}

const legacy = database({status: 'clean',detail: JSON.stringify({model: PERSONAL_MODEL_VERSION})}, true);
const legacyResult = await maybeRecomputePersonal({DB: legacy.DB});
if (!legacyResult.ok || legacyResult.status !== 'clean' || legacy.queries.filter(q => q.includes('FROM content_scores')).length !== 1) {
  throw new Error('legacy state must use the verification fallback');
}

const invalid = database({...completed, detail: '{broken'}, true);
const invalidResult = await maybeRecomputePersonal({DB: invalid.DB});
if (!invalidResult.ok || invalidResult.status !== 'clean' || invalid.queries.filter(q => q.includes('FROM content_scores')).length !== 1) {
  throw new Error('malformed state must use the verification fallback');
}

console.log('D1_CLEAN_PROFILE_PROOF_FASTPATH_PASS', JSON.stringify({
  cleanReads: clean.queries.length,
  cleanWrites: clean.getDirtyWrites(),
  legacyReads: legacy.queries.length,
  invalidReads: invalid.queries.length,
  cases: cases.length,
}));
