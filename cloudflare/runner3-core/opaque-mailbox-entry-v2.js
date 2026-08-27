import app from "./mailbox-entry.js";

const OPAQUE_REQUEST_ID_RE = /^[0-9a-f]{64}$/;

function jsonError(error) {
  return new Response(JSON.stringify({ ok: false, error }), {
    status: 400,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function mailboxRequestId(pathname) {
  const patterns = [
    /^\/mailbox\/requests\/([^/]+)$/,
    /^\/mailbox\/jobs\/([^/]+)(?:\/fail)?$/,
    /^\/mailbox\/results\/([^/]+)\.csv$/,
    /^\/mailbox\/results\/([^/]+)$/,
  ];
  for (const pattern of patterns) {
    const match = pathname.match(pattern);
    if (match) return match[1];
  }
  return null;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const requestId = mailboxRequestId(url.pathname);
    if (requestId !== null && !OPAQUE_REQUEST_ID_RE.test(requestId)) {
      return jsonError("INVALID_REQUEST_ID");
    }
    return app.fetch(request, env, ctx);
  },
  async scheduled(event, env, ctx) {
    if (typeof app.scheduled === "function") {
      return app.scheduled(event, env, ctx);
    }
  },
};
