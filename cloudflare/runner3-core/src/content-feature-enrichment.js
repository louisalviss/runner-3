export const FEATURE_MODEL_VERSION = "semantic-bridge-v3";

const AUTO_MODELS = new Set(["reader-bridge-v2", FEATURE_MODEL_VERSION]);
const STOP = new Set([
  "the","a","an","and","or","but","for","to","of","in","on","at","by","from","with","as","is","are","was","were","be","been","being","this","that","these","those","it","its","into","after","before","over","under","new","how","why","what","when","who","will","can","could","would","should","about","more","than","via",
  "và","hoặc","nhưng","của","cho","trong","trên","tại","từ","với","là","được","bị","có","một","những","các","này","đó","sau","trước","về","khi","như","đang","mới","sẽ","đã","để","vì","sao","thế","nào","vào","ra","theo","giữa","không"
]);
const ENTITY_ACRONYM_BLOCK = new Set(["AI","API","GPU","CPU","GDP","US","USA","EU","VN","RSS","HTTP","HTTPS","LLM","SaaS"]);

const TOPIC_RULES = [
  ["ai", [" artificial intelligence "," tri tue nhan tao "," machine learning "," llm "," generative ai "," openai "," gpt "," ai agent "," ai agents "]],
  ["ai-agents", [" agent orchestration "," agentic "," multi agent "," multi-agent "," ai agent "," ai agents "," tac nhan ai "]],
  ["ai-infrastructure", [" inference "," gpu "," compute "," data center "," datacenter "," model serving "," accelerator "]],
  ["semiconductors", [" semiconductor "," chip "," nvidia "," amd "," tsmc "," foundry "]],
  ["cloud-infrastructure", [" cloudflare "," cloud computing "," edge computing "," serverless "," cdn "," cloud infrastructure "]],
  ["developer-tools", [" developer tool "," developer tools "," github "," coding "," code generation "," framework "," api platform "," open source "]],
  ["cybersecurity", [" cybersecurity "," cyber security "," security breach "," malware "," ransomware "," zero trust "," hack "," hacked "]],
  ["crypto", [" bitcoin "," ethereum "," crypto "," blockchain "," stablecoin "," tokenization "," tokenised "," tokenized "]],
  ["markets", [" stock market "," stocks "," equity "," equities "," trading "," investing "," capital market "," thi truong von "," chung khoan "," co phieu "]],
  ["macroeconomics", [" inflation "," interest rate "," central bank "," gdp "," economy "," economic growth "," recession "," kinh te "," lam phat "," lai suat "]],
  ["vietnam", [" vietnam "," viet nam "," vietnamese "]],
  ["geopolitics", [" geopolitics "," geopolitical "," sanctions "," diplomacy "," election "," china us "," us china "," war "," conflict "]],
  ["hardware", [" hardware "," camera "," laptop "," smartphone "," phone "," device "," wearable "," headset "]],
  ["robotics", [" robot "," robotics "," drone "," autonomous "," humanoid "]],
  ["science", [" science "," physics "," astronomy "," space "," biology "," quantum "]],
  ["saas", [" saas "," startup "," founder "," b2b software "," subscription software "]],
  ["wordpress", [" wordpress "," woocommerce "," plugin "," wp "]],
  ["ecommerce", [" ecommerce "," e-commerce "," shopify "," online retail "]],
  ["industrial-policy", [" industrial park "," industrial parks "," manufacturing "," supply chain "," factory "," khu cong nghiep "]]
];

const CONCEPT_RULES = [
  ["agent-orchestration", [" agent orchestration "," orchestration tools "]],
  ["ai-inference", [" ai inference "," inference cost "," inference chip "," inference compute "]],
  ["open-source-ai", [" open source ai "," open-source ai "," open model "," open models "]],
  ["data-center-buildout", [" data center "," datacenter "," ai data center "]],
  ["capital-market-reform", [" capital market reform "," capital markets reform "," cai cach thi truong von "," thi truong von "]],
  ["industrial-parks", [" industrial park "," industrial parks "," khu cong nghiep "]],
  ["autonomous-drone", [" autonomous drone "," flying camera "," camera biet bay "," drone "]],
  ["stablecoins", [" stablecoin "," stablecoins "]],
  ["asset-tokenization", [" tokenization "," tokenized stock "," tokenised stock "]],
  ["wordpress-compatibility", [" plugin compatibility "," wordpress compatibility "," woocommerce compatibility "]],
  ["developer-automation", [" coding agent "," code agent "," developer automation "," ai coding "]],
  ["edge-compute", [" edge compute "," edge computing "," cloudflare computer "]]
];

function fold(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}
function normalizedText(value) {
  return ` ${fold(value).replace(/[^a-z0-9$+.-]+/g, " ").replace(/\s+/g, " ").trim()} `;
}
function hostname(value) {
  try { return new URL(String(value || "")).hostname.toLowerCase().replace(/^www\./, ""); } catch { return null; }
}
function uniqPush(out, seen, key, limit) {
  const clean = String(key || "").trim().slice(0, 300);
  if (!clean || seen.has(clean) || out.length >= limit) return;
  seen.add(clean);
  out.push(clean);
}
function contentTokens(title) {
  const raw = fold(title).match(/[\p{L}\p{N}][\p{L}\p{N}._+-]{1,}/gu) || [];
  return raw.filter((t) => t.length >= 3 && !STOP.has(t) && !/^\d+$/.test(t));
}
function keywordFeatures(title) {
  const out = [], seen = new Set();
  for (const token of contentTokens(title)) uniqPush(out, seen, token, 8);
  return out;
}
function conceptNgrams(title) {
  const tokens = contentTokens(title).slice(0, 14);
  const out = [], seen = new Set();
  for (let i = 0; i < tokens.length - 1; i += 1) {
    uniqPush(out, seen, `${tokens[i]} ${tokens[i + 1]}`, 6);
    if (i + 2 < tokens.length && out.length < 6) uniqPush(out, seen, `${tokens[i]} ${tokens[i + 1]} ${tokens[i + 2]}`, 6);
  }
  return out;
}
function matchedRules(title, rules, limit) {
  const text = normalizedText(title);
  const out = [];
  for (const [key, terms] of rules) {
    if (terms.some((term) => text.includes(term))) out.push(key);
    if (out.length >= limit) break;
  }
  return out;
}
function entityFeatures(title) {
  const words = String(title || "").match(/[$]?[\p{L}\p{N}][\p{L}\p{N}.$+_-]*/gu) || [];
  const out = [], seen = new Set();
  const isCap = (w) => /^\p{Lu}[\p{L}\p{M}\d._+-]{2,}$/u.test(w) && !STOP.has(fold(w));
  for (const word of words) {
    if (/^\$[A-Z]{1,8}$/.test(word)) uniqPush(out, seen, word.toUpperCase(), 8);
    else if (/^[A-Z][A-Z0-9.-]{1,8}$/.test(word) && !ENTITY_ACRONYM_BLOCK.has(word)) uniqPush(out, seen, word, 8);
    else if (/\p{Ll}.*\p{Lu}/u.test(word) || /\p{Lu}.*\p{Ll}.*\p{Lu}/u.test(word)) uniqPush(out, seen, word, 8);
  }
  for (let i = 0; i < words.length - 1 && out.length < 8; i += 1) {
    if (!isCap(words[i]) || !isCap(words[i + 1])) continue;
    const parts = [words[i], words[i + 1]];
    if (i + 2 < words.length && isCap(words[i + 2])) parts.push(words[i + 2]);
    uniqPush(out, seen, parts.join(" "), 8);
  }
  return out;
}

export function extractSemanticFeatures(item = {}) {
  const title = String(item.title || "").trim();
  const sourceKey = String(item.source_key || item.sourceKey || "").trim().toLowerCase() || null;
  const sourceName = String(item.source_name || item.sourceName || "").trim() || null;
  const language = String(item.language || item.source_language || "").trim().toLowerCase() || null;
  const canonicalUrl = item.canonical_url || item.canonicalUrl || item.item_id || null;
  const domain = hostname(canonicalUrl);
  const features = [];
  const add = (feature_type, feature_key, weight, confidence, feature_value = null) => {
    if (!feature_key) return;
    features.push({ feature_type, feature_key: String(feature_key).slice(0, 300), feature_value, weight, confidence, model_version: FEATURE_MODEL_VERSION });
  };

  add("source", sourceKey || fold(sourceName), 0.14, 1.0);
  add("domain", domain, 0.10, 1.0);
  add("language", language, 0.04, 1.0);
  for (const topic of matchedRules(title, TOPIC_RULES, 5)) add("topic", topic, 0.42, 0.90);
  for (const concept of matchedRules(title, CONCEPT_RULES, 5)) add("concept", concept, 0.34, 0.88);
  for (const entity of entityFeatures(title)) add("entity", fold(entity), 0.28, 0.76, entity);
  for (const concept of conceptNgrams(title)) add("concept", concept, 0.20, 0.62);
  for (const keyword of keywordFeatures(title)) add("keyword", keyword, 0.09, 0.58);

  const deduped = new Map();
  for (const f of features) {
    const k = `${f.feature_type}\u0000${f.feature_key}`;
    const prev = deduped.get(k);
    if (!prev || f.weight * f.confidence > prev.weight * prev.confidence) deduped.set(k, f);
  }
  return [...deduped.values()];
}

function normalizedFeature(row = {}) {
  return {
    feature_type: String(row.feature_type || ""),
    feature_key: String(row.feature_key || ""),
    feature_value: row.feature_value == null ? null : String(row.feature_value),
    weight: Number(row.weight ?? 1),
    confidence: Number(row.confidence ?? 1),
    model_version: String(row.model_version || ""),
  };
}

function featureSetsEqual(existing, generated) {
  if (existing.length !== generated.length) return false;
  const keyOf = (row) => `${row.feature_type}\u0000${row.feature_key}`;
  const current = new Map(existing.map((row) => {
    const normalized = normalizedFeature(row);
    return [keyOf(normalized), normalized];
  }));
  for (const row of generated) {
    const normalized = normalizedFeature(row);
    const prior = current.get(keyOf(normalized));
    if (!prior) return false;
    if (prior.feature_value !== normalized.feature_value) return false;
    if (prior.weight !== normalized.weight || prior.confidence !== normalized.confidence) return false;
    if (prior.model_version !== normalized.model_version) return false;
  }
  return true;
}

export async function replaceAutoSemanticFeatures(env, itemId, item = {}) {
  if (!env?.DB || !itemId) return { applied: 0, features: [], unchanged: true };
  const generated = extractSemanticFeatures({ ...item, item_id: itemId });
  const models = [...AUTO_MODELS];
  const current = await env.DB.prepare(`
    SELECT feature_type,feature_key,feature_value,weight,confidence,model_version
    FROM content_features
    WHERE item_id=? AND model_version IN (${models.map(() => "?").join(",")})
  `).bind(itemId, ...models).all();
  const existing = current.results || [];
  if (featureSetsEqual(existing, generated)) {
    return { applied: 0, features: generated, unchanged: true };
  }

  await env.DB.prepare(`DELETE FROM content_features WHERE item_id=? AND model_version IN (${models.map(() => "?").join(",")})`).bind(itemId, ...models).run();
  let applied = 0;
  for (const feature of generated) {
    const result = await env.DB.prepare(`
      INSERT INTO content_features(item_id,feature_type,feature_key,feature_value,weight,confidence,model_version,updated_at)
      VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
      ON CONFLICT(item_id,feature_type,feature_key) DO UPDATE SET
        feature_value=excluded.feature_value,weight=excluded.weight,confidence=excluded.confidence,
        model_version=excluded.model_version,updated_at=CURRENT_TIMESTAMP
    `).bind(itemId, feature.feature_type, feature.feature_key, feature.feature_value, feature.weight, feature.confidence, feature.model_version).run();
    applied += Number(result.meta?.changes || 0);
  }
  return { applied, features: generated, unchanged: false };
}
