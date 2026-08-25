import legacy from "./rss-wrapper.js";
import { handleRssLibrary } from "./src/rss-library.js";
import { handleRssReader } from "./src/rss-reader.js";
import { enrichFetchedArticleImages } from "./src/rss-image-enrich.js";

const BLOCKED_INCOMPLETE_SOURCE_IDS = new Set([
  "projectsyndicate-url-26a9686e21ebe4fa865d",
  "projectsyndicate-url-db223b141f372578df3c",
]);

const STRICT_READER_ARTICLE_ID = "nghiencuuquocte-url-6cd04807aefc80d9be93";

function fetchArticleId(request, url) {
  if (request.method !== "POST") return null;
  const match = url.pathname.match(/^\/api\/rss\/articles\/([^/]+)\/fetch$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

function blockedRestrictedFetch(request, url) {
  const articleId = fetchArticleId(request, url);
  if (!articleId || !BLOCKED_INCOMPLETE_SOURCE_IDS.has(articleId)) return null;
  return Response.json({
    ok: false,
    error: "INCOMPLETE_RESTRICTED_SOURCE_DIRECT_ONLY",
    articleId,
    message: "Full source is not available through the authorized direct route; refusing to store or translate an excerpt as a full article.",
  }, { status: 409, headers: { "cache-control": "private, no-store" } });
}

function previousParagraphBoundary(text, position) {
  const doubleBreak = text.lastIndexOf("\n\n", position);
  if (doubleBreak >= 0) return doubleBreak;
  const singleBreak = text.lastIndexOf("\n", position);
  return singleBreak >= 0 ? singleBreak : position;
}

export function strictTrimReferenceTail(value) {
  const text = String(value ?? "").replace(/\r/g, "").trim();
  const n = text.length;
  if (n < 3000) return text;

  const hardFloor = Math.floor(n * 0.55);
  const lower = text.toLowerCase();
  const explicit = [
    "tài liệu tham khảo", "nguồn tham khảo", "danh mục tài liệu", "danh sách tài liệu",
    "references", "reference list", "bibliography", "footnotes", "endnotes",
  ];
  let cut = n;
  for (const marker of explicit) {
    const pos = lower.indexOf(marker, hardFloor);
    if (pos >= 0 && pos < cut) cut = previousParagraphBoundary(text, pos);
  }

  // The source sometimes loses its references heading during HTML -> text extraction.
  // Detect a citation-dense tail instead. We only scan from 62% onward and require
  // multiple strong signals in a compact window, so ordinary inline sourcing is kept.
  if (cut === n) {
    const scanStart = Math.floor(n * 0.62);
    const tail = text.slice(scanStart);
    const signalPatterns = [
      { re: /https?:\/\/|www\./gi, weight: 4 },
      { re: /doi\.org\/|\bdoi\s*:/gi, weight: 5 },
      { re: /\[\d{1,3}\]/g, weight: 2 },
      { re: /(?:^|\n)\s*\[?\d{1,3}\]?\s*[.)-]\s+/g, weight: 3 },
      { re: /\((?:19|20)\d{2}[a-z]?\)/gi, weight: 1 },
    ];
    const signals = [];
    for (const { re, weight } of signalPatterns) {
      for (const match of tail.matchAll(re)) signals.push({ pos: scanStart + match.index, weight });
    }
    signals.sort((a, b) => a.pos - b.pos);

    let left = 0;
    let score = 0;
    const windowChars = 4200;
    for (let right = 0; right < signals.length; right++) {
      score += signals[right].weight;
      while (signals[right].pos - signals[left].pos > windowChars) {
        score -= signals[left].weight;
        left++;
      }
      const distinct = right - left + 1;
      if (score >= 16 && distinct >= 5) {
        cut = previousParagraphBoundary(text, signals[left].pos);
        break;
      }
    }
  }

  // Final fallback for bibliography-style references without links: a dense run of
  // publication years in the final 30% is extremely unlikely to be editorial prose.
  if (cut === n) {
    const scanStart = Math.floor(n * 0.70);
    const tail = text.slice(scanStart);
    const years = [...tail.matchAll(/\((?:19|20)\d{2}[a-z]?\)/gi)].map((m) => scanStart + m.index);
    let left = 0;
    for (let right = 0; right < years.length; right++) {
      while (years[right] - years[left] > 4500) left++;
      if (right - left + 1 >= 8) {
        cut = previousParagraphBoundary(text, years[left]);
        break;
      }
    }
  }

  if (cut >= n) return text;
  return text.slice(0, cut).replace(/\n{3,}/g, "\n\n").trim();
}

function readerViewId(url) {
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/(?:original|vi)$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

async function postProcessReaderResponse(response, url) {
  if (!response?.ok || readerViewId(url) !== STRICT_READER_ARTICLE_ID) return response;
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return response;
  const payload = await response.json().catch(() => null);
  if (!payload?.artifact || typeof payload.artifact.body !== "string") {
    return Response.json(payload ?? { ok: false, error: "READER_PAYLOAD_INVALID" }, {
      status: response.status,
      headers: { "cache-control": "private, no-store" },
    });
  }
  payload.artifact.body = strictTrimReferenceTail(payload.artifact.body);
  return Response.json(payload, {
    status: response.status,
    headers: { "cache-control": "private, no-store" },
  });
}

// Preserve the production-proven /v1/rss/* and private /api/rss/* routes.
// The browser reader is a separate read-only surface with its own token and
// never receives RUNNER3_CORE_TOKEN.
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/ui/rss") {
      return Response.redirect(new URL("/rss/library", url).toString(), 302);
    }

    const integrityResponse = blockedRestrictedFetch(request, url);
    if (integrityResponse) return integrityResponse;

    const readerResponse = await handleRssReader(request, env, url);
    if (readerResponse) return postProcessReaderResponse(readerResponse, url);

    const articleId = fetchArticleId(request, url);
    const rssResponse = await handleRssLibrary(request, env, url);
    if (rssResponse) {
      if (articleId && rssResponse.ok) {
        try {
          await enrichFetchedArticleImages(env, articleId);
        } catch (error) {
          console.warn("rss image enrichment failed", articleId, String(error?.message || error));
        }
      }
      return rssResponse;
    }
    return legacy.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof legacy.scheduled === "function") {
      return legacy.scheduled(controller, env, ctx);
    }
  },
};
