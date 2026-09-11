import { canonicalInterestKey, familyDiminishingWeight, interestFamily, INTEREST_ONTOLOGY_VERSION } from "../cloudflare/runner3-core/src/content-interest-ontology.js";
import { FEATURE_MODEL_VERSION, canonicalizeFeatureKey, extractSemanticFeatures } from "../cloudflare/runner3-core/src/content-feature-enrichment.js";

if (FEATURE_MODEL_VERSION !== "semantic-bridge-v4") throw new Error("feature model mismatch");
if (canonicalizeFeatureKey("topic", "AI_Economics") !== "ai-economics") throw new Error("underscore alias not normalized");
if (canonicalizeFeatureKey("topic", "Political Institutions") !== "political-institutions") throw new Error("space alias not normalized");
if (canonicalizeFeatureKey("mechanism", "causal_mechanism") !== "causal-mechanism") throw new Error("mechanism alias not normalized");

const features = extractSemanticFeatures({title:"Nanobot agent orchestration open source AI framework",canonical_url:"https://example.com/x",source_key:"x",language:"en"});
if (features.some((f) => f.feature_type === "keyword")) throw new Error("keyword generation reintroduced");
if (features.some((f) => f.feature_type === "concept" && !["agent-orchestration","open-source-ai"].includes(f.feature_key))) throw new Error("free-form title ngram concept reintroduced");
if (INTEREST_ONTOLOGY_VERSION !== "interest-family-v1") throw new Error("interest family version mismatch");
if (canonicalInterestKey("topic", "AI_Economics") !== "ai-economics") throw new Error("family canonical key mismatch");
if (interestFamily("concept", "ai-capex-capital-allocation") !== "ai-economics") throw new Error("AI economics family mismatch");
if (interestFamily("mechanism", "permission-boundaries-and-tool-action-monitoring") !== "ai-systems") throw new Error("AI systems family mismatch");
if (interestFamily("concept", "china-duv-euv-lithography") !== "industrial-power") throw new Error("industrial family mismatch");
if (interestFamily("mechanism", "bond-yield-equity-divergence") !== "macro-finance") throw new Error("macro family mismatch");
if (interestFamily("mechanism", "causal_mechanism") !== "analysis-style") throw new Error("analysis-style family mismatch");
if (familyDiminishingWeight(1) !== 1 || familyDiminishingWeight(2) !== 0.35 || familyDiminishingWeight(3) !== 0.15 || familyDiminishingWeight(9) !== 0.15) throw new Error("family diminishing weights mismatch");
console.log(JSON.stringify({ok:true,feature_model:FEATURE_MODEL_VERSION,interest_ontology:INTEREST_ONTOLOGY_VERSION,free_form_ngram_concepts:false,keyword_generation:false,canonical_key_format:"kebab-case",family_aware:true}));
