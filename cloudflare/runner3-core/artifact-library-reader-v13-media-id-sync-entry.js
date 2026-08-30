import app from "./artifact-library-reader-v12-unlock-sync-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const OLD_ID = "return u.searchParams.get('id')||'';";
const NEW_ID = "const queryId=u.searchParams.get('id');if(queryId)return queryId;const match=u.pathname.match(/\\/artifact-library\\/api\\/audio\\/([^/]+)\\/media$/);return match?decodeURIComponent(match[1]):'';";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;

    const original = await response.text();
    const updated = original.includes(OLD_ID) ? original.replace(OLD_ID, NEW_ID) : original;
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v13-wordboundary-cfi-media-id-sync");
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
