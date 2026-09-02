from pathlib import Path
import re

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
ROUTER = ROOT / 'opportunity-router-entry.js'
V2 = ROOT / 'artifact-library-reader-v2-entry.js'

simple = SIMPLE.read_text(encoding='utf-8')
router = ROUTER.read_text(encoding='utf-8')
v2 = V2.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# v65 identity.
simple = replace_once(simple, "reader_client_version:'v64'", "reader_client_version:'v65'", 'v65 server client version')
simple = replace_once(simple, "'x-r3-reader-client-version':'v64'", "'x-r3-reader-client-version':'v65'", 'v65 server version header')
v2 = replace_once(v2, "const R3_READER_CLIENT_VERSION_V63='v64';", "const R3_READER_CLIENT_VERSION_V63='v65';", 'v65 reader client version')

server = r'''
async function r3EnsureProgressTableV65(env) {
  if (!env.DB) throw new Error('DB_BINDING_MISSING');
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS ebook_reader_progress_v65 (
    book_key TEXT PRIMARY KEY,
    cfi TEXT NOT NULL DEFAULT '',
    percent INTEGER,
    last_open_at INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0
  )`).run();
  await env.DB.prepare('CREATE INDEX IF NOT EXISTS idx_ebook_reader_progress_v65_updated ON ebook_reader_progress_v65(updated_at DESC)').run();
}

function r3ProgressRowV65(row) {
  if (!row) return null;
  const raw = row.percent;
  const n = raw === null || raw === undefined ? NaN : Number(raw);
  return {key:String(row.book_key||''),cfi:String(row.cfi||''),percent:Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null,last_open_at:Math.max(0,Number(row.last_open_at||0)),updated_at:Math.max(0,Number(row.updated_at||0))};
}

async function publicProgressV65(request, env) {
  if (!(await hasBrowserLibrarySession(request, env))) return json({ok:false,error:'UNAUTHORIZED'},401);
  if (!env.DB) return json({ok:false,error:'DB_BINDING_MISSING'},503);
  try { await r3EnsureProgressTableV65(env); } catch (error) { return json({ok:false,error:'PROGRESS_DB_INIT_FAILED',detail:String(error?.message||error)},503); }
  const url = new URL(request.url);
  if (request.method === 'GET') {
    const key = String(url.searchParams.get('key') || '');
    if (key) {
      if (!isFinalEpub(key)) return json({ok:false,error:'FINAL_EPUB_ONLY'},403);
      const row = await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 WHERE book_key=?1').bind(key).first();
      return json({ok:true,progress:r3ProgressRowV65(row)});
    }
    const result = await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 ORDER BY updated_at DESC LIMIT 2000').all();
    return json({ok:true,items:(result.results||[]).map(r3ProgressRowV65)});
  }
  if (request.method !== 'POST') return json({ok:false,error:'METHOD_NOT_ALLOWED'},405);
  let body; try { body = await request.json(); } catch { return json({ok:false,error:'INVALID_JSON'},400); }
  const key = String(body?.key || '');
  if (!isFinalEpub(key)) return json({ok:false,error:'FINAL_EPUB_ONLY'},403);
  const cfi = String(body?.cfi || '').slice(0,4096);
  const rawPercent = body?.percent;
  const pn = rawPercent === null || rawPercent === undefined || rawPercent === '' ? NaN : Number(rawPercent);
  const percent = Number.isFinite(pn) ? Math.max(0,Math.min(100,Math.round(pn))) : null;
  const updatedAt = Math.max(0,Math.round(Number(body?.updated_at || body?.updatedAt || Date.now())));
  const lastOpenAt = Math.max(0,Math.round(Number(body?.last_open_at || body?.lastOpenAt || 0)));
  if (!Number.isFinite(updatedAt) || updatedAt <= 0) return json({ok:false,error:'INVALID_UPDATED_AT'},400);
  const existing = await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 WHERE book_key=?1').bind(key).first();
  if (!existing) {
    await env.DB.prepare('INSERT INTO ebook_reader_progress_v65(book_key,cfi,percent,last_open_at,updated_at) VALUES(?1,?2,?3,?4,?5)').bind(key,cfi,percent,lastOpenAt,updatedAt).run();
  } else if (updatedAt >= Number(existing.updated_at || 0)) {
    await env.DB.prepare('UPDATE ebook_reader_progress_v65 SET cfi=?2,percent=?3,last_open_at=MAX(last_open_at,?4),updated_at=?5 WHERE book_key=?1').bind(key,cfi,percent,lastOpenAt,updatedAt).run();
  } else if (lastOpenAt > Number(existing.last_open_at || 0)) {
    await env.DB.prepare('UPDATE ebook_reader_progress_v65 SET last_open_at=?2 WHERE book_key=?1').bind(key,lastOpenAt).run();
  }
  const row = await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 WHERE book_key=?1').bind(key).first();
  return json({ok:true,accepted:!existing||updatedAt>=Number(existing.updated_at||0),progress:r3ProgressRowV65(row)});
}

function r3CleanRenameV65(value) {
  let name=String(value||'').normalize('NFC').replace(/[\u0000-\u001f\u007f]/g,' ').replace(/[\\/]/g,'-').replace(/\s+/g,' ').trim();
  name=name.replace(/\.epub$/i,'').trim();if(!name)return '';if(name.length>170)name=name.slice(0,170).trim();return name;
}
async function r3WriteCatalogV65(env,catalog){catalog.version=Math.max(1,Number(catalog.version||1));catalog.generated_at=new Date().toISOString();await env.ARTIFACTS.put(LIBRARY_CATALOG_INDEX_KEY,JSON.stringify(catalog,null,2)+'\n',{httpMetadata:{contentType:'application/json'}})}
async function r3MoveProgressV65(env,oldKey,newKey){if(!env.DB)return;await r3EnsureProgressTableV65(env);const row=await env.DB.prepare('SELECT cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 WHERE book_key=?1').bind(oldKey).first();if(!row)return;const target=await env.DB.prepare('SELECT updated_at FROM ebook_reader_progress_v65 WHERE book_key=?1').bind(newKey).first();if(!target||Number(row.updated_at||0)>=Number(target.updated_at||0)){await env.DB.prepare(`INSERT INTO ebook_reader_progress_v65(book_key,cfi,percent,last_open_at,updated_at) VALUES(?1,?2,?3,?4,?5) ON CONFLICT(book_key) DO UPDATE SET cfi=excluded.cfi,percent=excluded.percent,last_open_at=MAX(ebook_reader_progress_v65.last_open_at,excluded.last_open_at),updated_at=excluded.updated_at`).bind(newKey,String(row.cfi||''),row.percent,Number(row.last_open_at||0),Number(row.updated_at||0)).run()}await env.DB.prepare('DELETE FROM ebook_reader_progress_v65 WHERE book_key=?1').bind(oldKey).run()}

async function publicManageBookV65(request, env) {
  if(request.method!=='POST')return json({ok:false,error:'METHOD_NOT_ALLOWED'},405);
  if(!(await hasBrowserLibrarySession(request,env)))return json({ok:false,error:'UNAUTHORIZED'},401);
  if(request.headers.get('x-runner3-library')!=='1')return json({ok:false,error:'BAD_LIBRARY_REQUEST'},400);
  if(!env.ARTIFACTS)return json({ok:false,error:'R2_NOT_BOUND'},503);
  let body;try{body=await request.json()}catch{return json({ok:false,error:'INVALID_JSON'},400)}
  const action=String(body?.action||''),key=String(body?.key||'');if(!isFinalEpub(key))return json({ok:false,error:'FINAL_EPUB_ONLY'},403);const scope=scopeOf(key);if(!scope)return json({ok:false,error:'INVALID_SCOPE'},400);
  if(action==='rename'){
    const title=r3CleanRenameV65(body?.name||body?.title);if(!title)return json({ok:false,error:'RENAME_REQUIRED'},400);const newKey=ROOT+scope+'/final/'+title+'.epub';if(newKey===key)return json({ok:true,key,new_key:key,title,unchanged:true});if(await env.ARTIFACTS.head(newKey))return json({ok:false,error:'EPUB_RENAME_COLLISION',key:newKey},409);
    const source=await env.ARTIFACTS.get(key);if(!source)return json({ok:false,error:'EPUB_NOT_FOUND'},404);await env.ARTIFACTS.put(newKey,source.body,{httpMetadata:source.httpMetadata||{contentType:'application/epub+zip'},customMetadata:{...(source.customMetadata||{}),renamed_from:key,renamed_at:new Date().toISOString()}});if(!(await env.ARTIFACTS.head(newKey)))return json({ok:false,error:'EPUB_RENAME_VERIFY_FAILED'},502);
    const catalog=await readCatalogDocumentV56(env);const previous=catalog.books[scope]&&typeof catalog.books[scope]==='object'?catalog.books[scope]:{};const entry={...previous,epub_key:newKey,title};catalog.books[scope]=entry;await r3WriteCatalogV65(env,catalog);const sidecar={bookKey:newKey,display_title:title,author:entry.creator||'',cover_key:entry.cover_key||'',updated_at:catalog.generated_at,renamed_from:key};await env.ARTIFACTS.put(ROOT+scope+'/meta/book.json',JSON.stringify(sidecar,null,2)+'\n',{httpMetadata:{contentType:'application/json'}});try{await r3MoveProgressV65(env,key,newKey)}catch(error){console.warn('R3_PROGRESS_RENAME_V65',error)}await env.ARTIFACTS.delete(key);return json({ok:true,action:'rename',key,new_key:newKey,scope,title});
  }
  if(action==='delete'){
    const prefixes=[ROOT+scope+'/final/',ROOT+scope+'/meta/'],keys=[];for(const prefix of prefixes){let cursor;do{const page=await env.ARTIFACTS.list({prefix,cursor,limit:1000});for(const object of page.objects||[])keys.push(object.key);cursor=page.truncated?page.cursor:undefined}while(cursor)}if(!keys.includes(key)&&!(await env.ARTIFACTS.head(key)))return json({ok:false,error:'EPUB_NOT_FOUND'},404);for(let i=0;i<keys.length;i+=500)await env.ARTIFACTS.delete(keys.slice(i,i+500));const catalog=await readCatalogDocumentV56(env);if(catalog.books&&Object.prototype.hasOwnProperty.call(catalog.books,scope)){delete catalog.books[scope];await r3WriteCatalogV65(env,catalog)}if(env.DB){try{await r3EnsureProgressTableV65(env);await env.DB.prepare("DELETE FROM ebook_reader_progress_v65 WHERE book_key LIKE ?1").bind(ROOT+scope+'/final/%').run()}catch(error){console.warn('R3_PROGRESS_DELETE_V65',error)}}return json({ok:true,action:'delete',key,scope,deleted_objects:keys.length});
  }
  return json({ok:false,error:'UNKNOWN_ACTION'},400);
}

'''
if 'async function publicProgressV65' not in simple:
    simple=replace_once(simple,'async function publicDelivery(request, env, ctx) {',server+'async function publicDelivery(request, env, ctx) {','v65 server handlers')

raw_route='    if (p === "/artifact-library/api/raw") return publicRawEpubV57(request, env);\n'
routes='    if (p === "/artifact-library/api/progress") return publicProgressV65(request, env);\n    if (p === "/artifact-library/api/manage") return publicManageBookV65(request, env);\n'
if 'p === "/artifact-library/api/progress"' not in simple:simple=replace_once(simple,raw_route,raw_route+routes,'v65 simple routes')
if '"/artifact-library/api/progress"' not in router:router=replace_once(router,'    "/artifact-library/api/client-version",\n','    "/artifact-library/api/client-version",\n    "/artifact-library/api/progress",\n    "/artifact-library/api/manage",\n','v65 router fast paths')

main_helpers=r'''
  async function r3HydrateServerProgressV65(){try{const response=await fetch('/artifact-library/api/progress',{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}});if(!response.ok)return false;const data=await response.json();if(!data||data.ok!==true||!Array.isArray(data.items))return false;let changed=false;for(const remote of data.items){const bookKey=String(remote&&remote.key||'');if(!bookKey)continue;let local=null;try{local=JSON.parse(localStorage.getItem(PROGRESS_PREFIX+bookKey)||'null')}catch{}const localUpdated=Number(local&&local.updatedAt||0),remoteUpdated=Number(remote&&remote.updated_at||0);if(remoteUpdated>localUpdated){try{localStorage.setItem(PROGRESS_PREFIX+bookKey,JSON.stringify({percent:remote.percent,cfi:String(remote.cfi||''),updatedAt:remoteUpdated,lastOpenAt:Number(remote.last_open_at||0),syncedBy:'v65'}));if(remote.cfi)localStorage.setItem(POSITION_PREFIX+bookKey,String(remote.cfi));changed=true}catch{}}}return changed}catch{return false}}
  function r3MigrateLocalBookKeyV65(oldKey,newKey){for(const prefix of [PROGRESS_PREFIX,POSITION_PREFIX]){try{const value=localStorage.getItem(prefix+oldKey);if(value!==null){localStorage.setItem(prefix+newKey,value);localStorage.removeItem(prefix+oldKey)}}catch{}}}
  async function r3ManageBookV65(bookKey,title){const choice=String(prompt('R = Rename\\nD = Delete\\nCancel = Hủy','R')||'').trim().toUpperCase();if(choice==='R'){const next=prompt('Tên mới',title||'');if(next===null)return;const name=String(next||'').trim();if(!name||name===String(title||'').trim())return;status('Đang đổi tên…');const response=await fetch('/artifact-library/api/manage',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({action:'rename',key:bookKey,name})});const data=await response.json().catch(()=>({}));if(!response.ok||data.ok!==true)throw new Error(data.error||('HTTP '+response.status));r3MigrateLocalBookKeyV65(bookKey,data.new_key||bookKey);status('Đã đổi tên.');await load();return}if(choice==='D'){if(!confirm('Xóa sách này khỏi Library?\\n\\n'+String(title||bookKey)))return;status('Đang xóa…');const response=await fetch('/artifact-library/api/manage',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({action:'delete',key:bookKey})});const data=await response.json().catch(()=>({}));if(!response.ok||data.ok!==true)throw new Error(data.error||('HTTP '+response.status));try{localStorage.removeItem(PROGRESS_PREFIX+bookKey);localStorage.removeItem(POSITION_PREFIX+bookKey)}catch{}status('Đã xóa.');await load()}}
  function r3InstallMainManageV65(){const style=document.createElement('style');style.textContent='.r3-manage-v65{appearance:none;border:0;border-left:1px solid #202832;background:#111820;color:#aeb9c6;width:42px;display:grid;place-items:center;padding:0;font:inherit;font-size:20px;font-weight:900;cursor:pointer}.book[data-r3-manage-v65="1"]{grid-template-columns:minmax(0,1fr) 42px 42px!important}';document.head.appendChild(style);const install=()=>document.querySelectorAll('article.book:not([data-r3-manage-v65])').forEach(article=>{const link=article.querySelector('a.read');if(!link)return;let bookKey='';try{bookKey=new URL(link.href,location.href).searchParams.get('key')||''}catch{}if(!bookKey)return;article.dataset.r3ManageV65='1';const button=document.createElement('button');button.type='button';button.className='r3-manage-v65';button.setAttribute('aria-label','Rename hoặc Delete');button.textContent='⋯';button.addEventListener('click',async e=>{e.preventDefault();e.stopPropagation();try{await r3ManageBookV65(bookKey,article.querySelector('.title')?.textContent||'')}catch(error){status('Library action failed: '+String(error&&error.message||error))}});article.appendChild(button)});install();new MutationObserver(install).observe($('list'),{childList:true,subtree:true})}
'''
if 'async function r3HydrateServerProgressV65()' not in simple:simple=replace_once(simple,"  const $=id=>document.getElementById(id);\n","  const $=id=>document.getElementById(id);\n"+main_helpers,'v65 main helpers')
load_old="state.books=Array.isArray(data.objects)?data.objects:[];status('');render();hydrateMeta();setTimeout(()=>migrateLegacyProgressV56(),700)"
load_new="state.books=Array.isArray(data.objects)?data.objects:[];await r3HydrateServerProgressV65();status('');render();hydrateMeta();setTimeout(()=>migrateLegacyProgressV56(),700)"
if 'await r3HydrateServerProgressV65();status' not in simple:simple=replace_once(simple,load_old,load_new,'v65 main progress hydration')
if 'r3InstallMainManageV65();load();' not in simple:simple=replace_once(simple,'load();\n})();','r3InstallMainManageV65();load();\n})();','v65 main manage install')

reader_helpers=r'''
  let r3ProgressSyncTimerV65=0;
  async function r3FetchRemoteProgressV65(bookKey){try{const response=await fetch('/artifact-library/api/progress?key='+encodeURIComponent(bookKey),{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}});if(!response.ok)return null;const data=await response.json();return data&&data.ok===true?data.progress:null}catch{return null}}
  async function r3PostProgressV65(row){try{await fetch('/artifact-library/api/progress',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify(row),keepalive:true})}catch{}}
  function r3ReadLocalProgressV65(bookKey){try{return JSON.parse(localStorage.getItem(R3_READER_PROGRESS_PREFIX_V54+bookKey)||'null')||null}catch{return null}}
  function r3ApplyRemoteProgressV65(bookKey,remote){if(!remote||!bookKey)return false;const local=r3ReadLocalProgressV65(bookKey);const localUpdated=Number(local&&local.updatedAt||0),remoteUpdated=Number(remote.updated_at||0);if(!(remoteUpdated>localUpdated))return false;try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+bookKey,JSON.stringify({percent:remote.percent,cfi:String(remote.cfi||''),updatedAt:remoteUpdated,lastOpenAt:Number(remote.last_open_at||0),syncedBy:'v65'}));if(remote.cfi)localStorage.setItem('r3-reader-position:'+bookKey,String(remote.cfi));return true}catch{return false}}
  async function r3MergeRemoteProgressV65(){const remote=await r3FetchRemoteProgressV65(key);r3ApplyRemoteProgressV65(key,remote);const local=r3ReadLocalProgressV65(key);const cfi=String(local&&local.cfi||localStorage.getItem(keys.position)||'');const now=Date.now(),updatedAt=Math.max(now,Number(local&&local.updatedAt||0)),percent=local&&local.percent!==undefined?local.percent:null;try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+key,JSON.stringify({...local,percent,cfi,updatedAt,lastOpenAt:now}));if(cfi)localStorage.setItem(keys.position,cfi)}catch{}r3PostProgressV65({key,cfi,percent,last_open_at:now,updated_at:updatedAt});return cfi}
  function r3ScheduleProgressSyncV65(percent,cfi){clearTimeout(r3ProgressSyncTimerV65);const now=Date.now();r3ProgressSyncTimerV65=setTimeout(()=>r3PostProgressV65({key,cfi:String(cfi||''),percent,last_open_at:now,updated_at:now}),700)}
  async function r3HydrateLiveProgressV65(){try{const response=await fetch('/artifact-library/api/progress',{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}});if(!response.ok)return;const data=await response.json();if(!data||data.ok!==true||!Array.isArray(data.items))return;for(const remote of data.items)r3ApplyRemoteProgressV65(String(remote&&remote.key||''),remote)}catch{}}
  function r3MigrateReaderLocalKeyV65(oldKey,newKey){for(const prefix of [R3_READER_PROGRESS_PREFIX_V54,'r3-reader-position:']){try{const value=localStorage.getItem(prefix+oldKey);if(value!==null){localStorage.setItem(prefix+newKey,value);localStorage.removeItem(prefix+oldKey)}}catch{}}}
  async function r3ReaderManageBookV65(bookKey,title){const choice=String(prompt('R = Rename\\nD = Delete\\nCancel = Hủy','R')||'').trim().toUpperCase();if(choice==='R'){const next=prompt('Tên mới',title||'');if(next===null)return;const name=String(next||'').trim();if(!name)return;const response=await fetch('/artifact-library/api/manage',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({action:'rename',key:bookKey,name})});const data=await response.json().catch(()=>({}));if(!response.ok||data.ok!==true)throw new Error(data.error||('HTTP '+response.status));r3MigrateReaderLocalKeyV65(bookKey,data.new_key||bookKey);if(bookKey===key){location.replace('/artifact-library/read?key='+encodeURIComponent(data.new_key));return}location.reload();return}if(choice==='D'){if(!confirm('Xóa sách này khỏi Library?\\n\\n'+String(title||bookKey)))return;const response=await fetch('/artifact-library/api/manage',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({action:'delete',key:bookKey})});const data=await response.json().catch(()=>({}));if(!response.ok||data.ok!==true)throw new Error(data.error||('HTTP '+response.status));try{localStorage.removeItem(R3_READER_PROGRESS_PREFIX_V54+bookKey);localStorage.removeItem('r3-reader-position:'+bookKey)}catch{}if(bookKey===key){location.replace('/artifact-library');return}location.reload()}}
  function r3InstallLiveManageV65(){const style=document.createElement('style');style.textContent='.r3-live-manage-v65{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:10px;min-width:38px;height:38px;padding:0 9px;font:inherit;font-size:18px;font-weight:900;margin-left:6px}.r3-live-book[data-r3-manage-v65="1"]{display:flex!important;align-items:center}.r3-live-book[data-r3-manage-v65="1"] .r3-live-book-link{min-width:0;flex:1}';document.head.appendChild(style);const root=$('r3LiveLibraryList');if(!root)return;const install=()=>root.querySelectorAll('.r3-live-book:not([data-r3-manage-v65])').forEach(article=>{const link=article.querySelector('.r3-live-book-link');if(!link)return;let bookKey='';if(link.tagName==='A'){try{bookKey=new URL(link.href,location.href).searchParams.get('key')||''}catch{}}else bookKey=key;if(!bookKey)return;article.dataset.r3ManageV65='1';const button=document.createElement('button');button.type='button';button.className='r3-live-manage-v65';button.setAttribute('aria-label','Rename hoặc Delete');button.textContent='⋯';button.addEventListener('click',async e=>{e.preventDefault();e.stopPropagation();try{await r3ReaderManageBookV65(bookKey,article.querySelector('.r3-live-book-name,.r3-live-title,.title')?.textContent||'')}catch(error){r3LiveLibraryStatus('Library action failed: '+String(error&&error.message||error))}});article.appendChild(button)});install();new MutationObserver(install).observe(root,{childList:true,subtree:true})}
'''
if 'async function r3FetchRemoteProgressV65' not in v2:v2=replace_once(v2,'  function r3StructuralPercentV64(loc){\n',reader_helpers+'\n  function r3StructuralPercentV64(loc){\n','v65 reader helpers')
writer_pattern=re.compile(r"  function r3WriteProgressV55\(percent,cfi\)\{\n(.*?)\n  \}",re.S);m=writer_pattern.search(v2)
if not m:raise SystemExit('v65 progress writer missing')
writer_block=m.group(0)
if 'r3ScheduleProgressSyncV65' not in writer_block:
    new_writer=writer_block.replace('    return value;',"    r3ScheduleProgressSyncV65(value,cfi||'');\n    return value;",1);v2=v2[:m.start()]+new_writer+v2[m.end():]
if 'await r3MergeRemoteProgressV65();' not in v2:v2=replace_once(v2,"      const saved=localStorage.getItem(keys.position)||'';\n","      await r3MergeRemoteProgressV65();\n      const saved=localStorage.getItem(keys.position)||'';\n",'v65 pre-display merge')
load_rows="      const rows=await r3FetchLiveLibraryListV63();\n      r3LiveLibraryBooks=rows.filter"
if 'await r3HydrateLiveProgressV65();' not in v2:v2=replace_once(v2,load_rows,"      const rows=await r3FetchLiveLibraryListV63();\n      await r3HydrateLiveProgressV65();\n      r3LiveLibraryBooks=rows.filter",'v65 live progress hydration')
if 'r3InstallLiveManageV65();' not in v2:v2=replace_once(v2,'  syncUi();hideControls();openBook();','  syncUi();hideControls();r3InstallLiveManageV65();openBook();','v65 live manage install')

for marker in ["reader_client_version:'v65'",'async function publicProgressV65','ebook_reader_progress_v65','async function publicManageBookV65','EPUB_RENAME_COLLISION','r3InstallMainManageV65','await r3HydrateServerProgressV65()','p === "/artifact-library/api/progress"','p === "/artifact-library/api/manage"']:
    if marker not in simple:raise SystemExit('V65_SIMPLE_MISSING:'+marker)
for marker in ['"/artifact-library/api/progress"','"/artifact-library/api/manage"','r3IsLibraryFastPathV57']:
    if marker not in router:raise SystemExit('V65_ROUTER_MISSING:'+marker)
for marker in ["R3_READER_CLIENT_VERSION_V63='v65'",'r3MergeRemoteProgressV65','r3ScheduleProgressSyncV65','await r3MergeRemoteProgressV65();','await r3HydrateLiveProgressV65();','r3InstallLiveManageV65','r3ReaderManageBookV65','function r3StructuralPercentV64','__r3SafariBootGeometryV61','__r3PaginatedVerticalClampV62']:
    if marker not in v2:raise SystemExit('V65_READER_MISSING:'+marker)

SIMPLE.write_text(simple,encoding='utf-8')
ROUTER.write_text(router,encoding='utf-8')
V2.write_text(v2,encoding='utf-8')
print('READER_V65_SYNC_MANAGE=PASS')
