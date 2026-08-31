import { handleContentIntelligence } from "./content-intelligence.js";

const MCP_ACCESS_SHA256 = "fbefa7761e4102360c4165f940ed7d9190961a6d9c19049af5d922b6cbe0ca6c";
const SERVER_NAME = "runner3-content-intelligence";
const SERVER_VERSION = "1.0.0";
const DEFAULT_PROTOCOL_VERSION = "2025-06-18";
const MAX_BODY_BYTES = 64 * 1024;

const SAVE_INTEREST_TOOL = {
  name: "save_interest",
  title: "Save interest",
  description: "Use this when the user explicitly asks to save an article, URL, topic, mechanism, or selected content as a Content Intelligence interest preference. This writes an idempotent durable interest_saved event to D1 and does not add the item to the RSS Library.",
  inputSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      canonical_url: { type: "string", minLength: 8, maxLength: 4096, description: "Canonical http(s) URL for the item." },
      title: { type: "string", maxLength: 4000 },
      source_type: { type: "string", enum: ["rss", "web", "x", "facebook", "reddit", "youtube"], default: "web" },
      source_name: { type: "string", maxLength: 300 },
      source_key: { type: "string", maxLength: 200 },
      language: { type: "string", maxLength: 50 },
      strength: { type: "string", enum: ["strong", "medium", "light", "exploratory"], default: "strong" },
      features: {
        type: "array",
        maxItems: 40,
        description: "Optional explicit semantic features inferred from the user's stated interest. Keep keys stable and machine-friendly.",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["feature_type", "feature_key"],
          properties: {
            feature_type: { type: "string", enum: ["topic", "concept", "mechanism", "entity", "source"] },
            feature_key: { type: "string", minLength: 1, maxLength: 300 },
            feature_value: { type: "string", maxLength: 4000 },
            weight: { type: "number", minimum: 0.1, maximum: 3.0, default: 1.0 },
            confidence: { type: "number", minimum: 0.0, maximum: 1.0, default: 0.9 },
            model_version: { type: "string", maxLength: 200, default: "chatgpt-explicit-interest-v1" }
          }
        }
      }
    },
    required: ["canonical_url"]
  },
  annotations: {
    readOnlyHint: false,
    destructiveHint: false,
    openWorldHint: false,
    idempotentHint: true
  }
};

function jsonRpc(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function jsonRpcError(id, code, message, data) {
  const error = { code, message };
  if (data !== undefined) error.data = data;
  return { jsonrpc: "2.0", id: id ?? null, error };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-expose-headers": "mcp-protocol-version"
    }
  });
}

async function sha256(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function authorized(url) {
  const supplied = url.searchParams.get("access") || "";
  if (!supplied || supplied.length > 128) return false;
  return (await sha256(supplied)) === MCP_ACCESS_SHA256;
}

function validateCanonicalUrl(value) {
  const raw = String(value || "").trim();
  const parsed = new URL(raw);
  if (!/^https?:$/.test(parsed.protocol)) throw new Error("canonical_url_must_be_http_or_https");
  return parsed.toString();
}

function normalizeFeatures(features) {
  if (!Array.isArray(features)) return [];
  if (features.length > 40) throw new Error("features_max_40");
  return features.map((f) => ({
    feature_type: String(f?.feature_type || "").trim(),
    feature_key: String(f?.feature_key || "").trim(),
    feature_value: f?.feature_value == null ? null : String(f.feature_value),
    weight: Number.isFinite(Number(f?.weight)) ? Number(f.weight) : 1,
    confidence: Number.isFinite(Number(f?.confidence)) ? Number(f.confidence) : 0.9,
    model_version: String(f?.model_version || "chatgpt-explicit-interest-v1")
  })).filter((f) => f.feature_type && f.feature_key);
}

async function saveInterest(args, request, env) {
  const canonicalUrl = validateCanonicalUrl(args?.canonical_url);
  const payload = {
    item: {
      item_id: canonicalUrl,
      canonical_url: canonicalUrl,
      source_type: String(args?.source_type || "web"),
      source_name: args?.source_name == null ? null : String(args.source_name),
      source_key: args?.source_key == null ? null : String(args.source_key),
      title: args?.title == null ? null : String(args.title),
      language: args?.language == null ? null : String(args.language)
    },
    features: normalizeFeatures(args?.features),
    context: {
      source: "chatgpt-direct-mcp",
      strength: String(args?.strength || "strong"),
      transport: "direct-worker-mcp"
    }
  };

  const target = new URL(request.url);
  target.pathname = "/content-intelligence/interests/ingest";
  target.search = "";
  const internalRequest = new Request(target.toString(), {
    method: "POST",
    headers: {
      authorization: `Bearer ${String(env.RUNNER3_CORE_TOKEN || "")}`,
      "content-type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  const response = await handleContentIntelligence(internalRequest, env, target);
  if (!response) throw new Error("interest_ingest_route_missing");
  const result = await response.json().catch(() => ({ ok: false, error: "invalid_core_response" }));
  if (!response.ok || result?.ok !== true || result?.durable !== true) {
    return {
      content: [{ type: "text", text: `Interest save failed: ${String(result?.error || `HTTP ${response.status}`)}` }],
      structuredContent: { ok: false, durable: false, error: result?.error || `HTTP_${response.status}` },
      isError: true
    };
  }
  const alreadyPresent = Number(result.event_applied || 0) === 0;
  return {
    content: [{ type: "text", text: alreadyPresent ? "Interest was already durably saved in D1." : "Interest saved durably to D1." }],
    structuredContent: {
      ok: true,
      durable: true,
      item_id: result.item_id,
      event_applied: Number(result.event_applied || 0),
      already_present: alreadyPresent,
      materialization_status: result.materialization_status || "dirty",
      semantic_enrichment: result.semantic_enrichment || "deferred",
      model_version: result.model_version || "personal-v2"
    }
  };
}

async function handleRpc(message, request, env) {
  if (!message || message.jsonrpc !== "2.0" || typeof message.method !== "string") {
    return jsonRpcError(message?.id, -32600, "Invalid Request");
  }
  if (message.method === "initialize") {
    const requested = String(message?.params?.protocolVersion || DEFAULT_PROTOCOL_VERSION);
    return jsonRpc(message.id, {
      protocolVersion: requested,
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      instructions: "Private Content Intelligence learning transport. Use save_interest only after the user explicitly asks to save an interest. Lưu interest is preference-only and must not create RSS Library membership."
    });
  }
  if (message.method === "notifications/initialized") return null;
  if (message.method === "ping") return jsonRpc(message.id, {});
  if (message.method === "tools/list") return jsonRpc(message.id, { tools: [SAVE_INTEREST_TOOL] });
  if (message.method === "tools/call") {
    const name = String(message?.params?.name || "");
    if (name !== SAVE_INTEREST_TOOL.name) return jsonRpcError(message.id, -32601, "Unknown tool");
    try {
      return jsonRpc(message.id, await saveInterest(message?.params?.arguments || {}, request, env));
    } catch (error) {
      return jsonRpc(message.id, {
        content: [{ type: "text", text: `Interest save failed: ${String(error?.message || error)}` }],
        structuredContent: { ok: false, durable: false, error: String(error?.message || error) },
        isError: true
      });
    }
  }
  return message.id === undefined ? null : jsonRpcError(message.id, -32601, "Method not found");
}

export async function handleChatGptMcp(request, env, url) {
  if (url.pathname !== "/mcp") return null;
  if (!(await authorized(url))) return new Response("Not Found", { status: 404, headers: { "cache-control": "no-store" } });

  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-headers": "content-type, accept, mcp-protocol-version",
        "access-control-max-age": "600"
      }
    });
  }
  if (request.method !== "POST") return jsonResponse({ error: "method_not_allowed" }, 405);

  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > MAX_BODY_BYTES) return jsonResponse(jsonRpcError(null, -32600, "Request too large"), 413);
  let body;
  try {
    const raw = await request.text();
    if (raw.length > MAX_BODY_BYTES) return jsonResponse(jsonRpcError(null, -32600, "Request too large"), 413);
    body = JSON.parse(raw);
  } catch {
    return jsonResponse(jsonRpcError(null, -32700, "Parse error"), 400);
  }

  if (Array.isArray(body)) {
    const results = [];
    for (const message of body) {
      const result = await handleRpc(message, request, env);
      if (result) results.push(result);
    }
    if (!results.length) return new Response(null, { status: 202, headers: { "cache-control": "no-store" } });
    return jsonResponse(results);
  }

  const result = await handleRpc(body, request, env);
  if (!result) return new Response(null, { status: 202, headers: { "cache-control": "no-store" } });
  const response = jsonResponse(result);
  response.headers.set("mcp-protocol-version", String(body?.params?.protocolVersion || request.headers.get("mcp-protocol-version") || DEFAULT_PROTOCOL_VERSION));
  return response;
}
