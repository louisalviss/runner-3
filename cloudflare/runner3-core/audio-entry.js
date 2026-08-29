import app from "./reader-media-adaptive-entry.js";
import { handleAudioMedia } from "./src/audio-media.js";
import { maybeRecomputePersonal } from "./src/rss-reader-learning.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const audioResponse = await handleAudioMedia(request, env, url);
    if (audioResponse) return audioResponse;
    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    const flush = maybeRecomputePersonal(env, { force: true }).catch((error) => {
      console.warn("content intelligence scheduled recompute failed", String(error?.message || error));
    });
    if (ctx?.waitUntil) ctx.waitUntil(flush);
    else await flush;
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};