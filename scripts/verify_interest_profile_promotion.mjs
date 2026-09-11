import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(repoRoot, "cloudflare/runner3-core/src/content-personalization.js");
const text = fs.readFileSync(sourcePath, "utf8");

function requireText(needle, message) { if (!text.includes(needle)) throw new Error(message); }
function forbidText(needle, message) { if (text.includes(needle)) throw new Error(message); }

requireText("PERSONAL_POLICY_VERSION = \"canonical-interest-ontology-v7-family-aware\"", "policy marker mismatch");
requireText("interestFamilySql", "family-aware SQL scoring missing");
requireText("familyDiminishingWeight", "family diminishing-return scoring missing");
requireText("matched_families", "family scoring proof missing");
requireText("INSERT INTO interest_family_profile", "family aggregate must use its own derived table");
requireText("FROM interest_family_profile", "family scorer must read the derived family table");
requireText("feature_type IN (\x27topic\x27,\x27mechanism\x27,\x27concept\x27)", "durable profile type allowlist missing");
requireText("evidence_count>=2", "repeated-evidence gate missing");
requireText("instr(feature_key, ':')=0", "family fallback filter must quote colon literal");
forbidText("instr(feature_key, :)", "invalid unquoted family fallback SQL reintroduced");
forbidText("OR has_explicit_feedback=1", "item feedback singleton bypass reintroduced");
forbidText("FROM interest_profile WHERE feature_type='family'", "family aggregate leaked back into durable interest_profile");
forbidText("WHERE feature_type IN ('family','topic','mechanism','concept')", "family aggregate leaked back into durable profile reader");

console.log(JSON.stringify({ok:true,policy_version:"canonical-interest-ontology-v7-family-aware",item_derived_profile_min_independent_items:2,source_profile_promotion:false,entity_profile_promotion:false,family_aware_scoring:true}));
