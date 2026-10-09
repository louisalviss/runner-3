import assert from "node:assert/strict";
import { handleContentIntelligence } from "../cloudflare/runner3-core/src/content-intelligence.js";

function fixture(events) {
  const queries = [];
  const db = {
    prepare(sql) {
      queries.push(sql);
      return {
        bind() { return this; },
        async first() {
          if (sql.includes("SELECT (SELECT COUNT(*) FROM content_items) AS items")) {
            assert(!sql.includes("COUNT(*) FROM user_content_events"), "redundant event full scan");
            assert(!sql.includes("FROM content_scores"), "redundant score full scan");
            return { items: 6, profile_features: 2, family_features: 1 };
          }
          if (sql.includes("MIN(score) AS min_score")) {
            return { count: 4, min_score: 1, max_score: 90, avg_score: 45, score_95_plus: 0, score_99_plus: 0 };
          }
          throw new Error("Unexpected first query: " + sql.slice(0, 90));
        },
        async all() {
          if (sql.includes("SELECT event_type,COUNT(*) AS count")) {
            assert(sql.includes("MAX(event_at) AS last_event_at"));
            return { results: events };
          }
          if (sql.includes("FROM interest_profile ORDER BY")) return { results: [] };
          if (sql.includes("FROM content_scores s JOIN content_items i")) return { results: [] };
          if (sql.includes("WHERE e.explicit_feedback IS NOT NULL")) return { results: [] };
          if (sql.includes("WHERE e.event_type<>'shown'")) return { results: [] };
          throw new Error("Unexpected all query: " + sql.slice(0, 90));
        },
      };
    },
  };
  return { db, queries };
}

async function run(events) {
  const { db, queries } = fixture(events);
  const url = new URL("https://core.example/content-intelligence/synthesis");
  const req = new Request(url, { headers: { Authorization: "Bearer integration-test-token" } });
  const resp = await handleContentIntelligence(req, { DB: db, RUNNER3_CORE_TOKEN: "integration-test-token" }, url);
  assert.equal(resp.status, 200);
  const out = await resp.json();
  assert.equal(out.ok, true);
  assert.equal(queries.length, 7);
  assert.equal(out.counts.items, 6);
  assert.equal(out.counts.scored_items, 4);
  assert.equal(out.counts.profile_features, 2);
  assert.equal(out.counts.leaf_features, 2);
  assert.equal(out.counts.family_features, 1);
  assert(!out.event_types.some(x => "last_event_at" in x), "internal timestamp leaked into event_types");
  return out;
}

const a = await run([
  {event_type:"liked",count:2,last_event_at:"2026-10-09 15:00:00"},
  {event_type:"shown",count:3,last_event_at:"2026-10-09 14:00:00"},
]);
assert.equal(a.counts.events, 5);
assert.equal(a.counts.last_event_at, "2026-10-09 15:00:00");
assert.deepEqual(a.event_types,[{event_type:"liked",count:2},{event_type:"shown",count:3}]);
const b = await run([]);
assert.equal(b.counts.events, 0);
assert.equal(b.counts.last_event_at, null);
assert.deepEqual(b.event_types, []);
console.log("CONTENT_SYNTHESIS_SINGLEPASS_PASS (2 fixtures, 7 SQL queries each)");
