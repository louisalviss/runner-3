import app from "./artifact-test-cleanup-entry.js";

const ROOT = "core/ebook/";
const LIBRARY_COOKIE = "r3_artifact_library";
const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

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

function redirectHome() {
  return new Response(null, { status: 303, headers: headers({ Location: "/artifact-library" }) });
}

function token(env) {
  return typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
}

async function sessionValue(env) {
  const secret = token(env);
  if (!secret) return "";
  const bytes = new TextEncoder().encode(`runner3-artifact-library-v1:${secret}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function mergeCookie(raw, name, value) {
  const kept = String(raw || "")
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .filter((part) => part.slice(0, part.indexOf("=") >= 0 ? part.indexOf("=") : part.length).trim() !== name);
  kept.push(`${name}=${value}`);
  return kept.join("; ");
}

async function internalRequest(request, env, bodyOverride) {
  const value = await sessionValue(env);
  if (!value) return null;
  const h = new Headers(request.headers);
  h.set("Cookie", mergeCookie(h.get("Cookie"), LIBRARY_COOKIE, value));
  const init = { method: request.method, headers: h, redirect: request.redirect };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = bodyOverride !== undefined ? bodyOverride : request.body;
  }
  return new Request(request.url, init);
}

function isFinalEpub(key) {
  return typeof key === "string" && key.startsWith(ROOT) && key.includes("/final/") && key.toLowerCase().endsWith(".epub");
}

function versionOf(key) {
  const m = String(key).match(/(?:^|[-_.])v(\d+)(?:\.epub)?$/i);
  return m ? Number(m[1]) : 0;
}

function scopeOf(key) {
  const p = String(key).split("/");
  return p[0] === "core" && p[1] === "ebook" ? (p[2] || "") : "";
}

async function canonicalFinalBooks(env) {
  if (!env.ARTIFACTS) throw new Error("ARTIFACTS_BINDING_MISSING");
  const latest = new Map();
  let cursor;
  do {
    const page = await env.ARTIFACTS.list({ prefix: ROOT, cursor, limit: 1000 });
    for (const object of page.objects || []) {
      if (!isFinalEpub(object.key)) continue;
      const scope = scopeOf(object.key) || object.key;
      const current = latest.get(scope);
      const uploaded = object.uploaded instanceof Date ? object.uploaded.toISOString() : (object.uploaded || null);
      const candidate = { key: object.key, size: Number(object.size || 0), uploaded, scope };
      if (!current) {
        latest.set(scope, candidate);
        continue;
      }
      const a = Date.parse(candidate.uploaded || "") || 0;
      const b = Date.parse(current.uploaded || "") || 0;
      if (a > b || (a === b && versionOf(candidate.key) > versionOf(current.key))) latest.set(scope, candidate);
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return [...latest.values()].sort((a, b) => a.scope.localeCompare(b.scope));
}

function libraryPage() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">
<title>Library</title>
<style>
:root{color-scheme:dark;background:#080a0d;color:#f2f5f8;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;background:#080a0d;color:#f2f5f8}.shell{max-width:860px;margin:0 auto;padding:max(12px,env(safe-area-inset-top)) 12px max(28px,env(safe-area-inset-bottom))}.tools{display:grid;grid-template-columns:minmax(0,1fr) 44px 44px;gap:8px;margin:0 0 12px}.search{min-width:0;border:1px solid #29313a;background:#0e1217;color:#f5f7fa;border-radius:12px;padding:12px 13px;font-size:16px;outline:none}.search:focus{border-color:#596979}.icon{appearance:none;border:1px solid #29313a;background:#12171d;color:#e8edf3;border-radius:12px;width:44px;height:44px;display:grid;place-items:center;padding:0;cursor:pointer}.icon svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.icon:disabled{opacity:.45}.status{display:none;color:#8793a0;font-size:12px;padding:6px 2px 10px}.status.show{display:block}.list{display:grid;gap:8px}.book{border:1px solid #202832;background:#0e1217;border-radius:14px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;overflow:hidden}.read{min-width:0;color:#f3f6fa;text-decoration:none;padding:16px 14px;display:flex;align-items:center}.title{font-size:17px;line-height:1.25;font-weight:750;overflow-wrap:anywhere}.download{appearance:none;border:0;border-left:1px solid #202832;background:#121820;color:#dfe6ee;padding:0 15px;font:inherit;font-size:13px;font-weight:750;cursor:pointer}.download:disabled{opacity:.5}.empty{color:#7f8b98;text-align:center;padding:42px 12px;font-size:14px}@media(min-width:720px){.shell{padding-left:18px;padding-right:18px}.title{font-size:18px}.book:hover{border-color:#36424f}.read{padding:18px 16px}}
</style>
</head>
<body><main class="shell"><form id="searchForm" class="tools" role="search"><input id="search" class="search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books"><button class="icon" type="submit" aria-label="Search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.6-3.6"></path></svg></button><button id="refresh" class="icon" type="button" aria-label="Refresh R2"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v5h-5"></path><path d="M19 11a8 8 0 1 0 1 5"></path></svg></button></form><div id="status" class="status"></div><section id="list" class="list"></section></main>
<script>
(() => {
  const titleMap={
    'blindsight':'Blindsight','broken-money':'Broken Money','chiec-hop-pandora':'Chiếc Hộp Pandora','consider-phlebas':'Consider Phlebas',
    'dcc-01':'Dungeon Crawler Carl','dcc-02':'Kịch bản Ngày Tận thế của Carl','dcc-03':'Cẩm nang Kẻ Vô chính phủ Hầm ngục','dcc-04':'Cánh cổng của các Dã thần','dcc-05':'Vũ hội Hóa trang của Đồ tể','dcc-06':'Con mắt của Cô dâu Loạn trí','dcc-07':'Sự Diệt vong Không thể Tránh khỏi','dcc-08':'Cuộc Diễu hành Kinh hoàng'
  };
  let books=[];
  let query='';
  const $=id=>document.getElementById(id);
  const humanize=s=>String(s||'').replace(/[-_]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  const titleFor=b=>titleMap[b.scope]||humanize(b.scope)||humanize((b.key.split('/').pop()||'Book').replace(/\.epub$/i,'').replace(/(?:-VI)?-v\d+$/i,''));
  function status(message){const node=$('status');node.textContent=message||'';node.classList.toggle('show',Boolean(message));}
  function filtered(){const q=query.trim().toLocaleLowerCase('vi');return books.filter(b=>!q||titleFor(b).toLocaleLowerCase('vi').includes(q)||b.key.toLocaleLowerCase('vi').includes(q)).sort((a,b)=>titleFor(a).localeCompare(titleFor(b),'vi'));}
  function render(){const root=$('list');root.textContent='';const items=filtered();if(!items.length){const e=document.createElement('div');e.className='empty';e.textContent=query?'No books found.':'No final EPUBs found.';root.appendChild(e);return;}for(const book of items){const row=document.createElement('article');row.className='book';const read=document.createElement('a');read.className='read';read.href='/artifact-library/read?key='+encodeURIComponent(book.key);const title=document.createElement('span');title.className='title';title.textContent=titleFor(book);read.appendChild(title);const download=document.createElement('button');download.className='download';download.type='button';download.textContent='Download';download.addEventListener('click',async()=>{download.disabled=true;try{const r=await fetch('/artifact-library/api/delivery',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key:book.key,ttl_seconds:900})});const data=await r.json();if(!r.ok||data.ok!==true||!data.delivery||!data.delivery.url)throw new Error(data.error||('HTTP '+r.status));location.href=data.delivery.url;}catch(e){status('Download failed: '+String(e&&e.message||e));}finally{download.disabled=false;}});row.append(read,download);root.appendChild(row);}}
  async function load(){const refresh=$('refresh');refresh.disabled=true;status('Loading…');try{const r=await fetch('/artifact-library/api/list',{cache:'no-store'});const data=await r.json();if(!r.ok||data.ok!==true)throw new Error(data.error||('HTTP '+r.status));books=Array.isArray(data.objects)?data.objects:[];status('');render();}catch(e){status('Could not load Library: '+String(e&&e.message||e));}finally{refresh.disabled=false;}}
  $('searchForm').addEventListener('submit',e=>{e.preventDefault();query=$('search').value;render();});
  $('refresh').addEventListener('click',load);
  load();
})();
</script></body></html>`;
}

function injectIframeSwipe(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-iframe-swipe="1"')) return html;
  const patch = `<script data-r3-iframe-swipe="1">(()=>{let timer=0;function bind(doc){if(!doc||doc.documentElement.dataset.r3SwipeBound)return;doc.documentElement.dataset.r3SwipeBound='1';let sx=0,sy=0;doc.addEventListener('touchstart',e=>{const t=e.changedTouches&&e.changedTouches[0];if(t){sx=t.clientX;sy=t.clientY;}},{passive:true});doc.addEventListener('touchend',e=>{const t=e.changedTouches&&e.changedTouches[0];if(!t)return;const dx=t.clientX-sx,dy=t.clientY-sy;if(Math.abs(dx)>45&&Math.abs(dx)>Math.abs(dy)*1.2){const id=dx>0?'prev':'next';document.getElementById(id)?.click();}},{passive:true});}function scan(){document.querySelectorAll('#viewer iframe').forEach(frame=>{try{bind(frame.contentDocument);}catch{}if(!frame.dataset.r3SwipeLoad){frame.dataset.r3SwipeLoad='1';frame.addEventListener('load',()=>{try{bind(frame.contentDocument);}catch{}});}});}const viewer=document.getElementById('viewer');if(viewer)new MutationObserver(scan).observe(viewer,{childList:true,subtree:true});scan();timer=setInterval(scan,750);window.addEventListener('beforeunload',()=>clearInterval(timer),{once:true});})();</script>`;
  return html.replace("</body>", patch + "</body>");
}

async function publicList(request, env) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  try {
    const objects = await canonicalFinalBooks(env);
    return json({ ok: true, prefix: ROOT, final_only: true, canonical_latest_per_scope: true, objects });
  } catch (error) {
    return json({ ok: false, error: "LIBRARY_LIST_FAILED", detail: String(error?.message || error) }, 503);
  }
}

async function publicDelivery(request, env, ctx) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  let payload;
  try { payload = await request.json(); } catch { return json({ ok: false, error: "INVALID_JSON" }, 400); }
  const key = String(payload?.key || "");
  if (!isFinalEpub(key)) return json({ ok: false, error: "FINAL_EPUB_ONLY" }, 403);
  const body = JSON.stringify({ key, ttl_seconds: Math.min(3600, Math.max(60, Number(payload?.ttl_seconds || 900))) });
  const inner = await internalRequest(new Request(request.url, { method: "POST", headers: request.headers }), env, body);
  if (!inner) return json({ ok: false, error: "LIBRARY_BACKEND_UNAVAILABLE" }, 503);
  const h = new Headers(inner.headers);
  h.set("Content-Type", "application/json");
  h.set("X-Runner3-Library", "1");
  const forwarded = new Request(inner.url, { method: "POST", headers: h, body });
  return app.fetch(forwarded, env, ctx);
}

async function publicReader(request, env, ctx) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  const url = new URL(request.url);
  const key = String(url.searchParams.get("key") || "");
  if (!isFinalEpub(key)) return redirectHome();
  const inner = await internalRequest(request, env);
  if (!inner) return json({ ok: false, error: "LIBRARY_BACKEND_UNAVAILABLE" }, 503);
  const response = await app.fetch(inner, env, ctx);
  const type = response.headers.get("Content-Type") || "";
  if (!type.toLowerCase().includes("text/html")) return response;
  const original = await response.text();
  const updated = injectIframeSwipe(original);
  const h = new Headers(response.headers);
  h.delete("Content-Length");
  return new Response(updated, { status: response.status, headers: h });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const p = url.pathname;
    if (p === "/artifact-library") {
      if (request.method !== "GET") return redirectHome();
      return new Response(libraryPage(), { status: 200, headers: headers({ "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" }) });
    }
    if (p === "/artifact-library/api/list") return publicList(request, env);
    if (p === "/artifact-library/api/delivery") return publicDelivery(request, env, ctx);
    if (p === "/artifact-library/read") return publicReader(request, env, ctx);
    if (["/artifact-library/login","/artifact-library/logout","/artifact-library/setup-pin","/artifact-library/change-pin","/artifact-library/reset-pin","/artifact-library/magic","/artifact-library/api/magic-link"].includes(p)) return redirectHome();
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
