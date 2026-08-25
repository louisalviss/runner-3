import legacy from "./rss-wrapper.js";
import { handleRssLibrary } from "./src/rss-library.js";

const BLOCKED_INCOMPLETE_SOURCE_IDS = new Set([
  "projectsyndicate-url-26a9686e21ebe4fa865d",
  "projectsyndicate-url-db223b141f372578df3c",
]);

function blockedRestrictedFetch(request, url) {
  if (request.method !== "POST") return null;
  const match = url.pathname.match(/^\/api\/rss\/articles\/([^/]+)\/fetch$/);
  if (!match) return null;
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return null; }
  if (!BLOCKED_INCOMPLETE_SOURCE_IDS.has(articleId)) return null;
  return Response.json({
    ok: false,
    error: "INCOMPLETE_RESTRICTED_SOURCE_DIRECT_ONLY",
    articleId,
    message: "Full source is not available through the authorized direct route; refusing to store or translate an excerpt as a full article.",
  }, { status: 409, headers: { "cache-control": "private, no-store" } });
}

// Preserve the production-proven /v1/rss/* routes while exposing the full
// private RSS Library API/UI implemented in src/rss-library.js. The legacy
// /ui/rss entry now points to the protected reader instead of a status-only table.
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/ui/rss") {
      return Response.redirect(new URL("/rss/library", url).toString(), 302);
    }

    const integrityResponse = blockedRestrictedFetch(request, url);
    if (integrityResponse) return integrityResponse;
    const rssResponse = await handleRssLibrary(request, env, url);
    if (rssResponse) return rssResponse;
    return legacy.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof legacy.scheduled === "function") {
      return legacy.scheduled(controller, env, ctx);
    }
  },
};
