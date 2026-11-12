import assert from "node:assert/strict";
import { handleContentIntelligence } from "../cloudflare/runner3-core/src/content-intelligence.js";

function fixture(events) {
  const queries = [];
  const snapshots = new Map();
  const maxId = events.reduce((n, row) => n+Number(row.count||0), 0);
  const db = {
    prepare(sql) {
      queries.push(sql);
      return {
        bind(...args) { this.arguments_ = args; return this; },
        async first() {
          if (sql.includes("SELECT detail FROM workflow_state WHERE source=?")) {
            const detail=snapshots.get(this.arguments_[0]); return detail ? {detail} : null;
          }
          if (sql.includes("SELECT COALESCE(MAX(rowid),0) AS max_rowid")) return {max_rowid:6};
          if (sql.includes("SELECT COUNT(*) AS n FROM content_items")) return {n:6};
          if (sql.includes("SELECT COALESCE(MAX(id),0) AS max_id FROM user_content_events")) return {max_id:maxId};
          if (sql.includes("SELECT (SELECT COUNT(*) FROM interest_profile) AS profile_features")) {
            assert(!sql.includes("FROM content_items"), "item count must use rowid checkpoint");
            assert(!sql.includes("FROM user_content_events"), "redundant event full scan");
            assert(!sql.includes("FROM content_scores"), "redundant score full scan");
            return { profile_features: 2, family_features: 1 };
          }
          if (sql.includes("MIN(score) AS min_score")) {
            return { count: 4, min_score: 1, max_score: 90, avg_score: 45, score_95_plus: 0, score_99_plus: 0 };
          }
          throw new Error("Unexpected first query: " + sql.slice(0, 90));
        },
        async run() {
          if (sql.includes("INSERT INTO workflow_state(source,status,detail,updated_at)")) {
            snapshots.set(this.arguments_[0],this.arguments_[1]); return {meta:{changes:1}};
          }
          throw new Error("Unexpected run query: " + sql.slice(0, 90));
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
  assert.equal(queries.length, 16);
  assert(queries.some(q => q.includes("MAX(id),0")), "D1 append-only event watermark required");
  assert(queries.some(q => q.includes("MAX(rowid),0")), "D1 content count highwater required");
  assert(queries.some(q => q.includes("WHERE rowid>?"))===false, "first count uses full snapshot");
  assert(queries.some(q => q.includes("INSERT INTO workflow_state")), "snapshot persisted");

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
assert.deepEqual(a.event_types,[{event_type:"shown",count:3},{event_type:"liked",count:2}]);
const b = await run([]);
assert.equal(b.counts.events, 0);
assert.equal(b.counts.last_event_at, null);
assert.deepEqual(b.event_types, []);
console.log("CONTENT_SYNTHESIS_SINGLEPASS_PASS (2 fixtures, 16 SQL operations each, indexed highwater cache)");
