import app from "./mailbox-entry.js";
import { handleOpportunityRegime } from "./src/opportunity-regime.js";
import { guardOpportunityRegimeWrite } from "./src/opportunity-regime-write-guard.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

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
