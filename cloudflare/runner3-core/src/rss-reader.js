const READER_TOKEN_SHA256 = "a4efd86ada61ed4398ec259b7f46262f10d4e2f7fa4f123c5619eb6366d0dd18";

function json(value, status = 200) {
  return Response.json(value, {
    status,
    headers: { "cache-control": "private, no-store" },
  });
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(text ?? "")));
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function readerAuthorized(request) {
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied) return false;
  return (await sha256Hex(supplied)) === READER_TOKEN_SHA256;
}

function requireBindings(env) {
  if (!env.DB) return json({ ok: false, error: "D1_NOT_BOUND" }, 503);
  if (!env.ARTIFACTS) return json({ ok: false, error: "R2_NOT_BOUND" }, 503);
  return null;
}

function parseJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}

function cleanRow(row) {
  if (!row) return null;
  return {
    article_id: row.article_id,
    canonical_url: row.canonical_url,
    source_key: row.source_key,
    source_name: row.source_name,
    source_language: row.source_language,
    title: row.title,
    published_at: row.published_at,
    fetch_status: row.fetch_status,
    translation_status: row.translation_status,
    qa_state: row.qa_state,
    last_error: row.last_error,
    updated_at: row.updated_at,
  };
}

async function getArticle(env, articleId) {
  return env.DB.prepare("SELECT * FROM rss_articles WHERE article_id = ?").bind(articleId).first();
}

async function readArtifact(env, key) {
  if (!key) return null;
  const object = await env.ARTIFACTS.get(key);
  if (!object) return null;
  return parseJson(await object.text());
}

async function listArticles(env) {
  const result = await env.DB.prepare(`
    SELECT article_id, canonical_url, source_key, source_name, source_language,
           title, published_at, fetch_status, translation_status, qa_state,
           last_error, updated_at
    FROM rss_articles
    ORDER BY published_at DESC, article_id
    LIMIT 100
  `).all();
  const articles = (result.results || []).map(cleanRow);
  return json({ ok: true, count: articles.length, articles });
}

async function articleDetail(env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  return json({ ok: true, article: cleanRow(article) });
}

async function articleView(env, articleId, kind) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);

  let key = article.original_object_key;
  let nativeVi = false;
  if (kind === "vi") {
    if (article.source_language === "vi") {
      nativeVi = true;
      key = article.original_object_key;
    } else {
      key = article.vi_object_key;
      if (!key) return json({ ok: false, error: "TRANSLATION_NOT_READY", article: cleanRow(article) }, 409);
    }
  }

  if (!key) return json({ ok: false, error: "ORIGINAL_NOT_FETCHED", article: cleanRow(article) }, 409);
  const artifact = await readArtifact(env, key);
  if (!artifact) return json({ ok: false, error: "ARTIFACT_MISSING", article: cleanRow(article) }, 500);
  return json({ ok: true, article: cleanRow(article), view: kind, nativeVi, artifact });
}

function libraryHtml() {
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RSS Library</title><style>
body{font:16px system-ui,-apple-system,sans-serif;max-width:920px;margin:28px auto;padding:0 18px;line-height:1.5;color:#111}h1{font-size:40px;margin:0 0 24px}.auth{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px}input,button{font:inherit;padding:10px 12px;border:1px solid #ccc;border-radius:10px}input{min-width:260px}button{cursor:pointer}.item{padding:16px 0;border-bottom:1px solid #ddd}.item a{font-size:18px;font-weight:650;text-decoration:none}.meta{font-size:13px;opacity:.65;margin-top:4px}.bad{color:#a00}.ok{color:#075}@media(max-width:600px){body{margin:20px auto}h1{font-size:34px}.auth input{width:100%;min-width:0}}
</style></head><body><h1>RSS Library</h1><div class="auth" id="auth"><input id="token" type="password" autocomplete="off" placeholder="RSS Reader token"><button id="save">Lưu trên thiết bị</button><button id="reload">Tải lại</button></div><p id="status"></p><main id="list"></main><script>
const KEY='rssReaderToken',token=document.querySelector('#token'),status=document.querySelector('#status'),list=document.querySelector('#list'),auth=document.querySelector('#auth');
function decodeText(value){const el=document.createElement('textarea');el.innerHTML=String(value??'');return el.value}
const hash=location.hash.startsWith('#token=')?decodeURIComponent(location.hash.slice(7)):'';if(hash){localStorage.setItem(KEY,hash);history.replaceState(null,'',location.pathname+location.search)}token.value=localStorage.getItem(KEY)||'';
document.querySelector('#save').onclick=()=>{localStorage.setItem(KEY,token.value.trim());load()};document.querySelector('#reload').onclick=load;
async function api(path){const t=localStorage.getItem(KEY)||token.value.trim();const r=await fetch(path,{headers:{Authorization:'Bearer '+t}});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||String(r.status));return j}
async function load(){list.textContent='';status.className='';status.textContent='Đang tải…';try{const j=await api('/reader/rss/library');auth.style.display='none';status.textContent=j.count+' bài';for(const a of j.articles){const d=document.createElement('div');d.className='item';const h=document.createElement('a');h.href='/rss/article/'+encodeURIComponent(a.article_id);h.textContent=decodeText(a.title);const m=document.createElement('div');m.className='meta';m.textContent=[decodeText(a.source_name),a.published_at,'fetch:'+a.fetch_status,'vi:'+a.translation_status].filter(Boolean).join(' · ');d.append(h,m);list.append(d)}}catch(e){auth.style.display='flex';status.className='bad';status.textContent=e.message==='UNAUTHORIZED'?'Reader token không hợp lệ':e.message}}load();
</script></body></html>`;
}

function articleHtml(articleId) {
  const encoded = JSON.stringify(articleId);
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RSS Article</title><style>
body{font:17px system-ui,-apple-system,sans-serif;max-width:820px;margin:24px auto;padding:0 18px;line-height:1.68;color:#111}h1{font-size:32px;line-height:1.15}.top{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}button{font:inherit;padding:9px 12px;border:1px solid #ccc;border-radius:10px;background:#f5f5f5;cursor:pointer}pre{white-space:pre-wrap;font:inherit}.meta{font-size:13px;opacity:.65}.bad{color:#a00}a{color:inherit}@media(max-width:600px){body{margin:18px auto}h1{font-size:28px}}
</style></head><body><p><a href="/rss/library">← Library</a></p><h1 id="title">RSS Article</h1><div class="top"><button id="vi">Tiếng Việt</button><button id="original">Original</button></div><p class="meta" id="meta"></p><p class="bad" id="error"></p><pre id="body"></pre><script>
const KEY='rssReaderToken',id=${encoded},body=document.querySelector('#body'),err=document.querySelector('#error'),meta=document.querySelector('#meta'),title=document.querySelector('#title');
function decodeText(value){const el=document.createElement('textarea');el.innerHTML=String(value??'');return el.value}
async function api(path){const t=localStorage.getItem(KEY)||'';if(!t)throw new Error('MISSING_READER_TOKEN');const r=await fetch(path,{headers:{Authorization:'Bearer '+t}});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||String(r.status));return j}
async function view(kind){err.textContent='';body.textContent='Đang tải…';try{const j=await api('/reader/rss/articles/'+encodeURIComponent(id)+'/'+kind);body.textContent=decodeText(j.artifact.body||'')}catch(e){body.textContent='';err.textContent=e.message==='UNAUTHORIZED'?'Reader token không hợp lệ':e.message}}
async function init(){try{const j=await api('/reader/rss/articles/'+encodeURIComponent(id));const a=j.article;title.textContent=decodeText(a.title);meta.textContent=[decodeText(a.source_name),a.published_at,'fetch:'+a.fetch_status,'vi:'+a.translation_status].filter(Boolean).join(' · ');const preferred=(a.source_language==='vi'||a.translation_status==='published'||a.translation_status==='native_vi')?'vi':'original';await view(preferred)}catch(e){err.textContent=e.message==='MISSING_READER_TOKEN'?'Mở lại RSS Library để đăng nhập':e.message}}
document.querySelector('#original').onclick=()=>view('original');document.querySelector('#vi').onclick=()=>view('vi');init();
</script></body></html>`;
}

export async function handleRssReader(request, env, url) {
  if (request.method === "GET" && url.pathname === "/rss/library") {
    return new Response(libraryHtml(), { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
  }

  const uiMatch = url.pathname.match(/^\/rss\/article\/([^/]+)$/);
  if (request.method === "GET" && uiMatch) {
    let articleId;
    try { articleId = decodeURIComponent(uiMatch[1]); } catch { return new Response("Bad Request", { status: 400 }); }
    return new Response(articleHtml(articleId), { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
  }

  if (!url.pathname.startsWith("/reader/rss/")) return null;
  const bindingError = requireBindings(env);
  if (bindingError) return bindingError;
  if (!(await readerAuthorized(request))) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  if (request.method !== "GET") return json({ ok: false, error: "READ_ONLY" }, 405);

  if (url.pathname === "/reader/rss/library") return listArticles(env);

  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)(?:\/(original|vi))?$/);
  if (!match) return json({ ok: false, error: "READER_ROUTE_NOT_FOUND" }, 404);
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return json({ ok: false, error: "INVALID_ARTICLE_ID" }, 400); }
  const action = match[2] || "detail";
  if (action === "detail") return articleDetail(env, articleId);
  return articleView(env, articleId, action);
}