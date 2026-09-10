import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(repoRoot, "cloudflare/runner3-core/src/content-personalization.js");
const text = fs.readFileSync(sourcePath, "utf8");

function requireText(needle, message) { if (!text.includes(needle)) throw new Error(message); }
function forbidText(needle, message) { if (text.includes(needle)) throw new Error(message); }

requireText("PERSONAL_POLICY_VERSION = \"canonical-interest-ontology-v5\"", "policy marker mismatch");
requireText("feature_type IN (\x27topic\x27,\x27mechanism\x27,\x27concept\x27,\x27source\x27)", "durable profile type allowlist missing");
requireText("evidence_count >= CASE WHEN feature_type=\x27source\x27 THEN 5 ELSE 2 END", "repeated-evidence gate missing");
forbidText("feature_type=\x27entity\x27 THEN 40", "entity profile promotion reintroduced");
forbidText("OR has_explicit_feedback=1", "item feedback singleton bypass reintroduced");

console.log(JSON.stringify({ok:true,policy_version:"canonical-interest-ontology-v5",item_derived_profile_min_independent_items:2,source_min_independent_items:5,entity_profile_promotion:false}));
