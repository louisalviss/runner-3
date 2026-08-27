const MIN_TTL_SECONDS = 60;
const MAX_TTL_SECONDS = 3600;
const MAX_ARTIFACT_KEY_CHARS = 900;
const textEncoder = new TextEncoder();

function json(data, status = 200) {
  return Response.json(data, {
    status,
    headers: {
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
    },
  });
}

function coreToken(env) {
  return typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
}

function requireBearer(request, env) {
  const expected = coreToken(env);
  if (!expected) return json({ ok: false, error: "DELIVERY_AUTH_NOT_CONFIGURED" }, 503);
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function cleanSegment(value) {
  const text = String(value || "").trim();
  if (!text || text === "." || text === ".." || /[\\/\u0000-\u001f\u007f]/.test(text)) return null;
  return text;
}

function cleanArtifact(projectRaw, scopeRaw, nameRaw) {
  const project = cleanSegment(projectRaw);
  const scope = cleanSegment(scopeRaw);
  if (!project || !scope) return null;
  const nameParts = String(nameRaw || "").split("/").map(cleanSegment);
  if (!nameParts.length || nameParts.some((part) => !part)) return null;
  const name = nameParts.join("/");
  const key = `core/${project}/${scope}/${name}`;
  if (key.length > MAX_ARTIFACT_KEY_CHARS) return null;
  return { project, scope, name, key, nameParts };
}

function b64url(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
}

function fromB64url(value) {
  const text = String(value || "").replaceAll("-", "+").replaceAll("_", "/");
  const padded = text + "=".repeat((4 - (text.length % 4)) % 4);
  const binary = atob(padded);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

async function signingKey(env) {
  const secret = typeof env.RUNNER3_DELIVERY_SECRET === "string" && env.RUNNER3_DELIVERY_SECRET.trim()
    ? env.RUNNER3_DELIVERY_SECRET.trim()
    : coreToken(env);
  if (!secret) throw new Error("DELIVERY_SIGNING_NOT_CONFIGURED");
  const derived = await crypto.subtle.digest("SHA-256", textEncoder.encode(`runner3-delivery-v1\n${secret}`));
  return crypto.subtle.importKey("raw", derived, { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

function canonicalMessage(pathname, expires) {
  return `GET\n${pathname}\n${expires}`;
}

async function signatureFor(pathname, expires, env) {
  const sig = await crypto.subtle.sign("HMAC", await signingKey(env), textEncoder.encode(canonicalMessage(pathname, expires)));
  return b64url(new Uint8Array(sig));
}

async function verifySignature(pathname, expires, signature, env) {
  let supplied;
  try {
    supplied = fromB64url(signature);
  } catch {
    return false;
  }
  try {
    return await crypto.subtle.verify("HMAC", await signingKey(env), supplied, textEncoder.encode(canonicalMessage(pathname, expires)));
  } catch {
    return false;
  }
}

function deliveryPath(artifact) {
  return ["", "delivery", artifact.project, artifact.scope, ...artifact.nameParts].map((part, i) => i === 0 ? "" : encodeURIComponent(part)).join("/");
}

function attachmentFilename(name) {
  const base = name.split("/").pop() || "artifact.bin";
  return base.replace(/[\r\n"\\]/g, "_").slice(0, 180) || "artifact.bin";
}

function objectHeaders(object, artifact) {
  const headers = new Headers();
  if (typeof object.writeHttpMetadata === "function") object.writeHttpMetadata(headers);
  if (object.httpEtag) headers.set("etag", object.httpEtag);
  if (Number.isFinite(object.size)) headers.set("content-length", String(object.size));
  headers.set("cache-control", "private, no-store, max-age=0");
  headers.set("content-disposition", `attachment; filename="${attachmentFilename(artifact.name)}"`);
  headers.set("x-content-type-options", "nosniff");
  headers.set("referrer-policy", "no-referrer");
  headers.set("x-runner3-delivery-project", artifact.project);
  headers.set("x-runner3-delivery-scope", artifact.scope);
  return headers;
}

export async function handleDelivery(request, env, url) {
  if (request.method === "POST" && url.pathname === "/delivery-links") {
    if (!env.ARTIFACTS) return json({ ok: false, error: "R2_NOT_BOUND" }, 503);
    const authError = requireBearer(request, env);
    if (authError) return authError;
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "INVALID_JSON" }, 400);
    }
    const artifact = cleanArtifact(body?.project, body?.scope, body?.name);
    if (!artifact) return json({ ok: false, error: "INVALID_ARTIFACT" }, 400);
    const requestedTtl = Number(body?.ttl_seconds || 900);
    const ttl = Number.isFinite(requestedTtl) ? Math.floor(requestedTtl) : 900;
    if (ttl < MIN_TTL_SECONDS || ttl > MAX_TTL_SECONDS) {
      return json({ ok: false, error: `TTL_OUT_OF_RANGE_${MIN_TTL_SECONDS}_${MAX_TTL_SECONDS}` }, 400);
    }
    const object = await env.ARTIFACTS.head(artifact.key);
    if (!object) return json({ ok: false, error: "ARTIFACT_NOT_FOUND" }, 404);
    const expires = Math.floor(Date.now() / 1000) + ttl;
    const pathname = deliveryPath(artifact);
    const sig = await signatureFor(pathname, expires, env);
    const signed = new URL(pathname, url.origin);
    signed.searchParams.set("exp", String(expires));
    signed.searchParams.set("sig", sig);
    return json({
      ok: true,
      delivery: {
        url: signed.toString(),
        expires_at_unix: expires,
        ttl_seconds: ttl,
        project: artifact.project,
        scope: artifact.scope,
        name: artifact.name,
        key: artifact.key,
        bytes: Number.isFinite(object.size) ? object.size : null,
        etag: object.httpEtag || object.etag || null,
      },
    });
  }

  if (request.method === "GET" && url.pathname.startsWith("/delivery/")) {
    if (!env.ARTIFACTS) return json({ ok: false, error: "R2_NOT_BOUND" }, 503);
    let segments;
    try {
      segments = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);
    } catch {
      return json({ ok: false, error: "INVALID_PATH_ENCODING" }, 400);
    }
    if (segments.length < 4 || segments[0] !== "delivery") return null;
    const artifact = cleanArtifact(segments[1], segments[2], segments.slice(3).join("/"));
    if (!artifact) return json({ ok: false, error: "INVALID_ARTIFACT" }, 400);
    const expires = Number(url.searchParams.get("exp") || 0);
    const signature = String(url.searchParams.get("sig") || "");
    const now = Math.floor(Date.now() / 1000);
    if (!Number.isInteger(expires) || expires <= 0 || !signature) return json({ ok: false, error: "DELIVERY_SIGNATURE_REQUIRED" }, 401);
    if (expires < now) return json({ ok: false, error: "DELIVERY_LINK_EXPIRED" }, 410);
    if (expires > now + MAX_TTL_SECONDS + 60) return json({ ok: false, error: "DELIVERY_EXPIRY_INVALID" }, 401);
    const valid = await verifySignature(url.pathname, expires, signature, env);
    if (!valid) return json({ ok: false, error: "DELIVERY_SIGNATURE_INVALID" }, 401);
    const object = await env.ARTIFACTS.get(artifact.key);
    if (!object) return json({ ok: false, error: "ARTIFACT_NOT_FOUND" }, 404);
    return new Response(object.body, { status: 200, headers: objectHeaders(object, artifact) });
  }

  return null;
}
