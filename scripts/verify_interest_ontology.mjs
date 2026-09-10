import { FEATURE_MODEL_VERSION, canonicalizeFeatureKey, extractSemanticFeatures } from "../cloudflare/runner3-core/src/content-feature-enrichment.js";

if (FEATURE_MODEL_VERSION !== "semantic-bridge-v4") throw new Error("feature model mismatch");
if (canonicalizeFeatureKey("topic", "AI_Economics") !== "ai-economics") throw new Error("underscore alias not normalized");
if (canonicalizeFeatureKey("topic", "Political Institutions") !== "political-institutions") throw new Error("space alias not normalized");
if (canonicalizeFeatureKey("mechanism", "causal_mechanism") !== "causal-mechanism") throw new Error("mechanism alias not normalized");

const features = extractSemanticFeatures({title:"Nanobot agent orchestration open source AI framework",canonical_url:"https://example.com/x",source_key:"x",language:"en"});
if (features.some((f) => f.feature_type === "keyword")) throw new Error("keyword generation reintroduced");
if (features.some((f) => f.feature_type === "concept" && !["agent-orchestration","open-source-ai"].includes(f.feature_key))) throw new Error("free-form title ngram concept reintroduced");
console.log(JSON.stringify({ok:true,feature_model:FEATURE_MODEL_VERSION,free_form_ngram_concepts:false,keyword_generation:false,canonical_key_format:"kebab-case"}));
