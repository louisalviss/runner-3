const TABLE = "library_file_index_v1";
const FAVORITES = "library_favorites_v1";
const FAVORITE_META = "library_favorite_meta_v1";
const MAX_LIMIT = 100;
const R2_ROOT = "core/ebook/";

const LEGACY_BOOK_INFO = {
  "blindsight": { title: "Blindsight", creator: "Peter Watts" },
  "broken-money": { title: "Broken Money", creator: "Lyn Alden" },
  "chiec-hop-pandora": { title: "Chiếc Hộp Pandora" },
  "consider-phlebas": { title: "Consider Phlebas", creator: "Iain M. Banks" },
  "skeleton-crew": { title: "Skeleton Crew", creator: "Stephen King" },
  "dcc-01": { title: "Dungeon Crawler Carl", creator: "Matt Dinniman", series: "DCC · Book 1" },
  "dcc-02": { title: "Carl's Doomsday Scenario", creator: "Matt Dinniman", series: "DCC · Book 2" },
  "dcc-03": { title: "The Dungeon Anarchist's Cookbook", creator: "Matt Dinniman", series: "DCC · Book 3" },
  "dcc-04": { title: "The Gate of the Feral Gods", creator: "Matt Dinniman", series: "DCC · Book 4" },
  "dcc-05": { title: "The Butcher's Masquerade", creator: "Matt Dinniman", series: "DCC · Book 5" },
  "dcc-06": { title: "The Eye of the Bedlam Bride", creator: "Matt Dinniman", series: "DCC · Book 6" },
  "dcc-07": { title: "This Inevitable Ruin", creator: "Matt Dinniman", series: "DCC · Book 7" },
  "dcc-08": { title: "A Parade of Horribles", creator: "Matt Dinniman", series: "DCC · Book 8" },
};

let favoritesInitPromise = null;
let legacySeedPromise = null;

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function headers(contentType) {
  return new Headers({
    "Content-Type": contentType,
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet, noimageindex",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
  });
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: headers("application/json; charset=utf-8") });
}

function html(body, status = 200) {
  const h = headers("text/html; charset=utf-8");
  h.set("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
  return new Response(body, { status, headers: h });
}

function libraryDb(env) { return env.LIBRARY_DB || null; }
function safeLimit(url) { return Math.max(1, Math.min(MAX_LIMIT, Number(url.searchParams.get("limit") || 100) || 100)); }
function safeOffset(url) { return Math.max(0, Math.min(100000, Number(url.searchParams.get("offset") || 0) || 0)); }
function validFormat(value) { const v = String(value || "").toLowerCase(); return /^[a-z0-9]{1,12}$/.test(v) ? v : ""; }
function isFinalEpubKey(key) { return typeof key === "string" && key.startsWith(R2_ROOT) && key.includes("/final/") && key.toLowerCase().endsWith(".epub"); }
function r2Scope(key) { const p = String(key || "").split("/"); return p[0] === "core" && p[1] === "ebook" ? String(p[2] || "") : ""; }
function r2Version(key) { const m = String(key || "").match(/(?:^|[-_.])v(\d+)(?:\.epub)?$/i); return m ? Number(m[1]) : 0; }
function cleanR2Name(key) {
  let s = String(key || "").split("/").filter(Boolean).pop() || "EPUB";
  try { s = decodeURIComponent(s); } catch {}
  s = s.replace(/\.epub$/i, "").replace(/(?:[-_\s]+VI)?[-_\s]*v\d+\s*$/i, "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return s || "EPUB";
}

async function ensureFavorites(env) {
  const db = libraryDb(env);
  if (!db) throw new Error("LIBRARY_DB_NOT_BOUND");
  if (!favoritesInitPromise) {
    favoritesInitPromise = (async () => {
      await db.prepare(`CREATE TABLE IF NOT EXISTS ${FAVORITES}(source TEXT NOT NULL,ref TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(source,ref))`).run();
      await db.prepare(`CREATE INDEX IF NOT EXISTS idx_library_favorites_created_v1 ON ${FAVORITES}(created_at DESC)`).run();
      await db.prepare(`CREATE TABLE IF NOT EXISTS ${FAVORITE_META}(k TEXT PRIMARY KEY,v TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`).run();
    })().catch((error) => { favoritesInitPromise = null; throw error; });
  }
  return favoritesInitPromise;
}

async function canonicalR2Books(env) {
  if (!env.ARTIFACTS) return [];
  const latest = new Map();
  let cursor;
  do {
    const page = await env.ARTIFACTS.list({ prefix: R2_ROOT, cursor, limit: 1000, include: ["customMetadata"] });
    for (const object of page.objects || []) {
      if (!isFinalEpubKey(object.key)) continue;
      const scope = r2Scope(object.key) || object.key;
      const current = latest.get(scope);
      const uploaded = object.uploaded instanceof Date ? object.uploaded.toISOString() : String(object.uploaded || "");
      const candidate = { object, scope, uploaded };
      if (!current) { latest.set(scope, candidate); continue; }
      const a = Date.parse(uploaded) || 0, b = Date.parse(current.uploaded || "") || 0;
      if (a > b || (a === b && r2Version(object.key) > r2Version(current.object.key))) latest.set(scope, candidate);
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return [...latest.values()].map(({ object, scope }) => {
    const custom = object.customMetadata || {};
    const known = LEGACY_BOOK_INFO[scope] || {};
    return {
      library_id: `r2:${scope}`,
      source_type: "r2",
      source_ref: object.key,
      category: "ebook",
      title: known.title || String(custom.title || custom.book_title || "").trim() || cleanR2Name(object.key),
      creator: known.creator || String(custom.creator || custom.author || "").trim() || null,
      series: known.series || String(custom.series || "").trim() || null,
      volume: null,
      format: "epub",
      file_name: String(object.key).split("/").pop() || "book.epub",
      size: Number(object.size || 0),
      telegram_link: null,
      tags: "legacy-r2 favorite",
      favorite: 1,
      r2_key: object.key,
    };
  });
}

async function seedLegacyR2Favorites(env) {
  await ensureFavorites(env);
  if (!legacySeedPromise) {
    legacySeedPromise = (async () => {
      const db = libraryDb(env);
      const marker = await db.prepare(`SELECT v FROM ${FAVORITE_META} WHERE k='legacy_r2_seed_v1'`).first();
      if (String(marker?.v || "") === "1") return 0;
      const books = await canonicalR2Books(env);
      for (const book of books) {
        await db.prepare(`INSERT OR IGNORE INTO ${FAVORITES}(source,ref,created_at) VALUES('r2',?,CURRENT_TIMESTAMP)`).bind(book.source_ref).run();
      }
      await db.prepare(`INSERT INTO ${FAVORITE_META}(k,v,updated_at) VALUES('legacy_r2_seed_v1','1',CURRENT_TIMESTAMP) ON CONFLICT(k) DO UPDATE SET v='1',updated_at=CURRENT_TIMESTAMP`).run();
      return books.length;
    })().catch((error) => { legacySeedPromise = null; throw error; });
  }
  return legacySeedPromise;
}

async function favoriteCount(env) {
  const db = libraryDb(env);
  const row = await db.prepare(`SELECT COUNT(*) AS n FROM ${FAVORITES}`).first();
  return Number(row?.n || 0);
}

async function meta(env) {
  const db = libraryDb(env);
  await seedLegacyR2Favorites(env);
  const total = await db.prepare(`SELECT COUNT(*) AS n FROM ${TABLE} WHERE category='ebook'`).first();
  const formats = await db.prepare(`SELECT format,COUNT(*) AS n FROM ${TABLE} WHERE category='ebook' GROUP BY format ORDER BY n DESC,format LIMIT 30`).all();
  const unknown = await db.prepare(`SELECT COUNT(*) AS n FROM ${TABLE} WHERE category='ebook' AND (creator IS NULL OR TRIM(creator)='')`).first();
  return {
    ok: true,
    count: Number(total?.n || 0),
    formats: formats.results || [],
    ebook_unknown_creator: Number(unknown?.n || 0),
    favorite_count: await favoriteCount(env),
    authority: "personal-library",
  };
}

function commonFilter(row, { q, format, unknownCreator }) {
  if (format && String(row.format || "").toLowerCase() !== format) return false;
  if (unknownCreator && String(row.creator || "").trim()) return false;
  if (q) {
    const hay = normalize([row.title, row.creator, row.series, row.file_name, row.tags].filter(Boolean).join(" "));
    for (const term of q.split(/\s+/).filter(Boolean).slice(0, 12)) if (!hay.includes(term)) return false;
  }
  return true;
}

function rowCompare(sort) {
  const coll = new Intl.Collator("vi", { sensitivity: "base", numeric: true });
  return (a, b) => {
    if (sort === "creator") return coll.compare(a.creator || "\uffff", b.creator || "\uffff") || coll.compare(a.title || "", b.title || "");
    if (sort === "series") return coll.compare(a.series || "\uffff", b.series || "\uffff") || Number(a.volume || 0) - Number(b.volume || 0) || coll.compare(a.title || "", b.title || "");
    return coll.compare(a.title || "", b.title || "") || Number(a.volume || 0) - Number(b.volume || 0);
  };
}

async function searchFavorites(env, url) {
  const db = libraryDb(env);
  await seedLegacyR2Favorites(env);
  const rawQ = String(url.searchParams.get("q") || "").trim();
  const q = normalize(rawQ);
  const format = validFormat(url.searchParams.get("format"));
  const unknownCreator = url.searchParams.get("unknown_creator") === "1";
  const sort = ["title", "creator", "series"].includes(url.searchParams.get("sort")) ? url.searchParams.get("sort") : "title";
  const limit = safeLimit(url), offset = safeOffset(url);
  const telegram = await db.prepare(`SELECT i.library_id,i.category,i.title,i.creator,i.series,i.volume,i.format,i.file_name,i.size,i.telegram_link,i.tags,'telegram' AS source_type,i.library_id AS source_ref,1 AS favorite FROM ${TABLE} i JOIN ${FAVORITES} f ON f.source='telegram' AND f.ref=i.library_id WHERE i.category='ebook'`).all();
  const r2FavRefs = new Set((await db.prepare(`SELECT ref FROM ${FAVORITES} WHERE source='r2'`).all()).results?.map((x) => String(x.ref)) || []);
  const r2 = (await canonicalR2Books(env)).filter((x) => r2FavRefs.has(String(x.source_ref)));
  const all = [...(telegram.results || []), ...r2].filter((x) => commonFilter(x, { q, format, unknownCreator })).sort(rowCompare(sort));
  return { ok: true, query: rawQ, normalized_query: q, total: all.length, items: all.slice(offset, offset + limit), limit, offset, format: format || null, unknown_creator: unknownCreator, sort, favorite_only: true };
}

async function search(env, url) {
  if (url.searchParams.get("favorite") === "1") return searchFavorites(env, url);
  const db = libraryDb(env);
  await ensureFavorites(env);
  const rawQ = String(url.searchParams.get("q") || "").trim();
  const q = normalize(rawQ);
  const format = validFormat(url.searchParams.get("format"));
  const unknownCreator = url.searchParams.get("unknown_creator") === "1";
  const sort = ["title", "creator", "series"].includes(url.searchParams.get("sort")) ? url.searchParams.get("sort") : "title";
  const limit = safeLimit(url), offset = safeOffset(url);
  const where = ["i.category='ebook'"];
  const params = [];
  if (q) for (const term of q.split(/\s+/).filter(Boolean).slice(0, 12)) { where.push("i.search_text LIKE ?"); params.push(`%${term}%`); }
  if (format) { where.push("LOWER(i.format)=?"); params.push(format); }
  if (unknownCreator) where.push("(i.creator IS NULL OR TRIM(i.creator)='')");
  const filter = `WHERE ${where.join(" AND ")}`;
  const order = sort === "creator"
    ? "CASE WHEN i.creator IS NULL OR TRIM(i.creator)='' THEN 1 ELSE 0 END,i.creator COLLATE NOCASE,i.title COLLATE NOCASE,i.volume,i.library_id"
    : sort === "series"
      ? "CASE WHEN i.series IS NULL OR TRIM(i.series)='' THEN 1 ELSE 0 END,i.series COLLATE NOCASE,i.volume,i.title COLLATE NOCASE,i.library_id"
      : "i.title COLLATE NOCASE,i.volume,i.library_id";
  const countRow = await db.prepare(`SELECT COUNT(*) AS n FROM ${TABLE} i ${filter}`).bind(...params).first();
  const rows = await db.prepare(`SELECT i.library_id,i.category,i.title,i.creator,i.series,i.volume,i.format,i.file_name,i.size,i.telegram_link,i.tags,'telegram' AS source_type,i.library_id AS source_ref,CASE WHEN f.ref IS NULL THEN 0 ELSE 1 END AS favorite FROM ${TABLE} i LEFT JOIN ${FAVORITES} f ON f.source='telegram' AND f.ref=i.library_id ${filter} ORDER BY ${order} LIMIT ? OFFSET ?`).bind(...params, limit, offset).all();
  return { ok: true, query: rawQ, normalized_query: q, total: Number(countRow?.n || 0), items: rows.results || [], limit, offset, format: format || null, unknown_creator: unknownCreator, sort, favorite_only: false };
}

async function setFavorite(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  await ensureFavorites(env);
  const db = libraryDb(env);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "INVALID_JSON" }, 400); }
  const source = String(body?.source || "");
  const ref = String(body?.ref || "").trim();
  const favorite = body?.favorite !== false;
  if (!(["telegram", "r2"].includes(source)) || !ref || ref.length > 1500) return json({ ok: false, error: "INVALID_FAVORITE" }, 400);
  if (source === "telegram") {
    if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,239}$/.test(ref)) return json({ ok: false, error: "INVALID_LIBRARY_ID" }, 400);
    const exists = await db.prepare(`SELECT library_id FROM ${TABLE} WHERE library_id=? AND category='ebook'`).bind(ref).first();
    if (!exists) return json({ ok: false, error: "EBOOK_NOT_FOUND" }, 404);
  } else {
    if (!isFinalEpubKey(ref)) return json({ ok: false, error: "INVALID_R2_KEY" }, 400);
    if (!env.ARTIFACTS || !(await env.ARTIFACTS.head(ref))) return json({ ok: false, error: "R2_EBOOK_NOT_FOUND" }, 404);
  }
  if (favorite) await db.prepare(`INSERT OR IGNORE INTO ${FAVORITES}(source,ref,created_at) VALUES(?,?,CURRENT_TIMESTAMP)`).bind(source, ref).run();
  else await db.prepare(`DELETE FROM ${FAVORITES} WHERE source=? AND ref=?`).bind(source, ref).run();
  return json({ ok: true, source, ref, favorite, favorite_count: await favoriteCount(env) });
}

function shell() {
  return `<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex"><title>Ebook Library</title>
<style>
:root{color-scheme:dark;--bg:#0a0b0d;--card:#111419;--line:#252b33;--muted:#98a3b3;--text:#f5f7fa;--accent:#f2f5f8;--chip:#171b21;--star:#f4cf63;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}html,body{max-width:100%;overflow-x:hidden}body{margin:0;background:radial-gradient(circle at 20% 0%,#17202b 0,transparent 28%),var(--bg);color:var(--text);min-height:100vh}.wrap{width:min(900px,100%);margin:0 auto;padding:max(16px,env(safe-area-inset-top)) 14px calc(76px + env(safe-area-inset-bottom))}.top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin:2px 2px 16px}.top-main{min-width:0}.back{color:#cbd3de;text-decoration:none;font-size:13px}.eyebrow{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#8f9bac;font-weight:800;margin-top:7px}h1{font-size:26px;line-height:1.08;margin:5px 0 0}.count{flex:0 0 auto;font-size:12px;color:var(--muted);padding-top:3px;text-align:right}.panel{background:rgba(17,20,25,.94);border:1px solid var(--line);border-radius:17px;padding:12px;position:sticky;top:max(4px,env(safe-area-inset-top));z-index:10;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}.search{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.search input{min-width:0;width:100%;background:#0b0e12;border:1px solid #303844;color:#fff;border-radius:12px;padding:12px 13px;font-size:16px;outline:none}.search button{border:0;border-radius:12px;padding:0 15px;min-height:44px;background:var(--accent);color:#090b0e;font-weight:800}.filters{display:flex;gap:7px;overflow-x:auto;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;padding:10px 1px 1px;scrollbar-width:none}.filters::-webkit-scrollbar{display:none}.chip,select{flex:0 0 auto;max-width:180px;white-space:nowrap;background:var(--chip);border:1px solid #2a313a;color:#cdd5df;border-radius:999px;padding:8px 11px;font-size:13px}.chip{cursor:pointer}.chip.active{background:#edf1f5;color:#11151a;border-color:#edf1f5;font-weight:800}select{outline:none}.status{font-size:13px;color:var(--muted);margin:14px 2px 9px}.grid{display:grid;gap:9px}.item{min-width:0;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:15px;padding:13px}.item-main{min-width:0}.title{max-width:100%;font-size:16px;font-weight:800;line-height:1.3;overflow-wrap:anywhere;word-break:normal}.meta{display:flex;flex-wrap:wrap;gap:5px 10px;margin-top:6px;color:#aab4c1;font-size:12px;line-height:1.4}.meta span{min-width:0;overflow-wrap:anywhere}.creator{color:#d8dee7}.unknown{color:#c99595}.badge{display:inline-flex;font-size:10px;border:1px solid #34404d;border-radius:999px;padding:3px 7px;color:#b8d6f0;margin-bottom:6px}.badge.r2{color:#e6d19a}.actions{display:flex;align-items:center;gap:7px}.open,.fav{appearance:none;display:inline-flex;align-items:center;justify-content:center;min-height:40px;border:1px solid #34404d;border-radius:11px;background:#151a20;color:#eef3f8;font-size:13px;font-weight:750;text-decoration:none}.open{padding:8px 12px}.fav{width:42px;padding:0;font-size:20px;cursor:pointer}.fav.on{color:var(--star)}.pager{display:flex;justify-content:center;gap:7px;margin:17px 0}.pager button{background:#171b21;color:#dde4ec;border:1px solid #303844;border-radius:10px;padding:9px 12px}.pager button:disabled{opacity:.35}.empty{padding:34px 14px;text-align:center;color:#8792a1;border:1px dashed #2b323c;border-radius:15px}
@media(max-width:620px){.wrap{padding-left:10px;padding-right:10px}.top{flex-direction:column;gap:6px;margin-bottom:12px}.count{text-align:left;padding:0}.panel{position:relative;top:auto;padding:10px;border-radius:14px}.search button{padding:0 13px}.item{grid-template-columns:minmax(0,1fr);gap:9px;padding:12px}.actions{width:100%}.open{flex:1}.fav{flex:0 0 44px}.title{font-size:15px}.meta{font-size:12px}.chip,select{max-width:160px}}
</style></head><body><main class="wrap">
<div class="top"><div class="top-main"><a class="back" href="/artifact-library/r2">R2 files</a><div class="eyebrow">Runner3 · Personal</div><h1>Ebook Library</h1></div><div class="count" id="total-count">…</div></div>
<section class="panel"><form class="search" id="search-form"><input id="q" name="q" autocomplete="off" placeholder="Tên sách, tác giả, bộ, tập…"><button>Tìm</button></form><div class="filters">
<button class="chip active" data-tab="all">📚 Tất cả</button><button class="chip" data-tab="favorite">★ Đã thích <span id="fav-count"></span></button>
<select id="format"><option value="">Mọi định dạng</option></select><select id="sort"><option value="title">Tên A–Z</option><option value="creator">Tác giả A–Z</option><option value="series">Series / tập</option></select><select id="limit"><option value="100">100 / trang</option><option value="40">40 / trang</option></select><button class="chip" id="unknown">❓ Chưa rõ tác giả</button>
</div></section><div class="status" id="status">Đang tải…</div><section class="grid" id="results"></section><div class="pager" id="pager"></div></main>
<script>(()=>{
const els={q:document.getElementById('q'),form:document.getElementById('search-form'),format:document.getElementById('format'),sort:document.getElementById('sort'),limit:document.getElementById('limit'),unknown:document.getElementById('unknown'),status:document.getElementById('status'),results:document.getElementById('results'),pager:document.getElementById('pager'),total:document.getElementById('total-count'),favCount:document.getElementById('fav-count')};
const state={q:'',favorite:false,format:'',sort:'title',unknown:false,offset:0,limit:100,total:0};
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=n=>{const x=Number(n||0);if(!x)return '';if(x>=1073741824)return (x/1073741824).toFixed(1)+' GB';if(x>=1048576)return (x/1048576).toFixed(1)+' MB';return Math.round(x/1024)+' KB'};
function syncUrl(){const u=new URL(location.href);state.q?u.searchParams.set('q',state.q):u.searchParams.delete('q');state.favorite?u.searchParams.set('favorite','1'):u.searchParams.delete('favorite');state.format?u.searchParams.set('format',state.format):u.searchParams.delete('format');state.sort!=='title'?u.searchParams.set('sort',state.sort):u.searchParams.delete('sort');state.limit!==100?u.searchParams.set('limit',state.limit):u.searchParams.delete('limit');state.unknown?u.searchParams.set('unknown','1'):u.searchParams.delete('unknown');state.offset?u.searchParams.set('offset',state.offset):u.searchParams.delete('offset');history.replaceState(null,'',u)}
function readUrl(){const u=new URL(location.href);state.q=u.searchParams.get('q')||'';state.favorite=u.searchParams.get('favorite')==='1';state.format=u.searchParams.get('format')||'';state.sort=u.searchParams.get('sort')||'title';state.limit=Number(u.searchParams.get('limit'))===40?40:100;state.unknown=u.searchParams.get('unknown')==='1';state.offset=Math.max(0,Number(u.searchParams.get('offset')||0)||0);els.q.value=state.q;els.sort.value=state.sort;els.limit.value=String(state.limit)}
function paintTabs(){document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',(b.dataset.tab==='favorite')===state.favorite));els.unknown.classList.toggle('active',state.unknown)}
async function loadMeta(){const r=await fetch('/artifact-library/api/personal-meta',{headers:{Accept:'application/json'}});if(r.status===401){location.href='/artifact-library';return}const d=await r.json();if(!d.ok)throw new Error(d.error||r.status);els.total.textContent=Number(d.count||0).toLocaleString('vi-VN')+' ebook';els.favCount.textContent='· '+Number(d.favorite_count||0).toLocaleString('vi-VN');const current=state.format;els.format.querySelectorAll('option:not(:first-child)').forEach(x=>x.remove());for(const f of d.formats||[]){if(!f.format)continue;const o=document.createElement('option');o.value=String(f.format).toLowerCase();o.textContent=String(f.format).toUpperCase()+' · '+Number(f.n||0).toLocaleString('vi-VN');els.format.appendChild(o)}els.format.value=current}
function card(x){const creator=x.creator?'<span class="creator">✍️ '+e(x.creator)+'</span>':'<span class="unknown">❓ Chưa rõ tác giả</span>';const series=x.series?'<span>📚 '+e(x.series)+(x.volume!=null?' · Tập '+e(x.volume):'')+'</span>':(x.volume!=null?'<span>🔢 Tập '+e(x.volume)+'</span>':'');const fmt=[x.format?String(x.format).toUpperCase():'',size(x.size)].filter(Boolean).join(' · ');const r2=x.source_type==='r2';const badge='<span class="badge '+(r2?'r2':'')+'">'+(r2?'R2 · CŨ':'TELEGRAM')+'</span>';const isEpub=String(x.format||'').toLowerCase()==='epub';let open='';if(r2&&x.r2_key)open='<a class="open" href="/artifact-library/read?key='+encodeURIComponent(String(x.r2_key))+'">Đọc</a>';else if(isEpub)open='<a class="open" href="/artifact-library/read?library_id='+encodeURIComponent(String(x.library_id||''))+'">Đọc</a>';else if(x.telegram_link)open='<a class="open" href="'+e(x.telegram_link)+'" target="_blank" rel="noreferrer">Telegram ↗</a>';const fav='<button class="fav '+(Number(x.favorite)?'on':'')+'" data-fav-source="'+e(x.source_type||'telegram')+'" data-fav-ref="'+e(x.source_ref||x.library_id||'')+'" data-favorite="'+(Number(x.favorite)?'1':'0')+'" aria-label="Đã thích">'+(Number(x.favorite)?'★':'☆')+'</button>';return '<article class="item"><div class="item-main">'+badge+'<div class="title">'+e(x.title||x.file_name||x.library_id)+'</div><div class="meta">'+creator+series+(fmt?'<span>📄 '+e(fmt)+'</span>':'')+'</div></div><div class="actions">'+open+fav+'</div></article>'}
function renderPager(){els.pager.innerHTML='';if(state.total<=state.limit)return;const prev=document.createElement('button');prev.textContent='← Trước';prev.disabled=state.offset===0;prev.onclick=()=>{state.offset=Math.max(0,state.offset-state.limit);run()};const page=document.createElement('button');page.disabled=true;page.textContent=(Math.floor(state.offset/state.limit)+1)+' / '+Math.ceil(state.total/state.limit);const next=document.createElement('button');next.textContent='Sau →';next.disabled=state.offset+state.limit>=state.total;next.onclick=()=>{state.offset+=state.limit;run()};els.pager.append(prev,page,next)}
let seq=0;async function run(){const mine=++seq;syncUrl();paintTabs();els.status.textContent='Đang tải…';const p=new URLSearchParams({limit:state.limit,offset:state.offset,sort:state.sort});if(state.q)p.set('q',state.q);if(state.favorite)p.set('favorite','1');if(state.format)p.set('format',state.format);if(state.unknown)p.set('unknown_creator','1');const r=await fetch('/artifact-library/api/personal-search?'+p,{headers:{Accept:'application/json'}});if(mine!==seq)return;if(r.status===401){location.href='/artifact-library';return}const d=await r.json();if(!d.ok){els.status.textContent='Lỗi: '+(d.error||r.status);return}state.total=Number(d.total||0);const shown=Array.isArray(d.items)?d.items.length:0;const from=state.total?state.offset+1:0,to=Math.min(state.offset+shown,state.total);els.status.textContent=(state.favorite?'Đã thích · ':'')+from.toLocaleString('vi-VN')+'–'+to.toLocaleString('vi-VN')+' / '+state.total.toLocaleString('vi-VN')+(state.q?' · “'+state.q+'”':'');els.results.innerHTML=shown?d.items.map(card).join(''):'<div class="empty">Không có sách phù hợp.</div>';renderPager()}
els.results.addEventListener('click',async ev=>{const btn=ev.target.closest('[data-fav-ref]');if(!btn)return;ev.preventDefault();const want=btn.dataset.favorite!=='1';btn.disabled=true;try{const r=await fetch('/artifact-library/api/personal-favorite',{method:'POST',headers:{'content-type':'application/json','accept':'application/json'},body:JSON.stringify({source:btn.dataset.favSource,ref:btn.dataset.favRef,favorite:want})});const d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||r.status);btn.dataset.favorite=want?'1':'0';btn.classList.toggle('on',want);btn.textContent=want?'★':'☆';els.favCount.textContent='· '+Number(d.favorite_count||0).toLocaleString('vi-VN');if(state.favorite&&!want)run()}catch(err){els.status.textContent='Không cập nhật được Đã thích: '+err.message}finally{btn.disabled=false}});
let timer;els.q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{state.q=els.q.value.trim();state.offset=0;run()},220)});els.form.addEventListener('submit',ev=>{ev.preventDefault();state.q=els.q.value.trim();state.offset=0;run()});document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{state.favorite=b.dataset.tab==='favorite';state.offset=0;run()});els.format.onchange=()=>{state.format=els.format.value;state.offset=0;run()};els.sort.onchange=()=>{state.sort=els.sort.value;state.offset=0;run()};els.limit.onchange=()=>{state.limit=Number(els.limit.value)===40?40:100;state.offset=0;run()};els.unknown.onclick=()=>{state.unknown=!state.unknown;state.offset=0;run()};
readUrl();paintTabs();loadMeta().then(run).catch(err=>{els.status.textContent='Không tải được Library: '+err.message});
})();</script></body></html>`;
}

export async function handlePersonalLibrary(request, env, url) {
  const db = libraryDb(env);
  if (!db) return json({ ok: false, error: "LIBRARY_DB_NOT_BOUND" }, 503);
  if (url.pathname === "/artifact-library/personal") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    return html(shell());
  }
  if (url.pathname === "/artifact-library/api/personal-meta") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    try { return json(await meta(env)); } catch (error) { return json({ ok: false, error: "PERSONAL_META_FAILED", detail: String(error?.message || error).slice(0, 240) }, 503); }
  }
  if (url.pathname === "/artifact-library/api/personal-search") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    try { return json(await search(env, url)); } catch (error) { return json({ ok: false, error: "PERSONAL_SEARCH_FAILED", detail: String(error?.message || error).slice(0, 240) }, 503); }
  }
  if (url.pathname === "/artifact-library/api/personal-favorite") return setFavorite(request, env);
  return json({ ok: false, error: "NOT_FOUND" }, 404);
}
