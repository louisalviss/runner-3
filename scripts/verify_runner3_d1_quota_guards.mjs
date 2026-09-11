import fs from "node:fs";

const read = (path) => fs.readFileSync(path, "utf8");
const personalization = read("cloudflare/runner3-core/src/content-personalization.js");
const intelligence = read("cloudflare/runner3-core/src/content-intelligence.js");
const enrichment = read("cloudflare/runner3-core/src/content-feature-enrichment.js");
const audio = read("cloudflare/runner3-core/audio-entry.js");
const wrangler = JSON.parse(read("cloudflare/runner3-core/wrangler.jsonc"));

const fail = (message) => { throw new Error(`D1_QUOTA_GUARD_FAILED: ${message}`); };
const requireText = (text, needle, message) => { if (!text.includes(needle)) fail(message); };
const forbidText = (text, needle, message) => { if (text.includes(needle)) fail(message); };

requireText(personalization, "RECOMPUTE_DEBOUNCE_MS = 4 * 60 * 60 * 1000", "4h debounce missing");
requireText(personalization, "priorityExplicit", "bounded explicit-feedback priority recompute missing");
requireText(personalization, "familyDiminishingWeight", "family diminishing-return scoring missing");
requireText(personalization, "interestFamilySql", "family-aware materialized scoring missing");
requireText(personalization, "status='recomputing'", "recompute lease state missing");
requireText(personalization, "run_id=?", "lease token missing");
requireText(personalization, "status='recomputing' AND run_id=?", "CAS lease completion missing");
forbidText(personalization, "force = false", "force option reintroduced");
forbidText(personalization, 'prepare("DELETE FROM interest_profile")', "full profile delete reintroduced");
forbidText(personalization, 'prepare("DELETE FROM content_scores WHERE score_type=\'personal_relevance\'")', "full score delete reintroduced");

requireText(intelligence, "handleGuardedRecompute", "direct recompute guard missing");
requireText(intelligence, "explicit_feedback_batch", "explicit feedback batch result marker missing");
requireText(intelligence, "priorityExplicit:true", "explicit feedback must trigger one priority recompute");
forbidText(intelligence, "recomputeInterestProfile,", "raw profile recompute import reintroduced");
forbidText(intelligence, "recomputePersonalScores,", "raw score recompute import reintroduced");
requireText(intelligence, "heartbeat_changes", "heartbeat/material-change separation missing");

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
