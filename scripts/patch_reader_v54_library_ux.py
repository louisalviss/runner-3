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


LIBRARY_PAGE = r'''function libraryPage() {
  return `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">
<title>Library</title>
<style>
:root{color-scheme:dark;background:#080a0d;color:#f2f5f8;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}body{margin:0;background:#080a0d;color:#f2f5f8}.shell{max-width:860px;margin:0 auto;padding:max(12px,env(safe-area-inset-top)) 12px max(28px,env(safe-area-inset-bottom))}.tools{display:grid;grid-template-columns:minmax(0,1fr) 44px 44px;gap:8px;margin:0 0 10px}.search{min-width:0;border:1px solid #29313a;background:#0e1217;color:#f5f7fa;border-radius:13px;padding:11px 13px;font-size:16px;outline:none;height:44px}.search:focus{border-color:#596979}.icon{appearance:none;border:1px solid #29313a;background:#12171d;color:#e8edf3;border-radius:12px;width:44px;height:44px;display:grid;place-items:center;padding:0;cursor:pointer}.icon svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.icon:disabled{opacity:.45}.action-row{display:flex;align-items:center;gap:7px;margin:0 0 12px;overflow-x:auto;scrollbar-width:none}.action-row::-webkit-scrollbar{display:none}.filter{appearance:none;border:1px solid #27313b;background:#0e1319;color:#9da9b6;border-radius:999px;height:36px;padding:0 12px;font:inherit;font-size:12px;font-weight:750;white-space:nowrap}.filter.active{background:#e9eef4;color:#0a0d10;border-color:#e9eef4}.upload-epub{margin-left:auto;appearance:none;border:1px solid #33404d;background:#151b22;color:#edf2f7;border-radius:11px;height:36px;padding:0 12px;font:inherit;font-size:12px;font-weight:800;white-space:nowrap;cursor:pointer}.upload-epub:disabled{opacity:.5}.status{display:none;color:#8793a0;font-size:12px;padding:2px 2px 10px;line-height:1.35}.status.show{display:block}.list{display:grid;gap:7px}.book{border:1px solid #202832;background:#0d1217;border-radius:15px;display:grid;grid-template-columns:minmax(0,1fr) 42px;align-items:stretch;overflow:hidden;min-height:88px}.read{min-width:0;color:#f3f6fa;text-decoration:none;padding:9px 9px 9px 10px;display:grid;grid-template-columns:50px minmax(0,1fr);gap:11px;align-items:center}.cover{position:relative;width:50px;height:70px;border-radius:8px;overflow:hidden;border:1px solid rgba(255,255,255,.12);background:linear-gradient(145deg,hsl(var(--cover-h) 46% 34%),hsl(calc(var(--cover-h) + 26) 58% 17%));box-shadow:0 6px 16px rgba(0,0,0,.25);display:flex;flex-direction:column;justify-content:flex-end;padding:6px}.cover img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.cover::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.58),transparent 58%);pointer-events:none}.cover-mark,.cover-series{position:relative;z-index:2}.cover-mark{font-size:15px;line-height:1;font-weight:900;letter-spacing:-.04em;color:#fff;text-shadow:0 1px 5px rgba(0,0,0,.45)}.cover-series{margin-top:3px;font-size:7px;line-height:1.1;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:rgba(255,255,255,.78);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.content{min-width:0;align-self:center}.title{font-size:15px;line-height:1.22;font-weight:760;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}.sub{font-size:11px;color:#8491a0;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.progress-line{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;margin-top:8px}.progress{height:5px;border-radius:999px;background:#222b35;overflow:hidden}.progress>span{display:block;height:100%;border-radius:inherit;background:#d7b462}.progress-text{font-size:10px;color:#98a4b1;font-variant-numeric:tabular-nums;white-space:nowrap}.download{appearance:none;border:0;border-left:1px solid #202832;background:#111820;color:#aeb9c6;width:42px;display:grid;place-items:center;padding:0;cursor:pointer}.download svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.download:disabled{opacity:.45}.empty{color:#7f8b98;text-align:center;padding:42px 12px;font-size:14px}@media(min-width:720px){.shell{padding-left:18px;padding-right:18px}.book:hover{border-color:#36424f}.read{padding:10px 11px}.title{font-size:16px}}
</style>
</head>
<body><main class="shell">
<form id="searchForm" class="tools" role="search"><input id="search" class="search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books"><button class="icon" type="submit" aria-label="Search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.6-3.6"></path></svg></button><button id="refresh" class="icon" type="button" aria-label="Refresh R2"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v5h-5"></path><path d="M19 11a8 8 0 1 0 1 5"></path></svg></button></form>
<div class="action-row"><button class="filter active" data-filter="all" type="button">Tất cả</button><button class="filter" data-filter="reading" type="button">Đang đọc</button><button class="filter" data-filter="unread" type="button">Chưa đọc</button><button class="filter" data-filter="done" type="button">Đã đọc</button><button id="uploadEpub" class="upload-epub" type="button">＋ EPUB</button><input id="uploadEpubInput" type="file" accept=".epub,application/epub+zip" hidden></div>
<div id="status" class="status" aria-live="polite"></div><section id="list" class="list"></section></main>
<script>
(() => {
  const BOOK_INFO={
    'blindsight':{title:"Blindsight",author:"Peter Watts",mark:"B"},
    'broken-money':{title:"Broken Money",author:"Lyn Alden",mark:"BM"},
    'chiec-hop-pandora':{title:"Chiếc Hộp Pandora",mark:"CHP"},
    'consider-phlebas':{title:"Consider Phlebas",author:"Iain M. Banks",mark:"CP"},
    'skeleton-crew':{title:"Skeleton Crew",author:"Stephen King",mark:"SC"},
    'dcc-01':{title:"Dungeon Crawler Carl",author:"Matt Dinniman",series:"DCC · Book 1",mark:"DCC 1"},
    'dcc-02':{title:"Carl's Doomsday Scenario",author:"Matt Dinniman",series:"DCC · Book 2",mark:"DCC 2"},
    'dcc-03':{title:"The Dungeon Anarchist's Cookbook",author:"Matt Dinniman",series:"DCC · Book 3",mark:"DCC 3"},
    'dcc-04':{title:"The Gate of the Feral Gods",author:"Matt Dinniman",series:"DCC · Book 4",mark:"DCC 4"},
    'dcc-05':{title:"The Butcher's Masquerade",author:"Matt Dinniman",series:"DCC · Book 5",mark:"DCC 5"},
    'dcc-06':{title:"The Eye of the Bedlam Bride",author:"Matt Dinniman",series:"DCC · Book 6",mark:"DCC 6"},
    'dcc-07':{title:"This Inevitable Ruin",author:"Matt Dinniman",series:"DCC · Book 7",mark:"DCC 7"},
    'dcc-08':{title:"A Parade of Horribles",author:"Matt Dinniman",series:"DCC · Book 8",mark:"DCC 8"}
  };
  const META_DB='r3-library-book-meta-v54',META_STORE='books',PROGRESS_PREFIX='r3-reader-progress-v1:',POSITION_PREFIX='r3-reader-position:';
  const state={books:[],query:'',filter:'all',meta:new Map(),coverUrls:[]};
  const $=id=>document.getElementById(id);
  const basename=key=>{const raw=String(key||'').split('/').filter(Boolean).pop()||'';try{return decodeURIComponent(raw)}catch{return raw}};
  const cleanFilename=key=>{let s=basename(key).replace(/\.epub$/i,'');s=s.replace(/\s*\([^)]{2,100}\)\s*\d*\s*$/,'');s=s.replace(/(?:[-_\s]+VI)?[-_\s]*v\d+\s*$/i,'');s=s.replace(/[_-]+/g,' ').replace(/\s+/g,' ').trim();return s||'Book'};
  const initials=title=>{const words=String(title||'').split(/\s+/).filter(Boolean).filter(x=>!['the','a','an','of','and'].includes(x.toLowerCase()));return (words.slice(0,2).map(x=>x[0]).join('')||'BK').toUpperCase()};
  const hueFor=value=>{let h=2166136261;for(const ch of String(value||'')){h^=ch.charCodeAt(0);h=Math.imul(h,16777619)>>>0}return h%360};
  const infoFor=b=>BOOK_INFO[b&&b.scope]||{};
  const metaFor=b=>state.meta.get(String(b&&b.key||''))||{};
  const titleFor=b=>infoFor(b).title||String(metaFor(b).title||'').trim()||cleanFilename(b&&b.key);
  const authorFor=b=>infoFor(b).author||String(metaFor(b).creator||'').trim();
  const seriesFor=b=>infoFor(b).series||'';
  const markFor=b=>infoFor(b).mark||initials(titleFor(b));
  function status(message){const node=$('status');node.textContent=message||'';node.classList.toggle('show',Boolean(message));}
  function progressFor(b){let row=null;try{row=JSON.parse(localStorage.getItem(PROGRESS_PREFIX+b.key)||'null')}catch{}const n=Number(row&&row.percent);const pct=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;let saved=false;try{saved=Boolean(localStorage.getItem(POSITION_PREFIX+b.key))}catch{}return {percent:pct,started:pct!==null||saved,updatedAt:Number(row&&row.updatedAt||0),done:pct!==null&&pct>=99};}
  function progressLabel(p){if(p.done)return '100% · Đã đọc';if(p.percent!==null)return p.percent+'% · '+(p.percent>0?'Tiếp tục':'Chưa đọc');if(p.started)return 'Đang đọc';return '0% · Chưa đọc';}
  function subtitleFor(b){const parts=[];const author=authorFor(b),series=seriesFor(b);if(author)parts.push(author);if(series)parts.push(series);return parts.join(' · ');}
  function filtered(){const q=state.query.trim().toLocaleLowerCase('vi');let items=state.books.filter(b=>!q||titleFor(b).toLocaleLowerCase('vi').includes(q)||authorFor(b).toLocaleLowerCase('vi').includes(q)||String(b.key||'').toLocaleLowerCase('vi').includes(q));items=items.filter(b=>{const p=progressFor(b);if(state.filter==='reading')return p.started&&!p.done;if(state.filter==='unread')return !p.started;if(state.filter==='done')return p.done;return true});return items.sort((a,b)=>{const pa=progressFor(a),pb=progressFor(b);const ra=pa.started&&!pa.done?0:pa.done?2:1,rb=pb.started&&!pb.done?0:pb.done?2:1;if(ra!==rb)return ra-rb;if(ra===0&&pa.updatedAt!==pb.updatedAt)return pb.updatedAt-pa.updatedAt;return titleFor(a).localeCompare(titleFor(b),'vi')})}
  function clearCoverUrls(){for(const u of state.coverUrls)try{URL.revokeObjectURL(u)}catch{}state.coverUrls=[]}
  function buildCover(book){const cover=document.createElement('div');cover.className='cover';cover.style.setProperty('--cover-h',String(hueFor(book.scope||book.key)));const meta=metaFor(book);if(meta.coverBlob instanceof Blob&&meta.coverBlob.size){const img=document.createElement('img');const u=URL.createObjectURL(meta.coverBlob);state.coverUrls.push(u);img.src=u;img.alt='';cover.appendChild(img)}const mark=document.createElement('div');mark.className='cover-mark';mark.textContent=markFor(book);const series=document.createElement('div');series.className='cover-series';series.textContent=seriesFor(book)||'EPUB';cover.append(mark,series);return cover}
  function render(){clearCoverUrls();const root=$('list');root.textContent='';const items=filtered();if(!items.length){const e=document.createElement('div');e.className='empty';e.textContent=state.query?'Không tìm thấy sách.':'Không có sách trong mục này.';root.appendChild(e);return}for(const book of items){const p=progressFor(book);const row=document.createElement('article');row.className='book';const read=document.createElement('a');read.className='read';read.href='/artifact-library/read?key='+encodeURIComponent(book.key);read.appendChild(buildCover(book));const content=document.createElement('div');content.className='content';const title=document.createElement('div');title.className='title';title.textContent=titleFor(book);const sub=document.createElement('div');sub.className='sub';sub.textContent=subtitleFor(book)||cleanFilename(book.key);const progressLine=document.createElement('div');progressLine.className='progress-line';const track=document.createElement('div');track.className='progress';const fill=document.createElement('span');fill.style.width=(p.percent===null?0:p.percent)+'%';track.appendChild(fill);const progressText=document.createElement('span');progressText.className='progress-text';progressText.textContent=progressLabel(p);progressLine.append(track,progressText);content.append(title,sub,progressLine);read.appendChild(content);const download=document.createElement('button');download.className='download';download.type='button';download.setAttribute('aria-label','Download '+titleFor(book));download.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"></path><path d="m7 10 5 5 5-5"></path><path d="M5 21h14"></path></svg>';download.addEventListener('click',()=>downloadBook(book.key,download));row.append(read,download);root.appendChild(row)}}
  let metaDbPromise=null;
  function openMetaDb(){if(metaDbPromise)return metaDbPromise;metaDbPromise=new Promise((resolve,reject)=>{if(!('indexedDB' in window)){reject(new Error('INDEXEDDB_UNAVAILABLE'));return}const req=indexedDB.open(META_DB,1);req.onupgradeneeded=()=>{const db=req.result;if(!db.objectStoreNames.contains(META_STORE))db.createObjectStore(META_STORE,{keyPath:'key'})};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error('INDEXEDDB_OPEN_FAILED'))}).catch(()=>null);return metaDbPromise}
  async function hydrateMeta(){try{const db=await openMetaDb();if(!db)return;const rows=await new Promise((resolve,reject)=>{const tx=db.transaction(META_STORE,'readonly');const req=tx.objectStore(META_STORE).getAll();req.onsuccess=()=>resolve(Array.isArray(req.result)?req.result:[]);req.onerror=()=>reject(req.error)});for(const row of rows)if(row&&row.key)state.meta.set(row.key,row);render()}catch{}}
  async function load(){const refresh=$('refresh');refresh.disabled=true;status('Loading…');try{const r=await fetch('/artifact-library/api/list',{cache:'no-store'});const data=await r.json();if(!r.ok||data.ok!==true)throw new Error(data.error||('HTTP '+r.status));state.books=Array.isArray(data.objects)?data.objects:[];status('');render();hydrateMeta()}catch(e){status('Không tải được Library: '+String(e&&e.message||e));state.books=[];render()}finally{refresh.disabled=false}}
  async function downloadBook(key,button){button.disabled=true;try{const r=await fetch('/artifact-library/api/delivery',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key,ttl_seconds:900})});const data=await r.json();if(!r.ok||data.ok!==true||!data.delivery||!data.delivery.url)throw new Error(data.error||('HTTP '+r.status));location.href=data.delivery.url}catch(e){status('Download failed: '+String(e&&e.message||e))}finally{button.disabled=false}}
  function uploadEpub(file){if(!file)return;if(!/\.epub$/i.test(file.name||'')){status('Chỉ nhận file .epub');return}if(Number(file.size||0)>90*1024*1024){status('EPUB vượt giới hạn 90 MiB.');return}const button=$('uploadEpub');button.disabled=true;button.textContent='Uploading…';status('Uploading '+file.name+'…');const xhr=new XMLHttpRequest();xhr.open('POST','/artifact-library/api/upload',true);xhr.setRequestHeader('x-runner3-library','1');xhr.setRequestHeader('x-r3-filename',encodeURIComponent(file.name));xhr.setRequestHeader('content-type','application/epub+zip');xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.max(0,Math.min(100,Math.round(e.loaded/e.total*100)));status('Uploading '+file.name+' · '+pct+'%')}};xhr.onerror=()=>{button.disabled=false;button.textContent='＋ EPUB';status('Upload failed: network error')};xhr.onload=()=>{let data={};try{data=JSON.parse(xhr.responseText||'{}')}catch{}button.disabled=false;button.textContent='＋ EPUB';if(xhr.status===401){status('Upload cần Library PIN session. Reload rồi đăng nhập lại.');return}if(xhr.status<200||xhr.status>=300||data.ok!==true){status('Upload failed: '+(data.error||('HTTP '+xhr.status)));return}status('Đã upload vào R2: '+file.name);load()};xhr.send(file)}
  $('uploadEpub').addEventListener('click',()=>$('uploadEpubInput').click());$('uploadEpubInput').addEventListener('change',e=>{const file=e.target.files&&e.target.files[0];e.target.value='';uploadEpub(file)});$('searchForm').addEventListener('submit',e=>{e.preventDefault();state.query=$('search').value||'';render()});$('search').addEventListener('input',e=>{state.query=e.target.value||'';render()});$('refresh').addEventListener('click',load);document.querySelectorAll('.filter').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('active'));btn.classList.add('active');state.filter=btn.dataset.filter||'all';render()}));load();
})();
</script></body></html>`;
}'''

start = simple.find('function libraryPage() {')
end = simple.find('function injectIframeSwipe(html) {', start)
if start < 0 or end < 0:
    raise SystemExit('v54: simple libraryPage boundaries missing')
simple = simple[:start] + LIBRARY_PAGE + '\n\n' + simple[end:]

META_HELPERS = r'''
  const R3_LIBRARY_META_DB_V54='r3-library-book-meta-v54';
  const R3_LIBRARY_META_STORE_V54='books';
  const R3_READER_PROGRESS_PREFIX_V54='r3-reader-progress-v1:';
  const R3_BOOK_INFO_V54={
    'blindsight':{title:"Blindsight",author:"Peter Watts",mark:"B"},
    'broken-money':{title:"Broken Money",author:"Lyn Alden",mark:"BM"},
    'chiec-hop-pandora':{title:"Chiếc Hộp Pandora",mark:"CHP"},
    'consider-phlebas':{title:"Consider Phlebas",author:"Iain M. Banks",mark:"CP"},
    'skeleton-crew':{title:"Skeleton Crew",author:"Stephen King",mark:"SC"},
    'dcc-01':{title:"Dungeon Crawler Carl",author:"Matt Dinniman",series:"DCC · Book 1",mark:"DCC 1"},
    'dcc-02':{title:"Carl's Doomsday Scenario",author:"Matt Dinniman",series:"DCC · Book 2",mark:"DCC 2"},
    'dcc-03':{title:"The Dungeon Anarchist's Cookbook",author:"Matt Dinniman",series:"DCC · Book 3",mark:"DCC 3"},
    'dcc-04':{title:"The Gate of the Feral Gods",author:"Matt Dinniman",series:"DCC · Book 4",mark:"DCC 4"},
    'dcc-05':{title:"The Butcher's Masquerade",author:"Matt Dinniman",series:"DCC · Book 5",mark:"DCC 5"},
    'dcc-06':{title:"The Eye of the Bedlam Bride",author:"Matt Dinniman",series:"DCC · Book 6",mark:"DCC 6"},
    'dcc-07':{title:"This Inevitable Ruin",author:"Matt Dinniman",series:"DCC · Book 7",mark:"DCC 7"},
    'dcc-08':{title:"A Parade of Horribles",author:"Matt Dinniman",series:"DCC · Book 8",mark:"DCC 8"}
  };
  let r3LibraryMetaDbPromiseV54=null;
  const r3LibraryMetaCacheV54=new Map();
  let r3LibraryMetaHydratedV54=false;
  const r3LibraryCoverUrlsV54=[];
  function r3ScopeV54(book){return String(book&&book.scope||String(book&&book.key||'').split('/')[2]||'');}
  function r3BaseNameV54(bookKey){const raw=String(bookKey||'').split('/').filter(Boolean).pop()||'';try{return decodeURIComponent(raw)}catch{return raw}}
  function r3CleanFilenameV54(bookKey){let s=r3BaseNameV54(bookKey).replace(/\.epub$/i,'');s=s.replace(/\s*\([^)]{2,100}\)\s*\d*\s*$/,'');s=s.replace(/(?:[-_\s]+VI)?[-_\s]*v\d+\s*$/i,'');return s.replace(/[_-]+/g,' ').replace(/\s+/g,' ').trim()||'Book';}
  function r3InfoV54(book){return R3_BOOK_INFO_V54[r3ScopeV54(book)]||{};}
  function r3TitleForBookV54(book){const info=r3InfoV54(book),meta=r3LibraryMetaCacheV54.get(String(book&&book.key||''))||{};return info.title||String(meta.title||'').trim()||r3CleanFilenameV54(book&&book.key);}
  function r3SubtitleForBookV54(book){const info=r3InfoV54(book),meta=r3LibraryMetaCacheV54.get(String(book&&book.key||''))||{};const parts=[];const author=info.author||String(meta.creator||'').trim();if(author)parts.push(author);if(info.series)parts.push(info.series);return parts.join(' · ');}
  function r3MarkForBookV54(book){const info=r3InfoV54(book);if(info.mark)return info.mark;const words=r3TitleForBookV54(book).split(/\s+/).filter(Boolean).filter(x=>!['the','a','an','of','and'].includes(x.toLowerCase()));return (words.slice(0,2).map(x=>x[0]).join('')||'BK').toUpperCase();}
  function r3HueV54(value){let h=2166136261;for(const ch of String(value||'')){h^=ch.charCodeAt(0);h=Math.imul(h,16777619)>>>0;}return h%360;}
  function r3ProgressForBookV54(book){let row=null;try{row=JSON.parse(localStorage.getItem(R3_READER_PROGRESS_PREFIX_V54+book.key)||'null')}catch{}const n=Number(row&&row.percent);const percent=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;let saved=false;try{saved=Boolean(localStorage.getItem('r3-reader-position:'+book.key))}catch{}return {percent,started:percent!==null||saved,updatedAt:Number(row&&row.updatedAt||0),done:percent!==null&&percent>=99};}
  function r3ProgressLabelV54(p){if(p.done)return '100% · Đã đọc';if(p.percent!==null)return p.percent+'% · '+(p.percent>0?'Tiếp tục':'Chưa đọc');if(p.started)return 'Đang đọc';return '0% · Chưa đọc';}
  function r3OpenLibraryMetaDbV54(){if(r3LibraryMetaDbPromiseV54)return r3LibraryMetaDbPromiseV54;r3LibraryMetaDbPromiseV54=new Promise((resolve,reject)=>{if(!('indexedDB' in window)){reject(new Error('INDEXEDDB_UNAVAILABLE'));return;}const req=indexedDB.open(R3_LIBRARY_META_DB_V54,1);req.onupgradeneeded=()=>{const db=req.result;if(!db.objectStoreNames.contains(R3_LIBRARY_META_STORE_V54))db.createObjectStore(R3_LIBRARY_META_STORE_V54,{keyPath:'key'});};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error('INDEXEDDB_OPEN_FAILED'));}).catch(()=>null);return r3LibraryMetaDbPromiseV54;}
  async function r3HydrateMetaCacheV54(){if(r3LibraryMetaHydratedV54)return;try{const db=await r3OpenLibraryMetaDbV54();if(!db)return;const rows=await new Promise((resolve,reject)=>{const tx=db.transaction(R3_LIBRARY_META_STORE_V54,'readonly');const req=tx.objectStore(R3_LIBRARY_META_STORE_V54).getAll();req.onsuccess=()=>resolve(Array.isArray(req.result)?req.result:[]);req.onerror=()=>reject(req.error);});for(const row of rows)if(row&&row.key)r3LibraryMetaCacheV54.set(row.key,row);r3LibraryMetaHydratedV54=true;}catch{}}
  async function r3PutMetaV54(row){try{const db=await r3OpenLibraryMetaDbV54();if(!db||!row||!row.key)return;await new Promise((resolve,reject)=>{const tx=db.transaction(R3_LIBRARY_META_STORE_V54,'readwrite');tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.objectStore(R3_LIBRARY_META_STORE_V54).put(row);});r3LibraryMetaCacheV54.set(row.key,row);r3LibraryMetaHydratedV54=true;}catch{}}
  async function r3PersistBookMetaV54(epubBook,bookKey){try{if(!epubBook||!bookKey)return;const metadata=await epubBook.loaded.metadata;let coverBlob=null;try{const coverUrl=await epubBook.coverUrl();if(coverUrl){const response=await fetch(coverUrl);if(response.ok)coverBlob=await response.blob();}}catch{}const text=v=>Array.isArray(v)?v.filter(Boolean).join(', '):typeof v==='string'?v:(v&&typeof v==='object'&&typeof v.name==='string'?v.name:'');const row={key:bookKey,title:text(metadata&&metadata.title).trim(),creator:text(metadata&&metadata.creator).trim(),coverBlob:coverBlob instanceof Blob?coverBlob:null,updatedAt:Date.now()};await r3PutMetaV54(row);if(typeof r3LiveLibraryVisible==='function'&&r3LiveLibraryVisible()&&typeof r3RenderLiveLibrary==='function')r3RenderLiveLibrary();}catch{}}
'''

if 'R3_LIBRARY_META_DB_V54' not in reader:
    reader = replace_once(reader, "  const $=id=>document.getElementById(id);", "  const $=id=>document.getElementById(id);\n" + META_HELPERS, 'v54 reader metadata helpers')

progress_pattern = re.compile(r"rendition\.on\('relocated',loc=>\{const cfi=loc\?\.start\?\.cfi;if\(cfi\)persist\(keys\.position,cfi\);const pct=Number\.isFinite\(loc\?\.start\?\.percentage\)\?Math\.round\(loc\.start\.percentage\*100\):null;\$\('position'\)\.textContent=pct===null\?'Đã lưu vị trí':pct\+'% · đã lưu';setTimeout\(bindEpubContents,0\);\}\);")
progress_replacement = "rendition.on('relocated',loc=>{const cfi=loc?.start?.cfi;if(cfi)persist(keys.position,cfi);const pct=Number.isFinite(loc?.start?.percentage)?Math.max(0,Math.min(100,Math.round(loc.start.percentage*100))):null;try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+key,JSON.stringify({percent:pct,cfi:cfi||'',updatedAt:Date.now()}));}catch{}$('position').textContent=pct===null?'Đã lưu vị trí':pct+'% · đã lưu';setTimeout(bindEpubContents,0);});"
reader, changed = progress_pattern.subn(progress_replacement, reader, count=1)
if changed != 1 and 'R3_READER_PROGRESS_PREFIX_V54+key' not in reader:
    raise SystemExit(f'v54 progress handler: expected 1 match, got {changed}')

if 'r3PersistBookMetaV54(book,key)' not in reader:
    reader = replace_once(reader, '      book=window.ePub(buffer);', "      book=window.ePub(buffer);\n      setTimeout(()=>r3PersistBookMetaV54(book,key),0);", 'v54 reader metadata persist hook')

if '  const r3TitleFor=b=>r3TitleForBookV54(b);' not in reader:
    reader, changed = re.subn(
        r"  const r3Humanize=.*?\n  const r3TitleFor=.*?;\n",
        "  const r3TitleFor=b=>r3TitleForBookV54(b);\n",
        reader,
        count=1,
    )
    if changed != 1:
        raise SystemExit(f'v54 live title resolver: expected 1 match, got {changed}')

LIVE_CSS = r'''
.r3-live-library-tools{grid-template-columns:minmax(0,1fr) auto!important;margin-bottom:10px!important}.r3-live-library-upload{height:40px!important;border-radius:11px!important;font-size:12px!important;padding:0 11px!important;background:#151b22!important;color:#edf2f7!important}.r3-live-library-list{gap:7px!important}.r3-live-book{border-radius:15px!important;background:#0d1217!important}.r3-live-book-link{padding:9px 10px!important;display:grid!important;grid-template-columns:48px minmax(0,1fr) auto!important;gap:10px!important;align-items:center!important}.r3-live-cover{position:relative;width:48px;height:68px;border-radius:8px;overflow:hidden;border:1px solid rgba(255,255,255,.12);background:linear-gradient(145deg,hsl(var(--r3-cover-h) 46% 34%),hsl(calc(var(--r3-cover-h) + 26) 58% 17%));box-shadow:0 6px 16px rgba(0,0,0,.25);display:flex;flex-direction:column;justify-content:flex-end;padding:6px}.r3-live-cover img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.r3-live-cover:after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.58),transparent 58%)}.r3-live-cover-mark,.r3-live-cover-series{position:relative;z-index:2}.r3-live-cover-mark{font-size:14px;line-height:1;font-weight:900;color:#fff}.r3-live-cover-series{margin-top:3px;font-size:7px;line-height:1.1;font-weight:800;color:rgba(255,255,255,.78);text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.r3-live-book-content{min-width:0}.r3-live-book-name{font-size:15px!important;line-height:1.22!important;font-weight:760!important;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.r3-live-book-sub{font-size:11px;color:#8491a0;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.r3-live-progress-line{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px;align-items:center;margin-top:8px}.r3-live-progress{height:5px;background:#222b35;border-radius:999px;overflow:hidden}.r3-live-progress>span{display:block;height:100%;background:#d7b462;border-radius:inherit}.r3-live-progress-text{font-size:10px;color:#98a4b1;font-variant-numeric:tabular-nums;white-space:nowrap}.r3-live-book-current{align-self:start;margin-top:2px;color:#d9e1ea!important;background:#18222d;border:1px solid #2a3948;border-radius:999px;padding:4px 7px;font-size:9px!important}
'''
if '.r3-live-cover{' not in reader:
    reader = replace_once(reader, '\n</style>\n</head>', LIVE_CSS + '\n</style>\n</head>', 'v54 live library css')

render_start = reader.find('  function r3RenderLiveLibrary(){')
render_end = reader.find('  async function r3LoadLiveLibrary(){', render_start)
if render_start < 0 or render_end < 0:
    raise SystemExit('v54 live render boundaries missing')
LIVE_RENDER = r'''  function r3RenderLiveLibrary(){
    const root=$('r3LiveLibraryList');if(!root)return;root.textContent='';
    while(r3LibraryCoverUrlsV54.length){try{URL.revokeObjectURL(r3LibraryCoverUrlsV54.pop())}catch{}}
    const q=String(r3LiveLibraryQuery||'').trim().toLocaleLowerCase('vi');
    const rows=(Array.isArray(r3LiveLibraryBooks)?r3LiveLibraryBooks:[]).filter(b=>!q||r3TitleFor(b).toLocaleLowerCase('vi').includes(q)||r3SubtitleForBookV54(b).toLocaleLowerCase('vi').includes(q)||String(b&&b.key||'').toLocaleLowerCase('vi').includes(q)).sort((a,b)=>{const pa=r3ProgressForBookV54(a),pb=r3ProgressForBookV54(b);const ra=pa.started&&!pa.done?0:pa.done?2:1,rb=pb.started&&!pb.done?0:pb.done?2:1;if(ra!==rb)return ra-rb;if(ra===0&&pa.updatedAt!==pb.updatedAt)return pb.updatedAt-pa.updatedAt;return r3TitleFor(a).localeCompare(r3TitleFor(b),'vi');});
    if(!rows.length){const empty=document.createElement('div');empty.className='r3-live-library-empty';empty.textContent=r3LiveLibraryBooks?'No books found.':'Loading…';root.appendChild(empty);return;}
    for(const row of rows){const article=document.createElement('article');article.className='r3-live-book';const same=String(row&&row.key||'')===key;const link=document.createElement(same?'button':'a');link.className='r3-live-book-link';if(same){link.type='button';link.addEventListener('click',r3CloseLiveLibrary);}else link.href='/artifact-library/read?key='+encodeURIComponent(String(row&&row.key||''));const cover=document.createElement('div');cover.className='r3-live-cover';cover.style.setProperty('--r3-cover-h',String(r3HueV54(row.scope||row.key)));const meta=r3LibraryMetaCacheV54.get(String(row&&row.key||''))||{};if(meta.coverBlob instanceof Blob&&meta.coverBlob.size){const img=document.createElement('img');const u=URL.createObjectURL(meta.coverBlob);r3LibraryCoverUrlsV54.push(u);img.src=u;img.alt='';cover.appendChild(img);}const mark=document.createElement('div');mark.className='r3-live-cover-mark';mark.textContent=r3MarkForBookV54(row);const coverSeries=document.createElement('div');coverSeries.className='r3-live-cover-series';coverSeries.textContent=r3InfoV54(row).series||'EPUB';cover.append(mark,coverSeries);const content=document.createElement('div');content.className='r3-live-book-content';const name=document.createElement('div');name.className='r3-live-book-name';name.textContent=r3TitleFor(row);const sub=document.createElement('div');sub.className='r3-live-book-sub';sub.textContent=r3SubtitleForBookV54(row)||r3CleanFilenameV54(row.key);const p=r3ProgressForBookV54(row);const progressLine=document.createElement('div');progressLine.className='r3-live-progress-line';const track=document.createElement('div');track.className='r3-live-progress';const fill=document.createElement('span');fill.style.width=(p.percent===null?0:p.percent)+'%';track.appendChild(fill);const pt=document.createElement('span');pt.className='r3-live-progress-text';pt.textContent=r3ProgressLabelV54(p);progressLine.append(track,pt);content.append(name,sub,progressLine);link.append(cover,content);if(same){const badge=document.createElement('span');badge.className='r3-live-book-current';badge.textContent='Đang đọc';link.appendChild(badge);}article.appendChild(link);root.appendChild(article);}
  }
'''
reader = reader[:render_start] + LIVE_RENDER + reader[render_end:]

old_loaded = "      r3LiveLibraryBooks=Array.isArray(data.objects)?data.objects:[];\n      r3LiveLibraryStatus('');r3RenderLiveLibrary();"
new_loaded = "      r3LiveLibraryBooks=Array.isArray(data.objects)?data.objects:[];\n      r3LiveLibraryStatus('');r3RenderLiveLibrary();r3HydrateMetaCacheV54().then(()=>r3RenderLiveLibrary());"
if old_loaded in reader:
    reader = replace_once(reader, old_loaded, new_loaded, 'v54 live meta hydration')
elif 'r3HydrateMetaCacheV54().then(()=>r3RenderLiveLibrary())' not in reader:
    raise SystemExit('v54 live meta hydration marker missing')

for marker in [
    "Carl's Doomsday Scenario",
    "The Dungeon Anarchist's Cookbook",
    'A Parade of Horribles',
    'r3-reader-progress-v1:',
    'r3-library-book-meta-v54',
    'r3PersistBookMetaV54(book,key)',
    "cover.className='r3-live-cover'",
    "progressLine.className='r3-live-progress-line'",
]:
    if marker not in reader:
        raise SystemExit('READER_V54_MISSING:' + marker)

for marker in [
    "Carl's Doomsday Scenario",
    "The Dungeon Anarchist's Cookbook",
    'A Parade of Horribles',
    "cover.className='cover'",
    "progressLine.className='progress-line'",
    'r3-reader-progress-v1:',
    'r3-library-book-meta-v54',
    'id="uploadEpub"',
    'async function publicUpload(request, env)',
]:
    if marker not in simple:
        raise SystemExit('SIMPLE_LIBRARY_V54_MISSING:' + marker)

for stale in ['Cánh cổng của các Dã thần','Cẩm nang Kẻ Vô chính phủ Hầm ngục','Con mắt của Cô dâu Loạn trí','Cuộc Diễu hành Kinh hoàng']:
    if stale in simple:
        raise SystemExit('SIMPLE_LIBRARY_V54_STALE_TITLE:' + stale)

SIMPLE.write_text(simple, encoding='utf-8')
READER.write_text(reader, encoding='utf-8')
print('READER_V54_LIBRARY_UX=PASS')
