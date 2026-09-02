from pathlib import Path
import re

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
READER = ROOT / 'artifact-library-reader-v2-entry.js'

simple = SIMPLE.read_text(encoding='utf-8')
reader = READER.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# ---------------------------------------------------------------------------
# R2 catalog metadata and real cover-image delivery.
# ---------------------------------------------------------------------------
if 'const LIBRARY_CATALOG_INDEX_KEY' not in simple:
    simple = replace_once(
        simple,
        'const ROOT = "core/ebook/";\n',
        'const ROOT = "core/ebook/";\nconst LIBRARY_CATALOG_INDEX_KEY = ROOT + "_index/library-books.json";\n',
        'catalog constant',
    )

catalog_helpers = r'''
async function libraryCatalogIndex(env) {
  if (!env.ARTIFACTS) return {};
  try {
    const object = await env.ARTIFACTS.get(LIBRARY_CATALOG_INDEX_KEY);
    if (!object) return {};
    const data = await object.json();
    return data && typeof data === 'object' && data.books && typeof data.books === 'object' ? data.books : {};
  } catch { return {}; }
}

async function publicCover(request, env) {
  if (request.method !== 'GET') return json({ ok: false, error: 'METHOD_NOT_ALLOWED' }, 405);
  if (!env.ARTIFACTS) return json({ ok: false, error: 'R2_NOT_BOUND' }, 503);
  const url = new URL(request.url);
  const key = String(url.searchParams.get('key') || '');
  if (!key.startsWith(ROOT) || !/\/meta\/cover\.(?:jpe?g|png|webp|gif)$/i.test(key)) return json({ ok: false, error: 'INVALID_COVER_KEY' }, 400);
  const object = await env.ARTIFACTS.get(key);
  if (!object) return new Response(null, { status: 404, headers: headers() });
  const h = new Headers();
  h.set('Content-Type', object.httpMetadata?.contentType || (key.toLowerCase().endsWith('.png') ? 'image/png' : key.toLowerCase().endsWith('.webp') ? 'image/webp' : key.toLowerCase().endsWith('.gif') ? 'image/gif' : 'image/jpeg'));
  h.set('Cache-Control', 'private, max-age=86400');
  h.set('X-Robots-Tag', ROBOTS);
  h.set('Referrer-Policy', 'no-referrer');
  if (object.httpEtag) h.set('ETag', object.httpEtag);
  return new Response(object.body, { status: 200, headers: h });
}

'''
if 'async function libraryCatalogIndex(env)' not in simple:
    simple = replace_once(simple, 'async function canonicalFinalBooks(env) {', catalog_helpers + 'async function canonicalFinalBooks(env) {', 'catalog helpers')

old_return = "  return [...latest.values()].sort((a, b) => a.scope.localeCompare(b.scope));\n}"
new_return = """  const rows = [...latest.values()].sort((a, b) => a.scope.localeCompare(b.scope));
  const catalog = await libraryCatalogIndex(env);
  for (const row of rows) {
    const meta = catalog && catalog[row.scope];
    if (!meta || typeof meta !== 'object') continue;
    if (typeof meta.title === 'string' && meta.title.trim()) row.title = meta.title.trim();
    if (typeof meta.creator === 'string' && meta.creator.trim()) row.creator = meta.creator.trim();
    if (typeof meta.cover_key === 'string' && meta.cover_key.startsWith(ROOT)) row.cover_key = meta.cover_key;
  }
  return rows;
}"""
if 'const catalog = await libraryCatalogIndex(env);' not in simple:
    simple = replace_once(simple, old_return, new_return, 'catalog merge')

route_marker = '    if (p === "/artifact-library/api/list") return publicList(request, env);\n'
if 'p === "/artifact-library/api/cover"' not in simple:
    simple = replace_once(simple, route_marker, route_marker + '    if (p === "/artifact-library/api/cover") return publicCover(request, env);\n', 'cover route')

# Main Library: true R2 cover first, then locally extracted cover, then placeholder.
old_title = "  const titleFor=b=>infoFor(b).title||String(metaFor(b).title||'').trim()||cleanFilename(b&&b.key);"
new_title = "  const titleFor=b=>infoFor(b).title||String(b&&b.title||'').trim()||String(metaFor(b).title||'').trim()||cleanFilename(b&&b.key);"
if old_title in simple:
    simple = replace_once(simple, old_title, new_title, 'catalog title preference')
old_author = "  const authorFor=b=>infoFor(b).author||String(metaFor(b).creator||'').trim();"
new_author = "  const authorFor=b=>infoFor(b).author||String(b&&b.creator||'').trim()||String(metaFor(b).creator||'').trim();"
if old_author in simple:
    simple = replace_once(simple, old_author, new_author, 'catalog author preference')

# Critical v54 bug: Number(null) === 0. Preserve null as unknown/started.
old_progress = "  function progressFor(b){let row=null;try{row=JSON.parse(localStorage.getItem(PROGRESS_PREFIX+b.key)||'null')}catch{}const n=Number(row&&row.percent);const pct=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;let saved=false;try{saved=Boolean(localStorage.getItem(POSITION_PREFIX+b.key))}catch{}return {percent:pct,started:pct!==null||saved,updatedAt:Number(row&&row.updatedAt||0),done:pct!==null&&pct>=99};}"
new_progress = "  function progressFor(b){let row=null;try{row=JSON.parse(localStorage.getItem(PROGRESS_PREFIX+b.key)||'null')}catch{}const raw=row&&row.percent;const n=(raw===null||raw===undefined||raw==='')?NaN:Number(raw);const pct=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;let saved=false;try{saved=Boolean(localStorage.getItem(POSITION_PREFIX+b.key))}catch{}return {percent:pct,started:pct!==null||saved,updatedAt:Number(row&&row.updatedAt||0),done:pct!==null&&pct>=99};}"
if old_progress in simple:
    simple = replace_once(simple, old_progress, new_progress, 'null progress fix')

cover_pattern = re.compile(r"  function buildCover\(book\)\{const cover=document\.createElement\('div'\);cover\.className='cover';.*?return cover\}", re.S)
cover_replacement = """  function buildCover(book){const cover=document.createElement('div');cover.className='cover';cover.style.setProperty('--cover-h',String(hueFor(book.scope||book.key)));const meta=metaFor(book);let src='';if(book&&book.cover_key)src='/artifact-library/api/cover?key='+encodeURIComponent(book.cover_key);if(src){const img=document.createElement('img');img.src=src;img.alt='';img.loading='lazy';img.decoding='async';img.addEventListener('error',()=>{img.remove();});cover.appendChild(img)}else if(meta.coverBlob instanceof Blob&&meta.coverBlob.size){const img=document.createElement('img');const u=URL.createObjectURL(meta.coverBlob);state.coverUrls.push(u);img.src=u;img.alt='';cover.appendChild(img)}const mark=document.createElement('div');mark.className='cover-mark';mark.textContent=markFor(book);const series=document.createElement('div');series.className='cover-series';series.textContent=seriesFor(book)||'EPUB';cover.append(mark,series);return cover}"""
simple, cover_count = cover_pattern.subn(cover_replacement, simple, count=1)
if cover_count != 1 and "book&&book.cover_key" not in simple:
    raise SystemExit(f'v55 main cover patch failed: {cover_count}')

# ---------------------------------------------------------------------------
# Reader: accurate percentage from generated epub.js Locations + old CFI backfill.
# ---------------------------------------------------------------------------
progress_helpers = r'''
  let r3LocationsReadyV55=false;
  let r3LocationsPromiseV55=null;
  function r3WriteProgressV55(percent,cfi){
    const n=Number(percent);const value=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;
    try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+key,JSON.stringify({percent:value,cfi:cfi||'',updatedAt:Date.now()}));}catch{}
    return value;
  }
  function r3PercentFromCfiV55(cfi,loc){
    if(r3LocationsReadyV55&&cfi&&book&&book.locations){
      try{const p=book.locations.percentageFromCfi(cfi);if(Number.isFinite(p))return Math.max(0,Math.min(100,Math.round(p*100)));}catch{}
    }
    if(Number.isFinite(loc?.start?.percentage))return Math.max(0,Math.min(100,Math.round(loc.start.percentage*100)));
    return null;
  }
  async function r3EnsureLocationsV55(){
    if(r3LocationsReadyV55)return true;
    if(r3LocationsPromiseV55)return r3LocationsPromiseV55;
    r3LocationsPromiseV55=(async()=>{
      try{
        if(!book||!book.locations)return false;
        await book.ready;
        await book.locations.generate(1600);
        r3LocationsReadyV55=true;
        const current=(rendition&&rendition.currentLocation&&rendition.currentLocation())||null;
        const saved=(current?.start?.cfi)||localStorage.getItem(keys.position)||'';
        if(saved){const pct=r3PercentFromCfiV55(saved,current);r3WriteProgressV55(pct,saved);if(pct!==null)$('position').textContent=pct+'% · đã lưu';}
        return true;
      }catch{return false;}
    })().finally(()=>{if(!r3LocationsReadyV55)r3LocationsPromiseV55=null;});
    return r3LocationsPromiseV55;
  }
'''
if 'async function r3EnsureLocationsV55()' not in reader:
    marker = "  const R3_BOOK_INFO_V54={"
    idx = reader.find(marker)
    if idx < 0: raise SystemExit('v55 metadata helper anchor missing')
    reader = reader[:idx] + progress_helpers + '\n' + reader[idx:]

old_reader_progress = "rendition.on('relocated',loc=>{const cfi=loc?.start?.cfi;if(cfi)persist(keys.position,cfi);const pct=Number.isFinite(loc?.start?.percentage)?Math.max(0,Math.min(100,Math.round(loc.start.percentage*100))):null;try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+key,JSON.stringify({percent:pct,cfi:cfi||'',updatedAt:Date.now()}));}catch{}$('position').textContent=pct===null?'Đã lưu vị trí':pct+'% · đã lưu';setTimeout(bindEpubContents,0);});"
new_reader_progress = "rendition.on('relocated',loc=>{const cfi=loc?.start?.cfi;if(cfi)persist(keys.position,cfi);const pct=r3PercentFromCfiV55(cfi,loc);r3WriteProgressV55(pct,cfi||'');$('position').textContent=pct===null?'Đã lưu vị trí':pct+'% · đã lưu';if(!r3LocationsReadyV55)setTimeout(()=>r3EnsureLocationsV55(),250);setTimeout(bindEpubContents,0);});"
if old_reader_progress in reader:
    reader = replace_once(reader, old_reader_progress, new_reader_progress, 'accurate relocated progress')

# Start generation after the book exists, but never block initial Reader reveal.
meta_call = '      setTimeout(()=>r3PersistBookMetaV54(book,key),0);'
if 'setTimeout(()=>r3EnsureLocationsV55(),900);' not in reader:
    reader = replace_once(reader, meta_call, meta_call + '\n      setTimeout(()=>r3EnsureLocationsV55(),900);', 'background location generation')

# Live Library uses same null-safe progress and true R2 cover URL.
old_live_progress = "function r3ProgressForBookV54(book){let row=null;try{row=JSON.parse(localStorage.getItem(R3_READER_PROGRESS_PREFIX_V54+book.key)||'null')}catch{}const n=Number(row&&row.percent);const percent=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;let saved=false;try{saved=Boolean(localStorage.getItem('r3-reader-position:'+book.key))}catch{}return {percent,started:percent!==null||saved,updatedAt:Number(row&&row.updatedAt||0),done:percent!==null&&percent>=99};}"
new_live_progress = "function r3ProgressForBookV54(book){let row=null;try{row=JSON.parse(localStorage.getItem(R3_READER_PROGRESS_PREFIX_V54+book.key)||'null')}catch{}const raw=row&&row.percent;const n=(raw===null||raw===undefined||raw==='')?NaN:Number(raw);const percent=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;let saved=false;try{saved=Boolean(localStorage.getItem('r3-reader-position:'+book.key))}catch{}return {percent,started:percent!==null||saved,updatedAt:Number(row&&row.updatedAt||0),done:percent!==null&&percent>=99};}"
if old_live_progress in reader:
    reader = replace_once(reader, old_live_progress, new_live_progress, 'live null progress fix')

# Catalog fields are returned by /api/list; prefer actual cover_key in live panel too.
old_live_title = "function r3TitleForBookV54(book){const info=r3InfoV54(book),meta=r3LibraryMetaCacheV54.get(String(book&&book.key||''))||{};return info.title||String(meta.title||'').trim()||r3CleanFilenameV54(book&&book.key);}"
new_live_title = "function r3TitleForBookV54(book){const info=r3InfoV54(book),meta=r3LibraryMetaCacheV54.get(String(book&&book.key||''))||{};return info.title||String(book&&book.title||'').trim()||String(meta.title||'').trim()||r3CleanFilenameV54(book&&book.key);}"
if old_live_title in reader:
    reader = replace_once(reader, old_live_title, new_live_title, 'live catalog title')
old_live_sub = "function r3SubtitleForBookV54(book){const info=r3InfoV54(book),meta=r3LibraryMetaCacheV54.get(String(book&&book.key||''))||{};const parts=[];const author=info.author||String(meta.creator||'').trim();if(author)parts.push(author);if(info.series)parts.push(info.series);return parts.join(' · ');}"
new_live_sub = "function r3SubtitleForBookV54(book){const info=r3InfoV54(book),meta=r3LibraryMetaCacheV54.get(String(book&&book.key||''))||{};const parts=[];const author=info.author||String(book&&book.creator||'').trim()||String(meta.creator||'').trim();if(author)parts.push(author);if(info.series)parts.push(info.series);return parts.join(' · ');}"
if old_live_sub in reader:
    reader = replace_once(reader, old_live_sub, new_live_sub, 'live catalog author')

# v54 live cover renderer has local coverBlob + placeholder. Inject R2 cover_key first.
live_cover_old = "const meta=r3LibraryMetaCacheV54.get(String(row&&row.key||''))||{};if(meta.coverBlob instanceof Blob&&meta.coverBlob.size){const img=document.createElement('img');const u=URL.createObjectURL(meta.coverBlob);r3LiveCoverUrlsV54.push(u);img.src=u;img.alt='';cover.appendChild(img)}"
live_cover_new = "const meta=r3LibraryMetaCacheV54.get(String(row&&row.key||''))||{};if(row&&row.cover_key){const img=document.createElement('img');img.src='/artifact-library/api/cover?key='+encodeURIComponent(row.cover_key);img.alt='';img.loading='lazy';img.decoding='async';img.addEventListener('error',()=>img.remove());cover.appendChild(img)}else if(meta.coverBlob instanceof Blob&&meta.coverBlob.size){const img=document.createElement('img');const u=URL.createObjectURL(meta.coverBlob);r3LiveCoverUrlsV54.push(u);img.src=u;img.alt='';cover.appendChild(img)}"
if live_cover_old in reader:
    reader = replace_once(reader, live_cover_old, live_cover_new, 'live real cover')

for marker in [
    'LIBRARY_CATALOG_INDEX_KEY', 'async function libraryCatalogIndex(env)',
    'async function publicCover(request, env)', 'p === "/artifact-library/api/cover"',
    'book&&book.cover_key', "raw===null||raw===undefined||raw===''",
]:
    if marker not in simple:
        raise SystemExit('V55_SIMPLE_MISSING:' + marker)
for marker in [
    'async function r3EnsureLocationsV55()', 'book.locations.generate(1600)',
    'percentageFromCfi(cfi)', 'r3WriteProgressV55(pct',
    'setTimeout(()=>r3EnsureLocationsV55(),900)',
]:
    if marker not in reader:
        raise SystemExit('V55_READER_MISSING:' + marker)

SIMPLE.write_text(simple, encoding='utf-8')
READER.write_text(reader, encoding='utf-8')
print('READER_V55_PROGRESS_REAL_COVERS=PASS')
