const VPS_MAILBOX_KEY_FINGERPRINT = "ebb40327771f9010511a734051b6208dd34b5acad5c0eb24e3cbc5b1f7b5d19b";
const VPS_MAILBOX_PUBLIC_KEY_DER_B64 = "MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAuHwx3zuFw1sCLdl4g8shTXv/Ep3+XUaamBXfr32FK+7VaQaDX3rKpOISJcEqKX6R0MCFqWAvhcRnyxbTImSiYThCJKNe5kHbJgRo8v89tKzwauBFtdfapxuoXddetzaCSqUQRK3e6YQeyqRBDk0RydbuNbEMweH5T6HHbdMk4yXHHrtkPuOXLf/DmvAuk+EJFmzG4DAbt7//vuTg3HZFEo8fLImi+wVacDrHq0AsQqbKDK7EQD00Jb8uBHowzM1Km5W2zy8xVi+jx+xjPCKsFhKA7TSUwOP75HNehrNOIkpgJqVSGG2LHdfHPgakc1r0rtQvF4RQ89JN6O9tqmOK84tTDDTchv/KCUBuSCZ5gBGDjRDh8/yDae1Z/lSkwtOE0uqL3Ux9q2pkK/s4qZWPoC5tH5SvibpYhBXMuQ/L1E7VBjr8TsnSMeyfyNE1FxrCIEAMlSRaoAnSvTuoujqmOGQy0IpnFDpVcD0TxBHwCTONU3Ea6R2bu/p5xLbER533AgMBAAE=";
const SIGNATURE_HEADERS = [
  "X-VPS-Mailbox-Key-Fingerprint",
  "X-VPS-Mailbox-Timestamp",
  "X-VPS-Mailbox-Worker",
  "X-VPS-Mailbox-Signature",
];

function b64ToBytes(value) {
  const binary = atob(String(value || ""));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

let verifyKeyPromise = null;
function verifyKey() {
  if (!verifyKeyPromise) {
    verifyKeyPromise = crypto.subtle.importKey(
      "spki",
      b64ToBytes(VPS_MAILBOX_PUBLIC_KEY_DER_B64),
      { name: "RSA-PSS", hash: "SHA-256" },
      false,
      ["verify"],
    );
  }
  return verifyKeyPromise;
}

function hasSignedIdentity(request) {
  return SIGNATURE_HEADERS.some((name) => Boolean(String(request.headers.get(name) || "").trim()));
}

async function verifySignedIdentity(request, url) {
  const fingerprint = String(request.headers.get("X-VPS-Mailbox-Key-Fingerprint") || "").trim();
  if (fingerprint !== VPS_MAILBOX_KEY_FINGERPRINT) {
    return Response.json({ ok: false, error: "MAILBOX_KEY_MISMATCH" }, { status: 401 });
  }

  const timestamp = String(request.headers.get("X-VPS-Mailbox-Timestamp") || "").trim();
  const parsed = Number(timestamp);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isInteger(parsed) || Math.abs(now - parsed) > 120) {
    return Response.json({ ok: false, error: "MAILBOX_TIMESTAMP_INVALID" }, { status: 401 });
  }

  const worker = String(request.headers.get("X-VPS-Mailbox-Worker") || "").trim().slice(0, 100);
  if (!worker) {
    return Response.json({ ok: false, error: "MAILBOX_WORKER_MISSING" }, { status: 401 });
  }

  const signatureB64 = String(request.headers.get("X-VPS-Mailbox-Signature") || "").trim();
  if (!signatureB64 || signatureB64.length > 2048) {
    return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_MISSING" }, { status: 401 });
  }

  const signed = new TextEncoder().encode(`${timestamp}\n${request.method}\n${url.pathname}\n${worker}`);
  let verified = false;
  try {
    verified = await crypto.subtle.verify(
      { name: "RSA-PSS", saltLength: 32 },
      await verifyKey(),
      b64ToBytes(signatureB64),
      signed,
    );
  } catch {
    verified = false;
  }
  if (!verified) {
    return Response.json({ ok: false, error: "MAILBOX_SIGNATURE_INVALID" }, { status: 401 });
  }
  return null;
}

function signedMethodAllowed(url, method) {
  if (url.pathname.startsWith("/checkpoints/")) return method === "GET" || method === "PUT";
  if (url.pathname.startsWith("/artifacts/")) return method === "GET" || method === "HEAD" || method === "PUT";
  return false;
}

export async function handlePrivateCoreFastPath(request, env, ctx, coreApp) {
  if (!hasSignedIdentity(request)) return coreApp.fetch(request, env, ctx);

  const url = new URL(request.url);
  if (!signedMethodAllowed(url, request.method)) {
    return Response.json({ ok: false, error: "MAILBOX_PERSISTENCE_METHOD_NOT_ALLOWED" }, { status: 405 });
  }

  const authError = await verifySignedIdentity(request, url);
  if (authError) return authError;

  const token = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!token) {
    return Response.json({ ok: false, error: "PERSISTENCE_AUTH_NOT_CONFIGURED" }, { status: 503 });
  }

  const headers = new Headers(request.headers);
  headers.set("Authorization", `Bearer ${token}`);
  for (const name of SIGNATURE_HEADERS) headers.delete(name);
  headers.set("X-Runner3-Source", "vps-mailbox-signed-persistence");
  const forwarded = new Request(request, { headers });
  return coreApp.fetch(forwarded, env, ctx);
}
