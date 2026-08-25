import legacy from "./rss-wrapper.js";
import { handleRssLibrary } from "./src/rss-library.js";
import { handleRssReader } from "./src/rss-reader.js";
import { enrichFetchedArticleImages } from "./src/rss-image-enrich.js";

const BLOCKED_INCOMPLETE_SOURCE_IDS = new Set([
  "projectsyndicate-url-26a9686e21ebe4fa865d",
  "projectsyndicate-url-db223b141f372578df3c",
]);

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
    if (readerResponse) return readerResponse;

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
