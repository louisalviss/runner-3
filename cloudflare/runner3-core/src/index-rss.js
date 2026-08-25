import core from "./index.js";
import { handleRssLibrary } from "./rss-library.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const rssResponse = await handleRssLibrary(request, env, url);
    if (rssResponse) return rssResponse;
    return core.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof core.scheduled === "function") {
      return core.scheduled(controller, env, ctx);
    }
  },
};
