import app from "./artifact-list-entry.js";

const ARTIFACT_PREFIXES = ["/artifact-library", "/artifact-list"];
const LIBRARY_COOKIE = "r3_artifact_library";
const REMEMBER_SECONDS = 30 * 24 * 60 * 60;
const MAGIC_TTL_SECONDS = 10 * 60;
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
  const cookie = next.get("Set-Cookie");
  if (cookie && cookie.includes(`${LIBRARY_COOKIE}=`)) {
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

function injectMagicLinkUi(body) {
  if (body.includes('id="magic-link-button"')) return body;
  const logoutPattern = /(<form\b[^>]*\baction=["']\/artifact-library\/logout["'][^>]*>[\s\S]*?<\/form>)/i;
  if (!logoutPattern.test(body)) return body;

  body = body.replace(
    logoutPattern,
    '<div style="display:flex;gap:8px;align-items:center"><button class="logout" id="magic-link-button" type="button">Magic link</button>$1</div>',
  );

  const script = `<script>
(()=>{const button=document.getElementById('magic-link-button');if(!button)return;button.addEventListener('click',async()=>{const label=button.textContent;button.disabled=true;button.textContent='Creating…';try{const response=await fetch('/artifact-library/api/magic-link',{method:'POST',headers:{Accept:'application/json'}});const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||('HTTP '+response.status));if(navigator.clipboard&&navigator.clipboard.writeText){try{await navigator.clipboard.writeText(data.url)}catch(_){}}window.prompt('One-time magic link — valid 10 minutes',data.url)}catch(error){window.alert('Could not create magic link: '+error.message)}finally{button.disabled=false;button.textContent=label}})})();
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
  if (new URL(request.url).pathname.startsWith("/artifact-library")) body = injectMagicLinkUi(body);
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
  } catch (error) {
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
  } catch (error) {
    return hardenedJson({ ok: false, error: "MAGIC_LINK_CHECK_FAILED" }, 503);
  }

  if (changed !== 1) return hardenedJson({ ok: false, error: "MAGIC_LINK_INVALID_OR_EXPIRED" }, 410);

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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/artifact-library/api/magic-link") {
      return mintMagicLink(request, env);
    }
    if (url.pathname === "/artifact-library/magic") {
      return consumeMagicLink(request, env);
    }

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
