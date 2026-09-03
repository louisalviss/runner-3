from pathlib import Path
import re

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
text = SIMPLE.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

if 'R3_LIBRARY_FAST_INDEX_KEY_V65' in text:
    print('READER_V65_FAST_LIBRARY_INDEX=ALREADY_APPLIED')
    raise SystemExit(0)

server_helpers = r'''
const R3_LIBRARY_FAST_INDEX_KEY_V65 = ROOT + '_system/library-index-v65.json';
const R3_LIBRARY_FAST_INDEX_MAX_AGE_MS_V65 = 5 * 60 * 1000;

function r3ValidFastLibraryRowV65(row){
  return Boolean(row&&typeof row==='object'&&isFinalEpub(String(row.key||''))&&String(row.scope||scopeOf(String(row.key||''))||''));
}
async function r3ReadLibraryFastIndexV65(env){
  if(!env.ARTIFACTS)return null;
  try{
    const object=await env.ARTIFACTS.get(R3_LIBRARY_FAST_INDEX_KEY_V65);
    if(!object)return null;
    const data=await object.json();
    if(!data||data.schema!==1||!Array.isArray(data.objects))return null;
    const generatedAt=Number(data.generated_at_ms||0);
    if(!generatedAt||Date.now()-generatedAt>R3_LIBRARY_FAST_INDEX_MAX_AGE_MS_V65)return null;
    const objects=data.objects.filter(r3ValidFastLibraryRowV65).map(row=>({key:String(row.key),size:Number(row.size||0),uploaded:row.uploaded||null,scope:String(row.scope||scopeOf(String(row.key))||'')}));
    if(objects.length!==data.objects.length)return null;
    return {objects,generated_at_ms:generatedAt};
  }catch(error){console.warn('R3_LIBRARY_FAST_INDEX_READ_V65',error);return null}
}
async function r3WriteLibraryFastIndexV65(env,objects){
  if(!env.ARTIFACTS)return false;
  try{
    const generatedAt=Date.now();
    const payload={schema:1,generated_at_ms:generatedAt,count:Array.isArray(objects)?objects.length:0,objects:Array.isArray(objects)?objects:[]};
    await env.ARTIFACTS.put(R3_LIBRARY_FAST_INDEX_KEY_V65,JSON.stringify(payload),{httpMetadata:{contentType:'application/json'},customMetadata:{source:'artifact-library-fast-index-v65'}});
    return generatedAt;
  }catch(error){console.warn('R3_LIBRARY_FAST_INDEX_WRITE_V65',error);return false}
}
async function r3InvalidateLibraryFastIndexV65(env,reason=''){
  if(!env.ARTIFACTS)return false;
  try{await env.ARTIFACTS.delete(R3_LIBRARY_FAST_INDEX_KEY_V65);return true}catch(error){console.warn('R3_LIBRARY_FAST_INDEX_INVALIDATE_V65',reason,error);return false}
}
async function r3LibraryObjectsFastV65(env,forceRebuild=false){
  const started=Date.now();
  if(!forceRebuild){
    const cached=await r3ReadLibraryFastIndexV65(env);
    if(cached)return {objects:cached.objects,source:'index',generated_at_ms:cached.generated_at_ms,elapsed_ms:Date.now()-started};
  }
  const objects=await canonicalFinalBooks(env);
  const generatedAt=(await r3WriteLibraryFastIndexV65(env,objects))||Date.now();
  return {objects,source:'rebuild',generated_at_ms:generatedAt,elapsed_ms:Date.now()-started};
}

'''
text = replace_once(text, 'async function publicList(request, env) {', server_helpers + 'async function publicList(request, env) {', 'fast index server helpers')

public_list_re = re.compile(r"async function publicList\(request, env\) \{\n.*?\n\}\n\nasync function publicUpload", re.S)
m = public_list_re.search(text)
if not m:
    raise SystemExit('fast index publicList block missing')
new_public_list = r'''async function publicList(request, env) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  try {
    const url=new URL(request.url);
    const force=url.searchParams.get('refresh')==='1';
    const result=await r3LibraryObjectsFastV65(env,force);
    return json({ok:true,prefix:ROOT,final_only:true,canonical_latest_per_scope:true,objects:result.objects,source:result.source,index_generated_at_ms:result.generated_at_ms,elapsed_ms:result.elapsed_ms});
  } catch (error) {
    return json({ ok: false, error: "LIBRARY_LIST_FAILED", detail: String(error?.message || error) }, 503);
  }
}

async function publicUpload'''
text = text[:m.start()] + new_public_list + text[m.end():]

# Raw upload changes the canonical object set. Invalidate only after R2 put has
# succeeded; the following normal Library load will rebuild exactly once.
upload_old = "    const stored = await env.ARTIFACTS.put(key, request.body, { httpMetadata: { contentType: 'application/epub+zip' }, customMetadata: { source: 'artifact-library-upload-v53' } });\n    return json({ ok: true, key, size: Number.isFinite(size) ? size : null, etag: stored?.httpEtag || stored?.etag || null }, 201);"
upload_new = "    const stored = await env.ARTIFACTS.put(key, request.body, { httpMetadata: { contentType: 'application/epub+zip' }, customMetadata: { source: 'artifact-library-upload-v53' } });\n    await r3InvalidateLibraryFastIndexV65(env,'upload');\n    return json({ ok: true, key, size: Number.isFinite(size) ? size : null, etag: stored?.httpEtag || stored?.etag || null }, 201);"
text = replace_once(text, upload_old, upload_new, 'fast index upload invalidation')

rename_old = "try{await r3MoveProgressV65(env,key,newKey)}catch(error){console.warn('R3_PROGRESS_RENAME_V65',error)}await env.ARTIFACTS.delete(key);return json({ok:true,action:'rename',key,new_key:newKey,scope,title});"
rename_new = "try{await r3MoveProgressV65(env,key,newKey)}catch(error){console.warn('R3_PROGRESS_RENAME_V65',error)}await env.ARTIFACTS.delete(key);await r3InvalidateLibraryFastIndexV65(env,'rename');return json({ok:true,action:'rename',key,new_key:newKey,scope,title});"
text = replace_once(text, rename_old, rename_new, 'fast index rename invalidation')

delete_old = "if(env.DB){try{await r3EnsureProgressTableV65(env);await env.DB.prepare(\"DELETE FROM ebook_reader_progress_v65 WHERE book_key LIKE ?1\").bind(ROOT+scope+'/final/%').run()}catch(error){console.warn('R3_PROGRESS_DELETE_V65',error)}}return json({ok:true,action:'delete',key,scope,deleted_objects:keys.length});"
delete_new = "if(env.DB){try{await r3EnsureProgressTableV65(env);await env.DB.prepare(\"DELETE FROM ebook_reader_progress_v65 WHERE book_key LIKE ?1\").bind(ROOT+scope+'/final/%').run()}catch(error){console.warn('R3_PROGRESS_DELETE_V65',error)}}await r3InvalidateLibraryFastIndexV65(env,'delete');return json({ok:true,action:'delete',key,scope,deleted_objects:keys.length});"
text = replace_once(text, delete_old, delete_new, 'fast index delete invalidation')

client_helpers = r'''
  const R3_LIBRARY_FAST_CLIENT_CACHE_V65='r3-library-fast-list-v65';
  const R3_LIBRARY_FAST_CLIENT_MAX_AGE_MS_V65=24*60*60*1000;
  let r3LibraryFastBootCacheUsedV65=false;
  function r3ReadLibraryClientCacheV65(){try{const data=JSON.parse(localStorage.getItem(R3_LIBRARY_FAST_CLIENT_CACHE_V65)||'null');if(!data||!Array.isArray(data.objects))return null;const at=Number(data.saved_at||0);if(!at||Date.now()-at>R3_LIBRARY_FAST_CLIENT_MAX_AGE_MS_V65)return null;return data.objects}catch{return null}}
  function r3WriteLibraryClientCacheV65(objects){try{localStorage.setItem(R3_LIBRARY_FAST_CLIENT_CACHE_V65,JSON.stringify({saved_at:Date.now(),objects:Array.isArray(objects)?objects:[]}))}catch{}}
'''
text = replace_once(text, "  const $=id=>document.getElementById(id);\n", "  const $=id=>document.getElementById(id);\n" + client_helpers, 'fast index client helpers')

load_re = re.compile(r"  async function load\(\)\{.*?\}\n  async function downloadBook", re.S)
m = load_re.search(text)
if not m:
    raise SystemExit('fast index load block missing')
new_load = r'''  async function load(forceRebuild=false){
    const refresh=$('refresh');refresh.disabled=true;
    const force=forceRebuild===true;
    let showedCached=false;
    if(!force&&!r3LibraryFastBootCacheUsedV65&&state.books.length===0){
      r3LibraryFastBootCacheUsedV65=true;
      const cached=r3ReadLibraryClientCacheV65();
      if(cached){state.books=cached;showedCached=true;status('');render();hydrateMeta()}
    }
    if(force)status('Đang đồng bộ R2…');else if(!showedCached&&state.books.length===0)status('Loading…');
    try{
      const endpoint='/artifact-library/api/list'+(force?'?refresh=1':'');
      const r=await fetch(endpoint,{cache:'no-store'});const data=await r.json();if(!r.ok||data.ok!==true)throw new Error(data.error||('HTTP '+r.status));
      state.books=Array.isArray(data.objects)?data.objects:[];r3WriteLibraryClientCacheV65(state.books);status('');render();hydrateMeta();
      r3HydrateServerProgressV65().then(changed=>{if(changed)render()}).catch(()=>{});
      setTimeout(()=>migrateLegacyProgressV56(),700);
    }catch(e){
      if(state.books.length===0){status('Không tải được Library: '+String(e&&e.message||e));render()}
      else{status('');console.warn('R3_LIBRARY_FAST_REFRESH_V65',e)}
    }finally{refresh.disabled=false}
  }
  async function downloadBook'''
text = text[:m.start()] + new_load + text[m.end():]

text = replace_once(text, "$('refresh').addEventListener('click',load);", "$('refresh').addEventListener('click',()=>load(true));", 'force refresh binding')

for marker in [
    'R3_LIBRARY_FAST_INDEX_KEY_V65',
    'R3_LIBRARY_FAST_INDEX_MAX_AGE_MS_V65',
    'r3LibraryObjectsFastV65(env,force)',
    "source:result.source",
    "r3InvalidateLibraryFastIndexV65(env,'upload')",
    "r3InvalidateLibraryFastIndexV65(env,'rename')",
    "r3InvalidateLibraryFastIndexV65(env,'delete')",
    'R3_LIBRARY_FAST_CLIENT_CACHE_V65',
    'r3ReadLibraryClientCacheV65()',
    "r3HydrateServerProgressV65().then(changed=>{if(changed)render()})",
    "$('refresh').addEventListener('click',()=>load(true));",
]:
    if marker not in text:
        raise SystemExit('READER_V65_FAST_LIBRARY_INDEX_MISSING:' + marker)

SIMPLE.write_text(text, encoding='utf-8')
print('READER_V65_FAST_LIBRARY_INDEX=PASS')
