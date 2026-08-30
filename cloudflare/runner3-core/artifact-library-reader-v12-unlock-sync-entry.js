import app from "./artifact-library-reader-v11-text-cfi-sync-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const OLD_FOLLOW_GUARD = "if(!row||audio.paused||audio.ended)return;";
const NEW_FOLLOW_GUARD = "if(!row)return;if(!force&&(audio.paused||audio.ended))return;";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;

    const original = await response.text();
    const updated = original.includes(OLD_FOLLOW_GUARD)
      ? original.replace(OLD_FOLLOW_GUARD, NEW_FOLLOW_GUARD)
      : original;
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v12-wordboundary-cfi-unlock-sync");
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
