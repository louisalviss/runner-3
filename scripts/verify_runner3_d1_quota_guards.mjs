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
requireText(personalization, "status='recomputing'", "recompute lease state missing");
requireText(personalization, "run_id=?", "lease token missing");
requireText(personalization, "status='recomputing' AND run_id=?", "CAS lease completion missing");
forbidText(personalization, "force = false", "force option reintroduced");
forbidText(personalization, 'prepare("DELETE FROM interest_profile")', "full profile delete reintroduced");
forbidText(personalization, 'prepare("DELETE FROM content_scores WHERE score_type=\'personal_relevance\'")', "full score delete reintroduced");

requireText(intelligence, "handleGuardedRecompute", "direct recompute guard missing");
forbidText(intelligence, "recomputeInterestProfile,", "raw profile recompute import reintroduced");
forbidText(intelligence, "recomputePersonalScores,", "raw score recompute import reintroduced");
requireText(intelligence, "heartbeat_changes", "heartbeat/material-change separation missing");

forbidText(enrichment, "await env.DB.prepare(`DELETE FROM content_features WHERE item_id=? AND model_version IN", "delete-all semantic rewrite reintroduced");
forbidText(audio, "force: true", "scheduled force bypass reintroduced");
requireText(audio, 'PERSONALIZATION_CRON = "47 * * * *"', "personalization-only cron routing missing");

const crons = wrangler?.triggers?.crons || [];
if (!crons.includes("17 3 * * *")) fail("daily legacy cron missing");
if (!crons.includes("47 * * * *")) fail("hourly personalization cron missing");
console.log("D1_QUOTA_GUARDS_PASS");
