import app from "./artifact-library-pin-v2-entry.js";

const ROOT = "core/ebook/";
const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const TEST_SCOPE_PREFIXES = [
  "core/ebook/ebook-resume-proof-",
  "core/ebook/ebook-runtime-smoke-",
  "core/ebook/ebook-runtime-codex-smoke-",
];
const EXACT_TEST_BASENAMES = new Set([
  "smoke-book.vi.epub",
  "smoke-book.codex.vi.epub",
  "mailbox-bookforge-codex-smoke.vi.epub",
]);
const RESUME_PROOF_BASENAME = /^resume-proof-v\d+\.vi\.epub$/;
const EPUBJS_URL = "https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js";
const JSZIP_URL = "https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js";

function expectedToken(env) {
  return typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
}

function authorized(request, env) {
  const expected = expectedToken(env);
  if (!expected) return false;
  const auth = request.headers.get("Authorization") || "";
  return auth.startsWith("Bearer ") && auth.slice(7).trim() === expected;
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

function classify(key) {
  if (!key.startsWith(ROOT)) return null;
  if (key.startsWith("core/ebook/dcc-")) return null;

  const scopePrefix = TEST_SCOPE_PREFIXES.find((prefix) => key.startsWith(prefix));
  if (scopePrefix) return { reason: "explicit_test_scope", scope_prefix: scopePrefix };

  const basename = key.slice(key.lastIndexOf("/") + 1);
  if (EXACT_TEST_BASENAMES.has(basename)) {
    return { reason: "exact_test_fixture_basename", basename };
  }
  if (RESUME_PROOF_BASENAME.test(basename)) {
    return { reason: "resume_proof_fixture_basename", basename };
  }
  return null;
}

async function listAll(env) {
  const objects = [];
  let cursor;
  for (;;) {
    const page = await env.ARTIFACTS.list({ prefix: ROOT, cursor, limit: 1000 });
    for (const object of page.objects || []) objects.push(object);
    if (!page.truncated || !page.cursor) break;
    cursor = page.cursor;
  }
  return objects;
}

async function cleanup(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!authorized(request, env)) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  if (!env.ARTIFACTS) return json({ ok: false, error: "ARTIFACTS_BINDING_MISSING" }, 503);

  const url = new URL(request.url);
  const apply = url.searchParams.get("apply") === "1";
  const all = await listAll(env);
  const candidates = [];

  for (const object of all) {
    const rule = classify(object.key);
    if (!rule) continue;
    candidates.push({
      key: object.key,
      size: Number(object.size || 0),
      uploaded: object.uploaded ? new Date(object.uploaded).toISOString() : null,
      ...rule,
    });
  }

  const protectedDccCount = all.filter((object) => object.key.startsWith("core/ebook/dcc-")).length;
  if (candidates.some((item) => item.key.startsWith("core/ebook/dcc-"))) {
    return json({ ok: false, error: "DCC_SAFETY_GUARD_TRIPPED" }, 500);
  }

  const deleted = [];
  if (apply) {
    for (const item of candidates) {
      await env.ARTIFACTS.delete(item.key);
      deleted.push(item.key);
    }
  }

  return json({
    ok: true,
    mode: apply ? "apply" : "dry-run",
    root: ROOT,
    scanned_count: all.length,
    candidate_count: candidates.length,
    protected_dcc_object_count: protectedDccCount,
    candidates,
    deleted_count: deleted.length,
    deleted,
  });
}

function htmlEscape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function displayName(key) {
  const raw = key.split("/").filter(Boolean).pop() || "EPUB";
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

async function hasLibrarySession(request, env, ctx) {
  const target = new URL("/artifact-library/api/list", request.url);
  target.searchParams.set("prefix", ROOT);
  target.searchParams.set("limit", "1");
  const probe = new Request(target.toString(), {
    method: "GET",
    headers: {
      "Cookie": request.headers.get("Cookie") || "",
      "Accept": "application/json",
      "User-Agent": request.headers.get("User-Agent") || "runner3-reader-session-probe/1.0",
    },
  });
  const response = await app.fetch(probe, env, ctx);
  return response.status === 200;
}

function readerPage(key) {
  const keyJson = JSON.stringify(key).replaceAll("<", "\\u003c");
  const title = htmlEscape(displayName(key));
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">
<title>${title}</title>
<style>
:root{font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light;--bg:#f7f7f4;--panel:#fff;--text:#1c1d20;--muted:#6e737b;--line:#d9dce1;--button:#f0f1f3;--active:#1d2025;--activeText:#fff}*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden}body{height:100dvh;background:var(--bg);color:var(--text);display:grid;grid-template-rows:auto minmax(0,1fr) auto;transition:background .18s,color .18s}body[data-theme="dark"]{color-scheme:dark;--bg:#0d0f12;--panel:#14171b;--text:#e9edf2;--muted:#9199a5;--line:#2b3038;--button:#1d2229;--active:#edf1f5;--activeText:#111317}body[data-theme="brown"]{color-scheme:light;--bg:#e9dcc0;--panel:#f0e4ca;--text:#4a3829;--muted:#846d58;--line:#cdbb99;--button:#dfcfad;--active:#5b422d;--activeText:#f8edd7}.bar{background:color-mix(in srgb,var(--panel) 94%,transparent);border-bottom:1px solid var(--line);padding:max(8px,env(safe-area-inset-top)) 10px 8px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:center;z-index:10}.back,.control,.theme,.nav{appearance:none;border:1px solid var(--line);background:var(--button);color:var(--text);border-radius:10px;height:36px;padding:0 11px;font:inherit;font-size:13px;font-weight:700;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}.book-title{min-width:0;text-align:center;font-size:13px;font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tools{display:flex;gap:5px;align-items:center}.font-label{min-width:43px;text-align:center;color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}.theme{width:34px;padding:0;font-size:0}.theme::after{content:"";width:15px;height:15px;border-radius:50%;border:1px solid var(--line)}.theme[data-theme="light"]::after{background:#fff}.theme[data-theme="dark"]::after{background:#15181d}.theme[data-theme="brown"]::after{background:#b48a58}.theme.active{outline:2px solid var(--active);outline-offset:1px}#viewer{min-height:0;width:100%;height:100%;overflow:hidden;background:var(--bg);position:relative}#loading{position:absolute;inset:0;display:grid;place-items:center;padding:28px;color:var(--muted);font-size:13px;text-align:center;z-index:3;pointer-events:none}.bottom{border-top:1px solid var(--line);background:var(--panel);padding:8px 10px max(8px,env(safe-area-inset-bottom));display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;z-index:10}.position{text-align:center;color:var(--muted);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nav{min-width:56px;font-size:18px}.hidden{display:none!important}@media(max-width:640px){.bar{grid-template-columns:auto minmax(0,1fr)}.tools{grid-column:1/-1;justify-content:center}.book-title{text-align:left}.control{height:34px}.theme{height:34px}.back{height:34px}}
</style>
</head>
<body data-theme="light">
<header class="bar"><a class="back" href="/artifact-library">‹ Library</a><div class="book-title" title="${title}">${title}</div><div class="tools"><button id="fontDown" class="control" type="button" aria-label="Smaller text">A−</button><span id="fontLabel" class="font-label">100%</span><button id="fontUp" class="control" type="button" aria-label="Larger text">A+</button><button class="theme" type="button" data-theme="light" aria-label="Light mode"></button><button class="theme" type="button" data-theme="dark" aria-label="Dark mode"></button><button class="theme" type="button" data-theme="brown" aria-label="Brown mode"></button></div></header>
<main id="viewer"><div id="loading">Preparing EPUB…</div></main>
<footer class="bottom"><button id="prev" class="nav" type="button" aria-label="Previous page">‹</button><div id="position" class="position">Opening book…</div><button id="next" class="nav" type="button" aria-label="Next page">›</button></footer>
<script src="/artifact-library/vendor/jszip.min.js"></script>
<script src="/artifact-library/vendor/epub.min.js"></script>
<script>
(() => {
  const key=${keyJson};
  const fontKey='r3-reader-font-size';
  const themeKey='r3-reader-theme';
  const positionKey='r3-reader-position:'+key;
  let fontSize=Math.min(180,Math.max(70,parseInt(localStorage.getItem(fontKey)||'100',10)||100));
  let theme=['light','dark','brown'].includes(localStorage.getItem(themeKey))?localStorage.getItem(themeKey):'light';
  let book=null;
  let rendition=null;
  const $=id=>document.getElementById(id);

  function updateChrome(){
    document.body.dataset.theme=theme;
    $('fontLabel').textContent=fontSize+'%';
    document.querySelectorAll('.theme').forEach(btn=>btn.classList.toggle('active',btn.dataset.theme===theme));
  }

  function applyReaderTheme(){
    updateChrome();
    if(!rendition)return;
    rendition.themes.select(theme);
    rendition.themes.fontSize(fontSize+'%');
  }

  function registerThemes(){
    rendition.themes.register('light',{
      'html,body':{'background':'#f7f7f4 !important','color':'#1c1d20 !important'},
      'body':{'padding-left':'3% !important','padding-right':'3% !important','line-height':'1.62 !important'},
      'a':{'color':'#375c7d !important'}
    });
    rendition.themes.register('dark',{
      'html,body':{'background':'#0d0f12 !important','color':'#e9edf2 !important'},
      'body':{'padding-left':'3% !important','padding-right':'3% !important','line-height':'1.62 !important'},
      'a':{'color':'#8ab4df !important'}
    });
    rendition.themes.register('brown',{
      'html,body':{'background':'#e9dcc0 !important','color':'#4a3829 !important'},
      'body':{'padding-left':'3% !important','padding-right':'3% !important','line-height':'1.62 !important'},
      'a':{'color':'#765431 !important'}
    });
  }

  async function signedUrl(){
    const r=await fetch('/artifact-library/api/delivery',{
      method:'POST',credentials:'same-origin',
      headers:{'content-type':'application/json','x-runner3-library':'1'},
      body:JSON.stringify({key,ttl_seconds:3600})
    });
    if(r.status===401){location.href='/artifact-library';throw new Error('Session expired');}
    const data=await r.json();
    if(!r.ok||data.ok!==true||!data.delivery||!data.delivery.url)throw new Error(data.error||('HTTP '+r.status));
    return data.delivery.url;
  }

  async function openBook(){
    try{
      if(typeof window.ePub!=='function')throw new Error('Reader engine failed to load');
      $('loading').textContent='Loading EPUB…';
      const url=await signedUrl();
      const response=await fetch(url,{credentials:'same-origin'});
      if(!response.ok)throw new Error('EPUB download failed: HTTP '+response.status);
      const buffer=await response.arrayBuffer();
      $('loading').textContent='Opening book…';
      book=window.ePub(buffer);
      rendition=book.renderTo('viewer',{width:'100%',height:'100%',spread:'none',flow:'paginated',manager:'default'});
      registerThemes();
      applyReaderTheme();
      rendition.on('relocated',loc=>{
        const cfi=loc&&loc.start&&loc.start.cfi;
        if(cfi)localStorage.setItem(positionKey,cfi);
        const pct=loc&&loc.start&&Number.isFinite(loc.start.percentage)?Math.round(loc.start.percentage*100):null;
        $('position').textContent=pct===null?'Position saved':pct+'% · saved';
      });
      rendition.on('rendered',()=>{$('loading').classList.add('hidden');});
      const saved=localStorage.getItem(positionKey)||'';
      try{
        await rendition.display(saved||undefined);
      }catch(error){
        localStorage.removeItem(positionKey);
        await rendition.display();
      }
      $('loading').classList.add('hidden');
    }catch(error){
      $('loading').classList.remove('hidden');
      $('loading').textContent='Could not open this EPUB. '+String(error&&error.message||error);
      $('position').textContent='Reader error';
    }
  }

  $('fontDown').addEventListener('click',()=>{fontSize=Math.max(70,fontSize-10);localStorage.setItem(fontKey,String(fontSize));applyReaderTheme();});
  $('fontUp').addEventListener('click',()=>{fontSize=Math.min(180,fontSize+10);localStorage.setItem(fontKey,String(fontSize));applyReaderTheme();});
  document.querySelectorAll('.theme').forEach(btn=>btn.addEventListener('click',()=>{theme=btn.dataset.theme;localStorage.setItem(themeKey,theme);applyReaderTheme();}));
  $('prev').addEventListener('click',()=>rendition&&rendition.prev());
  $('next').addEventListener('click',()=>rendition&&rendition.next());
  document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'&&rendition)rendition.prev();if(e.key==='ArrowRight'&&rendition)rendition.next();});

  let sx=0,sy=0;
  $('viewer').addEventListener('touchstart',e=>{const t=e.changedTouches&&e.changedTouches[0];if(t){sx=t.clientX;sy=t.clientY;}},{passive:true});
  $('viewer').addEventListener('touchend',e=>{const t=e.changedTouches&&e.changedTouches[0];if(!t||!rendition)return;const dx=t.clientX-sx,dy=t.clientY-sy;if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.3){if(dx>0)rendition.prev();else rendition.next();}},{passive:true});
  window.addEventListener('beforeunload',()=>{try{book&&book.destroy();}catch{}});
  updateChrome();
  openBook();
})();
</script>
</body></html>`;
}

async function reader(request, env, ctx) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!(await hasLibrarySession(request, env, ctx))) {
    return new Response(null, { status: 303, headers: headers({ Location: "/artifact-library" }) });
  }
  const url = new URL(request.url);
  const key = String(url.searchParams.get("key") || "");
  if (!key.startsWith(ROOT) || !key.toLowerCase().endsWith(".epub")) {
    return json({ ok: false, error: "INVALID_EPUB_KEY" }, 400);
  }
  const object = await env.ARTIFACTS?.head(key);
  if (!object) return json({ ok: false, error: "EPUB_NOT_FOUND" }, 404);
  return new Response(readerPage(key), {
    status: 200,
    headers: headers({
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    }),
  });
}

async function vendorScript(request, sourceUrl) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  try {
    const upstream = await fetch(sourceUrl, { headers: { "Accept": "application/javascript,*/*;q=0.8" } });
    if (!upstream.ok) return json({ ok: false, error: "READER_VENDOR_FETCH_FAILED", status: upstream.status }, 502);
    const body = await upstream.arrayBuffer();
    const h = headers({
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=604800, immutable",
      "Cross-Origin-Resource-Policy": "same-origin",
    });
    h.delete("Pragma");
    return new Response(body, { status: 200, headers: h });
  } catch (error) {
    return json({ ok: false, error: "READER_VENDOR_FETCH_FAILED", detail: String(error?.message || error) }, 502);
  }
}

function injectReaderButton(body) {
  if (!body.includes('id="list"') || body.includes('data-r3-reader-ui="1"')) return body;
  const addition = `<style data-r3-reader-ui="1">.r3-read{display:inline-flex!important;align-items:center;justify-content:center;text-decoration:none}.right .r3-read{margin-left:auto}@media(max-width:760px){.right .r3-read{margin-left:0}}</style><script data-r3-reader-ui="1">(()=>{function attach(){document.querySelectorAll('.row').forEach(row=>{if(row.querySelector('.r3-read'))return;const path=row.querySelector('.path');const right=row.querySelector('.right');if(!path||!right)return;const key=(path.textContent||'').trim();if(!key.toLowerCase().endsWith('.epub'))return;const read=document.createElement('a');read.className='download r3-read';read.textContent='Read';read.href='/artifact-library/read?key='+encodeURIComponent(key);const download=right.querySelector('.download');if(download)right.insertBefore(read,download);else right.appendChild(read);});}attach();const list=document.getElementById('list');if(list)new MutationObserver(attach).observe(list,{childList:true,subtree:true});})();</script>`;
  return body.includes("</body>") ? body.replace("</body>", addition + "</body>") : body + addition;
}

async function maybeInjectLibraryReader(request, env, ctx) {
  const response = await app.fetch(request, env, ctx);
  const type = response.headers.get("Content-Type") || "";
  if (request.method !== "GET" || !type.toLowerCase().includes("text/html")) return response;
  const body = await response.text();
  const updated = injectReaderButton(body);
  if (updated === body) return new Response(body, { status: response.status, headers: response.headers });
  const h = new Headers(response.headers);
  h.set("Content-Length", String(new TextEncoder().encode(updated).length));
  return new Response(updated, { status: response.status, headers: h });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/artifact-cleanup-tests") return cleanup(request, env);
    if (url.pathname === "/artifact-library/read") return reader(request, env, ctx);
    if (url.pathname === "/artifact-library/vendor/epub.min.js") return vendorScript(request, EPUBJS_URL);
    if (url.pathname === "/artifact-library/vendor/jszip.min.js") return vendorScript(request, JSZIP_URL);
    if (url.pathname === "/artifact-library") return maybeInjectLibraryReader(request, env, ctx);
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
