import app from "./artifact-library-reader-v8-continuous-audio-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const READER_CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; font-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;
    const headers = new Headers(response.headers);
    headers.set("Content-Security-Policy", READER_CSP);
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v9-csp-base-self");
    return new Response(response.body, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
