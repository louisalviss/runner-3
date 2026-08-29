import app from "./opaque-mailbox-entry-v2.js";

const LIBRARY_COOKIE = "r3_artifact_library";
const LIBRARY_SESSION_SECONDS = 12 * 60 * 60;

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, no-store",
      ...extraHeaders,
    },
  });
}

function html(body, status = 200, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "private, no-store",
      "x-frame-options": "DENY",
      "content-security-policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
      ...extraHeaders,
    },
  });
}

function expectedArtifactToken(env) {
  return typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
}

function requireArtifactAuth(request, env) {
  const expected = expectedArtifactToken(env);
  if (!expected) return json({ ok: false, error: "ARTIFACT_AUTH_NOT_CONFIGURED" }, 503);

  const auth = request.headers.get("Authorization") || "";
  const prefix = "Bearer ";
  const supplied = auth.startsWith(prefix) ? auth.slice(prefix.length).trim() : "";
  if (!supplied || supplied !== expected) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function parseLimit(raw) {
  const value = Number.parseInt(raw || "100", 10);
  if (!Number.isFinite(value)) return 100;
  return Math.min(Math.max(value, 1), 1000);
}

async function listArtifacts(url, env) {
  if (!env.ARTIFACTS) {
    return { response: json({ ok: false, error: "R2_NOT_BOUND" }, 503), result: null };
  }

  const prefix = url.searchParams.get("prefix") || "";
  const cursor = url.searchParams.get("cursor") || undefined;
  const delimiter = url.searchParams.get("delimiter") || undefined;
  const limit = parseLimit(url.searchParams.get("limit"));

  const options = { prefix, limit };
  if (cursor) options.cursor = cursor;
  if (delimiter) options.delimiter = delimiter;

  const result = await env.ARTIFACTS.list(options);
  const payload = {
    ok: true,
    prefix,
    limit,
    truncated: Boolean(result.truncated),
    cursor: result.truncated ? (result.cursor || null) : null,
    delimited_prefixes: Array.isArray(result.delimitedPrefixes) ? result.delimitedPrefixes : [],
    objects: (result.objects || []).map((object) => ({
      key: object.key,
      size: Number.isFinite(object.size) ? object.size : null,
      etag: object.httpEtag || object.etag || null,
      uploaded: object.uploaded instanceof Date ? object.uploaded.toISOString() : (object.uploaded || null),
    })),
  };
  return { response: null, result: payload };
}

async function handleArtifactList(request, env) {
  if (request.method !== "GET") {
    return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  }
  const authError = requireArtifactAuth(request, env);
  if (authError) return authError;
  const listed = await listArtifacts(new URL(request.url), env);
  return listed.response || json(listed.result);
}

function getCookie(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const index = part.indexOf("=");
    if (index < 0) continue;
    const key = part.slice(0, index).trim();
    if (key === name) return part.slice(index + 1).trim();
  }
  return "";
}

async function librarySessionValue(env) {
  const token = expectedArtifactToken(env);
  if (!token) return "";
  const bytes = new TextEncoder().encode(`runner3-artifact-library-v1:${token}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hasLibrarySession(request, env) {
  const expected = await librarySessionValue(env);
  if (!expected) return false;
  return getCookie(request, LIBRARY_COOKIE) === expected;
}

function libraryCookie(value, maxAge) {
  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Strict`;
}

function loginPage(error = "") {
  const errorBlock = error ? `<div class="error">${error}</div>` : "";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Runner3 R2 Library</title>
<style>
:root{color-scheme:dark;background:#0a0b0d;color:#f5f7fa;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 20% 0%,#18202c 0,transparent 35%),#0a0b0d;padding:24px}.card{width:min(440px,100%);background:#111419;border:1px solid #252b33;border-radius:20px;padding:28px;box-shadow:0 24px 80px rgba(0,0,0,.38)}.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8f9bac;font-weight:700}h1{font-size:28px;margin:8px 0 8px}.sub{color:#9da7b5;line-height:1.5;margin:0 0 24px}.field{display:grid;gap:8px}label{font-size:13px;color:#cbd2dc}.input{width:100%;border:1px solid #303844;background:#0b0e12;color:#fff;border-radius:12px;padding:13px 14px;font-size:16px;outline:none}.input:focus{border-color:#6d7f98}.button{width:100%;margin-top:14px;border:0;border-radius:12px;padding:13px 16px;background:#f2f5f8;color:#0a0b0d;font-weight:800;font-size:15px;cursor:pointer}.error{background:#35191c;color:#ffb4bd;border:1px solid #673039;border-radius:10px;padding:10px 12px;margin-bottom:14px;font-size:13px}.note{font-size:12px;color:#6f7987;margin-top:14px;line-height:1.5}
</style>
</head>
<body><main class="card"><div class="eyebrow">Runner3 Core</div><h1>R2 Artifact Library</h1><p class="sub">Private browser for objects stored in the Runner3 R2 artifacts bucket.</p>${errorBlock}<form method="post" action="/artifact-library/login"><div class="field"><label for="token">Core access token</label><input class="input" id="token" name="token" type="password" autocomplete="current-password" required autofocus></div><button class="button" type="submit">Open Library</button></form><div class="note">The token is submitted only to Runner3 Core. The browser receives an HttpOnly session cookie; the token is not exposed to library JavaScript.</div></main></body></html>`;
}

function libraryPage() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Runner3 R2 Library</title>
<style>
:root{color-scheme:dark;background:#090b0e;color:#f3f6fa;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;background:#090b0e;color:#f3f6fa}.shell{max-width:1280px;margin:0 auto;padding:20px}.top{display:flex;gap:16px;align-items:flex-start;justify-content:space-between;margin:8px 0 20px}.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#7e8998;font-weight:800}.title{font-size:28px;margin:5px 0 4px}.muted{color:#8994a3;font-size:13px}.logout{border:1px solid #29313b;background:#11151a;color:#c9d1dc;border-radius:10px;padding:9px 12px;cursor:pointer}.panel{border:1px solid #222934;background:#0f1318;border-radius:16px;padding:14px;margin-bottom:14px}.toolbar{display:grid;grid-template-columns:minmax(260px,1fr) minmax(180px,.55fr) auto;gap:10px}.input{border:1px solid #2a323d;background:#090c10;color:#fff;border-radius:10px;padding:11px 12px;font-size:14px;outline:none}.input:focus{border-color:#65758a}.button{border:1px solid #303946;background:#171c23;color:#eef2f7;border-radius:10px;padding:10px 13px;font-weight:700;cursor:pointer}.button.primary{background:#edf2f7;color:#090b0e;border-color:#edf2f7}.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.chip{border:1px solid #29323d;background:#10151b;color:#aeb8c5;border-radius:999px;padding:7px 11px;font-size:12px;cursor:pointer}.chip.active{background:#e8edf2;color:#0b0d10;border-color:#e8edf2}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.stat{border:1px solid #222934;background:#0f1318;border-radius:14px;padding:13px}.stat b{display:block;font-size:20px;margin-top:4px}.stat span{font-size:11px;color:#7f8a98;text-transform:uppercase;letter-spacing:.08em}.status{font-size:12px;color:#8290a0;margin:8px 2px 14px;min-height:18px}.list{display:grid;gap:9px}.row{border:1px solid #202731;background:#0e1217;border-radius:14px;padding:13px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center}.name{font-size:14px;font-weight:750;overflow-wrap:anywhere}.path{font-size:11px;color:#738091;margin-top:5px;overflow-wrap:anywhere}.meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}.badge{font-size:10px;padding:4px 7px;border:1px solid #2b3440;border-radius:999px;color:#9fabba}.badge.final{color:#c7f7d4;border-color:#31533a;background:#102217}.right{display:flex;align-items:center;gap:12px}.info{text-align:right;min-width:115px}.size{font-size:12px;font-weight:700}.time{font-size:10px;color:#738091;margin-top:4px}.download{border:1px solid #303a46;background:#171d24;color:#eef2f7;border-radius:9px;padding:8px 10px;font-size:12px;font-weight:700;cursor:pointer}.empty{padding:36px;text-align:center;border:1px dashed #28313d;border-radius:14px;color:#7e8998}.footer{font-size:11px;color:#596574;margin:18px 2px 30px}@media(max-width:760px){.shell{padding:14px}.toolbar{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:1fr}.right{justify-content:space-between}.info{text-align:left}.title{font-size:24px}}
</style>
</head>
<body><main class="shell"><div class="top"><div><div class="eyebrow">Runner3 Core</div><h1 class="title">R2 Artifact Library</h1><div class="muted">Private live inventory of the artifacts bucket</div></div><form method="post" action="/artifact-library/logout"><button class="logout" type="submit">Log out</button></form></div>
<section class="panel"><div class="toolbar"><input id="prefix" class="input" value="core/ebook/" aria-label="R2 prefix"><input id="search" class="input" placeholder="Search filename or path" aria-label="Search"><button id="refresh" class="button primary">Refresh R2</button></div><div class="chips"><button class="chip" data-mode="all">All objects</button><button class="chip" data-mode="final">Final only</button><button class="chip active" data-mode="latest">Latest final / scope</button></div></section>
<section class="stats"><div class="stat"><span>Objects</span><b id="statObjects">—</b></div><div class="stat"><span>Final</span><b id="statFinal">—</b></div><div class="stat"><span>Scopes</span><b id="statScopes">—</b></div><div class="stat"><span>Size</span><b id="statSize">—</b></div></section>
<div id="status" class="status">Loading live R2 inventory…</div><section id="list" class="list"></section><div class="footer">Downloads use short-lived signed delivery links. R2 itself remains private.</div></main>
<script>
const state={objects:[],mode:'latest'};
const el=id=>document.getElementById(id);
const basename=key=>key.split('/').filter(Boolean).pop()||key;
const formatBytes=n=>{if(!Number.isFinite(n))return '—';const u=['B','KB','MB','GB','TB'];let i=0,v=n;while(v>=1024&&i<u.length-1){v/=1024;i++}return (i? v.toFixed(v>=10?1:2):String(v))+' '+u[i]};
const formatTime=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):d.toLocaleString()};
const parts=key=>{const p=key.split('/');return {project:p[1]||'—',scope:p[2]||'—',stage:p[3]||'—'}};
function filtered(){const q=el('search').value.trim().toLowerCase();let items=state.objects.filter(x=>!q||x.key.toLowerCase().includes(q));if(state.mode==='final'||state.mode==='latest')items=items.filter(x=>x.key.includes('/final/'));if(state.mode==='latest'){const newest=new Map();for(const item of items){const p=parts(item.key);const id=p.project+'/'+p.scope;const prev=newest.get(id);if(!prev||new Date(item.uploaded||0)>new Date(prev.uploaded||0))newest.set(id,item)}items=[...newest.values()]}return items.sort((a,b)=>String(a.key).localeCompare(String(b.key)))}
function render(){const items=filtered();const allFinal=state.objects.filter(x=>x.key.includes('/final/'));const scopes=new Set(state.objects.map(x=>{const p=parts(x.key);return p.project+'/'+p.scope}));el('statObjects').textContent=state.objects.length;el('statFinal').textContent=allFinal.length;el('statScopes').textContent=scopes.size;el('statSize').textContent=formatBytes(state.objects.reduce((s,x)=>s+(Number(x.size)||0),0));const root=el('list');root.textContent='';if(!items.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='No objects match this view.';root.appendChild(empty);return}for(const item of items){const p=parts(item.key);const row=document.createElement('article');row.className='row';const left=document.createElement('div');const name=document.createElement('div');name.className='name';name.textContent=basename(item.key);const path=document.createElement('div');path.className='path';path.textContent=item.key;const meta=document.createElement('div');meta.className='meta';for(const value of [p.project,p.scope,p.stage]){const badge=document.createElement('span');badge.className='badge'+(value==='final'?' final':'');badge.textContent=value;meta.appendChild(badge)}left.append(name,path,meta);const right=document.createElement('div');right.className='right';const info=document.createElement('div');info.className='info';const size=document.createElement('div');size.className='size';size.textContent=formatBytes(item.size);const time=document.createElement('div');time.className='time';time.textContent=formatTime(item.uploaded);info.append(size,time);const btn=document.createElement('button');btn.className='download';btn.textContent='Download';btn.addEventListener('click',()=>download(item.key,btn));right.append(info,btn);row.append(left,right);root.appendChild(row)}}
async function load(){const prefix=el('prefix').value.trim();el('status').textContent='Reading R2…';el('refresh').disabled=true;try{let cursor='',pages=0,objects=[];do{const params=new URLSearchParams({prefix,limit:'1000'});if(cursor)params.set('cursor',cursor);const r=await fetch('/artifact-library/api/list?'+params,{credentials:'same-origin'});if(r.status===401){location.reload();return}const body=await r.json();if(!r.ok||body.ok!==true)throw new Error(body.error||('HTTP '+r.status));objects.push(...(body.objects||[]));cursor=body.truncated?body.cursor:'';pages++;if(pages>=25&&cursor)throw new Error('Inventory exceeds 25,000 objects; narrow the prefix.')}while(cursor);state.objects=objects;el('status').textContent='Live R2 · '+objects.length+' objects · '+pages+' page'+(pages===1?'':'s');render()}catch(err){el('status').textContent='Error: '+err.message;state.objects=[];render()}finally{el('refresh').disabled=false}}
async function download(key,btn){const old=btn.textContent;btn.disabled=true;btn.textContent='Signing…';try{const r=await fetch('/artifact-library/api/delivery',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key,ttl_seconds:900})});const body=await r.json();if(!r.ok||body.ok!==true||!body.delivery||!body.delivery.url)throw new Error(body.error||('HTTP '+r.status));window.open(body.delivery.url,'_blank','noopener')}catch(err){alert('Download failed: '+err.message)}finally{btn.disabled=false;btn.textContent=old}}
el('refresh').addEventListener('click',load);el('search').addEventListener('input',render);el('prefix').addEventListener('keydown',e=>{if(e.key==='Enter')load()});document.querySelectorAll('.chip').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));btn.classList.add('active');state.mode=btn.dataset.mode;render()}));load();
</script></body></html>`;
}

async function handleLibraryLogin(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  const expected = expectedArtifactToken(env);
  if (!expected) return html(loginPage("Library authentication is not configured."), 503);
  const form = await request.formData();
  const supplied = String(form.get("token") || "").trim();
  if (!supplied || supplied !== expected) return html(loginPage("Access denied."), 401);
  const session = await librarySessionValue(env);
  return new Response(null, {
    status: 303,
    headers: {
      location: "/artifact-library",
      "set-cookie": libraryCookie(session, LIBRARY_SESSION_SECONDS),
      "cache-control": "private, no-store",
    },
  });
}

async function handleLibraryLogout(request) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  return new Response(null, {
    status: 303,
    headers: {
      location: "/artifact-library",
      "set-cookie": libraryCookie("", 0),
      "cache-control": "private, no-store",
    },
  });
}

async function handleLibraryHome(request, env) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!expectedArtifactToken(env)) return html(loginPage("Library authentication is not configured."), 503);
  if (!(await hasLibrarySession(request, env))) return html(loginPage());
  return html(libraryPage());
}

async function handleLibraryList(request, env) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!(await hasLibrarySession(request, env))) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  const listed = await listArtifacts(new URL(request.url), env);
  return listed.response || json(listed.result);
}

async function handleLibraryDelivery(request, env, ctx) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!(await hasLibrarySession(request, env))) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  if (request.headers.get("x-runner3-library") !== "1") return json({ ok: false, error: "BAD_LIBRARY_REQUEST" }, 400);

  let payload;
  try {
    payload = await request.json();
  } catch {
    return json({ ok: false, error: "INVALID_JSON" }, 400);
  }
  const key = String(payload?.key || "");
  const parts = key.split("/");
  if (parts.length < 4 || parts[0] !== "core" || !parts[1] || !parts[2]) {
    return json({ ok: false, error: "INVALID_ARTIFACT_KEY" }, 400);
  }
  const ttl = Math.min(Math.max(Number.parseInt(payload?.ttl_seconds || "900", 10) || 900, 60), 3600);
  const project = parts[1];
  const scope = parts[2];
  const name = parts.slice(3).join("/");
  const coreToken = expectedArtifactToken(env);
  if (!coreToken) return json({ ok: false, error: "ARTIFACT_AUTH_NOT_CONFIGURED" }, 503);

  const target = new URL("/delivery-links", request.url);
  const internalRequest = new Request(target.toString(), {
    method: "POST",
    headers: {
      "authorization": `Bearer ${coreToken}`,
      "content-type": "application/json",
      "accept": "application/json",
    },
    body: JSON.stringify({ project, scope, name, ttl_seconds: ttl }),
  });
  return app.fetch(internalRequest, env, ctx);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/artifact-list") return handleArtifactList(request, env);
    if (url.pathname === "/artifact-library") return handleLibraryHome(request, env);
    if (url.pathname === "/artifact-library/login") return handleLibraryLogin(request, env);
    if (url.pathname === "/artifact-library/logout") return handleLibraryLogout(request);
    if (url.pathname === "/artifact-library/api/list") return handleLibraryList(request, env);
    if (url.pathname === "/artifact-library/api/delivery") return handleLibraryDelivery(request, env, ctx);
    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") {
      return app.scheduled(controller, env, ctx);
    }
  },
};
