import legacy from "./rss-wrapper.js";
import { handleRssLibrary } from "./src/rss-library.js";

// Preserve the production-proven /v1/rss/* and /ui/rss routes while exposing
// the full private RSS Library API/UI implemented in src/rss-library.js.
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
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
