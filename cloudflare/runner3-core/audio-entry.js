import app from "./reader-media-adaptive-entry.js";
import { handleAudioMedia } from "./src/audio-media.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const audioResponse = await handleAudioMedia(request, env, url);
    if (audioResponse) return audioResponse;
    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};