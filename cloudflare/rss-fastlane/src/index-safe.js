import app from "./index-get.js";

const DIRECT_ONLY_HOSTS = Object.freeze({
  projectsyndicate: ["project-syndicate.org"],
  economist: ["economist.com"],
  theatlantic: ["theatlantic.com"],
});
const MIN_TEXT_CHARS = 600;
const MAX_TEXT_CHARS = 120000;
const DIRECT_TIMEOUT_MS = 6000;
const UA = "Mozilla/5.0 (compatible; runner-3-rss-fastlane/1.0; +https://github.com/louisalviss/runner-3)";

function json(value, status = 200) {
  return Response.json(value, {
    status,
    headers: {
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
    },
  });
}

function hostMatches(hostname, suffix) {
  const host = hostname.toLowerCase();
  const allowed = suffix.toLowerCase();
  return host === allowed || host.endsWith(`.${allowed}`);
}

function decodeEntities(input) {
  const named = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", ndash: "–", mdash: "—", hellip: "…", rsquo: "’", lsquo: "‘", rdquo: "”", ldquo: "“" };
  return String(input ?? "").replace(/&(#x?[0-9a-f]+|[a-z][a-z0-9]+);/gi, (whole, entity) => {
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

async function directOnlyFetch(request, env, incoming) {
  const sourceKey = String(incoming.searchParams.get("sourceKey") || "").trim().toLowerCase();
  const canonicalUrl = String(incoming.searchParams.get("url") || "").trim();
  const title = String(incoming.searchParams.get("title") || canonicalUrl).trim();
  const allowed = DIRECT_ONLY_HOSTS[sourceKey];
  if (!allowed || !canonicalUrl) return json({ ok: false, error: "unsupported direct-only source" }, 400);

  let parsed;
  try { parsed = new URL(canonicalUrl); } catch { return json({ ok: false, error: "invalid canonicalUrl" }, 400); }
  if ((parsed.protocol !== "https:" && parsed.protocol !== "http:") || parsed.username || parsed.password || parsed.port) {
    return json({ ok: false, error: "invalid canonicalUrl" }, 400);
  }
  if (!allowed.some((suffix) => hostMatches(parsed.hostname, suffix))) {
    return json({ ok: false, error: "canonicalUrl host not allowed" }, 400);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), DIRECT_TIMEOUT_MS);
  try {
    const response = await fetch(parsed.toString(), {
      redirect: "follow",
      signal: controller.signal,
      headers: { "user-agent": UA, accept: "text/html,application/xhtml+xml,*/*;q=0.8", dnt: "1" },
    });
    if (response.status !== 200) return json({ ok: false, error: `direct HTTP ${response.status}`, fetched: [], errors: [{ sourceKey, canonicalUrl, error: `direct HTTP ${response.status}` }] }, 502);
    const raw = await response.text();
    const text = htmlToText(raw);
    if (text.length < MIN_TEXT_CHARS) {
      return json({ ok: false, error: `direct text too thin: ${text.length}`, fetched: [], errors: [{ sourceKey, canonicalUrl, error: `direct text too thin: ${text.length}` }] }, 502);
    }
    const fetched = {
      sourceKey,
      sourceName: sourceKey,
      canonicalUrl: parsed.toString(),
      title,
      itemType: "article",
      route: "direct",
      resolvedUrl: response.url || parsed.toString(),
      extractedTitle: title,
      rawText: text.slice(0, MAX_TEXT_CHARS),
      truncated: text.length > MAX_TEXT_CHARS,
      coverage: "best_accessible",
      chars: Math.min(text.length, MAX_TEXT_CHARS),
    };
    return json({ ok: true, serviceVersion: "direct-only-2026-08-25.1", requestedCount: 1, fetchedCount: 1, errorCount: 0, fetched: [fetched], errors: [] });
  } catch (error) {
    const detail = `${error?.name || "Error"}: ${error?.message || error}`;
    return json({ ok: false, error: detail, fetched: [], errors: [{ sourceKey, canonicalUrl, error: detail }] }, 502);
  } finally {
    clearTimeout(timer);
  }
}

export default {
  async fetch(request, env, ctx) {
    const incoming = new URL(request.url);
    if (request.method === "GET" && incoming.pathname === "/v1/rss/fetch" && incoming.searchParams.get("accessMode") === "direct_only") {
      return directOnlyFetch(request, env, incoming);
    }
    return app.fetch(request, env, ctx);
  },
};
