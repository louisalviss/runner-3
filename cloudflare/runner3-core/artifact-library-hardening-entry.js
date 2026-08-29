import app from "./artifact-list-entry.js";

const ARTIFACT_PREFIXES = ["/artifact-library", "/artifact-list"];
const REMEMBER_SECONDS = 30 * 24 * 60 * 60;
const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function isArtifactRoute(pathname) {
  return ARTIFACT_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(prefix + "/"));
}

function hardenedHeaders(headers) {
  const next = new Headers(headers);
  next.set("X-Robots-Tag", ROBOTS);
  next.set("Cache-Control", "private, no-store, max-age=0");
  next.set("Pragma", "no-cache");
  next.set("Referrer-Policy", "no-referrer");
  const cookie = next.get("Set-Cookie");
  if (cookie && cookie.includes("r3_artifact_library=")) {
    next.set("Set-Cookie", cookie.replace(/Max-Age=\d+/i, `Max-Age=${REMEMBER_SECONDS}`));
  }
  return next;
}

async function hardenArtifactResponse(request, response) {
  const headers = hardenedHeaders(response.headers);
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/html")) {
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  }

  let body = await response.text();
  const meta = '<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">';
  if (!body.toLowerCase().includes('name="robots"')) {
    body = body.replace(/<head>/i, `<head>\n${meta}`);
  }
  return new Response(body, { status: response.status, statusText: response.statusText, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (!isArtifactRoute(url.pathname)) return response;
    return hardenArtifactResponse(request, response);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") {
      return app.scheduled(controller, env, ctx);
    }
  },
};
