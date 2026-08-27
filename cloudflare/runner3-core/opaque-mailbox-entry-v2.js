import app from "./delivery-entry.js";

const OPAQUE_REQUEST_ID_RE = /^m_[0-9a-f]{32}$/;

function jsonError(error) {
  return new Response(JSON.stringify({ ok: false, error }), {
    status: 400,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function isNewRequestSubmit(request, pathname) {
  return request.method === "PUT" && /^\/mailbox\/requests\/[^/]+$/.test(pathname);
}

function requestIdFromRequestPath(pathname) {
  const match = pathname.match(/^\/mailbox\/requests\/([^/]+)$/);
  return match ? match[1] : null;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Migration policy: every NEW mailbox submit must use an opaque ID.
    // Existing jobs/results/status/fail routes remain readable/writable so
    // legacy in-flight work can drain without being stranded.
    if (isNewRequestSubmit(request, url.pathname)) {
      const requestId = requestIdFromRequestPath(url.pathname);
      if (!OPAQUE_REQUEST_ID_RE.test(requestId || "")) {
        return jsonError("INVALID_REQUEST_ID");
      }
    }

    return app.fetch(request, env, ctx);
  },
  async scheduled(event, env, ctx) {
    if (typeof app.scheduled === "function") {
      return app.scheduled(event, env, ctx);
    }
  },
};
