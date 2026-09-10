from pathlib import Path
import re

ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
READER=ROOT/'artifact-library-reader-v2-entry.js'
simple=SIMPLE.read_text(encoding='utf-8')
reader=READER.read_text(encoding='utf-8')

if "R3_UNIFIED_STATE_V72='v72'" in simple and "R3_READER_UNIFIED_STATE_V72='v72'" in reader:
    print('READER_V72_UNIFIED_STATE=ALREADY_APPLIED')
    raise SystemExit(0)

# ---------------- Library client: server is canonical; local is recovery/cache only. ----------------
hydrate_re=re.compile(r"  async function r3HydrateServerProgressV65\(\)\{.*?\n  \}\n  function r3MigrateLocalBookKeyV65",re.S)
m=hydrate_re.search(simple)
if not m: raise SystemExit('V72_LIBRARY_HYDRATE_ANCHOR_MISSING')
new_hydrate=r'''  const R3_UNIFIED_STATE_V72='v72';
  const R3_CLIENT_KIND_V72=(window.navigator&&window.navigator.standalone===true)?'home-screen':'browser';
  let r3VisibleSyncBusyV72=false,r3LastVisibleSyncV72=0;
  function r3PickLocalSeedV72(rows){return (rows||[]).filter(Boolean).sort((a,b)=>Number(b.updated_at||b.last_open_at||0)-Number(a.updated_at||a.last_open_at||0)||r3ProgressSubstanceV70(b)-r3ProgressSubstanceV70(a))[0]||null}
  async function r3HydrateServerProgressV65(){
    try{
      const response=await fetch('/artifact-library/api/progress',{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}});
      if(!response.ok){if(response.status===401)status('Read data cần Library session.');return false}
      const data=await response.json();if(!data||data.ok!==true||!Array.isArray(data.items))return false;
      const localRows=r3CollectLocalProgressV70(),remoteByScope=new Map();let changed=false;const upload=[];
      for(const remote of data.items){const scope=String(remote&&remote.scope||r3ScopeFromBookKeyV70(remote&&remote.key));if(!scope)continue;const prev=remoteByScope.get(scope);if(!prev||Number(remote.updated_at||0)>Number(prev.updated_at||0))remoteByScope.set(scope,remote)}
      for(const book of state.books){
        const scope=String(book&&book.scope||r3ScopeFromBookKeyV70(book&&book.key));if(!scope)continue;
        const remote=remoteByScope.get(scope);
        if(remote){
          const canonical={...remote,key:String(book.key),scope};
          if(r3WriteRecoveredLocalV70(book.key,canonical))changed=true;
          continue;
        }
        const candidates=localRows.filter(row=>r3ScopeFromBookKeyV70(row.key)===scope);
        const best=r3PickLocalSeedV72(candidates);if(!best)continue;
        const stamp=Math.max(1,Number(best.updated_at||best.last_open_at||Date.now()));
        upload.push({key:String(book.key),scope,cfi:String(best.cfi||''),percent:best.percent===undefined?null:best.percent,last_open_at:Math.max(0,Number(best.last_open_at||0)),updated_at:stamp,source_client:R3_CLIENT_KIND_V72,legacy_seed:true});
      }
      if(upload.length){
        const pushed=await fetch('/artifact-library/api/progress',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({items:upload,client_version:R3_UNIFIED_STATE_V72,source_client:R3_CLIENT_KIND_V72})});
        if(pushed.ok){const body=await pushed.json().catch(()=>null);for(const remote of body&&Array.isArray(body.items)?body.items:[]){const scope=String(remote&&remote.scope||'');const book=state.books.find(row=>String(row&&row.scope||'')===scope);if(book&&r3WriteRecoveredLocalV70(book.key,{...remote,key:book.key}))changed=true}}
        else if(pushed.status===401)status('Read data chưa sync: cần Library session.');
      }
      return changed
    }catch{return false}
  }
  async function r3SyncVisibleV72(){if(document.hidden||r3VisibleSyncBusyV72||!state.books.length)return;const now=Date.now();if(now-r3LastVisibleSyncV72<900)return;r3LastVisibleSyncV72=now;r3VisibleSyncBusyV72=true;try{if(await r3HydrateServerProgressV65())render()}finally{r3VisibleSyncBusyV72=false}}
  function r3MigrateLocalBookKeyV65'''
simple=simple[:m.start()]+new_hydrate+simple[m.end():]

# Re-sync whenever Safari/Home Screen becomes foreground again.
boot_anchor="r3InstallMainManageV65();load();"
if boot_anchor not in simple: raise SystemExit('V72_LIBRARY_BOOT_ANCHOR_MISSING')
simple=simple.replace(boot_anchor,"document.addEventListener('visibilitychange',()=>{if(!document.hidden)r3SyncVisibleV72()});window.addEventListener('focus',()=>r3SyncVisibleV72());r3InstallMainManageV65();load();",1)

# Client list cache namespace: never reuse a cache written under an older contract.
simple=simple.replace("const R3_LIBRARY_FAST_CLIENT_CACHE_V65='r3-library-fast-list-v71';","const R3_LIBRARY_FAST_CLIENT_CACHE_V65='r3-library-fast-list-v72';",1)

# ---------------- Progress server: stable scope key, monotonic event timestamps. ----------------
server_re=re.compile(r"async function r3SelectProgressForKeyV70\(env,key\)\{.*?\n\}\n\nfunction r3CleanRenameV65",re.S)
m=server_re.search(simple)
if not m: raise SystemExit('V72_PROGRESS_SERVER_ANCHOR_MISSING')
new_server=r'''let r3ProgressInitV72=null;
async function r3EnsureProgressTableV72(env){
  if(!env.DB)throw new Error('DB_BINDING_MISSING');
  if(!r3ProgressInitV72)r3ProgressInitV72=(async()=>{
    await env.DB.prepare(`CREATE TABLE IF NOT EXISTS ebook_reader_state_v72(
      scope TEXT PRIMARY KEY,
      book_key TEXT NOT NULL,
      cfi TEXT NOT NULL DEFAULT '',
      percent INTEGER,
      last_open_at INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER NOT NULL DEFAULT 0,
      source_client TEXT NOT NULL DEFAULT ''
    )`).run();
    await env.DB.prepare('CREATE INDEX IF NOT EXISTS idx_ebook_reader_state_v72_updated ON ebook_reader_state_v72(updated_at DESC)').run();
    const count=await env.DB.prepare('SELECT COUNT(*) AS n FROM ebook_reader_state_v72').first();
    if(Number(count&&count.n||0)===0){
      try{const legacy=await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 ORDER BY updated_at ASC').all();for(const row of legacy.results||[]){const scope=scopeOf(String(row.book_key||''));if(!scope)continue;await env.DB.prepare('INSERT OR REPLACE INTO ebook_reader_state_v72(scope,book_key,cfi,percent,last_open_at,updated_at,source_client) VALUES(?1,?2,?3,?4,?5,?6,?7)').bind(scope,String(row.book_key||''),String(row.cfi||''),row.percent,Number(row.last_open_at||0),Number(row.updated_at||0),'v65-migration').run()}}catch(error){console.warn('R3_PROGRESS_V72_MIGRATE',error)}
    }
  })().catch(error=>{r3ProgressInitV72=null;throw error});
  return r3ProgressInitV72;
}
function r3ProgressRowV72(row){if(!row)return null;const raw=row.percent,n=raw===null||raw===undefined?NaN:Number(raw);return {scope:String(row.scope||scopeOf(String(row.book_key||''))||''),key:String(row.book_key||''),cfi:String(row.cfi||''),percent:Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null,last_open_at:Math.max(0,Number(row.last_open_at||0)),updated_at:Math.max(0,Number(row.updated_at||0)),source_client:String(row.source_client||''),state_version:'v72'}}
async function r3SelectProgressForKeyV72(env,key){const scope=scopeOf(key);if(!scope)return null;return env.DB.prepare('SELECT scope,book_key,cfi,percent,last_open_at,updated_at,source_client FROM ebook_reader_state_v72 WHERE scope=?1 LIMIT 1').bind(scope).first()}
async function r3UpsertProgressV72(env,input,requestSource=''){
  const key=String(input&&input.key||'');if(!isFinalEpub(key))return null;const scope=scopeOf(key);if(!scope)return null;
  const cfi=String(input&&input.cfi||'').slice(0,4096);const raw=input&&input.percent,pn=raw===null||raw===undefined||raw===''?NaN:Number(raw);const percent=Number.isFinite(pn)?Math.max(0,Math.min(100,Math.round(pn))):null;
  const stamp=Number(input&&((input.updated_at??input.updatedAt)));if(!Number.isFinite(stamp)||stamp<=0)return null;const updatedAt=Math.round(stamp),lastOpenAt=Math.max(0,Math.round(Number(input&&((input.last_open_at??input.lastOpenAt))||0)));const source=String(input&&input.source_client||requestSource||'').slice(0,40);
  const current=await r3SelectProgressForKeyV72(env,key);
  if(!current){await env.DB.prepare('INSERT INTO ebook_reader_state_v72(scope,book_key,cfi,percent,last_open_at,updated_at,source_client) VALUES(?1,?2,?3,?4,?5,?6,?7)').bind(scope,key,cfi,percent,lastOpenAt,updatedAt,source).run()}
  else if(updatedAt>Number(current.updated_at||0)){
    await env.DB.prepare('UPDATE ebook_reader_state_v72 SET book_key=?2,cfi=CASE WHEN ?3<>\'\' THEN ?3 ELSE cfi END,percent=CASE WHEN ?4 IS NOT NULL THEN ?4 ELSE percent END,last_open_at=MAX(last_open_at,?5),updated_at=?6,source_client=?7 WHERE scope=?1').bind(scope,key,cfi,percent,lastOpenAt,updatedAt,source).run();
  }else{
    await env.DB.prepare('UPDATE ebook_reader_state_v72 SET book_key=?2,last_open_at=MAX(last_open_at,?3) WHERE scope=?1').bind(scope,key,lastOpenAt).run();
  }
  return r3ProgressRowV72(await r3SelectProgressForKeyV72(env,key));
}
async function r3SnapshotProgressV72(env){if(!env.ARTIFACTS)return false;try{const result=await env.DB.prepare('SELECT scope,book_key,cfi,percent,last_open_at,updated_at,source_client FROM ebook_reader_state_v72 ORDER BY updated_at DESC LIMIT 2000').all();const items=(result.results||[]).map(r3ProgressRowV72),now=new Date(),day=now.toISOString().slice(0,10),payload=JSON.stringify({schema:2,version:'v72',generated_at:now.toISOString(),count:items.length,items},null,2)+'\n';await env.ARTIFACTS.put(ROOT+'_system/progress-v72/latest.json',payload,{httpMetadata:{contentType:'application/json'},customMetadata:{source:'ebook-progress-v72'}});await env.ARTIFACTS.put(ROOT+'_system/progress-v72/snapshots/'+day+'.json',payload,{httpMetadata:{contentType:'application/json'},customMetadata:{source:'ebook-progress-v72-daily'}});return true}catch(error){console.warn('R3_PROGRESS_SNAPSHOT_V72',error);return false}}
async function r3RenameProgressScopeV72(env,scope,newKey){if(!env.DB||!scope)return;await r3EnsureProgressTableV72(env);await env.DB.prepare('UPDATE ebook_reader_state_v72 SET book_key=?2 WHERE scope=?1').bind(scope,newKey).run()}
async function r3DeleteProgressScopeV72(env,scope){if(!env.DB||!scope)return;await r3EnsureProgressTableV72(env);await env.DB.prepare('DELETE FROM ebook_reader_state_v72 WHERE scope=?1').bind(scope).run();await r3SnapshotProgressV72(env)}
async function publicProgressV65(request,env){
  if(!(await hasBrowserLibrarySession(request,env)))return json({ok:false,error:'UNAUTHORIZED'},401);if(!env.DB)return json({ok:false,error:'DB_BINDING_MISSING'},503);
  try{await r3EnsureProgressTableV72(env)}catch(error){return json({ok:false,error:'PROGRESS_DB_INIT_FAILED',detail:String(error&&error.message||error)},503)}
  const url=new URL(request.url);if(request.method==='GET'){const key=String(url.searchParams.get('key')||'');if(key){if(!isFinalEpub(key))return json({ok:false,error:'FINAL_EPUB_ONLY'},403);return json({ok:true,progress:r3ProgressRowV72(await r3SelectProgressForKeyV72(env,key)),recovery_version:'v72',canonical:'d1-scope'})}const result=await env.DB.prepare('SELECT scope,book_key,cfi,percent,last_open_at,updated_at,source_client FROM ebook_reader_state_v72 ORDER BY updated_at DESC LIMIT 2000').all();return json({ok:true,items:(result.results||[]).map(r3ProgressRowV72),recovery_version:'v72',canonical:'d1-scope'})}
  if(request.method!=='POST')return json({ok:false,error:'METHOD_NOT_ALLOWED'},405);let body;try{body=await request.json()}catch{return json({ok:false,error:'INVALID_JSON'},400)}const inputs=Array.isArray(body&&body.items)?body.items:[body];if(!inputs.length||inputs.length>100)return json({ok:false,error:'INVALID_PROGRESS_BATCH'},400);const source=String(body&&body.source_client||'').slice(0,40),saved=[];for(const input of inputs){const row=await r3UpsertProgressV72(env,input,source);if(row)saved.push(row)}if(!saved.length)return json({ok:false,error:'NO_VALID_PROGRESS_ROWS'},400);await r3SnapshotProgressV72(env);return json({ok:true,accepted:saved.length,items:saved,recovery_version:'v72',canonical:'d1-scope'})
}

function r3CleanRenameV65'''
simple=simple[:m.start()]+new_server+simple[m.end():]

# Rename/delete must update stable scope state too.
old="try{await r3MoveProgressV65(env,key,newKey)}catch(error){console.warn('R3_PROGRESS_RENAME_V65',error)}await env.ARTIFACTS.delete(key);"
new="try{await r3MoveProgressV65(env,key,newKey)}catch(error){console.warn('R3_PROGRESS_RENAME_V65',error)}try{await r3RenameProgressScopeV72(env,scope,newKey)}catch(error){console.warn('R3_PROGRESS_RENAME_V72',error)}await env.ARTIFACTS.delete(key);"
if old not in simple: raise SystemExit('V72_RENAME_PROGRESS_ANCHOR_MISSING')
simple=simple.replace(old,new,1)
old="if(env.DB){try{await r3EnsureProgressTableV65(env);await env.DB.prepare(\"DELETE FROM ebook_reader_progress_v65 WHERE book_key LIKE ?1\").bind(ROOT+scope+'/final/%').run()}catch(error){console.warn('R3_PROGRESS_DELETE_V65',error)}}await r3InvalidateLibraryFastIndexV65(env,'delete');"
new="if(env.DB){try{await r3EnsureProgressTableV65(env);await env.DB.prepare(\"DELETE FROM ebook_reader_progress_v65 WHERE book_key LIKE ?1\").bind(ROOT+scope+'/final/%').run()}catch(error){console.warn('R3_PROGRESS_DELETE_V65',error)}try{await r3DeleteProgressScopeV72(env,scope)}catch(error){console.warn('R3_PROGRESS_DELETE_V72',error)}}await r3InvalidateLibraryFastIndexV65(env,'delete');"
if old not in simple: raise SystemExit('V72_DELETE_PROGRESS_ANCHOR_MISSING')
simple=simple.replace(old,new,1)

# ---------------- Metadata/cache invariants. ----------------
simple=simple.replace("const R3_LIBRARY_FAST_INDEX_MAX_AGE_MS_V65 = 5 * 60 * 1000;","const R3_LIBRARY_FAST_INDEX_MAX_AGE_MS_V65 = 5 * 60 * 1000;\nconst R3_LIBRARY_FAST_INDEX_SCHEMA_V72 = 2;",1)
simple=simple.replace("if(!data||data.schema!==1||!Array.isArray(data.objects))return null;","if(!data||data.schema!==R3_LIBRARY_FAST_INDEX_SCHEMA_V72||!Array.isArray(data.objects))return null;",1)
simple=simple.replace("const payload={schema:1,generated_at_ms:generatedAt,count:Array.isArray(objects)?objects.length:0,objects:Array.isArray(objects)?objects:[]};","const payload={schema:R3_LIBRARY_FAST_INDEX_SCHEMA_V72,generated_at_ms:generatedAt,count:Array.isArray(objects)?objects.length:0,objects:Array.isArray(objects)?objects:[]};",1)

# Restore the v56 enrich server contract that v65's broad publicList replacement accidentally removed.
# The route existed while the handler/helpers were missing, which allowed raw EPUB upload to succeed
# while title/author/cover publication failed. v72 makes handler presence a deploy invariant.
anchor="async function publicRawEpubV57(request, env) {"
if anchor not in simple: raise SystemExit('V72_RAW_ROUTE_ANCHOR_MISSING')
enrich_server=r'''
const SIMPLE_EPUB_COVER_MAX_BYTES_V72 = 12 * 1024 * 1024;
function catalogTextV72(value,max=300){return String(value||'').normalize('NFC').replace(/[\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').trim().slice(0,max)}
function coverTypeV72(file){const type=String(file&&file.type||'').toLowerCase();if(type==='image/png')return ['.png','image/png'];if(type==='image/webp')return ['.webp','image/webp'];if(type==='image/gif')return ['.gif','image/gif'];if(type==='image/jpeg'||type==='image/jpg')return ['.jpg','image/jpeg'];return null}
async function readCatalogDocumentV56(env){let data={version:2,generated_at:new Date().toISOString(),books:{}};try{const object=await env.ARTIFACTS.get(LIBRARY_CATALOG_INDEX_KEY);if(object){const parsed=await object.json();if(parsed&&typeof parsed==='object')data=parsed}}catch{}if(!data.books||typeof data.books!=='object')data.books={};return data}
async function r3SnapshotCatalogV72(env,catalog){if(!env.ARTIFACTS||!catalog)return false;try{const now=new Date(),day=now.toISOString().slice(0,10),payload=JSON.stringify({...catalog,snapshot_version:'v72',snapshot_at:now.toISOString()},null,2)+'\n';await env.ARTIFACTS.put(ROOT+'_system/catalog-v72/latest.json',payload,{httpMetadata:{contentType:'application/json'},customMetadata:{source:'ebook-catalog-v72'}});await env.ARTIFACTS.put(ROOT+'_system/catalog-v72/snapshots/'+day+'.json',payload,{httpMetadata:{contentType:'application/json'},customMetadata:{source:'ebook-catalog-v72-daily'}});return true}catch(error){console.warn('R3_CATALOG_SNAPSHOT_V72',error);return false}}
async function publicEnrichUpload(request,env){
  if(request.method!=='POST')return json({ok:false,error:'METHOD_NOT_ALLOWED'},405);
  if(!(await hasBrowserLibrarySession(request,env)))return json({ok:false,error:'UNAUTHORIZED'},401);
  if(request.headers.get('x-runner3-library')!=='1')return json({ok:false,error:'BAD_LIBRARY_REQUEST'},400);
  if(!env.ARTIFACTS)return json({ok:false,error:'R2_NOT_BOUND'},503);
  let form;try{form=await request.formData()}catch{return json({ok:false,error:'INVALID_FORM_DATA'},400)}
  const key=String(form.get('key')||'');if(!isFinalEpub(key))return json({ok:false,error:'FINAL_EPUB_ONLY'},403);if(!(await env.ARTIFACTS.head(key)))return json({ok:false,error:'EPUB_NOT_FOUND'},404);const scope=scopeOf(key);if(!scope)return json({ok:false,error:'INVALID_SCOPE'},400);
  const title=catalogTextV72(form.get('title'),500),creator=catalogTextV72(form.get('creator'),300),cover=form.get('cover');let coverKey='',coverContentType='';
  if(cover&&typeof cover.stream==='function'&&Number(cover.size||0)>0){if(Number(cover.size||0)>SIMPLE_EPUB_COVER_MAX_BYTES_V72)return json({ok:false,error:'COVER_TOO_LARGE',max_bytes:SIMPLE_EPUB_COVER_MAX_BYTES_V72},413);const resolved=coverTypeV72(cover);if(!resolved)return json({ok:false,error:'UNSUPPORTED_COVER_TYPE'},415);const [ext,type]=resolved;coverKey=ROOT+scope+'/meta/cover'+ext;coverContentType=type;await env.ARTIFACTS.put(coverKey,cover.stream(),{httpMetadata:{contentType:type},customMetadata:{source:'artifact-library-upload-v72'}})}
  const catalog=await readCatalogDocumentV56(env),previous=catalog.books[scope]&&typeof catalog.books[scope]==='object'?catalog.books[scope]:{},entry={...previous,epub_key:key};if(title)entry.title=title;if(creator)entry.creator=creator;if(coverKey){entry.cover_key=coverKey;entry.cover_type=coverContentType;entry.cover_bytes=Number(cover.size||0);delete entry.cover_missing_reason}catalog.version=Math.max(2,Number(catalog.version||1));catalog.generated_at=new Date().toISOString();catalog.books[scope]=entry;
  const sidecar={bookKey:key,display_title:entry.title||'',author:entry.creator||'',cover_key:entry.cover_key||'',updated_at:catalog.generated_at,source:'upload-enrich-v72'};await env.ARTIFACTS.put(ROOT+scope+'/meta/book.json',JSON.stringify(sidecar,null,2)+'\n',{httpMetadata:{contentType:'application/json'}});await env.ARTIFACTS.put(LIBRARY_CATALOG_INDEX_KEY,JSON.stringify(catalog,null,2)+'\n',{httpMetadata:{contentType:'application/json'}});await r3SnapshotCatalogV72(env,catalog);await r3InvalidateLibraryFastIndexV65(env,'enrich');
  const check=await readCatalogDocumentV56(env),saved=check.books&&check.books[scope]||null;if(!saved||String(saved.epub_key||'')!==key)return json({ok:false,error:'CATALOG_READBACK_FAILED'},502);if(title&&String(saved.title||'')!==title)return json({ok:false,error:'TITLE_READBACK_FAILED'},502);if(creator&&String(saved.creator||'')!==creator)return json({ok:false,error:'CREATOR_READBACK_FAILED'},502);if(coverKey&&String(saved.cover_key||'')!==coverKey)return json({ok:false,error:'COVER_READBACK_FAILED'},502);
  return json({ok:true,key,scope,title:entry.title||'',creator:entry.creator||'',cover_key:entry.cover_key||null,enrich_version:'v72',readback:true},200)
}

'''
# Preferred path after v65 root fix: upgrade the preserved v56 helper+handler block in place.
legacy_enrich_re=re.compile(r"const SIMPLE_EPUB_COVER_MAX_BYTES_V56 = .*?\n\nasync function publicUpload",re.S)
legacy_match=legacy_enrich_re.search(simple)
if legacy_match:
    simple=simple[:legacy_match.start()]+enrich_server+'async function publicUpload'+simple[legacy_match.end():]
elif 'async function publicEnrichUpload(request, env)' in simple:
    raise SystemExit('V72_ENRICH_LEGACY_BLOCK_SHAPE_CHANGED')
elif 'async function publicEnrichUpload(request,env)' not in simple:
    # Backward-compatible recovery path for old generated trees where v65 already deleted v56.
    simple=simple.replace(anchor,enrich_server+anchor,1)
else:
    raise SystemExit('V72_ENRICH_HANDLER_DUPLICATE')

# Snapshot all rename/delete catalog writes too.
old="async function r3WriteCatalogV65(env,catalog){catalog.version=Math.max(1,Number(catalog.version||1));catalog.generated_at=new Date().toISOString();await env.ARTIFACTS.put(LIBRARY_CATALOG_INDEX_KEY,JSON.stringify(catalog,null,2)+'\\n',{httpMetadata:{contentType:'application/json'}})}"
new="async function r3WriteCatalogV65(env,catalog){catalog.version=Math.max(2,Number(catalog.version||1));catalog.generated_at=new Date().toISOString();await env.ARTIFACTS.put(LIBRARY_CATALOG_INDEX_KEY,JSON.stringify(catalog,null,2)+'\\n',{httpMetadata:{contentType:'application/json'}});await r3SnapshotCatalogV72(env,catalog)}"
if old not in simple: raise SystemExit('V72_CATALOG_WRITE_ANCHOR_MISSING')
simple=simple.replace(old,new,1)

# EPUB upload metadata: if no formal cover marker exists, inspect the first spine document image.
extract_re=re.compile(r"  async function extractUploadMetadataV56\(file\)\{.*?return \{title,creator,cover\}\}\n",re.S)
m=extract_re.search(simple)
if not m: raise SystemExit('V72_EXTRACTOR_ANCHOR_MISSING')
new_extract=r'''  async function extractUploadMetadataV56(file){
    if(!window.JSZip||typeof window.JSZip.loadAsync!=='function')throw new Error('ZIP_ENGINE_MISSING');const zip=await window.JSZip.loadAsync(file);const containerEntry=zip.file('META-INF/container.xml')||Object.values(zip.files).find(x=>String(x&&x.name||'').toLowerCase()==='meta-inf/container.xml');if(!containerEntry)throw new Error('EPUB_CONTAINER_MISSING');const parser=new DOMParser();const container=parser.parseFromString(await containerEntry.async('text'),'application/xml');const rootNode=xmlElementsV56(container,'rootfile')[0];const rootfile=String(rootNode&&rootNode.getAttribute('full-path')||'').trim();if(!rootfile)throw new Error('EPUB_ROOTFILE_MISSING');let opfEntry=zip.file(rootfile);if(!opfEntry){let decoded=rootfile;try{decoded=decodeURIComponent(rootfile)}catch{}opfEntry=zip.file(decoded)}if(!opfEntry)throw new Error('EPUB_OPF_MISSING');const opf=parser.parseFromString(await opfEntry.async('text'),'application/xml');const title=xmlFirstTextV56(opf,'title');const creator=xmlFirstTextV56(opf,'creator');const base=rootfile.includes('/')?rootfile.slice(0,rootfile.lastIndexOf('/')):'';const items=xmlElementsV56(opf,'item').map(node=>({id:String(node.getAttribute('id')||''),href:String(node.getAttribute('href')||''),type:String(node.getAttribute('media-type')||''),props:String(node.getAttribute('properties')||'').split(/\s+/).filter(Boolean)}));let coverId='';for(const node of xmlElementsV56(opf,'meta'))if(String(node.getAttribute('name')||'').toLowerCase()==='cover'){coverId=String(node.getAttribute('content')||'');break}let coverItem=items.find(x=>x.props.includes('cover-image'))||items.find(x=>coverId&&x.id===coverId)||items.find(x=>x.type.startsWith('image/')&&/cover/i.test(x.id+' '+x.href))||null;
    if(!coverItem){const firstRef=xmlElementsV56(opf,'itemref').map(node=>String(node.getAttribute('idref')||'')).find(Boolean),spineItem=items.find(x=>x.id===firstRef);if(spineItem&&spineItem.href){try{const pagePath=zipJoinV56(base,spineItem.href),pageEntry=zip.file(pagePath)||zip.file(decodeURIComponent(pagePath));if(pageEntry){const page=parser.parseFromString(await pageEntry.async('text'),'text/html'),img=page.querySelector('img[src]');if(img){const href=String(img.getAttribute('src')||'');const pageBase=pagePath.includes('/')?pagePath.slice(0,pagePath.lastIndexOf('/')):'';const imagePath=zipJoinV56(pageBase,href);const normalized=items.find(x=>x.type.startsWith('image/')&&zipJoinV56(base,x.href)===imagePath);coverItem=normalized||{id:'spine-first-image-v72',href:imagePath,type:/\.png$/i.test(imagePath)?'image/png':/\.webp$/i.test(imagePath)?'image/webp':/\.gif$/i.test(imagePath)?'image/gif':'image/jpeg',absolute:true}}}}catch{}}
    }
    if(!coverItem)coverItem=items.find(x=>x.type.startsWith('image/'))||null;let cover=null;if(coverItem&&coverItem.href){const path=coverItem.absolute?coverItem.href:zipJoinV56(base,coverItem.href);let entry=zip.file(path);if(!entry){let decoded=path;try{decoded=decodeURIComponent(path)}catch{}entry=zip.file(decoded)}if(entry){const bytes=await entry.async('uint8array');if(bytes&&bytes.byteLength){const type=coverItem.type&&coverItem.type.startsWith('image/')?coverItem.type:'image/jpeg';cover=new Blob([bytes],{type})}}}return {title,creator,cover,cover_source:coverItem&&coverItem.id==='spine-first-image-v72'?'spine-first-image':'manifest'}
  }
'''
simple=simple[:m.start()]+new_extract+simple[m.end():]

# ---------------- Reader: do not re-stamp stale local state on boot; foreground pulls newer server state. ----------------
reader_re=re.compile(r"  let r3ProgressSyncTimerV65=0;.*?\n  function r3MigrateReaderLocalKeyV65",re.S)
m=reader_re.search(reader)
if not m: raise SystemExit('V72_READER_SYNC_ANCHOR_MISSING')
new_reader=r'''  const R3_READER_UNIFIED_STATE_V72='v72';
  const R3_READER_CLIENT_KIND_V72=(window.navigator&&window.navigator.standalone===true)?'home-screen':'browser';
  let r3ProgressSyncTimerV65=0,r3ProgrammaticSyncV72=false,r3VisibleReaderSyncBusyV72=false,r3LastReaderVisibleSyncV72=0;
  async function r3FetchRemoteProgressV65(bookKey){try{const response=await fetch('/artifact-library/api/progress?key='+encodeURIComponent(bookKey),{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}});if(!response.ok)return null;const data=await response.json();return data&&data.ok===true?data.progress:null}catch{return null}}
  async function r3PostProgressV65(row){try{const response=await fetch('/artifact-library/api/progress',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({...row,source_client:R3_READER_CLIENT_KIND_V72}),keepalive:true});if(!response.ok)return null;const data=await response.json().catch(()=>null);return data&&Array.isArray(data.items)?data.items[0]||null:null}catch{return null}}
  function r3ReadLocalProgressV65(bookKey){try{return JSON.parse(localStorage.getItem(R3_READER_PROGRESS_PREFIX_V54+bookKey)||'null')||null}catch{return null}}
  function r3ApplyRemoteProgressV65(bookKey,remote,force=false){if(!remote||!bookKey)return false;const local=r3ReadLocalProgressV65(bookKey),localUpdated=Number(local&&local.updatedAt||0),remoteUpdated=Number(remote.updated_at||0);if(!force&&!(remoteUpdated>localUpdated))return false;try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+bookKey,JSON.stringify({percent:remote.percent,cfi:String(remote.cfi||''),updatedAt:remoteUpdated,lastOpenAt:Number(remote.last_open_at||0),syncedBy:'v72-server'}));if(remote.cfi)localStorage.setItem('r3-reader-position:'+bookKey,String(remote.cfi));return true}catch{return false}}
  async function r3MergeRemoteProgressV65(){const remote=await r3FetchRemoteProgressV65(key);if(remote){r3ApplyRemoteProgressV65(key,remote,true);return String(remote.cfi||localStorage.getItem(keys.position)||'')}const local=r3ReadLocalProgressV65(key),cfi=String(local&&local.cfi||localStorage.getItem(keys.position)||''),percent=local&&local.percent!==undefined?local.percent:null;if(cfi||percent!==null){const stamp=Math.max(1,Number(local&&local.updatedAt||local&&local.lastOpenAt||Date.now()));const seeded=await r3PostProgressV65({key,cfi,percent,last_open_at:Number(local&&local.lastOpenAt||0),updated_at:stamp,legacy_seed:true});if(seeded)r3ApplyRemoteProgressV65(key,seeded,true)}return cfi}
  function r3ScheduleProgressSyncV65(percent,cfi){clearTimeout(r3ProgressSyncTimerV65);if(r3ProgrammaticSyncV72||window.__R3_BASE_READER_BOOT_DONE!==true)return;const now=Date.now();r3ProgressSyncTimerV65=setTimeout(async()=>{const saved=await r3PostProgressV65({key,cfi:String(cfi||''),percent,last_open_at:now,updated_at:now});if(saved)r3ApplyRemoteProgressV65(key,saved,false)},700)}
  async function r3HydrateLiveProgressV65(){try{const response=await fetch('/artifact-library/api/progress',{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}});if(!response.ok)return;const data=await response.json();if(!data||data.ok!==true||!Array.isArray(data.items))return;for(const remote of data.items)r3ApplyRemoteProgressV65(String(remote&&remote.key||''),remote)}catch{}}
  async function r3SyncReaderVisibleV72(){if(document.hidden||!rendition||r3VisibleReaderSyncBusyV72)return;const now=Date.now();if(now-r3LastReaderVisibleSyncV72<900)return;r3LastReaderVisibleSyncV72=now;r3VisibleReaderSyncBusyV72=true;try{const remote=await r3FetchRemoteProgressV65(key);if(!remote)return;const local=r3ReadLocalProgressV65(key);if(Number(remote.updated_at||0)<=Number(local&&local.updatedAt||0))return;const target=String(remote.cfi||'');r3ApplyRemoteProgressV65(key,remote,true);if(target){let current='';try{current=String(rendition.currentLocation()?.start?.cfi||'')}catch{}if(current!==target){r3ProgrammaticSyncV72=true;try{await rendition.display(target)}catch{}finally{await new Promise(resolve=>requestAnimationFrame(resolve));r3ProgrammaticSyncV72=false}}}}finally{r3VisibleReaderSyncBusyV72=false}}
  function r3MigrateReaderLocalKeyV65'''
reader=reader[:m.start()]+new_reader+reader[m.end():]

old="document.addEventListener('visibilitychange',()=>{if(document.hidden)hideControls();});"
new="document.addEventListener('visibilitychange',()=>{if(document.hidden)hideControls();else r3SyncReaderVisibleV72()});window.addEventListener('focus',()=>r3SyncReaderVisibleV72());"
if old not in reader: raise SystemExit('V72_READER_VISIBILITY_ANCHOR_MISSING')
reader=reader.replace(old,new,1)

# Expose the real client contract version for live canaries and stale-runtime reload logic.
simple=simple.replace("reader_client_version:'v65'","reader_client_version:'v72'",1).replace("'x-r3-reader-client-version':'v65'","'x-r3-reader-client-version':'v72'",1)
reader=reader.replace("const R3_READER_CLIENT_VERSION_V63='v65';","const R3_READER_CLIENT_VERSION_V63='v72';",1)

# Metadata publish retries transient failures; server readback remains authoritative.
old_enrich="  async function enrichUploadedBookV56(bookKey,meta){const form=new FormData();form.append('key',bookKey);form.append('title',String(meta&&meta.title||''));form.append('creator',String(meta&&meta.creator||''));if(meta&&meta.cover instanceof Blob&&meta.cover.size)form.append('cover',meta.cover,coverFilenameV56(meta.cover));const r=await fetch('/artifact-library/api/enrich-upload',{method:'POST',headers:{'x-runner3-library':'1'},body:form});const data=await r.json();if(!r.ok||data.ok!==true)throw new Error(data.error||('HTTP '+r.status));return data}"
new_enrich="  async function enrichUploadedBookV56(bookKey,meta){let last=null;for(let attempt=1;attempt<=3;attempt++){const form=new FormData();form.append('key',bookKey);form.append('title',String(meta&&meta.title||''));form.append('creator',String(meta&&meta.creator||''));if(meta&&meta.cover instanceof Blob&&meta.cover.size)form.append('cover',meta.cover,coverFilenameV56(meta.cover));try{const r=await fetch('/artifact-library/api/enrich-upload',{method:'POST',headers:{'x-runner3-library':'1','x-r3-enrich-client':'v72'},body:form});const data=await r.json().catch(()=>({}));if(r.ok&&data.ok===true&&data.readback===true)return data;last=new Error(data.error||('HTTP '+r.status))}catch(error){last=error}if(attempt<3)await new Promise(resolve=>setTimeout(resolve,350*attempt))}throw last||new Error('ENRICH_READBACK_FAILED')}"
if old_enrich not in simple: raise SystemExit('V72_ENRICH_CLIENT_ANCHOR_MISSING')
simple=simple.replace(old_enrich,new_enrich,1)

for marker in ["R3_UNIFIED_STATE_V72='v72'","ebook_reader_state_v72","canonical:'d1-scope'","R3_LIBRARY_FAST_INDEX_SCHEMA_V72 = 2","r3SnapshotCatalogV72","r3-library-fast-list-v72","spine-first-image-v72","r3SyncVisibleV72"]:
    if marker not in simple: raise SystemExit('V72_SIMPLE_MARKER_MISSING:'+marker)
for marker in ["R3_READER_UNIFIED_STATE_V72='v72'","window.__R3_BASE_READER_BOOT_DONE!==true","r3SyncReaderVisibleV72","source_client:R3_READER_CLIENT_KIND_V72"]:
    if marker not in reader: raise SystemExit('V72_READER_MARKER_MISSING:'+marker)

SIMPLE.write_text(simple,encoding='utf-8')
READER.write_text(reader,encoding='utf-8')
print('READER_V72_UNIFIED_STATE=PASS')
