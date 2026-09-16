import { buildInterestEvidenceSnapshot } from "../cloudflare/runner3-core/src/content-interest-evidence.js";

function cteNames(sql) {
  const names = [];
  const re = /(?:\bWITH|,)\s*([a-z_][a-z0-9_]*)\s+AS\s*\(/gi;
  for (const match of String(sql).matchAll(re)) names.push(match[1].toLowerCase());
  return names;
}

function assertNoDuplicateCtes(sql) {
  const seen = new Set();
  for (const name of cteNames(sql)) {
    if (seen.has(name)) throw new Error(`duplicate CTE name: ${name}`);
    seen.add(name);
  }
}

const queries = [];
const env = {
  DB: {
    prepare(sql) {
      const text = String(sql);
      queries.push(text);
      assertNoDuplicateCtes(text);
      if (text.includes("family_nodes AS") && !text.includes("LEFT JOIN family_evidence_rows e")) {
        throw new Error("family evidence query must join family_evidence_rows");
      }
      return {
        bind() { return this; },
        async all() { return { results: [] }; },
        async first() { return { status: "clean", updated_at: "2026-09-17 00:00:00" }; },
      };
    },
  },
};
const result = await buildInterestEvidenceSnapshot(env, {
  profileLimit: 3,
  familyLimit: 2,
  evidencePerNode: 2,
});

if (result.ok !== true) throw new Error("projection did not return ok");
if (result.derived !== true) throw new Error("projection must remain derived-only");
if (result.source_of_truth !== "cloudflare-d1:user_content_events") throw new Error("authority drift");
if (result.model_version !== "personal-v4") throw new Error("model drift");
if (result.minimum_independent_signaled_items !== 2) throw new Error("promotion gate drift");
if (result.projection_consistent !== true) throw new Error("clean projection expected");
if (queries.length !== 3) throw new Error(`unexpected query count: ${queries.length}`);

console.log(JSON.stringify({
  ok: true,
  schema: result.schema,
  query_count: queries.length,
  duplicate_cte_guard: true,
  derived_only: true,
  source_of_truth: result.source_of_truth,
  model_version: result.model_version,
  minimum_independent_signaled_items: result.minimum_independent_signaled_items,
}));