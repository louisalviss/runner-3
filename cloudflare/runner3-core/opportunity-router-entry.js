import { handleMailboxFast } from "./mailbox-fast-entry.js";

let appPromise = null;
let opportunityPromise = null;
let privateCorePromise = null;

function loadApp() {
  if (!appPromise) appPromise = import("./mailbox-entry.js").then((module) => module.default);
  return appPromise;
}

function loadOpportunity() {
  if (!opportunityPromise) {
    opportunityPromise = Promise.all([
      import("./src/opportunity-regime.js"),
      import("./src/opportunity-regime-write-guard.js"),
    ]).then(([regime, guard]) => ({
      handleOpportunityRegime: regime.handleOpportunityRegime,
      guardOpportunityRegimeWrite: guard.guardOpportunityRegimeWrite,
    }));
  }
  return opportunityPromise;
}

function loadPrivateCore() {
  if (!privateCorePromise) {
    privateCorePromise = Promise.all([
      import("./src/index.js").then((module) => module.default),
      import("./vps-persistence-auth.js"),
    ]).then(([coreApp, persistence]) => ({ coreApp, handlePrivateCoreFastPath: persistence.handlePrivateCoreFastPath }));
  }
  return privateCorePromise;
}

function isMailboxPath(pathname) { return pathname === "/mailbox" || pathname.startsWith("/mailbox/"); }
function isPrivateCoreFastPath(pathname) { return pathname.startsWith("/artifacts/") || pathname.startsWith("/checkpoints/"); }

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (isMailboxPath(url.pathname)) {
      const response = await handleMailboxFast(request, env, url);
      if (response) return response;
      return Response.json({ ok: false, error: "MAILBOX_ROUTE_NOT_FOUND" }, { status: 404, headers: { "Cache-Control": "no-store" } });
    }
    if (isPrivateCoreFastPath(url.pathname)) {
      const { coreApp, handlePrivateCoreFastPath } = await loadPrivateCore();
      return handlePrivateCoreFastPath(request, env, ctx, coreApp);
    }
    const { handleOpportunityRegime, guardOpportunityRegimeWrite } = await loadOpportunity();
    const regimeWriteGuard = await guardOpportunityRegimeWrite(request, url);
    if (regimeWriteGuard) return regimeWriteGuard;
    const regimeResponse = await handleOpportunityRegime(request, env, url);
    if (regimeResponse) return regimeResponse;
    const app = await loadApp();
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    const app = await loadApp();
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
