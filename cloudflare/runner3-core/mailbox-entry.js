import app from "./audio-entry.js";

const REQUEST_ID_RE = /^[A-Za-z0-9._-]{8,100}$/;
const MAILBOX_ALG = "RSA-OAEP-SHA256+A256GCM";
const VPS_MAILBOX_KEY_FINGERPRINT = "ebb40327771f9010511a734051b6208dd34b5acad5c0eb24e3cbc5b1f7b5d19b";
const VPS_MAILBOX_PUBLIC_KEY_DER_B64 = "MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAuHwx3zuFw1sCLdl4g8shTXv/Ep3+XUaamBXfr32FK+7VaQaDX3rKpOISJcEqKX6R0MCFqWAvhcRnyxbTImSiYThCJKNe5kHbJgRo8v89tKzwauBFtdfapxuoXddetzaCSqUQRK3e6YQeyqRBDk0RydbuNbEMweH5T6HHbdMk4yXHHrtkPuOXLf/DmvAuk+EJFmzG4DAbt7//vuTg3HZFEo8fLImi+wVacDrHq0AsQqbKDK7EQD00Jb8uBHowzM1Km5W2zy8xVi+jx+xjPCKsFhKA7TSUwOP75HNehrNOIkpgJqVSGG2LHdfHPgakc1r0rtQvF4RQ89JN6O9tqmOK84tTDDTchv/KCUBuSCZ5gBGDjRDh8/yDae1Z/lSkwtOE0uqL3Ux9q2pkK/s4qZWPoC5tH5SvibpYhBXMuQ/L1E7VBjr8TsnSMeyfyNE1FxrCIEAMlSRaoAnSvTuoujqmOGQy0IpnFDpVcD0TxBHwCTONU3Ea6R2bu/p5xLbER533AgMBAAE=";

function b64ToBytes(value) {
  const binary = atob(String(value || ""));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

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

let mailboxVerifyKeyPromise = null;
function mailboxVerifyKey() {
  if (!mailboxVerifyKeyPromise) {
    mailboxVerifyKeyPromise = crypto.subtle.importKey(
      "spki",
      b64ToBytes(VPS_MAILBOX_PUBLIC_KEY_DER_B64),
      { name: "RSA-PSS", hash: "SHA-256" },
      false,
      ["verify"],
    );
  }
  return mailboxVerifyKeyPromise;
}

async function handleMailboxSignedPublish(request, env, url) {
  if (request.method !== "PUT") return null;
  const match = /^\/mailbox\/results\/([A-Za-z0-9._-]{8,100})$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });

  const requestId = match[1];
  if (!REQUEST_ID_RE.test(requestId)) {
    return Response.json({ ok: false, error: "INVALID_REQUEST_ID" }, { status: 400 });
  }
  const fingerprint = String(request.headers.get("X-VPS-Mailbox-Key-Fingerprint") || "").trim();
  if (fingerprint !== VPS_MAILBOX_KEY_FINGERPRINT) {
    return Response.json({ ok: false, error: "MAILBOX_KEY_MISMATCH" }, { status: 401 });
  }
  const signatureB64 = String(request.headers.get("X-VPS-Mailbox-Signature") || "").trim();
  if (!signatureB64 || signatureB64.length > 2048) {
    return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_MISSING" }, { status: 401 });
  }

  const raw = await request.arrayBuffer();
  if (!raw.byteLength || raw.byteLength > 300000) {
    return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_SIZE" }, { status: 413 });
  }
  let verified = false;
  try {
    verified = await crypto.subtle.verify(
      { name: "RSA-PSS", saltLength: 32 },
      await mailboxVerifyKey(),
      b64ToBytes(signatureB64),
      raw,
    );
  } catch {
    verified = false;
  }
  if (!verified) {
    return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_INVALID" }, { status: 401 });
  }

  let payload = null;
  try {
    payload = JSON.parse(new TextDecoder().decode(raw));
  } catch {
    return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_JSON" }, { status: 400 });
  }
  const status = String(payload?.status || "");
  const detail = payload?.detail;
  if (!['done', 'failed'].includes(status) || String(payload?.run_id || "") !== requestId) {
    return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_STATE" }, { status: 400 });
  }
  if (!detail || typeof detail !== "object" || String(detail.request_id || "") !== requestId || detail.alg !== MAILBOX_ALG) {
    return Response.json({ ok: false, error: "MAILBOX_ENVELOPE_INVALID" }, { status: 400 });
  }
  for (const key of ["version", "encrypted_key", "nonce", "ciphertext"]) {
    if (detail[key] == null || String(detail[key]).length === 0) {
      return Response.json({ ok: false, error: `MAILBOX_ENVELOPE_${key.toUpperCase()}` }, { status: 400 });
    }
  }

  const source = `vps-mailbox-result-${requestId}`;
  await env.DB.prepare(
    `INSERT INTO workflow_state(source,status,run_id,detail,updated_at)
     VALUES(?,?,?,?,CURRENT_TIMESTAMP)
     ON CONFLICT(source) DO UPDATE SET
       status=excluded.status,
       run_id=excluded.run_id,
       detail=excluded.detail,
       updated_at=CURRENT_TIMESTAMP`
  ).bind(source, status, requestId, JSON.stringify(detail)).run();

  return Response.json({
    ok: true,
    state: { source, status, run_id: requestId, detail, signer: VPS_MAILBOX_KEY_FINGERPRINT },
  }, { headers: { "Cache-Control": "no-store" } });
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
    const signedPublish = await handleMailboxSignedPublish(request, env, url);
    if (signedPublish) return signedPublish;
    const mailboxResponse = await handleMailboxResultCsv(request, env, url);
    if (mailboxResponse) return mailboxResponse;
    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
