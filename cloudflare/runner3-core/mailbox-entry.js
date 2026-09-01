import app from "./audio-entry.js";

const REQUEST_ID_RE = /^[A-Za-z0-9._-]{8,100}$/;
const NEW_REQUEST_ID_RE = /^m_[0-9a-f]{32}$/;
const MAILBOX_ALG = "RSA-OAEP-SHA256+A256GCM";
const MAX_MAILBOX_BYTES = 300000;
const CLAIM_LEASE_SECONDS = 1900;
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
  for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(binary);
}

function csvCell(value) {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function requireCoreWriteAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return Response.json({ ok: false, error: "WRITE_AUTH_NOT_CONFIGURED" }, { status: 503 });
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return Response.json({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  return null;
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

async function verifyVpsControlRequest(request, url) {
  const fingerprint = String(request.headers.get("X-VPS-Mailbox-Key-Fingerprint") || "").trim();
  if (fingerprint !== VPS_MAILBOX_KEY_FINGERPRINT) return Response.json({ ok: false, error: "MAILBOX_KEY_MISMATCH" }, { status: 401 });
  const timestamp = String(request.headers.get("X-VPS-Mailbox-Timestamp") || "").trim();
  const parsed = Number(timestamp);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isInteger(parsed) || Math.abs(now - parsed) > 120) return Response.json({ ok: false, error: "MAILBOX_TIMESTAMP_INVALID" }, { status: 401 });
  const worker = String(request.headers.get("X-VPS-Mailbox-Worker") || "").trim().slice(0, 100);
  if (!worker) return Response.json({ ok: false, error: "MAILBOX_WORKER_MISSING" }, { status: 401 });
  const signatureB64 = String(request.headers.get("X-VPS-Mailbox-Signature") || "").trim();
  if (!signatureB64 || signatureB64.length > 2048) return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_MISSING" }, { status: 401 });
  const signed = new TextEncoder().encode(`${timestamp}\n${request.method}\n${url.pathname}\n${worker}`);
  let verified = false;
  try {
    verified = await crypto.subtle.verify({ name: "RSA-PSS", saltLength: 32 }, await mailboxVerifyKey(), b64ToBytes(signatureB64), signed);
  } catch {
    verified = false;
  }
  if (!verified) return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_INVALID" }, { status: 401 });
  return null;
}

function validateEnvelope(envelope, requestId) {
  if (!envelope || typeof envelope !== "object") return "MAILBOX_ENVELOPE_INVALID";
  if (Number(envelope.version) !== 1 || envelope.alg !== MAILBOX_ALG) return "MAILBOX_ENVELOPE_ALG";
  if (String(envelope.request_id || "") !== requestId) return "MAILBOX_REQUEST_ID_MISMATCH";
  for (const key of ["encrypted_key", "nonce", "ciphertext", "reply_public_key_der"]) {
    if (!envelope[key] || typeof envelope[key] !== "string") return `MAILBOX_ENVELOPE_${key.toUpperCase()}`;
  }
  return null;
}

async function handleMailboxRequestSubmit(request, env, url) {
  if (request.method !== "PUT") return null;
  const match = /^\/mailbox\/requests\/([A-Za-z0-9._-]{8,100})$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  const authError = requireCoreWriteAuth(request, env);
  if (authError) return authError;
  const requestId = match[1];
  if (!NEW_REQUEST_ID_RE.test(requestId)) return Response.json({ ok: false, error: "INVALID_REQUEST_ID" }, { status: 400 });
  const raw = await request.arrayBuffer();
  if (!raw.byteLength || raw.byteLength > MAX_MAILBOX_BYTES) return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_SIZE" }, { status: 413 });
  let envelope;
  try {
    envelope = JSON.parse(new TextDecoder().decode(raw));
  } catch {
    return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_JSON" }, { status: 400 });
  }
  const envelopeError = validateEnvelope(envelope, requestId);
  if (envelopeError) return Response.json({ ok: false, error: envelopeError }, { status: 400 });
  const envelopeJson = JSON.stringify(envelope);
  const existing = await env.DB.prepare("SELECT envelope_json,status FROM vps_mailbox_jobs WHERE request_id=?").bind(requestId).first();
  if (existing) {
    if (String(existing.envelope_json || "") !== envelopeJson) return Response.json({ ok: false, error: "MAILBOX_REQUEST_CONFLICT" }, { status: 409 });
    return Response.json({ ok: true, accepted: true, duplicate: true, request_id: requestId, status: existing.status });
  }
  await env.DB.prepare(`INSERT INTO vps_mailbox_jobs(request_id,envelope_json,status,attempts,created_at,updated_at)
    VALUES(?,?,'queued',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)`).bind(requestId, envelopeJson).run();
  return Response.json({ ok: true, accepted: true, duplicate: false, request_id: requestId, status: "queued" }, { status: 202 });
}

async function handleMailboxClaim(request, env, url) {
  if (request.method !== "POST" || url.pathname !== "/mailbox/claim") return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  const authError = await verifyVpsControlRequest(request, url);
  if (authError) return authError;
  const worker = String(request.headers.get("X-VPS-Mailbox-Worker") || "").trim().slice(0, 100);
  const now = Math.floor(Date.now() / 1000);
  const leaseUntil = now + CLAIM_LEASE_SECONDS;
  for (let attempt = 0; attempt < 4; attempt++) {
    const candidate = await env.DB.prepare(`SELECT request_id FROM vps_mailbox_jobs
      WHERE status='queued' OR (status='claimed' AND COALESCE(lease_until,0) < ?)
      ORDER BY created_at ASC LIMIT 1`).bind(now).first();
    if (!candidate) return Response.json({ ok: true, job: null, lease_seconds: CLAIM_LEASE_SECONDS }, { headers: { "Cache-Control": "no-store" } });
    const requestId = String(candidate.request_id || "");
    if (!REQUEST_ID_RE.test(requestId)) continue;
    const claimed = await env.DB.prepare(`UPDATE vps_mailbox_jobs
      SET status='claimed',lease_owner=?,lease_until=?,attempts=attempts+1,updated_at=CURRENT_TIMESTAMP
      WHERE request_id=? AND (status='queued' OR (status='claimed' AND COALESCE(lease_until,0) < ?))`).bind(worker, leaseUntil, requestId, now).run();
    if (Number(claimed?.meta?.changes || 0) !== 1) continue;
    const row = await env.DB.prepare("SELECT request_id,envelope_json,attempts,lease_until FROM vps_mailbox_jobs WHERE request_id=?").bind(requestId).first();
    if (!row) continue;
    let envelope;
    try {
      envelope = JSON.parse(String(row.envelope_json || "{}"));
    } catch {
      await env.DB.prepare("UPDATE vps_mailbox_jobs SET status='failed',lease_owner=NULL,lease_until=NULL,updated_at=CURRENT_TIMESTAMP WHERE request_id=?").bind(requestId).run();
      continue;
    }
    return Response.json({ ok: true, job: { request_id: requestId, envelope, attempts: Number(row.attempts || 0), lease_until: Number(row.lease_until || 0) }, lease_seconds: CLAIM_LEASE_SECONDS }, { headers: { "Cache-Control": "no-store" } });
  }
  return Response.json({ ok: true, job: null, contention: true, lease_seconds: CLAIM_LEASE_SECONDS }, { headers: { "Cache-Control": "no-store" } });
}

async function handleMailboxJobFail(request, env, url) {
  if (request.method !== "POST") return null;
  const match = /^\/mailbox\/jobs\/([A-Za-z0-9._-]{8,100})\/fail$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  const authError = await verifyVpsControlRequest(request, url);
  if (authError) return authError;
  let detail = null;
  try { detail = await request.json(); } catch { detail = null; }
  const reason = String(detail?.error || "vps_failed").slice(0, 1000);
  await env.DB.prepare("UPDATE vps_mailbox_jobs SET status='failed',lease_owner=NULL,lease_until=NULL,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE request_id=?").bind(reason, match[1]).run();
  return Response.json({ ok: true, request_id: match[1], status: "failed" }, { headers: { "Cache-Control": "no-store" } });
}

async function handleMailboxJobStatus(request, env, url) {
  if (request.method !== "GET") return null;
  const match = /^\/mailbox\/jobs\/([A-Za-z0-9._-]{8,100})$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  const authError = requireCoreWriteAuth(request, env);
  if (authError) return authError;
  const row = await env.DB.prepare(`SELECT request_id,status,attempts,lease_owner,lease_until,last_error,created_at,updated_at
    FROM vps_mailbox_jobs WHERE request_id=?`).bind(match[1]).first();
  if (!row) return Response.json({ ok: false, error: "MAILBOX_JOB_NOT_FOUND" }, { status: 404 });
  return Response.json({ ok: true, job: row }, { headers: { "Cache-Control": "no-store" } });
}

async function handleMailboxCancel(request, env, url) {
  if (request.method !== "DELETE") return null;
  const match = /^\/mailbox\/requests\/([A-Za-z0-9._-]{8,100})$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  const authError = requireCoreWriteAuth(request, env);
  if (authError) return authError;
  const result = await env.DB.prepare("UPDATE vps_mailbox_jobs SET status='cancelled',lease_owner=NULL,lease_until=NULL,updated_at=CURRENT_TIMESTAMP WHERE request_id=? AND status='queued'").bind(match[1]).run();
  if (Number(result?.meta?.changes || 0) !== 1) return Response.json({ ok: false, error: "MAILBOX_JOB_NOT_CANCELLABLE" }, { status: 409 });
  return Response.json({ ok: true, request_id: match[1], status: "cancelled" });
}

async function handleMailboxSignedPublish(request, env, url) {
  if (request.method !== "PUT") return null;
  const match = /^\/mailbox\/results\/([A-Za-z0-9._-]{8,100})$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  const requestId = match[1];
  const fingerprint = String(request.headers.get("X-VPS-Mailbox-Key-Fingerprint") || "").trim();
  if (fingerprint !== VPS_MAILBOX_KEY_FINGERPRINT) return Response.json({ ok: false, error: "MAILBOX_KEY_MISMATCH" }, { status: 401 });
  const signatureB64 = String(request.headers.get("X-VPS-Mailbox-Signature") || "").trim();
  if (!signatureB64 || signatureB64.length > 2048) return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_MISSING" }, { status: 401 });
  const raw = await request.arrayBuffer();
  if (!raw.byteLength || raw.byteLength > MAX_MAILBOX_BYTES) return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_SIZE" }, { status: 413 });
  let verified = false;
  try { verified = await crypto.subtle.verify({ name: "RSA-PSS", saltLength: 32 }, await mailboxVerifyKey(), b64ToBytes(signatureB64), raw); } catch { verified = false; }
  if (!verified) return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_INVALID" }, { status: 401 });
  let payload = null;
  try { payload = JSON.parse(new TextDecoder().decode(raw)); } catch { return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_JSON" }, { status: 400 }); }
  const status = String(payload?.status || "");
  const detail = payload?.detail;
  if (!["done", "failed"].includes(status) || String(payload?.run_id || "") !== requestId) return Response.json({ ok: false, error: "MAILBOX_PAYLOAD_STATE" }, { status: 400 });
  if (!detail || typeof detail !== "object" || String(detail.request_id || "") !== requestId || detail.alg !== MAILBOX_ALG) return Response.json({ ok: false, error: "MAILBOX_ENVELOPE_INVALID" }, { status: 400 });
  for (const key of ["version", "encrypted_key", "nonce", "ciphertext"]) if (detail[key] == null || String(detail[key]).length === 0) return Response.json({ ok: false, error: `MAILBOX_ENVELOPE_${key.toUpperCase()}` }, { status: 400 });
  const source = `vps-mailbox-result-${requestId}`;
  await env.DB.prepare(`INSERT INTO workflow_state(source,status,run_id,detail,updated_at)
    VALUES(?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP`).bind(source, status, requestId, JSON.stringify(detail)).run();
  await env.DB.prepare("UPDATE vps_mailbox_jobs SET status=?,lease_owner=NULL,lease_until=NULL,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE request_id=?").bind(status, requestId).run();
  return Response.json({ ok: true, state: { source, status, run_id: requestId, detail, signer: VPS_MAILBOX_KEY_FINGERPRINT } }, { headers: { "Cache-Control": "no-store" } });
}

async function handleMailboxResultCsv(request, env, url) {
  if (request.method !== "GET") return null;
  const match = /^\/mailbox\/results\/([A-Za-z0-9._-]{8,100})\.csv$/.exec(url.pathname);
  if (!match) return null;
  if (!env.DB) return new Response('"status","detail_b64"\n"error","D1_NOT_BOUND"\n', { status: 503, headers: { "Content-Type": "text/csv; charset=utf-8", "Cache-Control": "no-store" } });
  const requestId = match[1];
  const source = `vps-mailbox-result-${requestId}`;
  const row = await env.DB.prepare("SELECT status, detail, updated_at FROM workflow_state WHERE source = ?").bind(source).first();
  const headers = { "Content-Type": "text/csv; charset=utf-8", "Cache-Control": "no-store, max-age=0", "Access-Control-Allow-Origin": "*" };
  if (!row) return new Response('"status","detail_b64","updated_at"\n"pending","",""\n', { status: 200, headers });
  const detail = typeof row.detail === "string" ? row.detail : JSON.stringify(row.detail ?? null);
  const body = [["status", "detail_b64", "updated_at"], [String(row.status || "unknown"), encodeBase64Utf8(detail), String(row.updated_at || "")]].map((cells) => cells.map(csvCell).join(",")).join("\n") + "\n";
  return new Response(body, { status: 200, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const submitResponse = await handleMailboxRequestSubmit(request, env, url); if (submitResponse) return submitResponse;
    const claimResponse = await handleMailboxClaim(request, env, url); if (claimResponse) return claimResponse;
    const failResponse = await handleMailboxJobFail(request, env, url); if (failResponse) return failResponse;
    const statusResponse = await handleMailboxJobStatus(request, env, url); if (statusResponse) return statusResponse;
    const cancelResponse = await handleMailboxCancel(request, env, url); if (cancelResponse) return cancelResponse;
    const signedPublish = await handleMailboxSignedPublish(request, env, url); if (signedPublish) return signedPublish;
    const mailboxResponse = await handleMailboxResultCsv(request, env, url); if (mailboxResponse) return mailboxResponse;
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
