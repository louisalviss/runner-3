const READER_TOKEN_SHA256 = "a4efd86ada61ed4398ec259b7f46262f10d4e2f7fa4f123c5619eb6366d0dd18";
const PAGE_SIZES = new Set([10, 20, 50, 100]);

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

function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function containsTerm(text, term) {
  if (!term) return false;
  return (` ${text} `).includes(` ${term} `);
}

async function loadCategories(env) {
  const rows = await env.DB.prepare(`
    SELECT c.name, c.keywords, c.sort_order,
           COUNT(CASE WHEN s.category = c.name THEN 1 END) AS usage
    FROM rss_reader_categories c
    LEFT JOIN rss_reader_state s ON s.category = c.name
    GROUP BY c.name, c.keywords, c.sort_order
    ORDER BY c.sort_order, lower(c.name)
  `).all();
  return (rows.results || []).map((row) => ({
    name: String(row.name || "").trim(),
    keywords: String(row.keywords || "").trim(),
    sort_order: Number(row.sort_order || 100),
    usage: Number(row.usage || 0),
  })).filter((x) => x.name);
}

function inferCategory(article, categories) {
  const title = normalizeText(article?.title);
  const source = normalizeText(article?.source_name);
  const haystack = `${title} ${source}`.trim();
  let best = null;
  let bestScore = 0;

  for (const category of categories) {
    if (category.name === "Khác") continue;
    const terms = String(category.keywords || "")
      .split(",")
      .map(normalizeText)
      .filter(Boolean);
    let score = 0;
    for (const term of terms) {
      if (containsTerm(haystack, term)) score += term.includes(" ") ? 4 : 2;
      if (containsTerm(title, term)) score += 1;
    }
    if (score > bestScore) {
      bestScore = score;
      best = category.name;
    }
  }
  return best || (categories.some((x) => x.name === "Khác") ? "Khác" : categories[0]?.name || null);
}

async function runBatches(env, statements, size = 50) {
  for (let i = 0; i < statements.length; i += size) {
    await env.DB.batch(statements.slice(i, i + size));
  }
}

async function autoCategorizeMissing(env) {
  const categories = await loadCategories(env);
  if (!categories.length) return categories;
  const missing = await env.DB.prepare(`
    SELECT a.article_id, a.title, a.source_name
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE (s.category IS NULL OR trim(s.category) = '')
      AND COALESCE(s.lifecycle, 'active') != 'deleted'
    ORDER BY a.published_at DESC, a.article_id
    LIMIT 500
  `).all();
  const statements = [];
  for (const row of missing.results || []) {
    const category = inferCategory(row, categories);
    if (!category) continue;
    statements.push(env.DB.prepare(`
      INSERT INTO rss_reader_state (article_id, lifecycle, featured, category, updated_at)
      VALUES (?, 'active', 0, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(article_id) DO UPDATE SET
        category = CASE
          WHEN rss_reader_state.category IS NULL OR trim(rss_reader_state.category) = '' THEN excluded.category
          ELSE rss_reader_state.category
        END,
        updated_at = CURRENT_TIMESTAMP
    `).bind(row.article_id, category));
  }
  if (statements.length) await runBatches(env, statements);
  return loadCategories(env);
}

function viewCondition(view) {
  if (view === "featured") return "COALESCE(s.featured,0)=1 AND COALESCE(s.lifecycle,'active')!='deleted'";
  if (view === "archived") return "COALESCE(s.lifecycle,'active')='archived'";
  if (view === "deleted") return "COALESCE(s.lifecycle,'active')='deleted'";
  if (view === "all") return "1=1";
  return "COALESCE(s.lifecycle,'active')='active'";
}

async function listLibraryV2(env, url) {
  const categories = await autoCategorizeMissing(env);
  const requestedView = String(url.searchParams.get("view") || "active");
  const view = new Set(["active", "featured", "archived", "deleted", "all"]).has(requestedView) ? requestedView : "active";
  const q = String(url.searchParams.get("q") || "").trim();
  const category = String(url.searchParams.get("category") || "").trim();
  const requestedPageSize = Number(url.searchParams.get("pageSize") || 20);
  const pageSize = PAGE_SIZES.has(requestedPageSize) ? requestedPageSize : 20;
  const requestedPage = Math.max(1, Number(url.searchParams.get("page") || 1) || 1);

  const where = [viewCondition(view)];
  const args = [];
  if (category) {
    where.push("s.category = ?");
    args.push(category);
  }
  if (q) {
    where.push("(lower(a.title) LIKE ? OR lower(a.source_name) LIKE ? OR lower(COALESCE(s.category,'')) LIKE ?)");
    const needle = `%${q.toLowerCase()}%`;
    args.push(needle, needle, needle);
  }
  const whereSql = where.join(" AND ");
  const countRow = await env.DB.prepare(`
    SELECT COUNT(*) AS total
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE ${whereSql}
  `).bind(...args).first();
  const total = Number(countRow?.total || 0);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const page = Math.min(requestedPage, totalPages);
  const offset = (page - 1) * pageSize;

  const rows = await env.DB.prepare(`
    SELECT a.article_id, a.canonical_url, a.source_key, a.source_name, a.source_language,
           a.title, a.published_at, a.fetch_status, a.translation_status, a.qa_state,
           a.last_error, a.updated_at,
           COALESCE(s.lifecycle, 'active') AS lifecycle,
           COALESCE(s.featured, 0) AS featured,
           s.category, s.preference, s.last_opened_at
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE ${whereSql}
    ORDER BY a.published_at DESC, a.article_id
    LIMIT ? OFFSET ?
  `).bind(...args, pageSize, offset).all();

  return json({
    ok: true,
    view,
    q,
    category,
    page,
    pageSize,
    total,
    totalPages,
    categories,
    articles: (rows.results || []).map(cleanRow),
  });
}

async function saveCategory(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "INVALID_JSON" }, 400); }
  const name = String(body?.name || "").trim();
  const keywords = String(body?.keywords || "").trim();
  if (!name) return json({ ok: false, error: "CATEGORY_REQUIRED" }, 400);
  if (name.length > 40) return json({ ok: false, error: "CATEGORY_TOO_LONG" }, 400);
  if (keywords.length > 800) return json({ ok: false, error: "KEYWORDS_TOO_LONG" }, 400);
  if (new Set(["Trading", "WordPress"]).has(name)) return json({ ok: false, error: "CATEGORY_RETIRED" }, 400);

  const order = name === "Khác" ? 999 : 100;
  await env.DB.prepare(`
    INSERT INTO rss_reader_categories (name, keywords, sort_order, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(name) DO UPDATE SET
      keywords = excluded.keywords,
      updated_at = CURRENT_TIMESTAMP
  `).bind(name, keywords, order).run();
  return json({ ok: true, categories: await loadCategories(env) });
}

async function deleteCategory(env, name) {
  if (!name) return json({ ok: false, error: "CATEGORY_REQUIRED" }, 400);
  if (name === "Khác") return json({ ok: false, error: "CATEGORY_FALLBACK_REQUIRED" }, 409);
  const exists = await env.DB.prepare("SELECT name FROM rss_reader_categories WHERE name = ?").bind(name).first();
  if (!exists) return json({ ok: false, error: "CATEGORY_NOT_FOUND" }, 404);
  await env.DB.batch([
    env.DB.prepare(`UPDATE rss_reader_state SET category = NULL, updated_at = CURRENT_TIMESTAMP WHERE category = ?`).bind(name),
    env.DB.prepare(`DELETE FROM rss_reader_categories WHERE name = ?`).bind(name),
  ]);
  await autoCategorizeMissing(env);
  return json({ ok: true, categories: await loadCategories(env) });
}

async function neighbors(env, articleId) {
  await autoCategorizeMissing(env);
  const rows = await env.DB.prepare(`
    SELECT a.article_id, a.title
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE COALESCE(s.lifecycle, 'active') != 'deleted'
    ORDER BY a.published_at DESC, a.article_id
    LIMIT 1000
  `).all();
  const items = rows.results || [];
  const index = items.findIndex((x) => x.article_id === articleId);
  if (index < 0) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  return json({
    ok: true,
    previous: index > 0 ? items[index - 1] : null,
    next: index + 1 < items.length ? items[index + 1] : null,
  });
}

function libraryHtml() {
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#090909"><title>RSS Library</title><style>
:root{color-scheme:dark;--bg:#090909;--card:#121212;--line:#2a2a2a;--text:#f4f4f5;--muted:#96969d;--good:#9be9a8;--bad:#ffaaaa}*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg)}body{color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}button,input,select{font:inherit}button{cursor:pointer}.app{position:relative;width:100%;max-width:760px;height:100dvh;margin:0 auto;display:flex;flex-direction:column;background:var(--bg);overflow:hidden}.head{flex:0 0 auto;padding:calc(11px + env(safe-area-inset-top)) 12px 9px;background:#090909ef;backdrop-filter:blur(18px);border-bottom:1px solid #202020;z-index:5}.titlebar{display:flex;align-items:center;gap:8px}.titlebar h1{font-size:25px;line-height:1;margin:0;letter-spacing:-.03em}.spacer{flex:1}.iconbtn,.act,.pager button{border:1px solid var(--line);background:#151515;color:#ddd;border-radius:11px;display:inline-flex;align-items:center;justify-content:center}.iconbtn{width:38px;height:38px;padding:0}.iconbtn svg,.act svg,.pager svg,.navbtn svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}.searchrow{display:grid;grid-template-columns:minmax(0,1fr) 132px;gap:8px;margin-top:10px}.search,.catfilter{height:42px;border:1px solid var(--line);border-radius:12px;background:#111;color:#eee;min-width:0;padding:0 12px;outline:none}.statusrow{display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12px;color:var(--muted)}.statusrow .right{margin-left:auto}.viewport{flex:1 1 auto;min-height:0;overflow:auto;-webkit-overflow-scrolling:touch;padding:10px 10px 166px}.list{display:grid;gap:9px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px;min-width:0}.card.featured{border-color:#555}.cardtop{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);min-width:0}.source{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.date{margin-left:auto;flex:0 0 auto}.badge{flex:0 0 auto;border:1px solid #343434;border-radius:999px;padding:2px 7px;background:#1b1b1b;color:#ccc}.card h2{font-size:17px;line-height:1.32;margin:8px 0 10px;letter-spacing:-.01em;overflow-wrap:anywhere}.card h2 a{color:inherit;text-decoration:none}.actions{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px}.act{height:38px;padding:0}.act.on{background:#f0f0f0;color:#090909;border-color:#f0f0f0}.act.like.on{background:#17351f;color:var(--good);border-color:#285d35}.act.dislike.on{background:#391b1b;color:var(--bad);border-color:#633030}.act.trash{color:#ff9090}.catrow{display:grid;grid-template-columns:76px minmax(0,1fr);gap:8px;align-items:center;margin-top:8px}.catrow label{font-size:12px;color:var(--muted)}.catsel{height:36px;border:1px solid #2d2d2d;border-radius:10px;background:#151515;color:#ddd;padding:0 8px;width:100%}.empty{text-align:center;color:var(--muted);padding:50px 20px}.pager{position:absolute;left:10px;right:10px;bottom:calc(70px + env(safe-area-inset-bottom));height:48px;padding:5px 8px;display:flex;align-items:center;justify-content:center;gap:10px;background:#111e;backdrop-filter:blur(18px);border:1px solid #292929;border-radius:14px;z-index:7}.pager button{width:38px;height:36px}.pager span{min-width:64px;text-align:center;font-size:13px}.nav{position:absolute;left:0;right:0;bottom:0;display:grid;grid-template-columns:repeat(4,1fr);gap:4px;padding:6px 9px calc(7px + env(safe-area-inset-bottom));background:#0a0a0af2;backdrop-filter:blur(20px);border-top:1px solid #242424;z-index:6}.navbtn{height:56px;border:0;border-radius:12px;background:transparent;color:#888;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:11px}.navbtn.on{color:#fff;background:#171717}.auth{position:fixed;inset:0;z-index:30;background:#090909;display:flex;align-items:center;justify-content:center;padding:22px}.authbox{width:100%;max-width:390px;background:#111;border:1px solid #2b2b2b;border-radius:18px;padding:18px}.authbox h2{margin:0 0 6px}.authbox p{color:var(--muted)}.authbox input{width:100%;height:46px;border:1px solid #333;border-radius:12px;background:#090909;color:#fff;padding:0 12px}.authbox button{width:100%;height:46px;border:0;border-radius:12px;background:#fff;color:#000;font-weight:700;margin-top:9px}.bad{color:#ff8f8f}.sheetback{position:fixed;inset:0;z-index:20;background:#000a;display:none;align-items:flex-end;justify-content:center}.sheetback.show{display:flex}.sheet{width:100%;max-width:760px;max-height:86dvh;overflow:auto;background:#151515;border:1px solid #333;border-radius:22px 22px 0 0;padding:16px 14px calc(24px + env(safe-area-inset-bottom))}.sheethead{display:flex;align-items:center;gap:8px}.sheethead h2{margin:0;font-size:20px}.setting{margin-top:18px}.setting h3{font-size:14px;margin:0 0 8px}.setting select,.setting input{height:40px;border:1px solid #303030;border-radius:10px;background:#101010;color:#eee;padding:0 10px;width:100%}.catcreate{display:grid;grid-template-columns:minmax(0,1fr) 44px;gap:7px}.catcreate .keywords{grid-column:1/-1}.catlist{display:grid;gap:7px;margin-top:10px}.catitem{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:9px 10px;border:1px solid #292929;border-radius:12px;background:#111}.catitem small{color:var(--muted)}.catdelete{width:34px;height:34px;border:1px solid #3a2a2a;border-radius:9px;background:#1a1111;color:#ff9a9a}.hint{font-size:12px;color:var(--muted);margin-top:6px}.toast{position:fixed;left:50%;bottom:140px;transform:translateX(-50%);z-index:40;background:#222;border:1px solid #444;border-radius:999px;padding:8px 12px;font-size:12px;opacity:0;pointer-events:none;transition:.2s}.toast.show{opacity:1}@media(max-width:430px){.searchrow{grid-template-columns:minmax(0,1fr) 112px}.actions{gap:5px}.viewport{padding-left:9px;padding-right:9px}.card{padding:11px}}
</style></head><body><div class="app"><header class="head"><div class="titlebar"><h1>Library</h1><div class="spacer"></div><button class="iconbtn" id="settings" aria-label="Cài đặt"></button><button class="iconbtn" id="reload" aria-label="Tải lại"></button></div><div class="searchrow"><input class="search" id="search" type="search" placeholder="Tìm tiêu đề, nguồn…"><select class="catfilter" id="cat"><option value="">Tất cả mục</option></select></div><div class="statusrow"><span id="status">Đang tải…</span><span class="right" id="pageInfo"></span></div></header><main class="viewport" id="viewport"><div class="list" id="list"></div></main><div class="pager"><button id="prevPage" aria-label="Trang trước"></button><span id="pagerText">1 / 1</span><button id="nextPage" aria-label="Trang sau"></button></div><nav class="nav"><button class="navbtn on" data-view="active"></button><button class="navbtn" data-view="featured"></button><button class="navbtn" data-view="archived"></button><button class="navbtn" data-view="deleted"></button></nav></div><div class="auth" id="auth"><div class="authbox"><h2>RSS Library</h2><p>Nhập Reader token trên thiết bị này.</p><input id="token" type="password" autocomplete="off" placeholder="RSS Reader token"><button id="save">Mở Library</button><p class="bad" id="authErr"></p></div></div><div class="sheetback" id="sheetback"><section class="sheet"><div class="sheethead"><h2>Library settings</h2><div class="spacer"></div><button class="iconbtn" id="closeSheet"></button></div><div class="setting"><h3>Số bài mỗi trang</h3><select id="pageSize"><option value="10">10 bài</option><option value="20">20 bài</option><option value="50">50 bài</option><option value="100">100 bài</option></select></div><div class="setting"><h3>Quản lý phân loại</h3><div class="catcreate"><input id="newCat" placeholder="Tên phân loại"><button class="iconbtn" id="saveCat" aria-label="Tạo hoặc cập nhật"></button><input class="keywords" id="newKeywords" placeholder="Từ khoá tự phân loại, cách nhau bằng dấu phẩy"></div><div class="hint">Bài chưa có phân loại sẽ được tự gán. Muốn sửa bài cụ thể, đổi ngay ở card hoặc trong Reader.</div><div class="catlist" id="catList"></div></div></section></div><div class="toast" id="toast"></div><script>
const KEY='rssReaderToken',SIZE_KEY='rssLibraryPageSize';
const ICONS={settings:'<circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.55V20h-3v-.09a1.7 1.7 0 0 0-1.03-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7 14.7a1.7 1.7 0 0 0-1.55-1.03H5v-3h.09A1.7 1.7 0 0 0 6.64 9.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.12-2.12.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 11.33 4.4V4h3v.09a1.7 1.7 0 0 0 1.03 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06A1.7 1.7 0 0 0 19 9.3c.2.63.78 1.06 1.44 1.06H21v3h-.09A1.7 1.7 0 0 0 19.4 15z"></path>',refresh:'<path d="M20 11a8 8 0 1 0-2.34 5.66"></path><path d="M20 4v7h-7"></path>',like:'<path d="M7 10v11"></path><path d="M15 5.5 13.5 10H20a2 2 0 0 1 1.9 2.6l-2 6A2 2 0 0 1 18 20H7V10l4-7a2 2 0 0 1 4 2.5z"></path>',dislike:'<path d="M17 14V3"></path><path d="m9 18.5 1.5-4.5H4a2 2 0 0 1-1.9-2.6l2-6A2 2 0 0 1 6 4h11v10l-4 7a2 2 0 0 1-4-2.5z"></path>',star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3z"></path>',archive:'<rect x="3" y="5" width="18" height="4" rx="1"></rect><path d="M5 9v11h14V9"></path><path d="M9 13h6"></path>',trash:'<path d="M4 7h16"></path><path d="m9 7 1-3h4l1 3"></path><path d="m6 7 1 14h10l1-14"></path>',share:'<circle cx="18" cy="5" r="2"></circle><circle cx="6" cy="12" r="2"></circle><circle cx="18" cy="19" r="2"></circle><path d="m8 11 8-5"></path><path d="m8 13 8 5"></path>',left:'<path d="m15 18-6-6 6-6"></path>',right:'<path d="m9 18 6-6-6-6"></path>',x:'<path d="M6 6l12 12M18 6 6 18"></path>',plus:'<path d="M12 5v14M5 12h14"></path>',inbox:'<path d="M4 4h16v16H4z"></path><path d="M4 14h4l2 3h4l2-3h4"></path>'};
function svg(name){const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');s.innerHTML=ICONS[name]||'';return s}
function setIcon(el,name,label){el.textContent='';el.append(svg(name));if(label){const t=document.createElement('span');t.textContent=label;el.append(t)}}
function iconButton(name,label,cls,on,handler){const b=document.createElement('button');b.className='act '+(cls||'')+(on?' on':'');b.title=label;b.setAttribute('aria-label',label);b.append(svg(name));b.onclick=handler;return b}
const state={view:'active',q:'',category:'',page:1,pageSize:Number(localStorage.getItem(SIZE_KEY)||20),timer:null,totalPages:1,categories:[]};if(![10,20,50,100].includes(state.pageSize))state.pageSize=20;
const token=document.querySelector('#token'),auth=document.querySelector('#auth'),authErr=document.querySelector('#authErr'),status=document.querySelector('#status'),list=document.querySelector('#list'),search=document.querySelector('#search'),cat=document.querySelector('#cat'),viewport=document.querySelector('#viewport'),sheetback=document.querySelector('#sheetback'),pageSize=document.querySelector('#pageSize'),catList=document.querySelector('#catList'),toast=document.querySelector('#toast');
setIcon(document.querySelector('#settings'),'settings');setIcon(document.querySelector('#reload'),'refresh');setIcon(document.querySelector('#prevPage'),'left');setIcon(document.querySelector('#nextPage'),'right');setIcon(document.querySelector('#closeSheet'),'x');setIcon(document.querySelector('#saveCat'),'plus');
const navDefs=[['active','inbox','Inbox'],['featured','star','Nổi bật'],['archived','archive','Lưu trữ'],['deleted','trash','Đã xoá']];for(const [view,ico,label] of navDefs){const b=document.querySelector('.navbtn[data-view="'+view+'"]');b.append(svg(ico));const s=document.createElement('span');s.textContent=label;b.append(s)}
function decodeText(value){const el=document.createElement('textarea');el.innerHTML=String(value??'');return el.value}
function fmtDate(value){if(!value)return '';const d=new Date(value);return Number.isNaN(d.getTime())?'':d.toLocaleDateString('vi-VN',{day:'2-digit',month:'2-digit'})}
const hash=location.hash.startsWith('#token=')?decodeURIComponent(location.hash.slice(7)):'';if(hash){localStorage.setItem(KEY,hash);history.replaceState(null,'',location.pathname+location.search)}token.value=localStorage.getItem(KEY)||'';
async function api(path,opt={}){const t=localStorage.getItem(KEY)||token.value.trim();const headers={Authorization:'Bearer '+t,...(opt.headers||{})};if(opt.body&&!headers['Content-Type'])headers['Content-Type']='application/json';const r=await fetch(path,{...opt,headers});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||String(r.status));return j}
function setAuth(show,msg=''){auth.style.display=show?'flex':'none';authErr.textContent=msg}
function option(value,label,selected){const o=document.createElement('option');o.value=value;o.textContent=label;o.selected=selected;return o}
function categorySelect(a,categories){const s=document.createElement('select');s.className='catsel';for(const x of categories){s.append(option(x.name,x.name,a.category===x.name))}if(a.category&&!categories.some(x=>x.name===a.category))s.append(option(a.category,a.category,true));s.onchange=async()=>{await patch(a.article_id,{category:s.value||null});await load()};return s}
async function patch(id,data){return api('/reader/rss/articles/'+encodeURIComponent(id)+'/state',{method:'POST',body:JSON.stringify(data)})}
async function shareArticle(a){const url=String(a.canonical_url||'');if(!url)return showToast('Không có link bài gốc');const data={title:decodeText(a.title||''),text:decodeText(a.title||''),url};try{if(navigator.share){await navigator.share(data)}else{await navigator.clipboard.writeText(url);showToast('Đã copy link bài gốc')}}catch(e){if(e&&e.name!=='AbortError')showToast('Không share được')}}
function renderCard(a,categories){const d=document.createElement('article');d.className='card'+(a.featured?' featured':'');const top=document.createElement('div');top.className='cardtop';const src=document.createElement('span');src.className='source';src.textContent=decodeText(a.source_name);top.append(src);if(a.category){const bd=document.createElement('span');bd.className='badge';bd.textContent=a.category;top.append(bd)}const dt=document.createElement('span');dt.className='date';dt.textContent=fmtDate(a.published_at);top.append(dt);const h=document.createElement('h2'),link=document.createElement('a');link.href='/rss/article/'+encodeURIComponent(a.article_id);link.textContent=decodeText(a.title);h.append(link);const acts=document.createElement('div');acts.className='actions';acts.append(iconButton('like','Thích','like',a.preference==='like',async()=>{await patch(a.article_id,{preference:a.preference==='like'?null:'like'});load()}));acts.append(iconButton('dislike','Không thích','dislike',a.preference==='dislike',async()=>{await patch(a.article_id,{preference:a.preference==='dislike'?null:'dislike'});load()}));acts.append(iconButton('star','Nổi bật','star',a.featured,async()=>{await patch(a.article_id,{featured:!a.featured});load()}));acts.append(iconButton('archive',a.lifecycle==='archived'?'Đưa về Inbox':'Lưu trữ','archive',a.lifecycle==='archived',async()=>{await patch(a.article_id,{lifecycle:a.lifecycle==='archived'?'active':'archived'});load()}));acts.append(iconButton('trash',a.lifecycle==='deleted'?'Khôi phục':'Xoá','trash',a.lifecycle==='deleted',async()=>{await patch(a.article_id,{lifecycle:a.lifecycle==='deleted'?'active':'deleted'});load()}));acts.append(iconButton('share','Chia sẻ','share',false,()=>shareArticle(a)));const cr=document.createElement('div');cr.className='catrow';const lab=document.createElement('label');lab.textContent='Phân loại';cr.append(lab,categorySelect(a,categories));d.append(top,h,acts,cr);return d}
function fillCategories(categories){state.categories=categories||[];const current=state.category;cat.textContent='';cat.append(option('','Tất cả mục',!current));for(const x of state.categories)cat.append(option(x.name,x.name,current===x.name))}
function renderCategoryManager(){catList.textContent='';for(const x of state.categories){const row=document.createElement('div');row.className='catitem';const name=document.createElement('div');const strong=document.createElement('div');strong.textContent=x.name;const small=document.createElement('small');small.textContent=(x.usage||0)+' bài'+(x.keywords?' · '+x.keywords:'');name.append(strong,small);const edit=document.createElement('button');edit.className='iconbtn';edit.title='Sửa từ khoá';edit.append(svg('settings'));edit.onclick=()=>{document.querySelector('#newCat').value=x.name;document.querySelector('#newKeywords').value=x.keywords||'';document.querySelector('#newKeywords').focus()};row.append(name,edit);if(x.name!=='Khác'){const del=document.createElement('button');del.className='catdelete';del.title='Xoá phân loại';del.append(svg('trash'));del.onclick=async()=>{if(!confirm('Xoá phân loại “'+x.name+'”? Các bài sẽ được tự phân loại lại.'))return;await api('/reader/rss/categories/'+encodeURIComponent(x.name),{method:'DELETE'});state.page=1;await load();renderCategoryManager()};row.append(del)}else{const pad=document.createElement('span');row.append(pad)}catList.append(row)}}
async function load(){status.textContent='Đang tải…';list.textContent='';try{const p=new URLSearchParams({view:state.view,page:String(state.page),pageSize:String(state.pageSize)});if(state.q)p.set('q',state.q);if(state.category)p.set('category',state.category);const j=await api('/reader/rss/library/v2?'+p.toString());setAuth(false);state.page=j.page;state.totalPages=j.totalPages;fillCategories(j.categories);status.textContent=j.total+' bài'+(state.category?' · '+state.category:'');document.querySelector('#pageInfo').textContent='Trang '+j.page+'/'+j.totalPages;document.querySelector('#pagerText').textContent=j.page+' / '+j.totalPages;document.querySelector('#prevPage').disabled=j.page<=1;document.querySelector('#nextPage').disabled=j.page>=j.totalPages;if(!j.articles.length){const e=document.createElement('div');e.className='empty';e.textContent='Không có bài trong mục này.';list.append(e)}else for(const a of j.articles)list.append(renderCard(a,j.categories));renderCategoryManager();viewport.scrollTo({top:0,behavior:'auto'})}catch(e){setAuth(true,e.message==='UNAUTHORIZED'?'Reader token không hợp lệ':e.message);status.textContent=''}}
function resetAndLoad(){state.page=1;load()}
function showToast(msg){toast.textContent=msg;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1600)}
document.querySelector('#save').onclick=()=>{localStorage.setItem(KEY,token.value.trim());load()};document.querySelector('#reload').onclick=load;search.oninput=()=>{state.q=search.value.trim();clearTimeout(state.timer);state.timer=setTimeout(resetAndLoad,220)};cat.onchange=()=>{state.category=cat.value;resetAndLoad()};for(const b of document.querySelectorAll('.navbtn'))b.onclick=()=>{state.view=b.dataset.view;for(const x of document.querySelectorAll('.navbtn'))x.classList.toggle('on',x===b);resetAndLoad()};document.querySelector('#prevPage').onclick=()=>{if(state.page>1){state.page--;load()}};document.querySelector('#nextPage').onclick=()=>{if(state.page<state.totalPages){state.page++;load()}};
pageSize.value=String(state.pageSize);pageSize.onchange=()=>{state.pageSize=Number(pageSize.value);localStorage.setItem(SIZE_KEY,String(state.pageSize));state.page=1;load()};document.querySelector('#settings').onclick=()=>{pageSize.value=String(state.pageSize);sheetback.classList.add('show');renderCategoryManager()};document.querySelector('#closeSheet').onclick=()=>sheetback.classList.remove('show');sheetback.onclick=e=>{if(e.target===sheetback)sheetback.classList.remove('show')};document.querySelector('#saveCat').onclick=async()=>{const name=document.querySelector('#newCat').value.trim(),keywords=document.querySelector('#newKeywords').value.trim();if(!name)return showToast('Nhập tên phân loại');await api('/reader/rss/categories',{method:'POST',body:JSON.stringify({name,keywords})});document.querySelector('#newCat').value='';document.querySelector('#newKeywords').value='';state.page=1;await load();renderCategoryManager();showToast('Đã lưu phân loại')};load();
</script></body></html>`;
}

export async function handleRssReaderPlus(request, env, url) {
  if (request.method === "GET" && url.pathname === "/rss/library") {
    return new Response(libraryHtml(), { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
  }

  const isPlusApi = url.pathname === "/reader/rss/library/v2" ||
    url.pathname === "/reader/rss/categories" ||
    url.pathname.startsWith("/reader/rss/categories/") ||
    /^\/reader\/rss\/articles\/[^/]+\/neighbors$/.test(url.pathname);
  if (!isPlusApi) return null;
  if (!env.DB) return json({ ok: false, error: "D1_NOT_BOUND" }, 503);
  if (!(await readerAuthorized(request))) return json({ ok: false, error: "UNAUTHORIZED" }, 401);

  if (request.method === "GET" && url.pathname === "/reader/rss/library/v2") return listLibraryV2(env, url);
  if (url.pathname === "/reader/rss/categories") {
    if (request.method === "GET") return json({ ok: true, categories: await loadCategories(env) });
    if (request.method === "POST") return saveCategory(request, env);
    return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  }
  const catMatch = url.pathname.match(/^\/reader\/rss\/categories\/([^/]+)$/);
  if (catMatch) {
    let name;
    try { name = decodeURIComponent(catMatch[1]); } catch { return json({ ok: false, error: "INVALID_CATEGORY" }, 400); }
    if (request.method === "DELETE") return deleteCategory(env, name);
    return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  }
  const neighborMatch = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/neighbors$/);
  if (neighborMatch) {
    let articleId;
    try { articleId = decodeURIComponent(neighborMatch[1]); } catch { return json({ ok: false, error: "INVALID_ARTICLE_ID" }, 400); }
    if (request.method === "GET") return neighbors(env, articleId);
    return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  }
  return null;
}
