export const INTEREST_ONTOLOGY_VERSION = "interest-family-v1";

const FAMILY_RULES = [
  ["ai-economics", ["ai-economics", "ai-capex", "ai-roi", "ai-revenue", "ai-inference", "inference-econom", "data-center-buildout", "ai-infrastructure", "task-compression", "diffusion-adoption", "capital-allocation"]],
  ["ai-systems", ["ai-agents", "agent-orchestration", "developer-automation", "ai-coding", "coding-workflow", "ai-agent-safety", "permission-bound", "model-monitorability", "open-source-ai", "external-validation", "cross-app-permissions"]],
  ["macro-finance", ["macro-finance", "macroeconomics", "monetary-policy", "interest-rate", "bond-yield", "real-yield", "term-premium", "capital-market", "market-expectation", "liquidity", "central-bank"]],
  ["industrial-power", ["industrial-policy", "strategic-supply", "supply-chain", "semiconductors", "lithograph", "rare-earth", "manufacturing", "industrial-park", "technology-transfer", "commercialization", "human-capital"]],
  ["geopolitics-security", ["geopolitics", "vietnam-sea", "taiwan", "military", "wartime", "warfare", "strategic-autonomy", "sanctions", "alliance", "coercion"]],
  ["institutions-policy", ["political-institutions", "regulation-policy", "governance", "electoral", "institutional", "policy-design", "state-capacity"]],
  ["digital-rights-data", ["data-portability", "cloud-lock", "privacy", "surveillance", "security-auth-ux", "identity", "data-ownership"]],
  ["structural-business", ["structural-business", "business-model", "market-structure", "platform-econom", "network-effect", "residual-value", "after-sales"]],
  ["robotics-physical-ai", ["robotics", "autonomous-drone", "humanoid", "physical-ai", "synthetic-world", "embodied"]],
  ["science-explainers", ["explanatory-science", "science", "physics", "astronomy", "biology", "quantum", "mathematics"]],
  ["developer-infrastructure", ["developer-tools", "wordpress", "wordpress-compatibility", "cloud-infrastructure", "edge-compute", "saas", "ecommerce"]],
  ["hardware-products", ["hardware", "wearable", "smartphone", "device", "display", "battery"]],
];

const ANALYSIS_STYLE_KEYS = new Set(["causal-mechanism", "second-order-effect", "economics-unit", "system-design"]);

function fold(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function canonicalInterestKey(featureType, value) {
  const type = String(featureType || "").trim().toLowerCase();
  const raw = String(value || "").trim();
  if (!type || !raw) return "";
  if (["topic", "concept", "mechanism", "story_attribute", "method", "workflow", "trend", "product"].includes(type)) {
    return fold(raw).replace(/[_\s]+/g, "-").replace(/[^a-z0-9-]+/g, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "").slice(0, 300);
  }
  if (type === "entity") return fold(raw).replace(/\s+/g, " ").trim().slice(0, 300);
  return raw.toLowerCase().replace(/\s+/g, " ").trim().slice(0, 300);
}

export function interestFamily(featureType, featureKey) {
  const type = String(featureType || "").trim().toLowerCase();
  const key = canonicalInterestKey(type, featureKey);
  if (!key) return "unknown";
  if (type === "mechanism" && ANALYSIS_STYLE_KEYS.has(key)) return "analysis-style";
  for (const [family, needles] of FAMILY_RULES) {
    if (needles.some((needle) => key.includes(needle))) return family;
  }
  return `${type}:${key}`;
}

export function familyDiminishingWeight(rank) {
  const n = Number(rank || 0);
  if (n <= 1) return 1.0;
  if (n === 2) return 0.35;
  return 0.15;
}

export function familySignalCap(familyId) {
  if (familyId === "analysis-style") return 3.0;
  return 5.0;
}

export function canonicalInterestKeySql(typeExpr, keyExpr) {
  return `CASE WHEN lower(${typeExpr}) IN ('topic','concept','mechanism','story_attribute','method','workflow','trend','product') THEN trim(replace(replace(lower(${keyExpr}),'_','-'),' ','-')) ELSE lower(${keyExpr}) END`;
}

export function interestFamilySql(typeExpr, keyExpr) {
  const key = canonicalInterestKeySql(typeExpr, keyExpr);
  const clauses = [
    `WHEN lower(${typeExpr})='mechanism' AND ${key} IN ('causal-mechanism','second-order-effect','economics-unit','system-design') THEN 'analysis-style'`,
  ];
  for (const [family, needles] of FAMILY_RULES) {
    const condition = needles.map((needle) => `${key} LIKE '%${needle.replaceAll("'", "''")}%'`).join(" OR ");
    clauses.push(`WHEN ${condition} THEN '${family}'`);
  }
  return `(CASE ${clauses.join(" ")} ELSE lower(${typeExpr}) || ':' || ${key} END)`;
}
