const AUDIO_PREFIX = "audio-library/";
const MAX_AUDIO_KEY_CHARS = 900;
const MAX_LIST_LIMIT = 1000;
const REDDIT_UA = "runner3-core-audio/1.0 (+public read-only acquisition)";

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

function requireAudioAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return json({ ok: false, error: "AUDIO_AUTH_NOT_CONFIGURED" }, 503);
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function requireAudioBucket(env) {
  if (!env.AUDIO_MEDIA) return json({ ok: false, error: "AUDIO_MEDIA_NOT_BOUND" }, 503);
  return null;
}

function cleanAudioKey(value) {
  let key;
  try { key = decodeURIComponent(String(value || "")); } catch { return null; }
  key = key.replace(/^\/+/, "");
  if (!key.startsWith(AUDIO_PREFIX) || key.length > MAX_AUDIO_KEY_CHARS) return null;
  if (/[\\\u0000-\u001f\u007f]/.test(key)) return null;
  if (key.split("/").some((part) => part === "." || part === "..")) return null;
  return key;
}

function objectHeaders(object, key) {
  const headers = new Headers();
  if (typeof object.writeHttpMetadata === "function") object.writeHttpMetadata(headers);
  if (object.httpEtag) headers.set("etag", object.httpEtag);
  if (Number.isFinite(object.size)) headers.set("content-length", String(object.size));
  headers.set("cache-control", "private, no-store");
  headers.set("x-runner3-audio-key", key);
  return headers;
}

async function handleAudioObject(request, env, url) {
  const bucketError = requireAudioBucket(env);
  if (bucketError) return bucketError;
  const authError = requireAudioAuth(request, env);
  if (authError) return authError;

  const key = cleanAudioKey(url.pathname.slice("/audio-media/".length));
  if (!key) return json({ ok: false, error: "INVALID_AUDIO_KEY" }, 400);

  if (request.method === "GET" || request.method === "HEAD") {
    const object = request.method === "HEAD" ? await env.AUDIO_MEDIA.head(key) : await env.AUDIO_MEDIA.get(key);
    if (!object) return json({ ok: false, error: "NOT_FOUND" }, 404);
    const headers = objectHeaders(object, key);
    if (request.method === "HEAD") return new Response(null, { status: 200, headers });
    return new Response(object.body, { status: 200, headers });
  }

  if (request.method === "PUT") {
    if (!request.body) return json({ ok: false, error: "BODY_REQUIRED" }, 400);
    const contentType = request.headers.get("content-type") || "application/octet-stream";
    const source = (request.headers.get("x-runner3-source") || "unknown").slice(0, 200);
    const object = await env.AUDIO_MEDIA.put(key, request.body, {
      httpMetadata: { contentType },
      customMetadata: { source, scope: "audio-library" },
    });
    return json({
      ok: true,
      key,
      size: object?.size ?? null,
      etag: object?.httpEtag || object?.etag || null,
    });
  }

  if (request.method === "DELETE") {
    await env.AUDIO_MEDIA.delete(key);
    return json({ ok: true, key, deleted: true });
  }

  return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
}

async function handleAudioList(request, env, url) {
  const bucketError = requireAudioBucket(env);
  if (bucketError) return bucketError;
  const authError = requireAudioAuth(request, env);
  if (authError) return authError;
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);

  const prefix = cleanAudioKey(url.searchParams.get("prefix") || AUDIO_PREFIX);
  if (!prefix) return json({ ok: false, error: "INVALID_AUDIO_PREFIX" }, 400);
  const requested = Number(url.searchParams.get("limit") || 100);
  const limit = Number.isFinite(requested) ? Math.max(1, Math.min(MAX_LIST_LIMIT, Math.floor(requested))) : 100;
  const cursor = url.searchParams.get("cursor") || undefined;
  const page = await env.AUDIO_MEDIA.list({ prefix, limit, cursor });
  return json({
    ok: true,
    prefix,
    truncated: Boolean(page.truncated),
    cursor: page.truncated ? page.cursor || null : null,
    objects: (page.objects || []).map((object) => ({
      key: object.key,
      size: object.size,
      etag: object.httpEtag || object.etag || null,
      uploaded: object.uploaded ? object.uploaded.toISOString() : null,
    })),
  });
}

function parseAllowedRedditUrl(value) {
  let u;
  try { u = new URL(String(value || "")); } catch { return null; }
  const host = u.hostname.toLowerCase();
  if (u.protocol !== "https:" || !(host === "reddit.com" || host.endsWith(".reddit.com"))) return null;
  if (u.username || u.password) return null;
  u.hash = "";
  return u;
}

function htmlDecode(value) {
  return String(value || "")
    .replaceAll("&amp;", "&")
    .replaceAll("&#x2F;", "/")
    .replaceAll("&#47;", "/")
    .replaceAll("&quot;", "\"")
    .replaceAll("\\u002F", "/")
    .replaceAll("\\/", "/");
}

function canonicalCandidate(value) {
  const decoded = htmlDecode(value);
  const match = decoded.match(/https?:\/\/(?:www\.)?reddit\.com(\/r\/[^\s"'<>]+\/comments\/[a-z0-9]+(?:\/[^\s"'<>?]*)?)/i)
    || decoded.match(/(\/r\/[^\s"'<>]+\/comments\/[a-z0-9]+(?:\/[^\s"'<>?]*)?)/i)
    || decoded.match(/https?:\/\/(?:www\.)?reddit\.com(\/comments\/[a-z0-9]+(?:\/[^\s"'<>?]*)?)/i);
  if (!match) return null;
  const path = match[1] || match[0];
  const url = path.startsWith("http") ? path : `https://www.reddit.com${path}`;
  const parsed = parseAllowedRedditUrl(url);
  return parsed ? parsed.toString().split("?")[0] : null;
}

function extractCanonicalFromHtml(body) {
  const text = htmlDecode(body || "");
  const patterns = [
    /<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']/i,
    /<link[^>]+href=["']([^"']+)["'][^>]+rel=["']canonical["']/i,
    /<meta[^>]+property=["']og:url["'][^>]+content=["']([^"']+)["']/i,
    /<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:url["']/i,
  ];
  for (const pattern of patterns) {
    const m = text.match(pattern);
    const candidate = m && canonicalCandidate(m[1]);
    if (candidate) return candidate;
  }
  return canonicalCandidate(text);
}

function redditHeaders(accept = "text/html,application/xhtml+xml,*/*") {
  return {
    "user-agent": REDDIT_UA,
    accept,
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    pragma: "no-cache",
  };
}

async function resolveReddit(rawUrl) {
  const input = parseAllowedRedditUrl(rawUrl);
  if (!input) return { canonicalUrl: null, diagnostics: ["invalid-reddit-url"] };
  if (/\/comments\/[a-z0-9]+/i.test(input.pathname)) {
    return { canonicalUrl: input.toString().split("?")[0], diagnostics: ["already-canonical"] };
  }
  const candidates = [input.toString()];
  if (input.hostname !== "www.reddit.com") {
    const www = new URL(input.toString());
    www.hostname = "www.reddit.com";
    candidates.push(www.toString());
  }
  const diagnostics = [];
  for (const target of candidates) {
    try {
      const response = await fetch(target, { headers: redditHeaders(), redirect: "manual" });
      const location = response.headers.get("location");
      diagnostics.push(`manual:${response.status}:${location ? "location" : "no-location"}`);
      if (location) {
        const found = canonicalCandidate(new URL(location, target).toString());
        if (found) return { canonicalUrl: found, diagnostics };
      }
      const found = extractCanonicalFromHtml(await response.text());
      if (found) return { canonicalUrl: found, diagnostics };
    } catch (error) {
      diagnostics.push(`manual-error:${String(error).slice(0, 80)}`);
    }
    try {
      const response = await fetch(target, { headers: redditHeaders(), redirect: "follow" });
      diagnostics.push(`follow:${response.status}:${response.url ? "url" : "no-url"}`);
      const byUrl = canonicalCandidate(response.url || "");
      if (byUrl) return { canonicalUrl: byUrl, diagnostics };
      const found = extractCanonicalFromHtml(await response.text());
      if (found) return { canonicalUrl: found, diagnostics };
    } catch (error) {
      diagnostics.push(`follow-error:${String(error).slice(0, 80)}`);
    }
  }
  return { canonicalUrl: null, diagnostics };
}

function cleanRaw(value) {
  return String(value || "").replace(/\r/g, "").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

function redditJsonToRaw(data) {
  if (!Array.isArray(data) || data.length < 2) throw new Error("reddit-json-shape");
  const post = data?.[0]?.data?.children?.[0]?.data || {};
  const title = cleanRaw(post.title || "Reddit");
  const selftext = cleanRaw(post.selftext || "");
  const comments = [];
  function walk(children, depth = 0) {
    if (!Array.isArray(children) || depth > 5 || comments.length >= 300) return;
    for (const child of children) {
      if (comments.length >= 300) break;
      if (child?.kind !== "t1") continue;
      const row = child?.data || {};
      const body = cleanRaw(row.body || "");
      if (body.length >= 40) comments.push(`[Comment${Number.isFinite(row.score) ? ` score ${row.score}` : ""}] ${body}`);
      if (row.replies && typeof row.replies === "object") walk(row.replies?.data?.children || [], depth + 1);
    }
  }
  walk(data?.[1]?.data?.children || []);
  const parts = [];
  if (selftext) parts.push(`[Post]\n${selftext}`);
  parts.push(...comments);
  return { title, rawText: cleanRaw(parts.join("\n\n")) };
}

async function fetchRedditJson(canonicalUrl) {
  const parsed = parseAllowedRedditUrl(canonicalUrl);
  if (!parsed) return { ok: false, diagnostics: ["canonical-invalid"] };
  const path = parsed.pathname.replace(/\/$/, "");
  const idMatch = path.match(/\/comments\/([a-z0-9]+)/i);
  const endpoints = [
    `https://www.reddit.com${path}.json?raw_json=1&limit=100&sort=top`,
    `https://old.reddit.com${path}.json?raw_json=1&limit=100&sort=top`,
  ];
  if (idMatch) endpoints.push(`https://www.reddit.com/comments/${idMatch[1]}.json?raw_json=1&limit=100&sort=top`);
  const diagnostics = [];
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, { headers: redditHeaders("application/json,text/plain,*/*"), redirect: "follow" });
      const text = await response.text();
      diagnostics.push(`json:${new URL(endpoint).hostname}:${response.status}:${text.length}`);
      if (response.status !== 200 || text.length < 200) continue;
      let data;
      try { data = JSON.parse(text); } catch { continue; }
      const parsedRaw = redditJsonToRaw(data);
      if (parsedRaw.rawText.length >= 400) return { ok: true, ...parsedRaw, diagnostics };
    } catch (error) {
      diagnostics.push(`json-error:${String(error).slice(0, 80)}`);
    }
  }
  return { ok: false, diagnostics };
}

async function handleAudioReddit(request, env) {
  const authError = requireAudioAuth(request, env);
  if (authError) return authError;
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "INVALID_JSON" }, 400); }
  const source = parseAllowedRedditUrl(body?.url);
  if (!source) return json({ ok: false, error: "ONLY_HTTPS_REDDIT_ALLOWED" }, 400);
  const resolved = await resolveReddit(source.toString());
  if (!resolved.canonicalUrl) return json({ ok: false, canonicalUrl: null, diagnostics: resolved.diagnostics }, 502);
  const fetched = await fetchRedditJson(resolved.canonicalUrl);
  return json({
    ok: Boolean(fetched.ok),
    canonicalUrl: resolved.canonicalUrl,
    sourceLabel: "Reddit",
    title: fetched.title || "Reddit",
    rawText: fetched.rawText || "",
    diagnostics: [...resolved.diagnostics, ...(fetched.diagnostics || [])],
  }, fetched.ok ? 200 : 502);
}

export async function handleAudioMedia(request, env, url = new URL(request.url)) {
  if (url.pathname === "/audio-media") return handleAudioList(request, env, url);
  if (url.pathname.startsWith("/audio-media/")) return handleAudioObject(request, env, url);
  if (url.pathname === "/audio-reddit/source") return handleAudioReddit(request, env);
  return null;
}
