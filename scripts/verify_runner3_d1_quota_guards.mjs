import fs from "node:fs";

const read = (path) => fs.readFileSync(path, "utf8");
const personalization = read("cloudflare/runner3-core/src/content-personalization.js");
const intelligence = read("cloudflare/runner3-core/src/content-intelligence.js");
const eventMigration = read("cloudflare/runner3-core/migrations/0017_user_content_event_idempotency.sql");
const readerLearning = read("cloudflare/runner3-core/src/rss-reader-learning.js");
const librarySave = read("cloudflare/runner3-core/src/rss-library-save.js");
const enrichment = read("cloudflare/runner3-core/src/content-feature-enrichment.js");
const client = read("scripts/content_intelligence_client.py");
const audio = read("cloudflare/runner3-core/audio-entry.js");
const wrangler = JSON.parse(read("cloudflare/runner3-core/wrangler.jsonc"));

const fail = (message) => { throw new Error(`D1_QUOTA_GUARD_FAILED: ${message}`); };
const requireText = (text, needle, message) => { if (!text.includes(needle)) fail(message); };
const forbidText = (text, needle, message) => { if (text.includes(needle)) fail(message); };

requireText(personalization, "RECOMPUTE_DEBOUNCE_MS = 4 * 60 * 60 * 1000", "4h debounce missing");
requireText(personalization, "RECOMMENDATION_ID_CHUNK = 50", "recommendation D1-safe chunk size missing");
requireText(personalization, "for(const batch of idChunks(ids))", "recommendation shown IDs are not chunked");
requireText(personalization, "priorityExplicit", "bounded explicit-feedback priority recompute missing");
requireText(personalization, "familyDiminishingWeight", "family diminishing-return scoring missing");
requireText(personalization, "interestFamilySql", "family-aware materialized scoring missing");
requireText(personalization, "materialization_identity_mismatch", "model/policy/ontology materialization identity guard missing");
requireText(personalization, "json_extract(reason_json,'$.profile_policy')", "profile policy materialization proof check missing");
requireText(personalization, "json_extract(reason_json,'$.ontology_version')", "ontology materialization proof check missing");
requireText(personalization, "const materializationMismatch = !materialized?.ok", "dirty-state materialization mismatch detection missing");
requireText(personalization, "priorityExplicit || materializationMismatch", "materialization repair must bypass debounce");
requireText(personalization, "status='recomputing'", "recompute lease state missing");
requireText(personalization, "run_id=?", "lease token missing");
requireText(personalization, "status='recomputing' AND run_id=?", "CAS lease completion missing");
forbidText(personalization, "force = false", "force option reintroduced");
forbidText(personalization, 'prepare("DELETE FROM interest_profile")', "full profile delete reintroduced");
forbidText(personalization, 'prepare("DELETE FROM content_scores WHERE score_type=\'personal_relevance\'")', "full score delete reintroduced");

requireText(intelligence, "handleGuardedRecompute", "direct recompute guard missing");
requireText(intelligence, "explicit_feedback_batch", "explicit feedback batch result marker missing");
requireText(intelligence, "priorityExplicit:true", "explicit feedback must trigger one priority recompute");
requireText(intelligence, "PERSONAL_MODEL_VERSION_MISMATCH", "non-canonical recompute model rejection missing");
forbidText(intelligence, "recomputeInterestProfile,", "raw profile recompute import reintroduced");
forbidText(intelligence, "recomputePersonalScores,", "raw score recompute import reintroduced");
requireText(intelligence, "heartbeat_changes", "heartbeat/material-change separation missing");
requireText(intelligence, "PREFERENCE_SIGNAL_ID_CHUNK = 50", "D1-safe preference-signal chunk missing");
requireText(intelligence, "ids.slice(i,i+PREFERENCE_SIGNAL_ID_CHUNK)", "preference-signal IDs are not chunked");
requireText(client, "def batches(rows: list[dict[str, Any]], n: int = 50)", "content intelligence client batch exceeds D1-safe size");
requireText(readerLearning, "datetime(content_items.last_seen_at) <= datetime('now','-6 hours')", "reader item heartbeat guard missing");
requireText(readerLearning, "if (currentEvent === targetEvent) return 0", "reader preference no-op guard missing");
requireText(readerLearning, "if (Boolean(current?.present) === targetFeatured) return 0", "reader featured no-op guard missing");
requireText(librarySave, "datetime(content_items.last_seen_at) <= datetime('now','-6 hours')", "library-save item heartbeat guard missing");
requireText(intelligence, "INSERT OR IGNORE INTO user_content_events", "core event insert is not race-safe");
requireText(eventMigration, "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_content_events_identity", "event identity unique index missing");

forbidText(enrichment, "await env.DB.prepare(`DELETE FROM content_features WHERE item_id=? AND model_version IN", "delete-all semantic rewrite reintroduced");
forbidText(audio, "force: true", "scheduled force bypass reintroduced");
requireText(audio, 'HOURLY_PERSONALIZATION_CRON = "17 * * * *"', "single hourly cron routing missing");
requireText(audio, "controller?.scheduledTime", "scheduled-time daily gate missing");
requireText(audio, "getUTCHours() === 3", "03 UTC daily gate missing");
requireText(audio, "getUTCMinutes() === 17", "minute-17 daily gate missing");
requireText(audio, "if (!dailyWindow)", "hourly legacy fan-out guard missing");

const crons = wrangler?.triggers?.crons || [];
if (crons.length !== 1 || crons[0] !== "17 * * * *") {
  fail(`runner3-core must consume exactly one cron slot; got ${JSON.stringify(crons)}`);
}
console.log("D1_QUOTA_GUARDS_PASS");
