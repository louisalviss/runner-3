from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
text = SIMPLE.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# Load the same vendored engines already used by Reader so Library can inspect an
# uploaded EPUB locally and calculate legacy progress without a Reader navigation.
script_anchor = '<div id="status" class="status" aria-live="polite"></div><section id="list" class="list"></section></main>\n<script>\n(() => {'
script_replacement = '<div id="status" class="status" aria-live="polite"></div><section id="list" class="list"></section></main>\n<script src="/artifact-library/vendor/jszip.min.js"></script>\n<script src="/artifact-library/vendor/epub.min.js"></script>\n<script>\n(() => {'
if 'data-r3-library-v56' not in text:
    if script_anchor not in text:
        raise SystemExit('v56 library script anchor missing')
    text = text.replace(script_anchor, script_replacement, 1)
    text = text.replace('<main class="shell">', '<main class="shell" data-r3-library-v56="1">', 1)

browser_helpers = r'''
  const EPUB_CACHE_DB_V56='r3-reader-epub-cache-v49',EPUB_CACHE_STORE_V56='books';
  let epubCacheDbPromiseV56=null,legacyMigrationRunningV56=false;
  function openEpubCacheV56(){if(epubCacheDbPromiseV56)return epubCacheDbPromiseV56;epubCacheDbPromiseV56=new Promise((resolve,reject)=>{if(!('indexedDB' in window)){reject(new Error('INDEXEDDB_UNAVAILABLE'));return}const req=indexedDB.open(EPUB_CACHE_DB_V56,1);req.onupgradeneeded=()=>{const db=req.result;if(!db.objectStoreNames.contains(EPUB_CACHE_STORE_V56))db.createObjectStore(EPUB_CACHE_STORE_V56,{keyPath:'key'})};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error('INDEXEDDB_OPEN_FAILED'))}).catch(()=>null);return epubCacheDbPromiseV56}
  async function cachedEpubBufferV56(bookKey){try{const db=await openEpubCacheV56();if(!db)return null;const row=await new Promise((resolve,reject)=>{const tx=db.transaction(EPUB_CACHE_STORE_V56,'readonly');const req=tx.objectStore(EPUB_CACHE_STORE_V56).get(bookKey);req.onsuccess=()=>resolve(req.result||null);req.onerror=()=>reject(req.error)});return row&&row.buffer instanceof ArrayBuffer&&row.buffer.byteLength>64?row.buffer:null}catch{return null}}
  async function deliveryEpubBufferV56(bookKey){const d=await fetch('/artifact-library/api/delivery',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key:bookKey,ttl_seconds:900})});const payload=await d.json();if(!d.ok||payload.ok!==true||!payload.delivery?.url)throw new Error(payload.error||('HTTP '+d.status));const r=await fetch(payload.delivery.url,{cache:'no-store'});if(!r.ok)throw new Error('EPUB HTTP '+r.status);return r.arrayBuffer()}
  async function migrateLegacyBookV56(bookRow){const p=progressFor(bookRow);if(!p.started||p.percent!==null)return false;let cfi='';try{cfi=localStorage.getItem(POSITION_PREFIX+bookRow.key)||''}catch{}if(!cfi||typeof window.ePub!=='function')return false;let epub=null;try{const buffer=(await cachedEpubBufferV56(bookRow.key))||(await deliveryEpubBufferV56(bookRow.key));epub=window.ePub(buffer);await epub.ready;await epub.locations.generate(1600);const raw=epub.locations.percentageFromCfi(cfi);if(!Number.isFinite(raw))return false;const pct=Math.max(0,Math.min(100,Math.round(raw*100)));localStorage.setItem(PROGRESS_PREFIX+bookRow.key,JSON.stringify({percent:pct,cfi,updatedAt:Date.now(),migratedBy:'library-v56'}));return true}catch{return false}finally{try{if(epub&&typeof epub.destroy==='function')epub.destroy()}catch{}}}
  async function migrateLegacyProgressV56(){if(legacyMigrationRunningV56||typeof window.ePub!=='function')return;const targets=state.books.filter(bookRow=>{const p=progressFor(bookRow);return p.started&&p.percent===null});if(!targets.length)return;legacyMigrationRunningV56=true;let changed=0;try{for(let i=0;i<targets.length;i++){status('Đang đồng bộ tiến độ cũ · '+(i+1)+'/'+targets.length);if(await migrateLegacyBookV56(targets[i])){changed++;render()}await new Promise(resolve=>setTimeout(resolve,80))}}finally{legacyMigrationRunningV56=false;status(changed?'Đã đồng bộ tiến độ '+changed+' sách.':'');if(changed)setTimeout(()=>status(''),1600)}}

  function zipJoinV56(base,href){let value=String(href||'').replace(/\\/g,'/').split('#')[0].split('?')[0];try{value=decodeURIComponent(value)}catch{}const parts=String(base||'').split('/').filter(Boolean);for(const part of value.split('/')){if(!part||part==='.')continue;if(part==='..')parts.pop();else parts.push(part)}return parts.join('/')}
  function xmlFirstTextV56(doc,local){const nodes=doc.getElementsByTagNameNS?doc.getElementsByTagNameNS('*',local):[];for(const node of nodes){const value=String(node&&node.textContent||'').trim();if(value)return value}return ''}
  function xmlElementsV56(doc,local){return Array.from(doc.getElementsByTagNameNS?doc.getElementsByTagNameNS('*',local):[])}
  async function extractUploadMetadataV56(file){if(!window.JSZip||typeof window.JSZip.loadAsync!=='function')throw new Error('ZIP_ENGINE_MISSING');const zip=await window.JSZip.loadAsync(file);const containerEntry=zip.file('META-INF/container.xml')||Object.values(zip.files).find(x=>String(x&&x.name||'').toLowerCase()==='meta-inf/container.xml');if(!containerEntry)throw new Error('EPUB_CONTAINER_MISSING');const parser=new DOMParser();const container=parser.parseFromString(await containerEntry.async('text'),'application/xml');const rootNode=xmlElementsV56(container,'rootfile')[0];const rootfile=String(rootNode&&rootNode.getAttribute('full-path')||'').trim();if(!rootfile)throw new Error('EPUB_ROOTFILE_MISSING');let opfEntry=zip.file(rootfile);if(!opfEntry){let decoded=rootfile;try{decoded=decodeURIComponent(rootfile)}catch{}opfEntry=zip.file(decoded)}if(!opfEntry)throw new Error('EPUB_OPF_MISSING');const opf=parser.parseFromString(await opfEntry.async('text'),'application/xml');const title=xmlFirstTextV56(opf,'title');const creator=xmlFirstTextV56(opf,'creator');const items=xmlElementsV56(opf,'item').map(node=>({id:String(node.getAttribute('id')||''),href:String(node.getAttribute('href')||''),type:String(node.getAttribute('media-type')||''),props:String(node.getAttribute('properties')||'').split(/\s+/).filter(Boolean)}));let coverId='';for(const node of xmlElementsV56(opf,'meta'))if(String(node.getAttribute('name')||'').toLowerCase()==='cover'){coverId=String(node.getAttribute('content')||'');break}let coverItem=items.find(x=>x.props.includes('cover-image'))||items.find(x=>coverId&&x.id===coverId)||items.find(x=>x.type.startsWith('image/')&&/cover/i.test(x.id+' '+x.href))||null;let cover=null;if(coverItem&&coverItem.href){const base=rootfile.includes('/')?rootfile.slice(0,rootfile.lastIndexOf('/')):'';const path=zipJoinV56(base,coverItem.href);let entry=zip.file(path);if(!entry){let encoded=path;try{encoded=decodeURIComponent(path)}catch{}entry=zip.file(encoded)}if(entry){const bytes=await entry.async('uint8array');if(bytes&&bytes.byteLength){const type=coverItem.type&&coverItem.type.startsWith('image/')?coverItem.type:'image/jpeg';cover=new Blob([bytes],{type})}}}return {title,creator,cover}}
  function coverFilenameV56(blob){const type=String(blob&&blob.type||'').toLowerCase();if(type==='image/png')return 'cover.png';if(type==='image/webp')return 'cover.webp';if(type==='image/gif')return 'cover.gif';return 'cover.jpg'}
  async function enrichUploadedBookV56(bookKey,meta){const form=new FormData();form.append('key',bookKey);form.append('title',String(meta&&meta.title||''));form.append('creator',String(meta&&meta.creator||''));if(meta&&meta.cover instanceof Blob&&meta.cover.size)form.append('cover',meta.cover,coverFilenameV56(meta.cover));const r=await fetch('/artifact-library/api/enrich-upload',{method:'POST',headers:{'x-runner3-library':'1'},body:form});const data=await r.json();if(!r.ok||data.ok!==true)throw new Error(data.error||('HTTP '+r.status));return data}
'''

upload_start = text.find('  function uploadEpub(file){')
if upload_start < 0:
    raise SystemExit('v56 upload function start missing')
if 'async function migrateLegacyProgressV56()' not in text:
    text = text[:upload_start] + browser_helpers + '\n' + text[upload_start:]

upload_start = text.find('  function uploadEpub(file){')
upload_end = text.find("\n  $('uploadEpub').addEventListener", upload_start)
if upload_start < 0 or upload_end < 0:
    raise SystemExit('v56 upload function boundaries missing')
new_upload = r'''  async function uploadEpub(file){
    if(!file)return;if(!/\.epub$/i.test(file.name||'')){status('Chỉ nhận file .epub');return}if(Number(file.size||0)>90*1024*1024){status('EPUB vượt giới hạn 90 MiB.');return}
    const button=$('uploadEpub');button.disabled=true;button.textContent='Đang đọc…';status('Đang đọc metadata và cover từ '+file.name+'…');
    let extracted={title:'',creator:'',cover:null};try{extracted=await extractUploadMetadataV56(file)}catch(error){console.warn('V56_EPUB_METADATA_PARSE',error)}
    button.textContent='Uploading…';status('Uploading '+file.name+'…');
    const xhr=new XMLHttpRequest();xhr.open('POST','/artifact-library/api/upload',true);xhr.setRequestHeader('x-runner3-library','1');xhr.setRequestHeader('x-r3-filename',encodeURIComponent(file.name));xhr.setRequestHeader('content-type','application/epub+zip');xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.max(0,Math.min(100,Math.round(e.loaded/e.total*100)));status('Uploading '+file.name+' · '+pct+'%')}};xhr.onerror=()=>{button.disabled=false;button.textContent='＋ EPUB';status('Upload failed: network error')};xhr.onload=async()=>{let data={};try{data=JSON.parse(xhr.responseText||'{}')}catch{}if(xhr.status===401){button.disabled=false;button.textContent='＋ EPUB';status('Upload cần Library PIN session. Reload rồi đăng nhập lại.');return}if(xhr.status<200||xhr.status>=300||data.ok!==true){button.disabled=false;button.textContent='＋ EPUB';status('Upload failed: '+(data.error||('HTTP '+xhr.status)));return}try{status('Đã upload EPUB · đang lưu tên và cover…');await enrichUploadedBookV56(data.key,extracted);status('Đã upload + cập nhật metadata/cover.')}catch(error){status('Đã upload EPUB; metadata/cover dùng fallback: '+String(error&&error.message||error))}finally{button.disabled=false;button.textContent='＋ EPUB';await load()}};xhr.send(file)
  }'''
text = text[:upload_start] + new_upload + text[upload_end:]

# Start a non-blocking legacy migration after a successful list load.
old_load_tail = "state.books=Array.isArray(data.objects)?data.objects:[];status('');render();hydrateMeta()}catch(e)"
new_load_tail = "state.books=Array.isArray(data.objects)?data.objects:[];status('');render();hydrateMeta();setTimeout(()=>migrateLegacyProgressV56(),700)}catch(e)"
if 'setTimeout(()=>migrateLegacyProgressV56(),700)' not in text:
    text = replace_once(text, old_load_tail, new_load_tail, 'legacy migration load hook')

server_helpers = r'''
const SIMPLE_EPUB_COVER_MAX_BYTES_V56 = 12 * 1024 * 1024;

function catalogTextV56(value,max=300){return String(value||'').normalize('NFC').replace(/[\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').trim().slice(0,max)}
function coverTypeV56(file){const type=String(file&&file.type||'').toLowerCase();if(type==='image/png')return ['.png','image/png'];if(type==='image/webp')return ['.webp','image/webp'];if(type==='image/gif')return ['.gif','image/gif'];if(type==='image/jpeg'||type==='image/jpg')return ['.jpg','image/jpeg'];return null}
async function readCatalogDocumentV56(env){let data={version:1,generated_at:new Date().toISOString(),books:{}};try{const object=await env.ARTIFACTS.get(LIBRARY_CATALOG_INDEX_KEY);if(object){const parsed=await object.json();if(parsed&&typeof parsed==='object')data=parsed}}catch{}if(!data.books||typeof data.books!=='object')data.books={};return data}

async function publicEnrichUpload(request, env) {
  if (request.method !== 'POST') return json({ ok: false, error: 'METHOD_NOT_ALLOWED' }, 405);
  if (!(await hasBrowserLibrarySession(request, env))) return json({ ok: false, error: 'UNAUTHORIZED' }, 401);
  if (request.headers.get('x-runner3-library') !== '1') return json({ ok: false, error: 'BAD_LIBRARY_REQUEST' }, 400);
  if (!env.ARTIFACTS) return json({ ok: false, error: 'R2_NOT_BOUND' }, 503);
  let form;try{form=await request.formData()}catch{return json({ok:false,error:'INVALID_FORM_DATA'},400)}
  const key=String(form.get('key')||'');if(!isFinalEpub(key))return json({ok:false,error:'FINAL_EPUB_ONLY'},403);
  if(!(await env.ARTIFACTS.head(key)))return json({ok:false,error:'EPUB_NOT_FOUND'},404);
  const scope=scopeOf(key);if(!scope)return json({ok:false,error:'INVALID_SCOPE'},400);
  const title=catalogTextV56(form.get('title'),500),creator=catalogTextV56(form.get('creator'),300);
  const cover=form.get('cover');let coverKey='',coverContentType='';
  if(cover&&typeof cover.stream==='function'&&Number(cover.size||0)>0){if(Number(cover.size||0)>SIMPLE_EPUB_COVER_MAX_BYTES_V56)return json({ok:false,error:'COVER_TOO_LARGE',max_bytes:SIMPLE_EPUB_COVER_MAX_BYTES_V56},413);const resolved=coverTypeV56(cover);if(!resolved)return json({ok:false,error:'UNSUPPORTED_COVER_TYPE'},415);const [ext,type]=resolved;coverKey=ROOT+scope+'/meta/cover'+ext;coverContentType=type;await env.ARTIFACTS.put(coverKey,cover.stream(),{httpMetadata:{contentType:type},customMetadata:{source:'artifact-library-upload-v56'}})}
  const catalog=await readCatalogDocumentV56(env);const previous=catalog.books[scope]&&typeof catalog.books[scope]==='object'?catalog.books[scope]:{};const entry={...previous,epub_key:key};if(title)entry.title=title;if(creator)entry.creator=creator;if(coverKey){entry.cover_key=coverKey;entry.cover_type=coverContentType;entry.cover_bytes=Number(cover.size||0)}catalog.version=Math.max(1,Number(catalog.version||1));catalog.generated_at=new Date().toISOString();catalog.books[scope]=entry;
  const sidecar={bookKey:key,display_title:entry.title||'',author:entry.creator||'',cover_key:entry.cover_key||'',updated_at:catalog.generated_at};await env.ARTIFACTS.put(ROOT+scope+'/meta/book.json',JSON.stringify(sidecar,null,2)+'\n',{httpMetadata:{contentType:'application/json'}});await env.ARTIFACTS.put(LIBRARY_CATALOG_INDEX_KEY,JSON.stringify(catalog,null,2)+'\n',{httpMetadata:{contentType:'application/json'}});
  return json({ok:true,key,scope,title:entry.title||'',creator:entry.creator||'',cover_key:entry.cover_key||null},200);
}

'''
if 'async function publicEnrichUpload(request, env)' not in text:
    marker = 'async function publicUpload(request, env) {'
    if marker not in text:
        raise SystemExit('v56 publicUpload anchor missing')
    text = text.replace(marker, server_helpers + marker, 1)

route_marker = '    if (p === "/artifact-library/api/upload") return publicUpload(request, env);\n'
if 'p === "/artifact-library/api/enrich-upload"' not in text:
    if route_marker not in text:
        raise SystemExit('v56 upload route anchor missing')
    text = text.replace(route_marker, route_marker + '    if (p === "/artifact-library/api/enrich-upload") return publicEnrichUpload(request, env);\n', 1)

for marker in [
    'data-r3-library-v56="1"',
    '/artifact-library/vendor/jszip.min.js',
    '/artifact-library/vendor/epub.min.js',
    'async function migrateLegacyProgressV56()',
    'epub.locations.percentageFromCfi(cfi)',
    "migratedBy:'library-v56'",
    'async function extractUploadMetadataV56(file)',
    'async function enrichUploadedBookV56(bookKey,meta)',
    'async function publicEnrichUpload(request, env)',
    "ROOT+scope+'/meta/book.json'",
    'p === "/artifact-library/api/enrich-upload"',
    'setTimeout(()=>migrateLegacyProgressV56(),700)',
]:
    if marker not in text:
        raise SystemExit('READER_V56_MISSING:' + marker)

SIMPLE.write_text(text, encoding='utf-8')
print('READER_V56_AUTO_ENRICH_PROGRESS_MIGRATION=PASS')
