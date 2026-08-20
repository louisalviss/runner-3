import inner from './worker.js';

const encoder = new TextEncoder();
const ITEM_PREFIX = 'audio-library/items/';
const QUEUE_PREFIX = 'audio-library/queue/';
const TRASH_PREFIX = 'audio-library/trash/';

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...headers },
  });
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function timingSafeEqualStrings(a, b) {
  const [aHash, bHash] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(a || '')),
    crypto.subtle.digest('SHA-256', encoder.encode(b || '')),
  ]);
  return crypto.subtle.timingSafeEqual(aHash, bHash);
}

function cookieValue(request, name) {
  const raw = request.headers.get('cookie') || '';
  for (const part of raw.split(';')) {
    const idx = part.indexOf('=');
    if (idx < 0) continue;
    const key = part.slice(0, idx).trim();
    if (key === name) return decodeURIComponent(part.slice(idx + 1).trim());
  }
  return '';
}

async function sessionToken(env) {
  if (!env.RUNNER_SHARED_TOKEN || !env.LIBRARY_ACCESS_SHA256) return '';
  return sha256Hex(`audio-library-session-v2\0${env.RUNNER_SHARED_TOKEN}\0${env.LIBRARY_ACCESS_SHA256}`);
}

async function authorized(request, env) {
  const expected = await sessionToken(env);
  if (!expected) return false;
  const cookie = cookieValue(request, 'audio_library_session');
  const auth = request.headers.get('authorization') || '';
  const bearer = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  if (cookie && await timingSafeEqualStrings(cookie, expected)) return true;
  if (bearer && await timingSafeEqualStrings(bearer, expected)) return true;
  return false;
}

function loginPage(error = '') {
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#000"><title>Audio Library</title><style>
  :root{color-scheme:dark}*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:#000;color:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{min-height:100dvh;display:grid;place-items:center;padding:22px}.card{width:min(420px,100%);border:1px solid #2b2b2b;background:#080808;border-radius:20px;padding:22px}.title{font-size:26px;font-weight:760;letter-spacing:-.03em;margin:0 0 8px}.sub{color:#8f8f95;font-size:14px;margin-bottom:20px}.field{width:100%;height:50px;border:1px solid #333;border-radius:13px;background:#000;color:#fff;padding:0 14px;font-size:17px;outline:none}.field:focus{border-color:#777}.btn{width:100%;height:50px;margin-top:10px;border:0;border-radius:13px;background:#fff;color:#000;font-size:16px;font-weight:750}.note{color:#777;font-size:12px;margin-top:12px;text-align:center}.err{color:#ff7979;font-size:13px;margin:0 0 10px}</style></head><body><form class="card" method="post" action="/login"><h1 class="title">Audio Library</h1><div class="sub">Nhập pass một lần. Safari sẽ ghi nhớ phiên đăng nhập trên thiết bị này.</div>${error ? `<div class="err">${error}</div>` : ''}<input class="field" name="password" type="password" autocomplete="current-password" autofocus placeholder="Pass" required><button class="btn" type="submit">Mở thư viện</button><div class="note">Phiên được lưu trên máy, không lưu lại pass.</div></form><script>(()=>{try{const t=localStorage.getItem('audio-library-session-v2');if(t){document.cookie='audio_library_session='+encodeURIComponent(t)+'; Max-Age=31536000; Path=/; Secure; SameSite=Lax';location.replace('/')}}catch{}})();</script></body></html>`;
}

function rememberPage(token) {
  const safe = JSON.stringify(token);
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#000"></head><body style="margin:0;background:#000;color:#fff"><script>try{localStorage.setItem('audio-library-session-v2',${safe});document.cookie='audio_library_session='+encodeURIComponent(${safe})+'; Max-Age=31536000; Path=/; Secure; SameSite=Lax'}catch{}location.replace('/');</script></body></html>`;
}

async function login(request, env) {
  let password = '';
  let wantsJson = false;
  try {
    const type = request.headers.get('content-type') || '';
    if (type.includes('application/json')) {
      wantsJson = true;
      password = String((await request.json())?.password || '');
    } else {
      password = String((await request.formData()).get('password') || '');
    }
  } catch {}
  const suppliedHash = await sha256Hex(password);
  if (!env.LIBRARY_ACCESS_SHA256 || !(await timingSafeEqualStrings(suppliedHash, env.LIBRARY_ACCESS_SHA256))) {
    if (wantsJson) return json({ error: 'Pass không đúng' }, 401);
    return new Response(loginPage('Pass không đúng.'), { status: 401, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });
  }
  const token = await sessionToken(env);
  const cookie = `audio_library_session=${encodeURIComponent(token)}; Max-Age=31536000; Path=/; HttpOnly; Secure; SameSite=Lax`;
  if (wantsJson) return json({ ok: true, token }, 200, { 'set-cookie': cookie });
  return new Response(rememberPage(token), {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'set-cookie': cookie },
  });
}

async function softDelete(request, env, id) {
  const key = `${ITEM_PREFIX}${id}.json`;
  const itemObject = await env.AUDIO_BUCKET.get(key);
  if (!itemObject) return json({ error: 'Không tìm thấy audio' }, 404);
  let item;
  try { item = JSON.parse(await itemObject.text()); } catch { return json({ error: 'Metadata audio lỗi' }, 500); }
  const now = new Date();
  const trash = { id, deletedAt: now.toISOString(), purgeAfter: new Date(now.getTime() + 30 * 86400000).toISOString(), item };
  await env.AUDIO_BUCKET.put(`${TRASH_PREFIX}${id}.json`, JSON.stringify(trash), {
    httpMetadata: { contentType: 'application/json; charset=utf-8' },
  });
  await env.AUDIO_BUCKET.delete([key, `${QUEUE_PREFIX}${id}.json`]);
  return new Response(null, { status: 204 });
}

async function appResponse(request, env, ctx) {
  const response = await inner.fetch(request, env, ctx);
  if (!response.ok || !(response.headers.get('content-type') || '').includes('text/html')) return response;
  const token = await sessionToken(env);
  let body = await response.text();
  const bootstrap = `<script>(()=>{const t=${JSON.stringify(token)};try{localStorage.setItem('audio-library-session-v2',t)}catch{}const nf=window.fetch.bind(window);window.fetch=(input,init={})=>{try{const u=new URL(typeof input==='string'?input:input.url,location.href);if(u.origin===location.origin&&u.pathname.startsWith('/api/')){const h=new Headers(init.headers||(typeof input!=='string'?input.headers:undefined)||{});h.set('authorization','Bearer '+t);init={...init,headers:h}}}catch{}return nf(input,init)};})();</script>`;
  body = body.replace('<body>', '<body>' + bootstrap);
  const headers = new Headers(response.headers);
  headers.set('content-type', 'text/html; charset=utf-8');
  headers.set('cache-control', 'no-store');
  headers.delete('content-length');
  return new Response(body, { status: response.status, headers });
}

async function handle(request, env, ctx) {
  const url = new URL(request.url);

  if (url.pathname.startsWith('/api/runner/')) return inner.fetch(request, env, ctx);
  if (url.pathname === '/health') return json({ ok: true, service: 'runner3-audio-library', access: 'password', remembered: true, auth: 'cookie+bearer-v2', softDeleteDays: 30 });
  if (url.pathname === '/login' && request.method === 'POST') return login(request, env);
  if (url.pathname === '/logout') {
    return new Response(`<!doctype html><script>try{localStorage.removeItem('audio-library-session-v2')}catch{}location.replace('/')</script>`, {
      status: 200,
      headers: { 'content-type': 'text/html; charset=utf-8', 'set-cookie': 'audio_library_session=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax' },
    });
  }

  const ok = await authorized(request, env);
  if (!ok) {
    if (url.pathname.startsWith('/api/')) return json({ error: 'Unauthorized' }, 401);
    return new Response(loginPage(), { status: 200, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });
  }

  const m = url.pathname.match(/^\/api\/items\/([0-9a-f-]+)$/i);
  if (m && request.method === 'DELETE') return softDelete(request, env, m[1]);
  if (url.pathname === '/' && request.method === 'GET') return appResponse(request, env, ctx);
  return inner.fetch(request, env, ctx);
}

export default {
  async fetch(request, env, ctx) {
    try { return await handle(request, env, ctx); }
    catch (error) {
      console.error(JSON.stringify({ event: 'audio_library_auth_wrapper_error', message: String(error?.stack || error) }));
      return json({ error: 'Internal error' }, 500);
    }
  },
  async scheduled(controller, env, ctx) {
    if (inner.scheduled) return inner.scheduled(controller, env, ctx);
  },
};
