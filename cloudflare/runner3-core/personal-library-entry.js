const TABLE = "library_file_index_v1";
const MAX_LIMIT = 100;

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
  return new Response(JSON.stringify(data), {
    status,
    headers: headers("application/json; charset=utf-8"),
  });
}

function html(body, status = 200) {
  const h = headers("text/html; charset=utf-8");
  h.set(
    "Content-Security-Policy",
    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
  );
  return new Response(body, { status, headers: h });
}

function libraryDb(env) {
  return env.LIBRARY_DB || null;
}

function safeLimit(url) {
  return Math.max(1, Math.min(MAX_LIMIT, Number(url.searchParams.get("limit") || 100) || 100));
}

function safeOffset(url) {
  return Math.max(0, Math.min(100000, Number(url.searchParams.get("offset") || 0) || 0));
}

function validCategory(value) {
  return ["ebook", "comic"].includes(value) ? value : "";
}

function validFormat(value) {
  const v = String(value || "").toLowerCase();
  return /^[a-z0-9]{1,12}$/.test(v) ? v : "";
}

async function meta(env) {
  const db = libraryDb(env);
  const total = await db.prepare(`SELECT COUNT(*) AS n FROM ${TABLE}`).first();
  const groups = await db.prepare(
    `SELECT category, COUNT(*) AS n FROM ${TABLE} GROUP BY category ORDER BY category`,
  ).all();
  const formats = await db.prepare(
    `SELECT format, COUNT(*) AS n FROM ${TABLE} GROUP BY format ORDER BY n DESC, format LIMIT 30`,
  ).all();
  const unknown = await db.prepare(
    `SELECT COUNT(*) AS n FROM ${TABLE} WHERE category='ebook' AND (creator IS NULL OR TRIM(creator)='')`,
  ).first();
  return {
    ok: true,
    count: Number(total?.n || 0),
    categories: groups.results || [],
    formats: formats.results || [],
    ebook_unknown_creator: Number(unknown?.n || 0),
    authority: "personal-library",
  };
}

async function search(env, url) {
  const db = libraryDb(env);
  const rawQ = String(url.searchParams.get("q") || "").trim();
  const q = normalize(rawQ);
  const category = validCategory(url.searchParams.get("category"));
  const format = validFormat(url.searchParams.get("format"));
  const unknownCreator = url.searchParams.get("unknown_creator") === "1";
  const sort = ["title", "creator", "series"].includes(url.searchParams.get("sort"))
    ? url.searchParams.get("sort")
    : "title";
  const limit = safeLimit(url);
  const offset = safeOffset(url);

  const where = [];
  const params = [];
  if (q) {
    for (const term of q.split(/\s+/).filter(Boolean).slice(0, 12)) {
      where.push("search_text LIKE ?");
      params.push(`%${term}%`);
    }
  }
  if (category) {
    where.push("category = ?");
    params.push(category);
  }
  if (format) {
    where.push("LOWER(format) = ?");
    params.push(format);
  }
  if (unknownCreator) {
    where.push("category = 'ebook'");
    where.push("(creator IS NULL OR TRIM(creator) = '')");
  }
  const filter = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const order = sort === "creator"
    ? "CASE WHEN creator IS NULL OR TRIM(creator)='' THEN 1 ELSE 0 END, creator COLLATE NOCASE, title COLLATE NOCASE, volume, library_id"
    : sort === "series"
      ? "CASE WHEN series IS NULL OR TRIM(series)='' THEN 1 ELSE 0 END, series COLLATE NOCASE, volume, title COLLATE NOCASE, library_id"
      : "title COLLATE NOCASE, volume, library_id";

  const countRow = await db.prepare(`SELECT COUNT(*) AS n FROM ${TABLE} ${filter}`).bind(...params).first();
  const rows = await db.prepare(
    `SELECT library_id,category,title,creator,series,volume,format,file_name,size,telegram_link,tags FROM ${TABLE} ${filter} ORDER BY ${order} LIMIT ? OFFSET ?`,
  ).bind(...params, limit, offset).all();

  return {
    ok: true,
    query: rawQ,
    normalized_query: q,
    total: Number(countRow?.n || 0),
    items: rows.results || [],
    limit,
    offset,
    category: category || null,
    format: format || null,
    unknown_creator: unknownCreator,
    sort,
  };
}

function shell() {
  return `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">
<title>Personal Library</title>
<style>
:root{color-scheme:dark;--bg:#0a0b0d;--card:#111419;--line:#252b33;--muted:#98a3b3;--text:#f5f7fa;--accent:#f2f5f8;--chip:#171b21;--good:#9bd7aa;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0%,#17202b 0,transparent 28%),var(--bg);color:var(--text);min-height:100vh}.wrap{width:min(980px,100%);margin:0 auto;padding:20px 16px 80px}.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}.back{color:#cbd3de;text-decoration:none;font-size:14px}.eyebrow{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#8f9bac;font-weight:800}h1{font-size:27px;margin:5px 0 0}.count{font-size:13px;color:var(--muted)}.panel{background:rgba(17,20,25,.92);border:1px solid var(--line);border-radius:18px;padding:14px;position:sticky;top:8px;z-index:10;backdrop-filter:blur(14px)}.search{display:flex;gap:9px}.search input{flex:1;background:#0b0e12;border:1px solid #303844;color:#fff;border-radius:13px;padding:13px 14px;font-size:16px;outline:none}.search input:focus{border-color:#708098}.search button{border:0;border-radius:13px;padding:0 16px;background:var(--accent);color:#090b0e;font-weight:800}.filters{display:flex;gap:8px;overflow-x:auto;padding-top:10px;scrollbar-width:none}.chip,select{white-space:nowrap;background:var(--chip);border:1px solid #2a313a;color:#cdd5df;border-radius:999px;padding:8px 11px;font-size:13px}.chip{cursor:pointer}.chip.active{background:#edf1f5;color:#11151a;border-color:#edf1f5;font-weight:800}select{outline:none}.status{font-size:13px;color:var(--muted);margin:16px 2px 10px}.grid{display:grid;gap:10px}.item{display:grid;grid-template-columns:1fr auto;gap:12px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px}.title{font-size:16px;font-weight:800;line-height:1.35}.meta{display:flex;flex-wrap:wrap;gap:6px 12px;margin-top:6px;color:#aab4c1;font-size:13px;line-height:1.45}.creator{color:#d8dee7}.unknown{color:#c99595}.open{align-self:center;text-decoration:none;border:1px solid #34404d;border-radius:11px;padding:9px 11px;color:#eef3f8;font-size:13px;font-weight:700}.open:hover{background:#1b222a}.pager{display:flex;justify-content:center;gap:8px;margin:18px 0}.pager button{background:#171b21;color:#dde4ec;border:1px solid #303844;border-radius:10px;padding:9px 13px}.pager button:disabled{opacity:.35}.empty{padding:34px 14px;text-align:center;color:#8792a1;border:1px dashed #2b323c;border-radius:16px}.tag{color:#8793a3}.badge{font-size:11px;border:1px solid #34404d;border-radius:999px;padding:3px 7px;color:#b7c0cc}.badge.comic{color:#f1c2d2}.badge.ebook{color:#b8d6f0}@media(max-width:620px){.item{grid-template-columns:1fr}.open{justify-self:start}.panel{top:4px}.wrap{padding-left:12px;padding-right:12px}}
</style>
</head>
<body><main class="wrap">
<div class="top"><div><a class="back" href="/artifact-library">← Library</a><div class="eyebrow">Runner3 · D1</div><h1>Personal Library</h1></div><div class="count" id="total-count">…</div></div>
<section class="panel">
<form class="search" id="search-form"><input id="q" name="q" autocomplete="off" placeholder="Tên sách, tác giả, bộ, tập…"><button>Tìm</button></form>
<div class="filters">
<button class="chip active" data-cat="">Tất cả</button><button class="chip" data-cat="ebook">📚 Ebook</button><button class="chip" data-cat="comic">🗯 Truyện tranh</button>
<select id="format"><option value="">Mọi định dạng</option></select>
<select id="sort"><option value="title">Tên A–Z</option><option value="creator">Tác giả A–Z</option><option value="series">Series / tập</option></select>
<select id="limit"><option value="100">100 mục / trang</option><option value="40">40 mục / trang</option></select>
<button class="chip" id="unknown">❓ Chưa rõ tác giả</button>
</div>
</section>
<div class="status" id="status">Đang tải…</div><section class="grid" id="results"></section><div class="pager" id="pager"></div>
</main>
<script>
(()=>{
const els={q:document.getElementById('q'),form:document.getElementById('search-form'),format:document.getElementById('format'),sort:document.getElementById('sort'),limit:document.getElementById('limit'),unknown:document.getElementById('unknown'),status:document.getElementById('status'),results:document.getElementById('results'),pager:document.getElementById('pager'),total:document.getElementById('total-count')};
const state={q:'',category:'',format:'',sort:'title',unknown:false,offset:0,limit:100,total:0};
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const size=n=>{const x=Number(n||0);if(!x)return '';if(x>=1073741824)return (x/1073741824).toFixed(1)+' GB';if(x>=1048576)return (x/1048576).toFixed(1)+' MB';return Math.round(x/1024)+' KB'};
function syncUrl(){const u=new URL(location.href);for(const k of ['q','category','format','sort'])state[k]?u.searchParams.set(k,state[k]):u.searchParams.delete(k);state.limit!==100?u.searchParams.set('limit',state.limit):u.searchParams.delete('limit');state.unknown?u.searchParams.set('unknown','1'):u.searchParams.delete('unknown');state.offset?u.searchParams.set('offset',state.offset):u.searchParams.delete('offset');history.replaceState(null,'',u)}
function readUrl(){const u=new URL(location.href);state.q=u.searchParams.get('q')||'';state.category=u.searchParams.get('category')||'';state.format=u.searchParams.get('format')||'';state.sort=u.searchParams.get('sort')||'title';state.limit=Number(u.searchParams.get('limit'))===40?40:100;state.unknown=u.searchParams.get('unknown')==='1';state.offset=Math.max(0,Number(u.searchParams.get('offset')||0)||0);els.q.value=state.q;els.sort.value=state.sort;els.limit.value=String(state.limit);}
function paintChips(){document.querySelectorAll('[data-cat]').forEach(b=>b.classList.toggle('active',b.dataset.cat===state.category));els.unknown.classList.toggle('active',state.unknown)}
async function loadMeta(){const r=await fetch('/artifact-library/api/personal-meta',{headers:{Accept:'application/json'}});if(r.status===401){location.href='/artifact-library';return}const d=await r.json();if(!d.ok)return;els.total.textContent=(d.count||0).toLocaleString('vi-VN')+' mục';const current=state.format;for(const f of d.formats||[]){if(!f.format)continue;const o=document.createElement('option');o.value=String(f.format).toLowerCase();o.textContent=String(f.format).toUpperCase()+' · '+Number(f.n||0).toLocaleString('vi-VN');els.format.appendChild(o)}els.format.value=current;}
function card(x){
  const creator=x.creator?'<span class="creator">✍️ '+e(x.creator)+'</span>':'<span class="unknown">❓ Chưa rõ tác giả</span>';
  const series=x.series?'<span>📚 '+e(x.series)+(x.volume!=null?' · Tập '+String(x.volume).padStart(2,'0'):'')+'</span>':(x.volume!=null?'<span>🔢 Tập '+e(x.volume)+'</span>':'');
  const fmt=[x.format?String(x.format).toUpperCase():'',size(x.size)].filter(Boolean).join(' · ');
  const badge='<span class="badge '+e(x.category)+'">'+(x.category==='comic'?'COMIC':'EBOOK')+'</span>';
  const open=x.telegram_link?'<a class="open" href="'+e(x.telegram_link)+'" target="_blank" rel="noreferrer">Mở Telegram ↗</a>':'';
  const fmtHtml=fmt?'<span>📄 '+e(fmt)+'</span>':'';
  return '<article class="item"><div><div>'+badge+'</div><div class="title">'+e(x.title||x.file_name||x.library_id)+'</div><div class="meta">'+creator+series+fmtHtml+'</div></div>'+open+'</article>';
}
function renderPager(){els.pager.innerHTML='';if(state.total<=state.limit)return;const prev=document.createElement('button');prev.textContent='← Trước';prev.disabled=state.offset===0;prev.onclick=()=>{state.offset=Math.max(0,state.offset-state.limit);run()};const page=document.createElement('button');page.disabled=true;page.textContent=(Math.floor(state.offset/state.limit)+1)+' / '+Math.ceil(state.total/state.limit);const next=document.createElement('button');next.textContent='Sau →';next.disabled=state.offset+state.limit>=state.total;next.onclick=()=>{state.offset+=state.limit;run()};els.pager.append(prev,page,next)}
let seq=0;async function run(){const mine=++seq;syncUrl();paintChips();els.status.textContent='Đang tìm…';const p=new URLSearchParams({limit:state.limit,offset:state.offset,sort:state.sort});if(state.q)p.set('q',state.q);if(state.category)p.set('category',state.category);if(state.format)p.set('format',state.format);if(state.unknown)p.set('unknown_creator','1');const r=await fetch('/artifact-library/api/personal-search?'+p,{headers:{Accept:'application/json'}});if(mine!==seq)return;if(r.status===401){location.href='/artifact-library';return}const d=await r.json();if(!d.ok){els.status.textContent='Lỗi: '+(d.error||r.status);return}state.total=Number(d.total||0);const shown=Array.isArray(d.items)?d.items.length:0;const from=state.total?state.offset+1:0;const to=Math.min(state.offset+shown,state.total);els.status.textContent='Đang hiển thị '+from.toLocaleString('vi-VN')+'–'+to.toLocaleString('vi-VN')+' / '+state.total.toLocaleString('vi-VN')+' kết quả'+(state.q?' cho “'+state.q+'”':'');els.results.innerHTML=shown?d.items.map(card).join(''):'<div class="empty">Không có kết quả phù hợp.</div>';renderPager();}
let t;els.q.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(()=>{state.q=els.q.value.trim();state.offset=0;run()},260)});els.form.addEventListener('submit',ev=>{ev.preventDefault();state.q=els.q.value.trim();state.offset=0;run()});document.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>{state.category=b.dataset.cat;state.unknown=false;state.offset=0;run()});els.format.onchange=()=>{state.format=els.format.value;state.offset=0;run()};els.sort.onchange=()=>{state.sort=els.sort.value;state.offset=0;run()};els.limit.onchange=()=>{state.limit=Number(els.limit.value)===40?40:100;state.offset=0;run()};els.unknown.onclick=()=>{state.unknown=!state.unknown;if(state.unknown)state.category='ebook';state.offset=0;run()};
readUrl();paintChips();loadMeta().then(run).catch(err=>{els.status.textContent='Không tải được Library: '+err.message});
})();
</script></body></html>`;
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
    return json(await meta(env));
  }
  if (url.pathname === "/artifact-library/api/personal-search") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    return json(await search(env, url));
  }
  return json({ ok: false, error: "NOT_FOUND" }, 404);
}
