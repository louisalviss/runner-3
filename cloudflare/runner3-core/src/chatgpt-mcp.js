import { handleContentIntelligence } from "./content-intelligence.js";

const SERVER_NAME = "runner3-content-intelligence";
const SERVER_VERSION = "1.1.0";
const DEFAULT_PROTOCOL_VERSION = "2025-06-18";
const MAX_BODY_BYTES = 64 * 1024;
const OWNER_READER_TOKEN_SHA256 = "a4efd86ada61ed4398ec259b7f46262f10d4e2f7fa4f123c5619eb6366d0dd18";
const ORIGIN = "https://runner3-core.ducduy2411.workers.dev";
const MCP_RESOURCE = `${ORIGIN}/mcp`;
const OAUTH_SCOPE = "interest:write";
const ACCESS_TTL_SECONDS = 60 * 60;
const REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60;
const CODE_TTL_SECONDS = 5 * 60;

const SECURITY_SCHEMES = [{ type: "oauth2", scopes: [OAUTH_SCOPE] }];
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
  },
  securitySchemes: SECURITY_SCHEMES,
  _meta: { securitySchemes: SECURITY_SCHEMES }
};

function jsonRpc(id, result) { return { jsonrpc: "2.0", id, result }; }
function jsonRpcError(id, code, message, data) {
  const error = { code, message };
  if (data !== undefined) error.data = data;
  return { jsonrpc: "2.0", id: id ?? null, error };
}
function jsonResponse(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-expose-headers": "mcp-protocol-version, www-authenticate",
      ...extraHeaders
    }
  });
}
function htmlResponse(html, status = 200) {
  return new Response(html, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "pragma": "no-cache",
      "referrer-policy": "no-referrer",
      "x-content-type-options": "nosniff",
      "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    }
  });
}
function oauthJson(payload, status = 200) {
  return jsonResponse(payload, status, { pragma: "no-cache" });
}
function nowSeconds() { return Math.floor(Date.now() / 1000); }
function bytesToBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
function randomToken(bytes = 32) {
  const value = new Uint8Array(bytes);
  crypto.getRandomValues(value);
  return bytesToBase64Url(value);
}
async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(value || "")));
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}
async function sha256Base64Url(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(value || "")));
  return bytesToBase64Url(new Uint8Array(digest));
}
function secureEqual(a, b) {
  const x = String(a || ""), y = String(b || "");
  if (x.length !== y.length) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x.charCodeAt(i) ^ y.charCodeAt(i);
  return diff === 0;
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function normalizeScope(value) {
  const scopes = [...new Set(String(value || OAUTH_SCOPE).split(/\s+/).filter(Boolean))];
  if (!scopes.length) scopes.push(OAUTH_SCOPE);
  if (scopes.some((scope) => scope !== OAUTH_SCOPE)) throw new Error("invalid_scope");
  return scopes.join(" ");
}
function authChallenge(error = "invalid_token", description = "Link Runner3 Content Intelligence to continue") {
  return `Bearer resource_metadata="${ORIGIN}/.well-known/oauth-protected-resource", scope="${OAUTH_SCOPE}", error="${error}", error_description="${description}"`;
}
function authRequiredResult(description = "Authentication required") {
  return {
    content: [{ type: "text", text: description }],
    structuredContent: { ok: false, durable: false, error: "AUTH_REQUIRED" },
    isError: true,
    _meta: { "mcp/www_authenticate": [authChallenge("invalid_token", description)] }
  };
}

async function cleanupOauth(env) {
  if (!env.DB) return;
  const now = nowSeconds();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM mcp_oauth_codes WHERE expires_at < ? OR used_at IS NOT NULL").bind(now - 300),
    env.DB.prepare("DELETE FROM mcp_oauth_tokens WHERE expires_at < ? OR (revoked_at IS NOT NULL AND revoked_at < ?)").bind(now - 86400, now - 86400)
  ]).catch(() => {});
}

function validateRedirectUri(value) {
  const redirect = new URL(String(value || ""));
  if (redirect.protocol !== "https:" || redirect.hostname !== "chatgpt.com") throw new Error("invalid_redirect_uri");
  const validPath = redirect.pathname.startsWith("/connector/oauth/") || redirect.pathname === "/connector_platform_oauth_redirect";
  if (!validPath) throw new Error("invalid_redirect_uri");
  return redirect.toString();
}
async function validateChatGptClient(clientId, redirectUri) {
  const client = new URL(String(clientId || ""));
  if (client.protocol !== "https:" || client.hostname !== "chatgpt.com" || !client.pathname.startsWith("/oauth/") || !client.pathname.endsWith("/client.json")) {
    throw new Error("invalid_client");
  }
  const redirect = validateRedirectUri(redirectUri);
  const response = await fetch(client.toString(), { headers: { accept: "application/json" }, redirect: "error" });
  if (!response.ok) throw new Error("invalid_client");
  const metadata = await response.json().catch(() => null);
  const allowed = Array.isArray(metadata?.redirect_uris) ? metadata.redirect_uris.map(String) : [];
  if (!allowed.includes(redirect)) throw new Error("invalid_redirect_uri");
  return { clientId: client.toString(), redirectUri: redirect };
}
function validateAuthorizationParams(params) {
  if (String(params.get("response_type") || "") !== "code") throw new Error("unsupported_response_type");
  const resource = String(params.get("resource") || "");
  if (resource !== MCP_RESOURCE) throw new Error("invalid_target");
  const challenge = String(params.get("code_challenge") || "");
  if (!/^[A-Za-z0-9_-]{43,128}$/.test(challenge)) throw new Error("invalid_request");
  if (String(params.get("code_challenge_method") || "") !== "S256") throw new Error("invalid_request");
  const state = String(params.get("state") || "");
  if (state.length > 4096) throw new Error("invalid_request");
  return {
    clientId: String(params.get("client_id") || ""),
    redirectUri: String(params.get("redirect_uri") || ""),
    resource,
    scope: normalizeScope(params.get("scope")),
    codeChallenge: challenge,
    state
  };
}
async function ownerAuthorized(readerToken) {
  const supplied = String(readerToken || "").trim();
  if (!supplied || supplied.length > 512) return false;
  return secureEqual(await sha256Hex(supplied), OWNER_READER_TOKEN_SHA256);
}

function protectedResourceMetadata() {
  return {
    resource: MCP_RESOURCE,
    authorization_servers: [ORIGIN],
    scopes_supported: [OAUTH_SCOPE],
    bearer_methods_supported: ["header"]
  };
}
function authorizationServerMetadata() {
  return {
    issuer: ORIGIN,
    authorization_endpoint: `${ORIGIN}/oauth/authorize`,
    token_endpoint: `${ORIGIN}/oauth/token`,
    client_id_metadata_document_supported: true,
    token_endpoint_auth_methods_supported: ["none"],
    code_challenge_methods_supported: ["S256"],
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    scopes_supported: [OAUTH_SCOPE]
  };
}
function renderConsentPage(values, error = "") {
  const fields = ["client_id", "redirect_uri", "resource", "scope", "state", "code_challenge", "code_challenge_method", "response_type"];
  const hidden = fields.map((key) => `<input type="hidden" name="${key}" value="${escapeHtml(values[key] || "")}">`).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Authorize Runner3</title><style>body{font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0b0b0c;color:#f5f5f5;margin:0;padding:28px}.card{max-width:520px;margin:5vh auto;background:#151517;border:1px solid #2d2d31;border-radius:18px;padding:22px}.muted{color:#aaa}.ok{color:#9be9a8}.err{color:#ffaaaa}input[type=password]{width:100%;box-sizing:border-box;margin:12px 0;padding:12px;border-radius:10px;border:1px solid #38383d;background:#0e0e10;color:#fff}button{width:100%;padding:12px;border:0;border-radius:10px;background:#f2f2f2;color:#111;font-weight:700}</style></head><body><div class="card"><h2>Authorize ChatGPT</h2><p>Allow ChatGPT to save explicit Content Intelligence interests to your private D1 profile.</p><p class="muted">Scope: <code>${escapeHtml(OAUTH_SCOPE)}</code>. This does not grant D1 read access or RSS Library membership.</p>${error ? `<p class="err">${escapeHtml(error)}</p>` : ""}<form method="post" action="/oauth/authorize">${hidden}<label for="reader_token">RSS Reader identity</label><input id="reader_token" name="reader_token" type="password" autocomplete="current-password" placeholder="Reader token" required><p id="identity" class="muted">Checking existing Reader session…</p><button type="submit">Authorize</button></form></div><script>(function(){try{var t=localStorage.getItem('rssReaderToken')||'';if(t){document.getElementById('reader_token').value=t;document.getElementById('identity').textContent='Existing RSS Reader identity found on this browser.';document.getElementById('identity').className='ok';}else{document.getElementById('identity').textContent='Reader identity is not stored in this browser; enter your Reader token once.';}}catch(e){document.getElementById('identity').textContent='Enter your Reader token once.';}})();</script></body></html>`;
}

async function handleAuthorize(request, env, url) {
  if (!env.DB) return oauthJson({ error: "temporarily_unavailable" }, 503);
  const params = request.method === "POST" ? new URLSearchParams(Array.from((await request.formData()).entries()).map(([k, v]) => [k, String(v)])) : url.searchParams;
  let auth;
  try {
    auth = validateAuthorizationParams(params);
    await validateChatGptClient(auth.clientId, auth.redirectUri);
  } catch (error) {
    return htmlResponse(`<h1>OAuth request rejected</h1><p>${escapeHtml(error?.message || error)}</p>`, 400);
  }
  const values = {
    client_id: auth.clientId,
    redirect_uri: auth.redirectUri,
    resource: auth.resource,
    scope: auth.scope,
    state: auth.state,
    code_challenge: auth.codeChallenge,
    code_challenge_method: "S256",
    response_type: "code"
  };
  if (request.method === "GET") return htmlResponse(renderConsentPage(values));
  const form = await request.clone().formData().catch(() => null);
  const readerToken = form ? String(form.get("reader_token") || "") : "";
  if (!(await ownerAuthorized(readerToken))) return htmlResponse(renderConsentPage(values, "RSS Reader identity was not accepted."), 401);

  await cleanupOauth(env);
  const code = randomToken(32);
  const codeHash = await sha256Hex(code);
  const now = nowSeconds();
  await env.DB.prepare(`INSERT INTO mcp_oauth_codes(code_hash,client_id,redirect_uri,resource,scope,code_challenge,expires_at,used_at,created_at) VALUES(?,?,?,?,?,?,?,NULL,?)`)
    .bind(codeHash, auth.clientId, auth.redirectUri, auth.resource, auth.scope, auth.codeChallenge, now + CODE_TTL_SECONDS, now).run();
  const redirect = new URL(auth.redirectUri);
  redirect.searchParams.set("code", code);
  if (auth.state) redirect.searchParams.set("state", auth.state);
  return Response.redirect(redirect.toString(), 302);
}

async function issueTokenPair(env, clientId, resource, scope, parentRefreshHash = null) {
  const accessToken = randomToken(32);
  const refreshToken = randomToken(48);
  const accessHash = await sha256Hex(accessToken);
  const refreshHash = await sha256Hex(refreshToken);
  const now = nowSeconds();
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO mcp_oauth_tokens(token_hash,token_type,client_id,resource,scope,expires_at,revoked_at,parent_refresh_hash,created_at) VALUES(?,'access',?,?,?,?,NULL,?,?)`)
      .bind(accessHash, clientId, resource, scope, now + ACCESS_TTL_SECONDS, parentRefreshHash || refreshHash, now),
    env.DB.prepare(`INSERT INTO mcp_oauth_tokens(token_hash,token_type,client_id,resource,scope,expires_at,revoked_at,parent_refresh_hash,created_at) VALUES(?,'refresh',?,?,?,?,NULL,NULL,?)`)
      .bind(refreshHash, clientId, resource, scope, now + REFRESH_TTL_SECONDS, now)
  ]);
  return { access_token: accessToken, token_type: "Bearer", expires_in: ACCESS_TTL_SECONDS, refresh_token: refreshToken, scope };
}

async function handleToken(request, env) {
  if (request.method !== "POST") return oauthJson({ error: "invalid_request" }, 405);
  if (!env.DB) return oauthJson({ error: "temporarily_unavailable" }, 503);
  const type = request.headers.get("content-type") || "";
  if (!type.includes("application/x-www-form-urlencoded")) return oauthJson({ error: "invalid_request" }, 400);
  const form = new URLSearchParams(await request.text());
  const grant = String(form.get("grant_type") || "");
  const clientId = String(form.get("client_id") || "");
  const resource = String(form.get("resource") || "");
  if (!clientId || resource !== MCP_RESOURCE) return oauthJson({ error: "invalid_request" }, 400);
  await cleanupOauth(env);

  if (grant === "authorization_code") {
    const code = String(form.get("code") || "");
    const redirectUri = String(form.get("redirect_uri") || "");
    const verifier = String(form.get("code_verifier") || "");
    if (!code || verifier.length < 43 || verifier.length > 128) return oauthJson({ error: "invalid_grant" }, 400);
    const codeHash = await sha256Hex(code);
    const row = await env.DB.prepare(`SELECT code_hash,client_id,redirect_uri,resource,scope,code_challenge,expires_at,used_at FROM mcp_oauth_codes WHERE code_hash=?`).bind(codeHash).first();
    if (!row || row.used_at != null || Number(row.expires_at || 0) < nowSeconds()) return oauthJson({ error: "invalid_grant" }, 400);
    if (row.client_id !== clientId || row.redirect_uri !== redirectUri || row.resource !== resource) return oauthJson({ error: "invalid_grant" }, 400);
    const expected = await sha256Base64Url(verifier);
    if (!secureEqual(expected, row.code_challenge)) return oauthJson({ error: "invalid_grant" }, 400);
    const consumed = await env.DB.prepare(`UPDATE mcp_oauth_codes SET used_at=? WHERE code_hash=? AND used_at IS NULL`).bind(nowSeconds(), codeHash).run();
    if (Number(consumed.meta?.changes || 0) !== 1) return oauthJson({ error: "invalid_grant" }, 400);
    return oauthJson(await issueTokenPair(env, clientId, resource, row.scope));
  }

  if (grant === "refresh_token") {
    const refreshToken = String(form.get("refresh_token") || "");
    if (!refreshToken) return oauthJson({ error: "invalid_grant" }, 400);
    const refreshHash = await sha256Hex(refreshToken);
    const row = await env.DB.prepare(`SELECT token_hash,client_id,resource,scope,expires_at,revoked_at FROM mcp_oauth_tokens WHERE token_hash=? AND token_type='refresh'`).bind(refreshHash).first();
    if (!row || row.revoked_at != null || Number(row.expires_at || 0) < nowSeconds()) return oauthJson({ error: "invalid_grant" }, 400);
    if (row.client_id !== clientId || row.resource !== resource) return oauthJson({ error: "invalid_grant" }, 400);
    const now = nowSeconds();
    const revoked = await env.DB.prepare(`UPDATE mcp_oauth_tokens SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL`).bind(now, refreshHash).run();
    if (Number(revoked.meta?.changes || 0) !== 1) return oauthJson({ error: "invalid_grant" }, 400);
    await env.DB.prepare(`UPDATE mcp_oauth_tokens SET revoked_at=? WHERE parent_refresh_hash=? AND token_type='access' AND revoked_at IS NULL`).bind(now, refreshHash).run();
    return oauthJson(await issueTokenPair(env, clientId, resource, row.scope, refreshHash));
  }

  return oauthJson({ error: "unsupported_grant_type" }, 400);
}

async function verifyAccessToken(request, env) {
  if (!env.DB) return null;
  const auth = request.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!token || token.length > 512) return null;
  const tokenHash = await sha256Hex(token);
  const row = await env.DB.prepare(`SELECT client_id,resource,scope,expires_at,revoked_at FROM mcp_oauth_tokens WHERE token_hash=? AND token_type='access'`).bind(tokenHash).first();
  if (!row || row.revoked_at != null || Number(row.expires_at || 0) < nowSeconds()) return null;
  if (row.resource !== MCP_RESOURCE) return null;
  const scopes = new Set(String(row.scope || "").split(/\s+/).filter(Boolean));
  if (!scopes.has(OAUTH_SCOPE)) return null;
  return row;
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
    context: { source: "chatgpt-oauth-mcp", strength: String(args?.strength || "strong"), transport: "direct-worker-mcp-oauth2" }
  };
  const target = new URL(request.url);
  target.pathname = "/content-intelligence/interests/ingest";
  target.search = "";
  const internalRequest = new Request(target.toString(), {
    method: "POST",
    headers: { authorization: `Bearer ${String(env.RUNNER3_CORE_TOKEN || "")}`, "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  const response = await handleContentIntelligence(internalRequest, env, target);
  if (!response) throw new Error("interest_ingest_route_missing");
  const result = await response.json().catch(() => ({ ok: false, error: "invalid_core_response" }));
  if (!response.ok || result?.ok !== true || result?.durable !== true) {
    return { content: [{ type: "text", text: `Interest save failed: ${String(result?.error || `HTTP ${response.status}`)}` }], structuredContent: { ok: false, durable: false, error: result?.error || `HTTP_${response.status}` }, isError: true };
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
  if (!message || message.jsonrpc !== "2.0" || typeof message.method !== "string") return jsonRpcError(message?.id, -32600, "Invalid Request");
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
    if (!(await verifyAccessToken(request, env))) return jsonRpc(message.id, authRequiredResult("Link Runner3 Content Intelligence to save interests."));
    try {
      return jsonRpc(message.id, await saveInterest(message?.params?.arguments || {}, request, env));
    } catch (error) {
      return jsonRpc(message.id, { content: [{ type: "text", text: `Interest save failed: ${String(error?.message || error)}` }], structuredContent: { ok: false, durable: false, error: String(error?.message || error) }, isError: true });
    }
  }
  return message.id === undefined ? null : jsonRpcError(message.id, -32601, "Method not found");
}

async function handleMcp(request, env) {
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-headers": "authorization, content-type, accept, mcp-protocol-version",
        "access-control-max-age": "600"
      }
    });
  }
  if (request.method !== "POST") return jsonResponse({ error: "method_not_allowed" }, 405, { "www-authenticate": authChallenge("invalid_token", "Use OAuth linking for write tools") });
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

export async function handleChatGptMcp(request, env, url) {
  if (url.pathname === "/.well-known/oauth-protected-resource" || url.pathname === "/.well-known/oauth-protected-resource/mcp") {
    if (request.method !== "GET") return oauthJson({ error: "method_not_allowed" }, 405);
    return oauthJson(protectedResourceMetadata());
  }
  if (url.pathname === "/.well-known/oauth-authorization-server") {
    if (request.method !== "GET") return oauthJson({ error: "method_not_allowed" }, 405);
    return oauthJson(authorizationServerMetadata());
  }
  if (url.pathname === "/oauth/authorize") {
    if (!new Set(["GET", "POST"]).has(request.method)) return oauthJson({ error: "method_not_allowed" }, 405);
    return handleAuthorize(request, env, url);
  }
  if (url.pathname === "/oauth/token") return handleToken(request, env);
  if (url.pathname === "/mcp") return handleMcp(request, env);
  return null;
}
