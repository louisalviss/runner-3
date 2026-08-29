import app from "./artifact-list-entry.js";

const ARTIFACT_PREFIXES = ["/artifact-library", "/artifact-list"];
const LIBRARY_COOKIE = "r3_artifact_library";
const REMEMBER_SECONDS = 30 * 24 * 60 * 60;
const MAGIC_TTL_SECONDS = 10 * 60;
const PIN_ITERATIONS = 180000;
const PIN_MAX_FAILURES = 5;
const PIN_LOCK_SECONDS = 15 * 60;
const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function isArtifactRoute(pathname) {
  return ARTIFACT_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(prefix + "/"));
}

function expectedArtifactToken(env) {
  return typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
}

function getCookie(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const index = part.indexOf("=");
    if (index < 0) continue;
    if (part.slice(0, index).trim() === name) return part.slice(index + 1).trim();
  }
  return "";
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function bytesToBase64(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function constantTimeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

async function derivePinHash(pin, saltBase64, iterations = PIN_ITERATIONS) {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(pin),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      hash: "SHA-256",
      salt: base64ToBytes(saltBase64),
      iterations,
    },
    material,
    256,
  );
  return new Uint8Array(bits);
}

async function librarySessionValue(env) {
  const token = expectedArtifactToken(env);
  if (!token) return "";
  return sha256Hex(`runner3-artifact-library-v1:${token}`);
}

async function hasLibrarySession(request, env) {
  const expected = await librarySessionValue(env);
  return Boolean(expected) && getCookie(request, LIBRARY_COOKIE) === expected;
}

function libraryCookie(value, maxAge = REMEMBER_SECONDS) {
  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Strict`;
}

function randomToken(byteLength = 32) {
  const bytes = crypto.getRandomValues(new Uint8Array(byteLength));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function hardenedHeaders(headers) {
  const next = new Headers(headers);
  next.set("X-Robots-Tag", ROBOTS);
  next.set("Cache-Control", "private, no-store, max-age=0");
  next.set("Pragma", "no-cache");
  next.set("Referrer-Policy", "no-referrer");
  next.set("X-Frame-Options", "DENY");
  const cookie = next.get("Set-Cookie");
  if (cookie && cookie.includes(`${LIBRARY_COOKIE}=`) && !/Max-Age=0(?:;|$)/i.test(cookie)) {
    next.set("Set-Cookie", cookie.replace(/Max-Age=\d+/i, `Max-Age=${REMEMBER_SECONDS}`));
  }
  return next;
}

function hardenedJson(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: hardenedHeaders(new Headers({
      "Content-Type": "application/json; charset=utf-8",
      ...extraHeaders,
    })),
  });
}

function hardenedHtml(body, status = 200, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: hardenedHeaders(new Headers({
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
      ...extraHeaders,
    })),
  });
}

function authShell({ title, subtitle, form, note, error = "" }) {
  const errorBlock = error ? `<div class="error">${error}</div>` : "";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">
<title>Runner3 R2 Library</title>
<style>
:root{color-scheme:dark;background:#0a0b0d;color:#f5f7fa;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 20% 0%,#18202c 0,transparent 35%),#0a0b0d;padding:24px}.card{width:min(440px,100%);background:#111419;border:1px solid #252b33;border-radius:20px;padding:28px;box-shadow:0 24px 80px rgba(0,0,0,.38)}.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8f9bac;font-weight:700}h1{font-size:28px;margin:8px 0 8px}.sub{color:#9da7b5;line-height:1.5;margin:0 0 24px}.field{display:grid;gap:8px;margin-top:12px}label{font-size:13px;color:#cbd2dc}.input{width:100%;border:1px solid #303844;background:#0b0e12;color:#fff;border-radius:12px;padding:13px 14px;font-size:18px;outline:none}.pin{letter-spacing:.3em;text-align:center;font-variant-numeric:tabular-nums}.input:focus{border-color:#6d7f98}.button{width:100%;margin-top:14px;border:0;border-radius:12px;padding:13px 16px;background:#f2f5f8;color:#0a0b0d;font-weight:800;font-size:15px;cursor:pointer}.error{background:#35191c;color:#ffb4bd;border:1px solid #673039;border-radius:10px;padding:10px 12px;margin-bottom:14px;font-size:13px}.note{font-size:12px;color:#6f7987;margin-top:14px;line-height:1.5}.link{display:inline-block;margin-top:12px;color:#aeb9c8;font-size:12px;text-decoration:none}.link:hover{text-decoration:underline}
</style>
</head>
<body><main class="card"><div class="eyebrow">Runner3 Core</div><h1>${title}</h1><p class="sub">${subtitle}</p>${errorBlock}${form}<div class="note">${note}</div></main></body></html>`;
}

function pinLoginPage(error = "", lockedSeconds = 0) {
  const lockText = lockedSeconds > 0 ? `Too many failed attempts. Try again in about ${Math.ceil(lockedSeconds / 60)} minute(s).` : error;
  const form = `<form method="post" action="/artifact-library/login">
<div class="field"><label for="pin">6-digit Library PIN</label><input class="input pin" id="pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="current-password" required autofocus></div>
<button class="button" type="submit">Open Library</button></form>
<a class="link" href="/artifact-library/reset-pin">Forgot PIN? Reset with Core token</a>`;
  return authShell({
    title: "R2 Artifact Library",
    subtitle: "Private browser for objects stored in the Runner3 R2 artifacts bucket.",
    form,
    note: "Your PIN is verified only by Runner3 Core. After login, this device keeps an HttpOnly session for 30 days.",
    error: lockText,
  });
}

function pinSetupPage(error = "", reset = false) {
  const heading = reset ? "Reset Library PIN" : "Create Library PIN";
  const subtitle = reset
    ? "Use the Core token once to replace the Library PIN."
    : "Set a separate 6-digit PIN for quick access on this device.";
  const form = `<form method="post" action="/artifact-library/setup-pin">
<div class="field"><label for="core_token">Core access token</label><input class="input" id="core_token" name="core_token" type="password" autocomplete="current-password" required autofocus></div>
<div class="field"><label for="pin">New 6-digit PIN</label><input class="input pin" id="pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required></div>
<div class="field"><label for="pin_confirm">Confirm PIN</label><input class="input pin" id="pin_confirm" name="pin_confirm" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required></div>
<button class="button" type="submit">${reset ? "Reset PIN" : "Create PIN"}</button></form>`;
  return authShell({
    title: heading,
    subtitle,
    form,
    note: "The Core token is never stored by the page. The PIN is stored only as a salted PBKDF2-SHA256 hash in D1. Five failed PIN attempts lock that client for 15 minutes.",
    error,
  });
}

async function getPinRecord(env) {
  if (!env.DB) return null;
  return env.DB.prepare(
    "SELECT salt, pin_hash, iterations, updated_at FROM artifact_library_auth WHERE id = 1"
  ).first();
}

async function storePin(env, pin) {
  const saltBytes = crypto.getRandomValues(new Uint8Array(16));
  const salt = bytesToBase64(saltBytes);
  const derived = await derivePinHash(pin, salt, PIN_ITERATIONS);
  const hash = bytesToBase64(derived);
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    `INSERT INTO artifact_library_auth (id, salt, pin_hash, iterations, updated_at)
     VALUES (1, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET salt = excluded.salt, pin_hash = excluded.pin_hash, iterations = excluded.iterations, updated_at = excluded.updated_at`
  ).bind(salt, hash, PIN_ITERATIONS, now).run();
  await env.DB.prepare("DELETE FROM artifact_library_pin_attempts").run();
}

async function verifyPin(pin, record) {
  const iterations = Number(record?.iterations || PIN_ITERATIONS);
  const derived = await derivePinHash(pin, String(record.salt), iterations);
  return constantTimeEqual(derived, base64ToBytes(String(record.pin_hash)));
}

async function pinClientHash(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  return sha256Hex(`runner3-artifact-library-pin:${expectedArtifactToken(env)}:${ip}`);
}

async function pinRateState(request, env) {
  const now = Math.floor(Date.now() / 1000);
  const key = await pinClientHash(request, env);
  const row = await env.DB.prepare(
    "SELECT window_started_at, failures, blocked_until FROM artifact_library_pin_attempts WHERE client_hash = ?"
  ).bind(key).first();
  const blockedUntil = Number(row?.blocked_until || 0);
  return {
    key,
    row,
    now,
    blocked: blockedUntil > now,
    remaining: Math.max(0, blockedUntil - now),
  };
}

async function recordPinFailure(env, rate) {
  let windowStartedAt = rate.now;
  let failures = 1;
  if (rate.row && rate.now - Number(rate.row.window_started_at || 0) < PIN_LOCK_SECONDS) {
    windowStartedAt = Number(rate.row.window_started_at || rate.now);
    failures = Number(rate.row.failures || 0) + 1;
  }
  const blockedUntil = failures >= PIN_MAX_FAILURES ? rate.now + PIN_LOCK_SECONDS : 0;
  await env.DB.prepare(
    `INSERT INTO artifact_library_pin_attempts (client_hash, window_started_at, failures, blocked_until, updated_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(client_hash) DO UPDATE SET window_started_at = excluded.window_started_at, failures = excluded.failures, blocked_until = excluded.blocked_until, updated_at = excluded.updated_at`
  ).bind(rate.key, windowStartedAt, failures, blockedUntil, rate.now).run();
  return blockedUntil;
}

async function clearPinFailures(env, key) {
  await env.DB.prepare("DELETE FROM artifact_library_pin_attempts WHERE client_hash = ?").bind(key).run();
}

async function issueLibrarySession(env) {
  const session = await librarySessionValue(env);
  if (!session) return hardenedJson({ ok: false, error: "ARTIFACT_AUTH_NOT_CONFIGURED" }, 503);
  return new Response(null, {
    status: 303,
    headers: hardenedHeaders(new Headers({
      "Location": "/artifact-library",
      "Set-Cookie": libraryCookie(session),
    })),
  });
}

async function handlePinLogin(request, env) {
  if (request.method !== "POST") return hardenedJson({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB) return hardenedHtml(pinLoginPage("Library authentication database is unavailable."), 503);
  const record = await getPinRecord(env);
  if (!record) return hardenedHtml(pinSetupPage("Create a Library PIN first."), 409);

  const rate = await pinRateState(request, env);
  if (rate.blocked) return hardenedHtml(pinLoginPage("", rate.remaining), 429);

  const form = await request.formData();
  const pin = String(form.get("pin") || "").trim();
  const validFormat = /^\d{6}$/.test(pin);
  const ok = validFormat && await verifyPin(pin, record);
  if (!ok) {
    const blockedUntil = await recordPinFailure(env, rate);
    const remaining = Math.max(0, blockedUntil - rate.now);
    return hardenedHtml(pinLoginPage(remaining ? "" : "Incorrect PIN.", remaining), remaining ? 429 : 401);
  }

  await clearPinFailures(env, rate.key);
  return issueLibrarySession(env);
}

async function handleSetupPin(request, env) {
  if (request.method !== "POST") return hardenedJson({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB) return hardenedHtml(pinSetupPage("Library authentication database is unavailable."), 503);
  const expected = expectedArtifactToken(env);
  if (!expected) return hardenedHtml(pinSetupPage("Core authentication is not configured."), 503);

  const form = await request.formData();
  const coreToken = String(form.get("core_token") || "").trim();
  const pin = String(form.get("pin") || "").trim();
  const confirm = String(form.get("pin_confirm") || "").trim();
  if (coreToken !== expected) return hardenedHtml(pinSetupPage("Core token is incorrect.", Boolean(await getPinRecord(env))), 401);
  if (!/^\d{6}$/.test(pin)) return hardenedHtml(pinSetupPage("PIN must contain exactly 6 digits.", Boolean(await getPinRecord(env))), 400);
  if (pin !== confirm) return hardenedHtml(pinSetupPage("PIN confirmation does not match.", Boolean(await getPinRecord(env))), 400);

  await storePin(env, pin);
  return issueLibrarySession(env);
}

async function handlePinChange(request, env) {
  if (request.method !== "POST") return hardenedJson({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB) return hardenedJson({ ok: false, error: "D1_NOT_BOUND" }, 503);
  if (!(await hasLibrarySession(request, env))) return hardenedJson({ ok: false, error: "UNAUTHORIZED" }, 401);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return hardenedJson({ ok: false, error: "INVALID_JSON" }, 400);
  }
  const pin = String(payload?.pin || "").trim();
  if (!/^\d{6}$/.test(pin)) return hardenedJson({ ok: false, error: "PIN_MUST_BE_6_DIGITS" }, 400);
  await storePin(env, pin);
  return hardenedJson({ ok: true });
}

function injectLibraryControls(body) {
  if (body.includes('id="magic-link-button"') || body.includes('id="change-pin-button"')) return body;
  const logoutPattern = /(<form\b[^>]*\baction=["']\/artifact-library\/logout["'][^>]*>[\s\S]*?<\/form>)/i;
  if (!logoutPattern.test(body)) return body;

  body = body.replace(
    logoutPattern,
    '<div style="display:flex;gap:8px;align-items:center"><button class="logout" id="change-pin-button" type="button">PIN</button><button class="logout" id="magic-link-button" type="button">Magic link</button>$1</div>',
  );

  const script = `<script>
(()=>{
const magic=document.getElementById('magic-link-button');
if(magic)magic.addEventListener('click',async()=>{const label=magic.textContent;magic.disabled=true;magic.textContent='Creating…';try{const response=await fetch('/artifact-library/api/magic-link',{method:'POST',headers:{Accept:'application/json'}});const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||('HTTP '+response.status));if(navigator.clipboard&&navigator.clipboard.writeText){try{await navigator.clipboard.writeText(data.url)}catch(_){}}window.prompt('One-time magic link — valid 10 minutes',data.url)}catch(error){window.alert('Could not create magic link: '+error.message)}finally{magic.disabled=false;magic.textContent=label}});
const pinButton=document.getElementById('change-pin-button');
if(pinButton)pinButton.addEventListener('click',async()=>{const first=window.prompt('New 6-digit Library PIN');if(first===null)return;if(!/^\\d{6}$/.test(first)){window.alert('PIN must contain exactly 6 digits.');return}const second=window.prompt('Confirm new PIN');if(second!==first){window.alert('PIN confirmation does not match.');return}pinButton.disabled=true;try{const response=await fetch('/artifact-library/api/pin',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({pin:first})});const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||('HTTP '+response.status));window.alert('Library PIN updated.')}catch(error){window.alert('Could not update PIN: '+error.message)}finally{pinButton.disabled=false}});
})();
</script>`;
  return body.replace(/<\/body>/i, `${script}</body>`);
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
  if (new URL(request.url).pathname.startsWith("/artifact-library")) body = injectLibraryControls(body);
  return new Response(body, { status: response.status, statusText: response.statusText, headers });
}

async function mintMagicLink(request, env) {
  if (request.method !== "POST") return hardenedJson({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB) return hardenedJson({ ok: false, error: "D1_NOT_BOUND" }, 503);
  if (!(await hasLibrarySession(request, env))) return hardenedJson({ ok: false, error: "UNAUTHORIZED" }, 401);

  const now = Math.floor(Date.now() / 1000);
  const token = randomToken();
  const tokenHash = await sha256Hex(token);
  const expiresAt = now + MAGIC_TTL_SECONDS;

  try {
    await env.DB.prepare(
      "DELETE FROM artifact_library_magic_links WHERE expires_at < ?"
    ).bind(now - 86400).run();
    await env.DB.prepare(
      "INSERT INTO artifact_library_magic_links (id, token_hash, created_at, expires_at, used_at) VALUES (?, ?, ?, ?, NULL)"
    ).bind(crypto.randomUUID(), tokenHash, now, expiresAt).run();
  } catch {
    return hardenedJson({ ok: false, error: "MAGIC_LINK_STORE_FAILED" }, 503);
  }

  const url = new URL(request.url);
  url.pathname = "/artifact-library/magic";
  url.search = "";
  url.searchParams.set("t", token);
  return hardenedJson({
    ok: true,
    url: url.toString(),
    expires_at: expiresAt,
    ttl_seconds: MAGIC_TTL_SECONDS,
    one_time: true,
  });
}

async function consumeMagicLink(request, env) {
  if (request.method !== "GET") return hardenedJson({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB) return hardenedJson({ ok: false, error: "D1_NOT_BOUND" }, 503);

  const url = new URL(request.url);
  const token = (url.searchParams.get("t") || "").trim();
  if (!token || token.length < 32 || token.length > 128) {
    return hardenedJson({ ok: false, error: "MAGIC_LINK_INVALID" }, 410);
  }

  const now = Math.floor(Date.now() / 1000);
  const tokenHash = await sha256Hex(token);
  let changed = 0;
  try {
    const result = await env.DB.prepare(
      "UPDATE artifact_library_magic_links SET used_at = ? WHERE token_hash = ? AND used_at IS NULL AND expires_at >= ?"
    ).bind(now, tokenHash, now).run();
    changed = Number(result?.meta?.changes || 0);
  } catch {
    return hardenedJson({ ok: false, error: "MAGIC_LINK_CHECK_FAILED" }, 503);
  }

  if (changed !== 1) return hardenedJson({ ok: false, error: "MAGIC_LINK_INVALID_OR_EXPIRED" }, 410);
  return issueLibrarySession(env);
}

async function handleLibraryHome(request, env, ctx) {
  if (request.method !== "GET") return hardenedJson({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!expectedArtifactToken(env)) return hardenedHtml(pinLoginPage("Library authentication is not configured."), 503);
  if (await hasLibrarySession(request, env)) {
    return hardenArtifactResponse(request, await app.fetch(request, env, ctx));
  }
  if (!env.DB) return hardenedHtml(pinLoginPage("Library authentication database is unavailable."), 503);
  const record = await getPinRecord(env);
  return hardenedHtml(record ? pinLoginPage() : pinSetupPage());
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/artifact-library") return handleLibraryHome(request, env, ctx);
    if (url.pathname === "/artifact-library/login") return handlePinLogin(request, env);
    if (url.pathname === "/artifact-library/setup-pin") return handleSetupPin(request, env);
    if (url.pathname === "/artifact-library/reset-pin" && request.method === "GET") return hardenedHtml(pinSetupPage("", true));
    if (url.pathname === "/artifact-library/api/pin") return handlePinChange(request, env);
    if (url.pathname === "/artifact-library/api/magic-link") return mintMagicLink(request, env);
    if (url.pathname === "/artifact-library/magic") return consumeMagicLink(request, env);

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
