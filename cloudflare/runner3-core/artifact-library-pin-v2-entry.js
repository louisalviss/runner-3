import app from "./artifact-library-hardening-entry.js";

const LIBRARY_COOKIE = "r3_artifact_library";
const REMEMBER_SECONDS = 30 * 24 * 60 * 60;
const PIN_MAX_FAILURES = 5;
const PIN_LOCK_SECONDS = 15 * 60;
const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const HMAC_MARKER = -1;

function expectedToken(env) {
  return typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
}

function getCookie(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i >= 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return "";
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sessionValue(env) {
  const token = expectedToken(env);
  return token ? sha256Hex(`runner3-artifact-library-v1:${token}`) : "";
}

async function hasSession(request, env) {
  const expected = await sessionValue(env);
  return Boolean(expected) && getCookie(request, LIBRARY_COOKIE) === expected;
}

function cookie(value, maxAge = REMEMBER_SECONDS) {
  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Strict`;
}

function headers(base = {}) {
  const h = new Headers(base);
  h.set("X-Robots-Tag", ROBOTS);
  h.set("Cache-Control", "private, no-store, max-age=0");
  h.set("Pragma", "no-cache");
  h.set("Referrer-Policy", "no-referrer");
  h.set("X-Frame-Options", "DENY");
  return h;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: headers({ "Content-Type": "application/json; charset=utf-8" }),
  });
}

function html(body, status = 200) {
  return new Response(body, {
    status,
    headers: headers({
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    }),
  });
}

function page({ title, subtitle, form, note, error = "" }) {
  const err = error ? `<div class="error">${error}</div>` : "";
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex"><title>Runner3 R2 Library</title><style>:root{color-scheme:dark;background:#0a0b0d;color:#f5f7fa;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 20% 0%,#18202c 0,transparent 35%),#0a0b0d;padding:24px}.card{width:min(440px,100%);background:#111419;border:1px solid #252b33;border-radius:20px;padding:28px;box-shadow:0 24px 80px rgba(0,0,0,.38)}.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8f9bac;font-weight:700}h1{font-size:28px;margin:8px 0}.sub{color:#9da7b5;line-height:1.5;margin:0 0 24px}.field{display:grid;gap:8px;margin-top:12px}label{font-size:13px;color:#cbd2dc}.input{width:100%;border:1px solid #303844;background:#0b0e12;color:#fff;border-radius:12px;padding:13px 14px;font-size:18px;outline:none}.pin{letter-spacing:.3em;text-align:center;font-variant-numeric:tabular-nums}.button{width:100%;margin-top:14px;border:0;border-radius:12px;padding:13px 16px;background:#f2f5f8;color:#0a0b0d;font-weight:800;font-size:15px}.error{background:#35191c;color:#ffb4bd;border:1px solid #673039;border-radius:10px;padding:10px 12px;margin-bottom:14px;font-size:13px}.note{font-size:12px;color:#6f7987;margin-top:14px;line-height:1.5}.link{display:inline-block;margin-top:12px;color:#aeb9c8;font-size:12px;text-decoration:none}</style></head><body><main class="card"><div class="eyebrow">Runner3 Core</div><h1>${title}</h1><p class="sub">${subtitle}</p>${err}${form}<div class="note">${note}</div></main></body></html>`;
}

function loginPage(error = "", remaining = 0) {
  const message = remaining > 0 ? `Too many failed attempts. Try again in about ${Math.ceil(remaining / 60)} minute(s).` : error;
  return page({
    title: "R2 Artifact Library",
    subtitle: "Private browser for objects stored in the Runner3 R2 artifacts bucket.",
    form: `<form method="post" action="/artifact-library/login"><div class="field"><label for="pin">6-digit Library PIN</label><input class="input pin" id="pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="current-password" required autofocus></div><button class="button" type="submit">Open Library</button></form><a class="link" href="/artifact-library/reset-pin">Forgot PIN? Reset with Core token</a>`,
    note: "The PIN is separate from the Core token. This device keeps an HttpOnly session for 30 days after a successful login.",
    error: message,
  });
}

function setupPage(error = "", reset = false) {
  return page({
    title: reset ? "Reset Library PIN" : "Create Library PIN",
    subtitle: reset ? "Use the Core token once to replace the Library PIN." : "Set a separate 6-digit PIN for quick access.",
    form: `<form method="post" action="/artifact-library/setup-pin"><div class="field"><label for="core_token">Core access token</label><input class="input" id="core_token" name="core_token" type="password" autocomplete="current-password" required autofocus></div><div class="field"><label for="pin">New 6-digit PIN</label><input class="input pin" id="pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required></div><div class="field"><label for="pin_confirm">Confirm PIN</label><input class="input pin" id="pin_confirm" name="pin_confirm" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required></div><button class="button" type="submit">${reset ? "Reset PIN" : "Create PIN"}</button></form>`,
    note: "The Core token is used only to authorize PIN setup/reset. D1 stores a salted HMAC-SHA256 digest keyed by the Core secret, never the PIN itself. Five failed attempts lock that client for 15 minutes.",
    error,
  });
}

async function record(env) {
  if (!env.DB) return null;
  return env.DB.prepare("SELECT salt, pin_hash, iterations FROM artifact_library_auth WHERE id=1").first();
}

async function hmacDigest(env, pin, salt) {
  const token = expectedToken(env);
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(token), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signed = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${salt}:${pin}`));
  return btoa(String.fromCharCode(...new Uint8Array(signed)));
}

function randomSalt() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}

async function savePin(env, pin) {
  const salt = randomSalt();
  const digest = await hmacDigest(env, pin, salt);
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(`INSERT INTO artifact_library_auth (id,salt,pin_hash,iterations,updated_at) VALUES (1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET salt=excluded.salt,pin_hash=excluded.pin_hash,iterations=excluded.iterations,updated_at=excluded.updated_at`).bind(salt, digest, HMAC_MARKER, now).run();
  await env.DB.prepare("DELETE FROM artifact_library_pin_attempts").run();
}

async function verifyPin(env, pin, row) {
  if (Number(row?.iterations) !== HMAC_MARKER) return false;
  const actual = await hmacDigest(env, pin, String(row.salt));
  const expected = String(row.pin_hash);
  if (actual.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < actual.length; i++) diff |= actual.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

async function clientKey(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  return sha256Hex(`runner3-artifact-library-pin:${expectedToken(env)}:${ip}`);
}

async function rateState(request, env) {
  const now = Math.floor(Date.now() / 1000);
  const key = await clientKey(request, env);
  const row = await env.DB.prepare("SELECT window_started_at,failures,blocked_until FROM artifact_library_pin_attempts WHERE client_hash=?").bind(key).first();
  const blockedUntil = Number(row?.blocked_until || 0);
  return { key, row, now, remaining: Math.max(0, blockedUntil - now), blocked: blockedUntil > now };
}

async function fail(env, state) {
  let start = state.now;
  let failures = 1;
  if (state.row && state.now - Number(state.row.window_started_at || 0) < PIN_LOCK_SECONDS) {
    start = Number(state.row.window_started_at || state.now);
    failures = Number(state.row.failures || 0) + 1;
  }
  const blockedUntil = failures >= PIN_MAX_FAILURES ? state.now + PIN_LOCK_SECONDS : 0;
  await env.DB.prepare(`INSERT INTO artifact_library_pin_attempts (client_hash,window_started_at,failures,blocked_until,updated_at) VALUES (?,?,?,?,?) ON CONFLICT(client_hash) DO UPDATE SET window_started_at=excluded.window_started_at,failures=excluded.failures,blocked_until=excluded.blocked_until,updated_at=excluded.updated_at`).bind(state.key, start, failures, blockedUntil, state.now).run();
  return blockedUntil;
}

async function issueSession(env) {
  const value = await sessionValue(env);
  return new Response(null, { status: 303, headers: headers({ Location: "/artifact-library", "Set-Cookie": cookie(value) }) });
}

async function home(request, env, ctx) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!expectedToken(env) || !env.DB) return html(loginPage("Library authentication is unavailable."), 503);
  if (await hasSession(request, env)) return app.fetch(request, env, ctx);
  return html((await record(env)) ? loginPage() : setupPage());
}

async function login(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  const row = await record(env);
  if (!row) return html(setupPage("Create a Library PIN first."), 409);
  if (Number(row.iterations) !== HMAC_MARKER) return html(setupPage("PIN storage needs a one-time reset with the Core token.", true), 409);
  const state = await rateState(request, env);
  if (state.blocked) return html(loginPage("", state.remaining), 429);
  const form = await request.formData();
  const pin = String(form.get("pin") || "").trim();
  if (!/^\d{6}$/.test(pin) || !(await verifyPin(env, pin, row))) {
    const blockedUntil = await fail(env, state);
    const remaining = Math.max(0, blockedUntil - state.now);
    return html(loginPage(remaining ? "" : "Incorrect PIN.", remaining), remaining ? 429 : 401);
  }
  await env.DB.prepare("DELETE FROM artifact_library_pin_attempts WHERE client_hash=?").bind(state.key).run();
  return issueSession(env);
}

async function setup(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB || !expectedToken(env)) return html(setupPage("Library authentication is unavailable."), 503);
  const form = await request.formData();
  const core = String(form.get("core_token") || "").trim();
  const pin = String(form.get("pin") || "").trim();
  const confirm = String(form.get("pin_confirm") || "").trim();
  const resetting = Boolean(await record(env));
  if (core !== expectedToken(env)) return html(setupPage("Core token is incorrect.", resetting), 401);
  if (!/^\d{6}$/.test(pin)) return html(setupPage("PIN must contain exactly 6 digits.", resetting), 400);
  if (pin !== confirm) return html(setupPage("PIN confirmation does not match.", resetting), 400);
  try {
    await savePin(env, pin);
  } catch (error) {
    return json({ ok: false, error: "PIN_STORE_FAILED", detail: String(error?.message || error) }, 500);
  }
  return issueSession(env);
}

async function changePin(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!(await hasSession(request, env))) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  let data;
  try { data = await request.json(); } catch { return json({ ok: false, error: "INVALID_JSON" }, 400); }
  const pin = String(data?.pin || "").trim();
  if (!/^\d{6}$/.test(pin)) return json({ ok: false, error: "PIN_MUST_BE_6_DIGITS" }, 400);
  await savePin(env, pin);
  return json({ ok: true });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/artifact-library") return home(request, env, ctx);
    if (url.pathname === "/artifact-library/login") return login(request, env);
    if (url.pathname === "/artifact-library/setup-pin") return setup(request, env);
    if (url.pathname === "/artifact-library/reset-pin" && request.method === "GET") return html(setupPage("", true));
    if (url.pathname === "/artifact-library/api/pin") return changePin(request, env);
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
