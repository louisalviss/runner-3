const VERSION = "2026-08-22.1";
const MIN_TEXT_CHARS = 600;
const MAX_TEXT_CHARS = 120_000;
const MAX_BATCH_ITEMS = 20;
const MAX_REQUEST_BYTES = 64 * 1024;
const DIRECT_TIMEOUT_MS = 6_000;
const JINA_TIMEOUT_MS = 20_000;
const TTL_DAYS = 7;

const SOURCE_HOSTS = Object.freeze({
  tinhte: ["tinhte.vn"],
  genk: ["genk.vn"],
  gamek: ["gamek.vn"],
  fulcrum: ["fulcrum.sg"],
  nghiencuuquocte: ["nghiencuuquocte.org"],
  noema: ["noemamag.com"],
  projectsyndicate: ["project-syndicate.org"],
  economist: ["economist.com"],
  theatlantic: ["theatlantic.com"],
  grimlogs: ["grimlogs.com"],
  scientificamerican: ["scientificamerican.com"],
  quanta: ["quantamagazine.org"],
  hoquoctuan: ["hoquoctuan.substack.com"],
  vohoanghac: ["vohoanghac.com"],
  vnhacker: ["vnhacker.substack.com"],
});

const UA = "Mozilla/5.0 (compatible; runner-3-rss-fastlane/1.0; +https://github.com/louisalviss/runner-3)";

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET,POST,OPTIONS",
      "access-control-allow-headers": "content-type",
    },
  });
}

function cleanText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function normalizeUrl(value) {
  return String(value ?? "").trim();
}

function hostMatches(hostname, suffix) {
  const host = hostname.toLowerCase();
  const allowed = suffix.toLowerCase();
  return host === allowed || host.endsWith(`.${allowed}`);
}

function validateSourceUrl(sourceKey, value) {
  const allowedHosts = SOURCE_HOSTS[sourceKey];
  if (!allowedHosts) return { ok: false, error: `unsupported sourceKey: ${sourceKey}` };

  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return { ok: false, error: "invalid canonicalUrl" };
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return { ok: false, error: "canonicalUrl must be HTTP(S)" };
  }
  if (parsed.username || parsed.password || parsed.port) {
    return { ok: false, error: "canonicalUrl credentials/ports are not allowed" };
  }
  if (!allowedHosts.some((suffix) => hostMatches(parsed.hostname, suffix))) {
    return { ok: false, error: `host ${parsed.hostname} is not allowed for ${sourceKey}` };
  }
  return { ok: true, url: parsed.toString() };
}

function decodeEntities(input) {
  const named = {
    amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ",
    ndash: "–", mdash: "—", hellip: "…", rsquo: "’", lsquo: "‘",
    rdquo: "”", ldquo: "“", copy: "©", reg: "®",
  };
  return input.replace(/&(#x?[0-9a-f]+|[a-z][a-z0-9]+);/gi, (whole, entity) => {
    if (entity[0] === "#") {
      const raw = entity.slice(1);
      const base = raw[0]?.toLowerCase() === "x" ? 16 : 10;
      const digits = base === 16 ? raw.slice(1) : raw;
      const code = Number.parseInt(digits, base);
      if (Number.isFinite(code) && code > 0 && code <= 0x10ffff) {
        try { return String.fromCodePoint(code); } catch { return whole; }
      }
      return whole;
    }
    return named[entity.toLowerCase()] ?? whole;
  });
}

function htmlToText(rawHtml) {
  let html = String(rawHtml ?? "");
  const article = html.match(/<article\b[^>]*>([\s\S]*?)<\/article\s*>/i);
  const main = html.match(/<main\b[^>]*>([\s\S]*?)<\/main\s*>/i);
  html = article?.[1] || main?.[1] || html;

  html = html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style|nav|footer|header|aside|form|svg|noscript)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, " ")
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<\/(p|li|h1|h2|h3|h4|blockquote|div|section)\s*>/gi, "\n\n")
    .replace(/<[^>]+>/g, " ");

  return decodeEntities(html)
    .replace(/\r/g, "")
    .replace(/[\t ]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function extractHtmlTitle(rawHtml) {
  const match = String(rawHtml ?? "").match(/<title\b[^>]*>([\s\S]*?)<\/title\s*>/i);
  return match ? cleanText(decodeEntities(match[1].replace(/<[^>]+>/g, " "))) : "";
}

async function fetchWithTimeout(url, init, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal, redirect: "follow" });
  } finally {
    clearTimeout(timer);
  }
}

async function extractDirect(url) {
  const response = await fetchWithTimeout(url, {
    headers: {
      "user-agent": UA,
      accept: "text/html,application/xhtml+xml,*/*;q=0.8",
      dnt: "1",
    },
  }, DIRECT_TIMEOUT_MS);
  if (response.status !== 200) throw new Error(`direct HTTP ${response.status}`);

  const raw = await response.text();
  const text = htmlToText(raw);
  if (text.length < MIN_TEXT_CHARS) throw new Error(`direct text too thin: ${text.length}`);

  return {
    route: "direct",
    resolvedUrl: response.url || url,
    extractedTitle: extractHtmlTitle(raw) || "Article",
    rawText: text.slice(0, MAX_TEXT_CHARS),
    truncated: text.length > MAX_TEXT_CHARS,
    coverage: "best_accessible",
  };
}

async function extractJina(url) {
  const target = `https://r.jina.ai/${url}`;
  const response = await fetchWithTimeout(target, {
    headers: {
      "user-agent": UA,
      accept: "text/plain",
      "x-no-cache": "true",
      dnt: "1",
    },
  }, JINA_TIMEOUT_MS);
  if (response.status !== 200) throw new Error(`jina HTTP ${response.status}`);

  const raw = await response.text();
  if (raw.length < MIN_TEXT_CHARS) throw new Error(`jina text too thin: ${raw.length}`);

  const title = raw.match(/^Title:\s*(.+)$/mi)?.[1]?.trim() || "Article";
  const resolvedUrl = raw.match(/^URL Source:\s*(https?:\/\/\S+)/mi)?.[1]?.trim() || url;
  const body = raw
    .replace(/^(Title|URL Source|Published Time|Markdown Content):\s*.*$/gim, "")
    .trim();
  if (body.length < MIN_TEXT_CHARS) throw new Error(`jina body too thin: ${body.length}`);

  return {
    route: "jina-live",
    resolvedUrl,
    extractedTitle: title,
    rawText: body.slice(0, MAX_TEXT_CHARS),
    truncated: body.length > MAX_TEXT_CHARS,
    coverage: "best_accessible",
  };
}

async function extractOne(item) {
  const errors = [];
  try {
    return { ok: true, item, result: await extractDirect(item.canonicalUrl) };
  } catch (error) {
    errors.push(`direct=${error?.name || "Error"}: ${error?.message || error}`);
  }
  try {
    return { ok: true, item, result: await extractJina(item.canonicalUrl) };
  } catch (error) {
    errors.push(`jina=${error?.name || "Error"}: ${error?.message || error}`);
  }
  return { ok: false, item, error: errors.join("; ").slice(0, 1200) };
}

function normalizeRequest(obj) {
  const requestId = cleanText(obj?.requestId).slice(0, 160);
  if (!requestId) throw new Error("requestId is required");
  if (!Array.isArray(obj?.items) || obj.items.length === 0) throw new Error("items[] is required");
  if (obj.items.length > MAX_BATCH_ITEMS) throw new Error(`too many items: ${obj.items.length} > ${MAX_BATCH_ITEMS}`);

  const items = [];
  const seen = new Set();
  const validationErrors = [];
  for (const raw of obj.items) {
    if (!raw || typeof raw !== "object") continue;
    const sourceKey = cleanText(raw.sourceKey).toLowerCase();
    const canonicalUrl = normalizeUrl(raw.canonicalUrl);
    const validated = validateSourceUrl(sourceKey, canonicalUrl);
    if (!validated.ok) {
      validationErrors.push({
        displayIndex: raw.displayIndex ?? null,
        sourceKey,
        canonicalUrl,
        error: validated.error,
      });
      continue;
    }
    if (seen.has(validated.url)) continue;
    seen.add(validated.url);
    items.push({
      displayIndex: raw.displayIndex ?? null,
      sourceKey,
      sourceName: cleanText(raw.sourceName) || null,
      canonicalUrl: validated.url,
      title: cleanText(raw.title) || validated.url,
      publishedAt: raw.publishedAt ?? null,
      contentHash: raw.contentHash ?? null,
      itemType: cleanText(raw.itemType) || "article",
    });
  }
  if (!items.length) throw new Error(validationErrors[0]?.error || "request has no valid items");
  return { requestId, items, validationErrors };
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function isoNow() {
  return new Date().toISOString();
}

function addDaysIso(isoString, days) {
  return new Date(new Date(isoString).getTime() + days * 86400_000).toISOString();
}

async function handleSelectedAnalysis(request, env) {
  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > MAX_REQUEST_BYTES) return jsonResponse({ ok: false, error: "request body too large" }, 413);

  const rawBody = await request.text();
  if (new TextEncoder().encode(rawBody).byteLength > MAX_REQUEST_BYTES) {
    return jsonResponse({ ok: false, error: "request body too large" }, 413);
  }

  let parsed;
  try { parsed = JSON.parse(rawBody); }
  catch { return jsonResponse({ ok: false, error: "invalid JSON" }, 400); }

  let normalized;
  try { normalized = normalizeRequest(parsed); }
  catch (error) { return jsonResponse({ ok: false, error: error.message }, 400); }

  const startedAt = isoNow();
  const startedMs = Date.now();
  const results = await Promise.all(normalized.items.map(extractOne));
  const fetched = [];
  const errors = [...normalized.validationErrors];

  for (const entry of results) {
    if (!entry.ok) {
      errors.push({
        displayIndex: entry.item.displayIndex,
        sourceKey: entry.item.sourceKey,
        canonicalUrl: entry.item.canonicalUrl,
        title: entry.item.title,
        error: entry.error,
      });
      continue;
    }
    fetched.push({ ...entry.item, ...entry.result, chars: entry.result.rawText.length });
  }

  const finishedAt = isoNow();
  const fingerprint = await sha256Hex(JSON.stringify(normalized.items.map((item) => item.canonicalUrl).sort()));
  const day = startedAt.slice(0, 10);
  const artifactKey = `rss-analysis/${day}/${fingerprint}.json`;
  const payload = {
    version: 1,
    serviceVersion: VERSION,
    requestId: normalized.requestId,
    startedAt,
    finishedAt,
    elapsedMs: Date.now() - startedMs,
    expiresAt: addDaysIso(finishedAt, TTL_DAYS),
    requestedCount: normalized.items.length + normalized.validationErrors.length,
    fetchedCount: fetched.length,
    errorCount: errors.length,
    items: fetched,
    errors,
  };

  let stored = false;
  let storageError = null;
  try {
    await env.RSS_ARTIFACTS.put(artifactKey, JSON.stringify(payload), {
      httpMetadata: { contentType: "application/json; charset=utf-8" },
      customMetadata: {
        requestId: normalized.requestId.slice(0, 80),
        expiresAt: payload.expiresAt,
        serviceVersion: VERSION,
      },
    });
    stored = true;
  } catch (error) {
    storageError = String(error?.message || error).slice(0, 500);
  }

  return jsonResponse({
    ok: errors.length === 0 && fetched.length > 0,
    serviceVersion: VERSION,
    requestId: normalized.requestId,
    startedAt,
    finishedAt,
    elapsedMs: payload.elapsedMs,
    requestedCount: payload.requestedCount,
    fetchedCount: fetched.length,
    errorCount: errors.length,
    artifact: { key: artifactKey, stored, expiresAt: payload.expiresAt, storageError },
    fetched,
    errors,
  }, fetched.length ? 200 : 502);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: jsonResponse({}).headers });

    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({
        ok: true,
        service: "runner3-rss-fastlane",
        version: VERSION,
        r2Bound: Boolean(env.RSS_ARTIFACTS),
        supportedSources: Object.keys(SOURCE_HOSTS),
        maxBatchItems: MAX_BATCH_ITEMS,
        ttlDays: TTL_DAYS,
      });
    }

    if (request.method === "POST" && url.pathname === "/v1/rss/selected-analysis") {
      return handleSelectedAnalysis(request, env);
    }

    return jsonResponse({ ok: false, error: "not found" }, 404);
  },
};
