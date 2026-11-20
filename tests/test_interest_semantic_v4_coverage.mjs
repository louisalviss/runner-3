import test from "node:test";
import assert from "node:assert/strict";
import { extractSemanticFeatures, FEATURE_MODEL_VERSION } from "../cloudflare/runner3-core/src/content-feature-enrichment.js";
import { interestFamily, INTEREST_ONTOLOGY_VERSION } from "../cloudflare/runner3-core/src/content-interest-ontology.js";

const fixtures = [
  ["quantitative-trading", "Backtest of a systematic FX trading strategy using MQL5"],
  ["banking-payments", "IBAN and ACH bank transfer payment rails"],
  ["asset-management", "DCA into S&P 500 and QQQ ETF portfolio"],
  ["game-development", "Open-source pixel art sprite world compiler for game development"],
  ["privacy-tools", "VPN with ECH censorship resistance and browser fingerprinting"],
  ["crypto-custody", "Hardware wallet cold wallet and 24 word seed recovery"],
  ["media-production", "CapCut video editing and short film production"],
  ["behavioral-science", "Parental conflict and psychological harm"],
];

test("explicit recurring subjects generate portable v4 topic keys", () => {
  assert.equal(FEATURE_MODEL_VERSION, "semantic-bridge-v4");
  assert.equal(INTEREST_ONTOLOGY_VERSION, "interest-family-v1");
  for (const [key, title] of fixtures) {
    const features = extractSemanticFeatures({
      title,
      canonical_url: "https://example.org/source",
      source_type: "web",
    });
    assert.ok(features.some(f => f.feature_type === "topic" && f.feature_key === key), key + ": " + title);
    assert.ok(features.every(f => f.model_version === "semantic-bridge-v4"));
  }
});

test("new reusable topics have bounded meaningful parent families", () => {
  const parents = {
    "quantitative-trading": "macro-finance",
    "asset-management": "macro-finance",
    "banking-payments": "macro-finance",
    "game-development": "developer-infrastructure",
    "privacy-tools": "digital-rights-data",
    "crypto-custody": "digital-rights-data",
    "media-production": "creative-production",
    "behavioral-science": "science-explainers",
  };
  for (const [child, family] of Object.entries(parents)) {
    assert.equal(interestFamily("topic", child), family, child + " should map to " + family);
  }
});

test("unverified or entity-only titles do not fabricate durable personal interests", () => {
  for (const title of ["@example on X", "Random Ledger quarterly earnings", "InventedTool 3.0 is launched"]) {
    const features = extractSemanticFeatures({title, canonical_url:"https://example.org"});
    assert.deepEqual(features.filter(f => ["topic", "concept", "mechanism"].includes(f.feature_type)), [], title);
  }
});

test("common general subjects remain detectable without old schema migration", () => {
  const subjects = [
    ["crypto", "BTC and Bitcoin long-term investment thesis"],
    ["ai", "AI adoption and productivity research"],
    ["science", "Riemann Hypothesis mathematics claim"],
  ];
  for (const [key, title] of subjects) {
    assert.ok(extractSemanticFeatures({title}).some(f => f.feature_type === "topic" && f.feature_key === key), title);
  }
});
