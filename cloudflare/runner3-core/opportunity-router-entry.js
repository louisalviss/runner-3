import app from "./mailbox-entry.js";
import coreApp from "./src/index.js";
import { handleOpportunityRegime } from "./src/opportunity-regime.js";
import { guardOpportunityRegimeWrite } from "./src/opportunity-regime-write-guard.js";

function isPrivateCoreFastPath(pathname) {
  return pathname.startsWith("/artifacts/") || pathname.startsWith("/checkpoints/");
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Keep durable artifact/checkpoint traffic out of the heavy Reader chain.
    // src/index.js is the canonical owner of these APIs; this only short-circuits routing.
    if (isPrivateCoreFastPath(url.pathname)) return coreApp.fetch(request, env, ctx);

    const regimeWriteGuard = await guardOpportunityRegimeWrite(request, url);
    if (regimeWriteGuard) return regimeWriteGuard;

    const regimeResponse = await handleOpportunityRegime(request, env, url);
    if (regimeResponse) return regimeResponse;

    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") {
      return app.scheduled(controller, env, ctx);
    }
  },
};
