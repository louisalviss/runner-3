const READER_TOKEN_SHA256 = "a4efd86ada61ed4398ec259b7f46262f10d4e2f7fa4f123c5619eb6366d0dd18";
const READER_CATEGORIES = ["AI", "Tech", "Kinh tế", "Chính trị", "Khoa học", "Trading", "WordPress", "Khác"];

function json(value, status = 200) {
  return Response.json(value, { status, headers: { "cache-control": "private, no-store" } });
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
    lifecycle: row.lifecycle || "active",
    featured: Number(row.featured || 0) === 1,
    category: row.category || null,
    preference: row.preference || null,
    last_opened_at: row.last_opened_at || null,
  };
}

function trimReaderBody(value, sourceKey = "") {
  const text = String(value ?? "").replace(/\r/g, "").trim();
  if (!text) return text;

  const lines = text.split("\n");
  const floor = Math.max(8, Math.floor(lines.length * 0.50));
  const genericFooter = /^(?:copy link|lấy link|link bài gốc|tags?\s*:|từ khóa\s*:|chủ đề\s*:|bài viết liên quan|bài liên quan|tin liên quan|xem thêm|đọc thêm|có thể bạn quan tâm|bình luận|comments?|share|chia sẻ|newsletter|subscribe|recommended|related (?:articles|posts)|more from|you may also like)\b/i;
  const referenceHeading = /^(?:tài liệu tham khảo|tham khảo|nguồn tham khảo|nguồn|chú thích|ghi chú|references?|reference list|bibliography|footnotes?|endnotes?|notes?)\s*:?[\s-]*$/i;
  const editorialPostscript = /^(?:bài viết (?:được )?trích từ (?:bản thảo|bản dịch|ấn phẩm)|rất mong nhận được ý kiến(?: phản biện| góp ý)?|mọi (?:liên hệ|góp ý|ý kiến)(?:,\s*góp ý)? xin gửi về|trân trọng cảm ơn!?)/i;

  let cut = lines.length;
  for (let i = floor; i < lines.length; i++) {
    const line = lines[i].trim();
    if (genericFooter.test(line) || referenceHeading.test(line) || editorialPostscript.test(line)) {
      cut = i;
      break;
    }
  }

  const isNcqt = String(sourceKey).toLowerCase() === "nghiencuuquocte";
  if (isNcqt) {
    const ncqtFloor = Math.max(8, Math.floor(lines.length * 0.42));
    const ncqtPostscript = /(?:bài viết (?:được )?trích từ bản thảo|vượt ra ngoài gia công|rất mong nhận được ý kiến phản biện|mọi liên hệ,?\s*góp ý xin gửi về|trân trọng cảm ơn)/i;
    for (let i = ncqtFloor; i < cut; i++) {
      if (ncqtPostscript.test(lines[i].trim())) {
        cut = i;
        break;
      }
    }
  }

  if (cut === lines.length) {
    const tailFloor = Math.max(floor, Math.floor(lines.length * (isNcqt ? 0.60 : 0.72)));
    const refLike = (line) => {
      const s = line.trim();
      return /^https?:\/\/\S+/i.test(s) ||
        /^\[\d{1,3}\]\s+/.test(s) ||
        /^\d{1,3}[.)]\s+/.test(s) ||
        /(?:doi\.org\/|www\.|https?:\/\/)/i.test(s) ||
        /\([12][0-9]{3}[a-z]?\)\.?$/.test(s);
    };
    for (let i = tailFloor; i < lines.length; i++) {
      const window = lines.slice(i, Math.min(lines.length, i + 7)).filter((x) => x.trim());
      if (window.length >= 3 && window.filter(refLike).length >= 3) {
        cut = i;
        break;
      }
    }
  }

  const out = lines.slice(0, cut);
  const trailingJunk = /^(?:copy link|lấy link|link bài gốc|tags?\s*:.*|từ khóa\s*:.*|chủ đề\s*:.*|share|chia sẻ|all rights reserved|©\s*\d{4}.*|https?:\/\/\S+|[-—_=]{5,})$/i;
  while (out.length && (!out[out.length - 1].trim() || trailingJunk.test(out[out.length - 1].trim()))) out.pop();
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

async function getArticle(env, articleId) {
  return env.DB.prepare(`
    SELECT a.*,
           COALESCE(s.lifecycle, 'active') AS lifecycle,
           COALESCE(s.featured, 0) AS featured,
           s.category, s.preference, s.last_opened_at
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE a.article_id = ?
  `).bind(articleId).first();
}

async function readArtifact(env, key) {
  if (!key) return null;
  const object = await env.ARTIFACTS.get(key);
  if (!object) return null;
  return parseJson(await object.text());
}

async function markOpened(env, articleId) {
  await env.DB.prepare(`
    INSERT INTO rss_reader_state (article_id, lifecycle, featured, last_opened_at, updated_at)
    VALUES (?, 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT(article_id) DO UPDATE SET
      last_opened_at = CURRENT_TIMESTAMP,
      updated_at = CURRENT_TIMESTAMP
  `).bind(articleId).run();
}

async function listArticles(env, url) {
  const result = await env.DB.prepare(`
    SELECT a.article_id, a.canonical_url, a.source_key, a.source_name, a.source_language,
           a.title, a.published_at, a.fetch_status, a.translation_status, a.qa_state,
           a.last_error, a.updated_at,
           COALESCE(s.lifecycle, 'active') AS lifecycle,
           COALESCE(s.featured, 0) AS featured,
           s.category, s.preference, s.last_opened_at
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    ORDER BY a.published_at DESC, a.article_id
    LIMIT 300
  `).all();

  const view = new Set(["active", "featured", "archived", "deleted", "all"]).has(url.searchParams.get("view"))
    ? url.searchParams.get("view")
    : "active";
  const q = String(url.searchParams.get("q") || "").trim().toLowerCase();
  const category = String(url.searchParams.get("category") || "").trim();

  let articles = (result.results || []).map(cleanRow);
  articles = articles.filter((a) => {
    if (view === "active" && a.lifecycle !== "active") return false;
    if (view === "archived" && a.lifecycle !== "archived") return false;
    if (view === "deleted" && a.lifecycle !== "deleted") return false;
    if (view === "featured" && (!a.featured || a.lifecycle === "deleted")) return false;
    if (category && a.category !== category) return false;
    if (q) {
      const haystack = [a.title, a.source_name, a.article_id, a.category].filter(Boolean).join(" ").toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  const categories = [...new Set((result.results || []).map((x) => String(x.category || "").trim()).filter(Boolean))].sort();
  return json({ ok: true, count: articles.length, view, categories, suggestedCategories: READER_CATEGORIES, articles });
}

async function articleDetail(env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  return json({ ok: true, article: cleanRow(article), suggestedCategories: READER_CATEGORIES });
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

  artifact.body = trimReaderBody(artifact.body, article.source_key);
  if (kind === "vi" && article.source_language !== "vi" && article.original_object_key) {
    const original = await readArtifact(env, article.original_object_key);
    if (original?.images?.length) artifact.images = original.images;
  }
  await markOpened(env, articleId);
  const fresh = await getArticle(env, articleId);
  return json({ ok: true, article: cleanRow(fresh), view: kind, nativeVi, artifact });
}

function validLifecycle(value) {
  return new Set(["active", "archived", "deleted"]).has(value);
}

function validPreference(value) {
  return value === null || value === "like" || value === "dislike";
}

async function updateReaderState(request, env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "INVALID_JSON" }, 400); }

  const current = cleanRow(article);
  let lifecycle = current.lifecycle;
  let featured = current.featured;
  let category = current.category;
  let preference = current.preference;
  const changes = [];

  if (Object.prototype.hasOwnProperty.call(body, "lifecycle")) {
    if (!validLifecycle(body.lifecycle)) return json({ ok: false, error: "INVALID_LIFECYCLE" }, 400);
    if (body.lifecycle !== lifecycle) changes.push(["lifecycle", body.lifecycle]);
    lifecycle = body.lifecycle;
  }
  if (Object.prototype.hasOwnProperty.call(body, "featured")) {
    if (typeof body.featured !== "boolean") return json({ ok: false, error: "INVALID_FEATURED" }, 400);
    if (body.featured !== featured) changes.push(["featured", body.featured ? "1" : "0"]);
    featured = body.featured;
  }
  if (Object.prototype.hasOwnProperty.call(body, "category")) {
    const next = body.category == null ? null : String(body.category).trim();
    if (next && next.length > 40) return json({ ok: false, error: "CATEGORY_TOO_LONG" }, 400);
    if (next !== category) changes.push(["category", next]);
    category = next || null;
  }
  if (Object.prototype.hasOwnProperty.call(body, "preference")) {
    const next = body.preference == null || body.preference === "" ? null : String(body.preference);
    if (!validPreference(next)) return json({ ok: false, error: "INVALID_PREFERENCE" }, 400);
    if (next !== preference) changes.push(["preference", next]);
    preference = next;
  }

  const statements = [
    env.DB.prepare(`
      INSERT INTO rss_reader_state (article_id, lifecycle, featured, category, preference, updated_at)
      VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(article_id) DO UPDATE SET
        lifecycle = excluded.lifecycle,
        featured = excluded.featured,
        category = excluded.category,
        preference = excluded.preference,
        updated_at = CURRENT_TIMESTAMP
    `).bind(articleId, lifecycle, featured ? 1 : 0, category, preference),
  ];

  for (const [action, value] of changes) {
    statements.push(env.DB.prepare(`
      INSERT INTO rss_preference_events
        (article_id, action, value, source_key, category, title_snapshot)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(articleId, action, value == null ? null : String(value), article.source_key, category, article.title));
  }
  await env.DB.batch(statements);
  const updated = await getArticle(env, articleId);
  return json({ ok: true, article: cleanRow(updated), changed: changes.map(([action]) => action) });
}

async function preferenceProfile(env) {
  const result = await env.DB.prepare(`
    SELECT a.article_id, a.title, a.source_key, a.source_name,
           COALESCE(s.lifecycle, 'active') AS lifecycle,
           COALESCE(s.featured, 0) AS featured,
           s.category, s.preference, s.updated_at
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    ORDER BY COALESCE(s.updated_at, a.updated_at) DESC
    LIMIT 500
  `).all();
  const rows = result.results || [];
  const countMap = (field, filter) => {
    const out = {};
    for (const row of rows) {
      if (filter && !filter(row)) continue;
      const key = String(row[field] || "").trim();
      if (!key) continue;
      out[key] = (out[key] || 0) + 1;
    }
    return Object.entries(out).sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count }));
  };
  const liked = rows.filter((x) => x.preference === "like").map((x) => ({ article_id: x.article_id, title: x.title, source: x.source_name, category: x.category || null }));
  const disliked = rows.filter((x) => x.preference === "dislike").map((x) => ({ article_id: x.article_id, title: x.title, source: x.source_name, category: x.category || null }));
  return json({
    ok: true,
    explicitSignals: liked.length + disliked.length,
    liked,
    disliked,
    featuredCount: rows.filter((x) => Number(x.featured || 0) === 1 && x.lifecycle !== "deleted").length,
    archivedCount: rows.filter((x) => x.lifecycle === "archived").length,
    deletedCount: rows.filter((x) => x.lifecycle === "deleted").length,
    categories: countMap("category"),
    likedCategories: countMap("category", (x) => x.preference === "like"),
    dislikedCategories: countMap("category", (x) => x.preference === "dislike"),
    likedSources: countMap("source_name", (x) => x.preference === "like"),
    dislikedSources: countMap("source_name", (x) => x.preference === "dislike"),
  });
}

function libraryHtml() {
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#090909"><title>RSS Library</title><style>
:root{color-scheme:dark;--bg:#090909;--card:#121212;--card2:#181818;--line:#2a2a2a;--text:#f4f4f5;--muted:#96969d;--accent:#fff;--danger:#ff7373;--good:#7ee787}*{box-sizing:border-box}html,body{width:100%;max-width:100%;height:100%;margin:0;overflow:hidden;background:var(--bg)}body{color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}button,input,select{font:inherit}button{cursor:pointer}.app{width:100%;max-width:720px;height:100dvh;margin:0 auto;display:flex;flex-direction:column;overflow:hidden;background:var(--bg)}.head{flex:0 0 auto;padding:calc(12px + env(safe-area-inset-top)) 14px 8px;background:#090909e8;backdrop-filter:blur(18px);border-bottom:1px solid #202020;z-index:5}.titlebar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.titlebar h1{font-size:25px;line-height:1.1;letter-spacing:-.03em;margin:0}.head-actions{display:flex;gap:7px}.iconbtn{height:36px;min-width:36px;border:1px solid var(--line);border-radius:11px;background:#111;color:#eee;padding:0 10px}.searchrow{display:grid;grid-template-columns:minmax(0,1fr) 126px;gap:8px}.search,.catfilter{height:42px;border:1px solid var(--line);border-radius:12px;background:#111;color:#eee;min-width:0;padding:0 12px;outline:none}.search:focus,.catfilter:focus{border-color:#555}.status{font-size:12px;color:var(--muted);margin:8px 2px 0}.viewport{flex:1 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch;padding:10px 12px 96px}.list{display:grid;gap:9px;min-width:0}.card{min-width:0;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:13px}.card.featured{border-color:#515151;background:#151515}.cardtop{display:flex;align-items:center;gap:7px;min-width:0;color:var(--muted);font-size:12px}.source{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.badge{flex:0 0 auto;border:1px solid #333;background:#1b1b1b;border-radius:999px;padding:2px 7px;color:#c8c8cc}.date{margin-left:auto;flex:0 0 auto}.card h2{font-size:17px;line-height:1.32;margin:8px 0 7px;letter-spacing:-.01em;overflow-wrap:anywhere;word-break:break-word}.card h2 a{color:inherit;text-decoration:none}.id{font:11px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;color:#6f6f75;overflow-wrap:anywhere}.actions{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin-top:11px}.act{height:38px;border:1px solid #2e2e2e;border-radius:10px;background:#181818;color:#d4d4d8;padding:0 4px;font-size:13px}.act.on{background:#f2f2f2;color:#090909;border-color:#f2f2f2}.act.like.on{background:#17351f;color:#a7f3b6;border-color:#285d35}.act.dislike.on{background:#391b1b;color:#ffb1b1;border-color:#633030}.act.trash{color:#ff8f8f}.catrow{display:grid;grid-template-columns:82px minmax(0,1fr);gap:8px;align-items:center;margin-top:8px}.catrow label{font-size:12px;color:var(--muted)}.catsel{width:100%;height:36px;border:1px solid #2d2d2d;border-radius:10px;background:#151515;color:#ddd;padding:0 8px}.empty{text-align:center;color:var(--muted);padding:44px 18px}.nav{position:absolute;left:0;right:0;bottom:0;display:grid;grid-template-columns:repeat(4,1fr);gap:5px;padding:8px 10px calc(8px + env(safe-area-inset-bottom));background:#0a0a0af2;backdrop-filter:blur(20px);border-top:1px solid #242424;z-index:6}.navbtn{height:54px;border:0;border-radius:12px;background:transparent;color:#888;font-size:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}.navbtn span{font-size:19px;line-height:1}.navbtn.on{color:#fff;background:#171717}.auth{position:fixed;inset:0;z-index:20;background:#090909;display:flex;align-items:center;justify-content:center;padding:22px}.authbox{width:100%;max-width:390px;background:#111;border:1px solid #2b2b2b;border-radius:18px;padding:18px}.authbox h2{margin:0 0 6px}.authbox p{color:var(--muted);margin:0 0 14px}.authbox input{width:100%;height:46px;border:1px solid #333;border-radius:12px;background:#090909;color:#fff;padding:0 12px}.authbox button{width:100%;height:46px;border:0;border-radius:12px;background:#fff;color:#000;font-weight:700;margin-top:9px}.profile{position:fixed;inset:0;z-index:15;background:#000a;display:none;align-items:flex-end;justify-content:center}.profile.show{display:flex}.sheet{width:100%;max-width:720px;max-height:82dvh;overflow:auto;background:#151515;border:1px solid #333;border-radius:22px 22px 0 0;padding:18px 16px calc(24px + env(safe-area-inset-bottom))}.sheethead{display:flex;justify-content:space-between;align-items:center}.sheet h2{margin:0}.metric{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.metric span{background:#202020;border:1px solid #303030;border-radius:999px;padding:6px 9px}.prefsec{margin-top:16px}.prefsec h3{font-size:14px;margin:0 0 7px}.prefitem{padding:8px 0;border-bottom:1px solid #262626;overflow-wrap:anywhere}.bad{color:var(--danger)}@media(max-width:430px){.searchrow{grid-template-columns:minmax(0,1fr) 112px}.actions{gap:5px}.act{font-size:12px}.viewport{padding-left:10px;padding-right:10px}.card{padding:12px}}
</style></head><body><div class="app" id="app"><header class="head"><div class="titlebar"><h1>Library</h1><div class="head-actions"><button class="iconbtn" id="profileBtn">Gu</button><button class="iconbtn" id="reload">↻</button></div></div><div class="searchrow"><input class="search" id="search" type="search" placeholder="Tìm bài, nguồn, ID"><select class="catfilter" id="cat"><option value="">Tất cả mục</option></select></div><div class="status" id="status">Đang tải…</div></header><main class="viewport"><div class="list" id="list"></div></main><nav class="nav" id="nav"><button class="navbtn on" data-view="active"><span>▤</span>Inbox</button><button class="navbtn" data-view="featured"><span>★</span>Nổi bật</button><button class="navbtn" data-view="archived"><span>▣</span>Lưu trữ</button><button class="navbtn" data-view="deleted"><span>⌫</span>Đã xoá</button></nav></div><div class="auth" id="auth"><div class="authbox"><h2>RSS Library</h2><p>Nhập Reader token trên thiết bị này.</p><input id="token" type="password" autocomplete="off" placeholder="RSS Reader token"><button id="save">Mở Library</button><p class="bad" id="authErr"></p></div></div><div class="profile" id="profile"><section class="sheet"><div class="sheethead"><h2>Gu đọc đang học</h2><button class="iconbtn" id="closeProfile">✕</button></div><div id="profileBody">Đang tải…</div></section></div><script>
const KEY='rssReaderToken';
const state={view:'active',q:'',category:'',timer:null};
const token=document.querySelector('#token'),auth=document.querySelector('#auth'),authErr=document.querySelector('#authErr'),status=document.querySelector('#status'),list=document.querySelector('#list'),search=document.querySelector('#search'),cat=document.querySelector('#cat'),profile=document.querySelector('#profile'),profileBody=document.querySelector('#profileBody');
function decodeText(value){const el=document.createElement('textarea');el.innerHTML=String(value??'');return el.value}
function esc(value){return String(value??'')}
function fmtDate(value){if(!value)return '';const d=new Date(value);return Number.isNaN(d.getTime())?'':d.toLocaleDateString('vi-VN',{day:'2-digit',month:'2-digit'})}
const hash=location.hash.startsWith('#token=')?decodeURIComponent(location.hash.slice(7)):'';if(hash){localStorage.setItem(KEY,hash);history.replaceState(null,'',location.pathname+location.search)}token.value=localStorage.getItem(KEY)||'';
async function api(path,opt={}){const t=localStorage.getItem(KEY)||token.value.trim();const headers={Authorization:'Bearer '+t,...(opt.headers||{})};if(opt.body&&!headers['Content-Type'])headers['Content-Type']='application/json';const r=await fetch(path,{...opt,headers});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||String(r.status));return j}
function setAuth(show,msg=''){auth.style.display=show?'flex':'none';authErr.textContent=msg}
function option(value,label,selected){const o=document.createElement('option');o.value=value;o.textContent=label;o.selected=selected;return o}
function categorySelect(a,suggested){const s=document.createElement('select');s.className='catsel';s.append(option('','Chưa phân loại',!a.category));const values=[...new Set([...(suggested||[]),a.category].filter(Boolean))];for(const x of values)s.append(option(x,x,a.category===x));s.onchange=async()=>{await patch(a.article_id,{category:s.value||null});await load()};return s}
async function patch(id,data){return api('/reader/rss/articles/'+encodeURIComponent(id)+'/state',{method:'POST',body:JSON.stringify(data)})}
function button(label,cls,on,handler){const b=document.createElement('button');b.className='act '+cls+(on?' on':'');b.textContent=label;b.onclick=handler;return b}
function renderCard(a,suggested){const d=document.createElement('article');d.className='card'+(a.featured?' featured':'');const top=document.createElement('div');top.className='cardtop';const src=document.createElement('span');src.className='source';src.textContent=decodeText(a.source_name);top.append(src);if(a.category){const bd=document.createElement('span');bd.className='badge';bd.textContent=a.category;top.append(bd)}const dt=document.createElement('span');dt.className='date';dt.textContent=fmtDate(a.published_at);top.append(dt);const h=document.createElement('h2'),link=document.createElement('a');link.href='/rss/article/'+encodeURIComponent(a.article_id);link.textContent=decodeText(a.title);h.append(link);const id=document.createElement('div');id.className='id';id.textContent='ID: '+a.article_id;const acts=document.createElement('div');acts.className='actions';acts.append(button('👍','like',a.preference==='like',async()=>{await patch(a.article_id,{preference:a.preference==='like'?null:'like'});load()}));acts.append(button('👎','dislike',a.preference==='dislike',async()=>{await patch(a.article_id,{preference:a.preference==='dislike'?null:'dislike'});load()}));acts.append(button('★','star',a.featured,async()=>{await patch(a.article_id,{featured:!a.featured});load()}));if(a.lifecycle==='archived')acts.append(button('↩','archive',false,async()=>{await patch(a.article_id,{lifecycle:'active'});load()}));else acts.append(button('▣','archive',false,async()=>{await patch(a.article_id,{lifecycle:'archived'});load()}));if(a.lifecycle==='deleted')acts.append(button('Khôi phục','restore',false,async()=>{await patch(a.article_id,{lifecycle:'active'});load()}));else acts.append(button('⌫','trash',false,async()=>{await patch(a.article_id,{lifecycle:'deleted'});load()}));const cr=document.createElement('div');cr.className='catrow';const lab=document.createElement('label');lab.textContent='Phân loại';cr.append(lab,categorySelect(a,suggested));d.append(top,h,id,acts,cr);return d}
function fillCategories(values,suggested){const current=cat.value;cat.textContent='';cat.append(option('','Tất cả mục',current===''));for(const x of [...new Set([...(suggested||[]),...(values||[])])])cat.append(option(x,x,current===x))}
async function load(){status.textContent='Đang tải…';list.textContent='';try{const p=new URLSearchParams({view:state.view});if(state.q)p.set('q',state.q);if(state.category)p.set('category',state.category);const j=await api('/reader/rss/library?'+p.toString());setAuth(false);fillCategories(j.categories,j.suggestedCategories);status.textContent=j.count+' bài'+(state.category?' · '+state.category:'');if(!j.articles.length){const e=document.createElement('div');e.className='empty';e.textContent='Không có bài trong mục này.';list.append(e)}else for(const a of j.articles)list.append(renderCard(a,j.suggestedCategories))}catch(e){setAuth(true,e.message==='UNAUTHORIZED'?'Reader token không hợp lệ':e.message);status.textContent=''}}
document.querySelector('#save').onclick=()=>{localStorage.setItem(KEY,token.value.trim());load()};document.querySelector('#reload').onclick=load;search.oninput=()=>{state.q=search.value.trim();clearTimeout(state.timer);state.timer=setTimeout(load,220)};cat.onchange=()=>{state.category=cat.value;load()};for(const b of document.querySelectorAll('.navbtn'))b.onclick=()=>{state.view=b.dataset.view;for(const x of document.querySelectorAll('.navbtn'))x.classList.toggle('on',x===b);load()};
function renderPairs(title,items){const sec=document.createElement('section');sec.className='prefsec';const h=document.createElement('h3');h.textContent=title;sec.append(h);if(!items||!items.length){const p=document.createElement('div');p.className='prefitem';p.textContent='Chưa đủ dữ liệu';sec.append(p)}else for(const x of items.slice(0,12)){const p=document.createElement('div');p.className='prefitem';p.textContent=x.name+' · '+x.count;sec.append(p)}return sec}
async function showProfile(){profile.classList.add('show');profileBody.textContent='Đang tải…';try{const j=await api('/reader/rss/preferences');profileBody.textContent='';const m=document.createElement('div');m.className='metric';for(const x of ['👍 '+j.liked.length,'👎 '+j.disliked.length,'★ '+j.featuredCount,'▣ '+j.archivedCount]){const s=document.createElement('span');s.textContent=x;m.append(s)}profileBody.append(m,renderPairs('Category hợp gu',j.likedCategories),renderPairs('Category không hợp',j.dislikedCategories),renderPairs('Nguồn hợp gu',j.likedSources),renderPairs('Nguồn không hợp',j.dislikedSources))}catch(e){profileBody.textContent=e.message}}
document.querySelector('#profileBtn').onclick=showProfile;document.querySelector('#closeProfile').onclick=()=>profile.classList.remove('show');profile.onclick=(e)=>{if(e.target===profile)profile.classList.remove('show')};load();
</script></body></html>`;
}

function articleHtml(articleId) {
  const encoded = JSON.stringify(articleId);
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#090909"><title>RSS Article</title><style>
:root{color-scheme:dark;--bg:#090909;--panel:#121212;--line:#2b2b2b;--text:#f4f4f5;--muted:#97979f;--danger:#ff7a7a}*{box-sizing:border-box}html,body{width:100%;max-width:100%;margin:0;overflow-x:hidden;background:var(--bg)}body{color:var(--text);font:17px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}.wrap{width:100%;max-width:760px;margin:0 auto;padding:0 15px 100px}.bar{position:sticky;top:0;z-index:6;margin:0 -15px;padding:calc(9px + env(safe-area-inset-top)) 14px 9px;background:#090909e8;backdrop-filter:blur(18px);border-bottom:1px solid #202020;display:flex;align-items:center;gap:8px}.bar a,.bar button{height:36px;border:1px solid #2d2d2d;border-radius:10px;background:#111;color:#eee;padding:0 10px;text-decoration:none;display:inline-flex;align-items:center}.bar .source{margin-left:auto;max-width:42%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.title{font-size:31px;line-height:1.16;letter-spacing:-.025em;margin:24px 0 9px;overflow-wrap:anywhere}.meta{font-size:13px;color:var(--muted);overflow-wrap:anywhere}.id{font:11px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;color:#6f6f75;overflow-wrap:anywhere;margin-top:5px}.statepanel{margin:16px 0;background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:10px}.actions{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}.act{height:38px;border:1px solid #303030;border-radius:10px;background:#181818;color:#ddd;padding:0 4px}.act.on{background:#f2f2f2;color:#090909;border-color:#f2f2f2}.act.like.on{background:#17351f;color:#a7f3b6;border-color:#285d35}.act.dislike.on{background:#391b1b;color:#ffb1b1;border-color:#633030}.act.trash{color:#ff9090}.catline{display:grid;grid-template-columns:82px minmax(0,1fr);gap:8px;align-items:center;margin-top:8px}.catline label{font-size:12px;color:var(--muted)}select{width:100%;height:36px;border:1px solid #303030;border-radius:10px;background:#151515;color:#ddd;padding:0 8px}.audio{margin:14px 0 20px;background:#111;border:1px solid #2b2b2b;border-radius:15px;padding:11px}.audiohead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.audiohead strong{font-size:14px}.audiohead span{font-size:12px;color:var(--muted)}.audiocontrols{display:grid;grid-template-columns:42px minmax(0,1fr) 42px 82px;gap:6px}.audiocontrols button,.audiocontrols select{height:40px;border:1px solid #303030;border-radius:10px;background:#181818;color:#eee}.bad{color:var(--danger);overflow-wrap:anywhere}.images{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;width:100%;margin:18px 0 24px;overflow:hidden}.images figure{margin:0;min-width:0}.images img{display:block;width:100%;max-width:100%;height:auto;max-height:700px;object-fit:contain;border-radius:12px;background:#111}.images figcaption{font-size:13px;color:var(--muted);margin-top:6px;overflow-wrap:anywhere}.body{display:block;width:100%;max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;overflow-x:hidden;font:inherit;margin:20px 0 0;color:#ececee}.lang{display:flex;gap:7px;margin:14px 0}.lang button{height:38px;border:1px solid #303030;border-radius:10px;background:#171717;color:#ddd;padding:0 11px}.lang button.on{background:#eee;color:#111;border-color:#eee}@media(max-width:430px){.wrap{padding-left:13px;padding-right:13px}.bar{margin-left:-13px;margin-right:-13px}.title{font-size:28px}.actions{gap:5px}.act{font-size:12px}.audiocontrols{grid-template-columns:40px minmax(0,1fr) 40px 76px}}
</style></head><body><main class="wrap"><div class="bar"><a href="/rss/library">‹ Library</a><a class="source" id="source" target="_blank" rel="noopener noreferrer">Bài gốc ↗</a></div><h1 class="title" id="title">RSS Article</h1><div class="meta" id="meta"></div><div class="id" id="articleId"></div><div class="lang"><button id="vi">Tiếng Việt</button><button id="original">Original</button></div><section class="statepanel"><div class="actions"><button class="act like" id="like">👍</button><button class="act dislike" id="dislike">👎</button><button class="act" id="star">★</button><button class="act" id="archive">▣</button><button class="act trash" id="trash">⌫</button></div><div class="catline"><label>Phân loại</label><select id="category"><option value="">Chưa phân loại</option></select></div></section><section class="audio"><div class="audiohead"><strong>Audio</strong><span id="audioState">Chưa phát</span></div><div class="audiocontrols"><button id="prevAudio">‹</button><button id="playAudio">▶ Nghe</button><button id="stopAudio">■</button><select id="rate"><option value="0.9">0.9×</option><option value="1" selected>1.0×</option><option value="1.1">1.1×</option><option value="1.2">1.2×</option></select></div></section><p class="bad" id="error"></p><section class="images" id="images"></section><div class="body" id="body"></div></main><script>
const KEY='rssReaderToken',id=${encoded};
const body=document.querySelector('#body'),images=document.querySelector('#images'),err=document.querySelector('#error'),meta=document.querySelector('#meta'),articleId=document.querySelector('#articleId'),title=document.querySelector('#title'),source=document.querySelector('#source'),category=document.querySelector('#category');
let article=null,artifact=null,activeKind='vi',chunks=[],audioIndex=0,audioUtterance=null;
function decodeText(value){const el=document.createElement('textarea');el.innerHTML=String(value??'');return el.value}
async function api(path,opt={}){const t=localStorage.getItem(KEY)||'';if(!t)throw new Error('MISSING_READER_TOKEN');const headers={Authorization:'Bearer '+t,...(opt.headers||{})};if(opt.body&&!headers['Content-Type'])headers['Content-Type']='application/json';const r=await fetch(path,{...opt,headers});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||String(r.status));return j}
function renderImages(value){images.textContent='';if(!Array.isArray(value))return;for(const item of value){const url=String(item&&item.url||'');if(!url.startsWith('http://')&&!url.startsWith('https://'))continue;const f=document.createElement('figure'),img=document.createElement('img');img.src=url;img.loading='lazy';img.decoding='async';img.alt=decodeText(item.alt||'');f.append(img);const cap=decodeText(item.caption||item.alt||'').trim();if(cap){const c=document.createElement('figcaption');c.textContent=cap;f.append(c)}images.append(f)}}
function fillCategories(values){const current=article&&article.category||'';category.textContent='';const blank=document.createElement('option');blank.value='';blank.textContent='Chưa phân loại';category.append(blank);for(const x of [...new Set([...(values||[]),current].filter(Boolean))]){const o=document.createElement('option');o.value=x;o.textContent=x;o.selected=x===current;category.append(o)}category.value=current}
function syncState(){if(!article)return;document.querySelector('#like').classList.toggle('on',article.preference==='like');document.querySelector('#dislike').classList.toggle('on',article.preference==='dislike');document.querySelector('#star').classList.toggle('on',!!article.featured);document.querySelector('#archive').classList.toggle('on',article.lifecycle==='archived');document.querySelector('#archive').textContent=article.lifecycle==='archived'?'↩':'▣';document.querySelector('#trash').classList.toggle('on',article.lifecycle==='deleted');document.querySelector('#trash').textContent=article.lifecycle==='deleted'?'Khôi phục':'⌫';category.value=article.category||''}
async function patch(data){const j=await api('/reader/rss/articles/'+encodeURIComponent(id)+'/state',{method:'POST',body:JSON.stringify(data)});article=j.article;syncState();return j}
function makeChunks(text){const raw=String(text||'').trim();if(!raw)return [];const paras=raw.split('\n\n').map(x=>x.trim()).filter(Boolean);const out=[];let current='';for(const p of paras){if(p.length>1300){if(current){out.push(current);current=''}for(let i=0;i<p.length;i+=1200)out.push(p.slice(i,i+1200));continue}if((current+' '+p).length>1200){if(current)out.push(current);current=p}else current=current?current+'\n\n'+p:p}if(current)out.push(current);return out}
function audioKey(){return 'rssAudio:'+id+':'+activeKind}
function updateAudioState(label){const el=document.querySelector('#audioState');if(label)el.textContent=label;else el.textContent=chunks.length?(Math.min(audioIndex+1,chunks.length)+' / '+chunks.length):'Không có nội dung'}
function chooseVoice(){const voices=speechSynthesis.getVoices();const lang=activeKind==='vi'?'vi':'en';return voices.find(v=>String(v.lang||'').toLowerCase().startsWith(lang))||null}
function speakCurrent(){if(!('speechSynthesis' in window)){updateAudioState('Trình duyệt không hỗ trợ');return}if(!chunks.length){updateAudioState('Không có nội dung');return}if(audioIndex>=chunks.length)audioIndex=0;speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(chunks[audioIndex]);u.lang=activeKind==='vi'?'vi-VN':'en-US';u.rate=Number(document.querySelector('#rate').value||1);const voice=chooseVoice();if(voice)u.voice=voice;audioUtterance=u;localStorage.setItem(audioKey(),String(audioIndex));updateAudioState('Đang nghe '+(audioIndex+1)+' / '+chunks.length);u.onend=()=>{if(audioUtterance!==u)return;audioIndex+=1;if(audioIndex<chunks.length){localStorage.setItem(audioKey(),String(audioIndex));speakCurrent()}else{audioIndex=0;localStorage.setItem(audioKey(),'0');updateAudioState('Đã nghe xong')}};u.onerror=()=>updateAudioState('Audio bị gián đoạn');speechSynthesis.speak(u)}
function stopSpeech(){if('speechSynthesis' in window)speechSynthesis.cancel();audioUtterance=null;updateAudioState()}
function rebuildAudio(){stopSpeech();chunks=makeChunks(decodeText(artifact&&artifact.body||''));const saved=Number(localStorage.getItem(audioKey())||0);audioIndex=Number.isFinite(saved)&&saved>=0&&saved<chunks.length?saved:0;updateAudioState()}
async function view(kind){err.textContent='';body.textContent='Đang tải…';images.textContent='';stopSpeech();try{const j=await api('/reader/rss/articles/'+encodeURIComponent(id)+'/'+kind);article=j.article;artifact=j.artifact;activeKind=kind;renderImages(artifact.images);body.textContent=decodeText(artifact.body||'');syncState();rebuildAudio();document.querySelector('#vi').classList.toggle('on',kind==='vi');document.querySelector('#original').classList.toggle('on',kind==='original')}catch(e){body.textContent='';err.textContent=e.message==='UNAUTHORIZED'?'Reader token không hợp lệ':e.message}}
async function init(){try{const j=await api('/reader/rss/articles/'+encodeURIComponent(id));article=j.article;title.textContent=decodeText(article.title);meta.textContent=[decodeText(article.source_name),article.published_at].filter(Boolean).join(' · ');articleId.textContent='ID: '+article.article_id;source.href=article.canonical_url||'#';fillCategories(j.suggestedCategories);syncState();const preferred=(article.source_language==='vi'||article.translation_status==='published'||article.translation_status==='native_vi')?'vi':'original';await view(preferred)}catch(e){err.textContent=e.message==='MISSING_READER_TOKEN'?'Mở lại RSS Library để đăng nhập':e.message}}
document.querySelector('#vi').onclick=()=>view('vi');document.querySelector('#original').onclick=()=>view('original');document.querySelector('#like').onclick=()=>patch({preference:article.preference==='like'?null:'like'});document.querySelector('#dislike').onclick=()=>patch({preference:article.preference==='dislike'?null:'dislike'});document.querySelector('#star').onclick=()=>patch({featured:!article.featured});document.querySelector('#archive').onclick=()=>patch({lifecycle:article.lifecycle==='archived'?'active':'archived'});document.querySelector('#trash').onclick=()=>patch({lifecycle:article.lifecycle==='deleted'?'active':'deleted'});category.onchange=()=>patch({category:category.value||null});document.querySelector('#playAudio').onclick=speakCurrent;document.querySelector('#stopAudio').onclick=stopSpeech;document.querySelector('#prevAudio').onclick=()=>{stopSpeech();audioIndex=Math.max(0,audioIndex-1);localStorage.setItem(audioKey(),String(audioIndex));speakCurrent()};document.querySelector('#rate').onchange=()=>{if(audioUtterance)speakCurrent()};window.addEventListener('pagehide',stopSpeech);init();
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

  if (request.method === "GET" && url.pathname === "/reader/rss/library") return listArticles(env, url);
  if (request.method === "GET" && url.pathname === "/reader/rss/preferences") return preferenceProfile(env);

  const stateMatch = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/state$/);
  if (stateMatch) {
    let articleId;
    try { articleId = decodeURIComponent(stateMatch[1]); } catch { return json({ ok: false, error: "INVALID_ARTICLE_ID" }, 400); }
    if (request.method === "POST") return updateReaderState(request, env, articleId);
    return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  }

  if (request.method !== "GET") return json({ ok: false, error: "READ_ONLY_EXCEPT_READER_STATE" }, 405);
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)(?:\/(original|vi))?$/);
  if (!match) return json({ ok: false, error: "READER_ROUTE_NOT_FOUND" }, 404);
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return json({ ok: false, error: "INVALID_ARTICLE_ID" }, 400); }
  const action = match[2] || "detail";
  if (action === "detail") return articleDetail(env, articleId);
  return articleView(env, articleId, action);
}
