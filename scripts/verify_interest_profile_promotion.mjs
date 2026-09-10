import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(repoRoot, 'cloudflare/runner3-core/src/content-personalization.js');
const text = fs.readFileSync(sourcePath, 'utf8');

function requireText(needle, message) {
  if (!text.includes(needle)) throw new Error(message);
}
function forbidText(needle, message) {
  if (text.includes(needle)) throw new Error(message);
}

requireText('PERSONAL_POLICY_VERSION = "shared-feature-promotion-v4"', 'policy marker mismatch');
requireText('WHERE evidence_count>=2', 'repeated-evidence promotion gate missing');
requireText("feature_type NOT IN ('keyword','domain','language')", 'noisy auto feature filter missing');
requireText("NOT (feature_type='source' AND evidence_count<3)", 'source repetition gate missing');
forbidText("OR feature_type IN ('topic','mechanism')", 'singleton topic/mechanism bypass reintroduced');
forbidText("OR (feature_type='concept' AND avg_feature_confidence>=0.80)", 'singleton concept bypass reintroduced');
forbidText('OR has_explicit_feature=1', 'feature-source singleton bypass reintroduced');
forbidText('OR has_explicit_feedback=1', 'item feedback singleton bypass reintroduced');

console.log(JSON.stringify({
  ok: true,
  policy_version: 'shared-feature-promotion-v4',
  item_derived_profile_min_independent_items: 2,
  item_feedback_changes_signal_not_promotion_gate: true,
}));
