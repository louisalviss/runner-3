import app from "./audio-entry.js";

const REQUEST_ID_RE = /^[A-Za-z0-9._-]{8,100}$/;

function encodeBase64Utf8(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function csvCell(value) {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

async function handleMailboxResultCsv(request, env, url) {
  if (request.method !== "GET") return null;
  const match = /^\/mailbox\/results\/([A-Za-z0-9._-]{8,100})\.csv$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) {
    return new Response('"status","detail_b64"\n"error","D1_NOT_BOUND"\n', {
      status: 503,
      headers: { "Content-Type": "text/csv; charset=utf-8", "Cache-Control": "no-store" },
    });
  }

  const requestId = match[1];
  if (!REQUEST_ID_RE.test(requestId)) {
    return new Response('"status","detail_b64"\n"error","invalid_request_id"\n', {
      status: 400,
      headers: { "Content-Type": "text/csv; charset=utf-8", "Cache-Control": "no-store" },
    });
  }

  const source = `vps-mailbox-result-${requestId}`;
  const row = await env.DB.prepare(
    "SELECT status, detail, updated_at FROM workflow_state WHERE source = ?"
  ).bind(source).first();

  const headers = {
    "Content-Type": "text/csv; charset=utf-8",
    "Cache-Control": "no-store, max-age=0",
    "Access-Control-Allow-Origin": "*",
  };
  if (!row) {
    return new Response('"status","detail_b64","updated_at"\n"pending","",""\n', { status: 200, headers });
  }

  const detail = typeof row.detail === "string" ? row.detail : JSON.stringify(row.detail ?? null);
  const body = [
    ["status", "detail_b64", "updated_at"],
    [String(row.status || "unknown"), encodeBase64Utf8(detail), String(row.updated_at || "")],
  ].map((cells) => cells.map(csvCell).join(",")).join("\n") + "\n";
  return new Response(body, { status: 200, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const mailboxResponse = await handleMailboxResultCsv(request, env, url);
    if (mailboxResponse) return mailboxResponse;
    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
