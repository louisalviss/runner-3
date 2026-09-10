from pathlib import Path
import re

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
text = SIMPLE.read_text(encoding='utf-8')

if 'R3_PROGRESS_RECOVERY_V70' in text:
    print('READER_V70_PROGRESS_RECOVERY=ALREADY_APPLIED')
    raise SystemExit(0)

client_helpers = r'''
  const R3_PROGRESS_RECOVERY_V70='v70';
  const R3_PROGRESS_LEGACY_PREFIX_V70='r3-reader-progress:';
  function r3ScopeFromBookKeyV70(bookKey){const parts=String(bookKey||'').split('/');return parts[0]==='core'&&parts[1]==='ebook'?String(parts[2]||''):''}
  function r3CollectLocalProgressV70(){
    const map=new Map(),ensure=bookKey=>{let row=map.get(bookKey);if(!row){row={key:bookKey,cfi:'',percent:null,last_open_at:0,updated_at:0,source:'local'};map.set(bookKey,row)}return row};
    try{
      for(let i=0;i<localStorage.length;i++){
        const storageKey=localStorage.key(i)||'';let bookKey='',kind='';
        if(storageKey.startsWith(PROGRESS_PREFIX)){bookKey=storageKey.slice(PROGRESS_PREFIX.length);kind='progress'}
        else if(storageKey.startsWith(R3_PROGRESS_LEGACY_PREFIX_V70)){bookKey=storageKey.slice(R3_PROGRESS_LEGACY_PREFIX_V70.length);kind='progress'}
        else if(storageKey.startsWith(POSITION_PREFIX)){bookKey=storageKey.slice(POSITION_PREFIX.length);kind='position'}
        else if(storageKey.startsWith('r3-reader-last-open:')){bookKey=storageKey.slice('r3-reader-last-open:'.length);kind='lastopen'}
        else continue;
        if(!r3ScopeFromBookKeyV70(bookKey))continue;const row=ensure(bookKey),raw=localStorage.getItem(storageKey);
        if(kind==='progress'){try{const p=JSON.parse(raw||'null')||{};const n=Number(p.percent);if(p.percent!==null&&p.percent!==undefined&&p.percent!==''&&Number.isFinite(n))row.percent=Math.max(0,Math.min(100,Math.round(n)));if(p.cfi)row.cfi=String(p.cfi);row.updated_at=Math.max(row.updated_at,Number(p.updatedAt||p.updated_at||0));row.last_open_at=Math.max(row.last_open_at,Number(p.lastOpenAt||p.last_open_at||0))}catch{}}
        else if(kind==='position'){if(raw)row.cfi=String(raw)}
        else if(kind==='lastopen'){const n=Number(raw||0);if(Number.isFinite(n)){row.last_open_at=Math.max(row.last_open_at,n);row.updated_at=Math.max(row.updated_at,n)}}
      }
    }catch{}
    return [...map.values()]
  }
  function r3ProgressSubstanceV70(row){return (String(row&&row.cfi||'')?2:0)+(Number(row&&row.percent||0)>0?2:(row&&row.percent!==null&&row.percent!==undefined?1:0))}
  function r3PickProgressV70(rows){return (rows||[]).filter(Boolean).sort((a,b)=>r3ProgressSubstanceV70(b)-r3ProgressSubstanceV70(a)||Number(b.updated_at||0)-Number(a.updated_at||0)||Number(b.last_open_at||0)-Number(a.last_open_at||0))[0]||null}
  function r3WriteRecoveredLocalV70(bookKey,row){if(!bookKey||!row)return false;let before='';try{before=localStorage.getItem(PROGRESS_PREFIX+bookKey)||''}catch{}const payload={percent:row.percent===undefined?null:row.percent,cfi:String(row.cfi||''),updatedAt:Math.max(0,Number(row.updated_at||row.last_open_at||Date.now())),lastOpenAt:Math.max(0,Number(row.last_open_at||0)),syncedBy:'v70-recovery'};try{const after=JSON.stringify(payload);localStorage.setItem(PROGRESS_PREFIX+bookKey,after);if(payload.cfi)localStorage.setItem(POSITION_PREFIX+bookKey,payload.cfi);if(payload.lastOpenAt)localStorage.setItem('r3-reader-last-open:'+bookKey,String(payload.lastOpenAt));return before!==after}catch{return false}}
'''

anchor = "  async function r3HydrateServerProgressV65(){"
idx = text.find(anchor)
if idx < 0:
    raise SystemExit('v70 client hydrate anchor missing')
text = text[:idx] + client_helpers + text[idx:]

hydrate_re = re.compile(r"  async function r3HydrateServerProgressV65\(\)\{.*?\}\n  function r3MigrateLocalBookKeyV65", re.S)
m = hydrate_re.search(text)
if not m:
    raise SystemExit('v70 client hydrate block missing')
new_hydrate = r'''  async function r3HydrateServerProgressV65(){
    try{
      const response=await fetch('/artifact-library/api/progress',{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}});
      if(!response.ok){if(response.status===401)status('Read data cần Library session.');return false}
      const data=await response.json();if(!data||data.ok!==true||!Array.isArray(data.items))return false;
      const localRows=r3CollectLocalProgressV70(),remoteRows=data.items.map(row=>({...row,source:'server'}));let changed=false;const upload=[];
      for(const book of state.books){
        const scope=String(book&&book.scope||r3ScopeFromBookKeyV70(book&&book.key));if(!scope)continue;
        const candidates=[];
        for(const row of localRows)if(r3ScopeFromBookKeyV70(row.key)===scope)candidates.push(row);
        for(const row of remoteRows)if(r3ScopeFromBookKeyV70(row.key)===scope)candidates.push(row);
        const best=r3PickProgressV70(candidates);if(!best)continue;
        const canonical={key:String(book.key),cfi:String(best.cfi||''),percent:best.percent===undefined?null:best.percent,last_open_at:Math.max(0,Number(best.last_open_at||0)),updated_at:Math.max(1,Number(best.updated_at||best.last_open_at||Date.now()))};
        if(r3WriteRecoveredLocalV70(book.key,canonical))changed=true;upload.push(canonical);
      }
      if(upload.length){
        const pushed=await fetch('/artifact-library/api/progress',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({items:upload,client_version:R3_PROGRESS_RECOVERY_V70})});
        if(!pushed.ok&&pushed.status===401)status('Read data chưa sync: cần Library session.');
      }
      return changed
    }catch{return false}
  }
  function r3MigrateLocalBookKeyV65'''
text = text[:m.start()] + new_hydrate + text[m.end():]

server_re = re.compile(r"async function publicProgressV65\(request, env\) \{.*?\n\}\n\nfunction r3CleanRenameV65", re.S)
m = server_re.search(text)
if not m:
    raise SystemExit('v70 server progress block missing')
new_server = r'''async function r3SelectProgressForKeyV70(env,key){
  let row=await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 WHERE book_key=?1').bind(key).first();
  if(row)return row;const scope=scopeOf(key);if(!scope)return null;
  row=await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 WHERE book_key LIKE ?1 ORDER BY updated_at DESC,last_open_at DESC LIMIT 1').bind(ROOT+scope+'/final/%').first();
  return row||null;
}
async function r3UpsertProgressV70(env,input){
  const key=String(input&&input.key||'');if(!isFinalEpub(key))return null;
  const cfi=String(input&&input.cfi||'').slice(0,4096);const raw=input&&input.percent;const pn=raw===null||raw===undefined||raw===''?NaN:Number(raw);const percent=Number.isFinite(pn)?Math.max(0,Math.min(100,Math.round(pn))):null;
  const updatedAt=Math.max(1,Math.round(Number(input&&((input.updated_at??input.updatedAt))||Date.now())));const lastOpenAt=Math.max(0,Math.round(Number(input&&((input.last_open_at??input.lastOpenAt))||0)));
  await env.DB.prepare(`INSERT INTO ebook_reader_progress_v65(book_key,cfi,percent,last_open_at,updated_at) VALUES(?1,?2,?3,?4,?5)
    ON CONFLICT(book_key) DO UPDATE SET
      cfi=CASE WHEN excluded.updated_at>=ebook_reader_progress_v65.updated_at AND excluded.cfi<>'' THEN excluded.cfi ELSE ebook_reader_progress_v65.cfi END,
      percent=CASE WHEN excluded.updated_at>=ebook_reader_progress_v65.updated_at AND excluded.percent IS NOT NULL THEN excluded.percent ELSE ebook_reader_progress_v65.percent END,
      last_open_at=MAX(ebook_reader_progress_v65.last_open_at,excluded.last_open_at),
      updated_at=MAX(ebook_reader_progress_v65.updated_at,excluded.updated_at)`).bind(key,cfi,percent,lastOpenAt,updatedAt).run();
  return r3ProgressRowV65(await r3SelectProgressForKeyV70(env,key));
}
async function r3SnapshotProgressV70(env){
  if(!env.ARTIFACTS)return false;try{const result=await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 ORDER BY updated_at DESC LIMIT 2000').all();const items=(result.results||[]).map(r3ProgressRowV65),now=new Date(),day=now.toISOString().slice(0,10),payload=JSON.stringify({schema:1,version:'v70',generated_at:now.toISOString(),count:items.length,items},null,2)+'\n';await env.ARTIFACTS.put(ROOT+'_system/progress-v70/latest.json',payload,{httpMetadata:{contentType:'application/json'},customMetadata:{source:'ebook-progress-v70'}});await env.ARTIFACTS.put(ROOT+'_system/progress-v70/snapshots/'+day+'.json',payload,{httpMetadata:{contentType:'application/json'},customMetadata:{source:'ebook-progress-v70-daily'}});return true}catch(error){console.warn('R3_PROGRESS_SNAPSHOT_V70',error);return false}
}
async function publicProgressV65(request, env) {
  if (!(await hasBrowserLibrarySession(request, env))) return json({ok:false,error:'UNAUTHORIZED'},401);
  if (!env.DB) return json({ok:false,error:'DB_BINDING_MISSING'},503);
  try { await r3EnsureProgressTableV65(env); } catch (error) { return json({ok:false,error:'PROGRESS_DB_INIT_FAILED',detail:String(error?.message||error)},503); }
  const url=new URL(request.url);
  if(request.method==='GET'){
    const key=String(url.searchParams.get('key')||'');if(key){if(!isFinalEpub(key))return json({ok:false,error:'FINAL_EPUB_ONLY'},403);return json({ok:true,progress:r3ProgressRowV65(await r3SelectProgressForKeyV70(env,key)),recovery_version:'v70'})}
    const result=await env.DB.prepare('SELECT book_key,cfi,percent,last_open_at,updated_at FROM ebook_reader_progress_v65 ORDER BY updated_at DESC LIMIT 2000').all();return json({ok:true,items:(result.results||[]).map(r3ProgressRowV65),recovery_version:'v70'});
  }
  if(request.method!=='POST')return json({ok:false,error:'METHOD_NOT_ALLOWED'},405);
  let body;try{body=await request.json()}catch{return json({ok:false,error:'INVALID_JSON'},400)}
  const inputs=Array.isArray(body&&body.items)?body.items:[body];if(!inputs.length||inputs.length>100)return json({ok:false,error:'INVALID_PROGRESS_BATCH'},400);
  const saved=[];for(const input of inputs){const row=await r3UpsertProgressV70(env,input);if(row)saved.push(row)}if(!saved.length)return json({ok:false,error:'NO_VALID_PROGRESS_ROWS'},400);
  await r3SnapshotProgressV70(env);return json({ok:true,accepted:saved.length,items:saved,recovery_version:'v70'});
}

function r3CleanRenameV65'''
text = text[:m.start()] + new_server + text[m.end():]

root_old = '''    if (p === "/artifact-library") {
      if (request.method !== "GET") return redirectHome();
      return new Response(libraryPage(), { status: 200, headers: headers({ "X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68", "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" }) });
    }'''
root_new = '''    if (p === "/artifact-library") {
      if (request.method !== "GET") return redirectHome();
      if (!(await hasBrowserLibrarySession(request, env))) return (await r3LoadLegacyLibraryAppV57()).fetch(request, env, ctx);
      return new Response(libraryPage(), { status: 200, headers: headers({ "X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68", "X-R3-Progress-Recovery": "v70", "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" }) });
    }'''
if root_old not in text:
    raise SystemExit('v70 authenticated root anchor missing')
text = text.replace(root_old, root_new, 1)

for marker in [
    "R3_PROGRESS_RECOVERY_V70='v70'",
    'r3CollectLocalProgressV70',
    'r3ScopeFromBookKeyV70',
    "JSON.stringify({items:upload,client_version:R3_PROGRESS_RECOVERY_V70})",
    'async function r3SelectProgressForKeyV70',
    'async function r3UpsertProgressV70',
    'async function r3SnapshotProgressV70',
    "ROOT+'_system/progress-v70/latest.json'",
    "recovery_version:'v70'",
    'if (!(await hasBrowserLibrarySession(request, env))) return (await r3LoadLegacyLibraryAppV57()).fetch(request, env, ctx);',
    '"X-R3-Progress-Recovery": "v70"',
]:
    if marker not in text:
        raise SystemExit('READER_V70_PROGRESS_RECOVERY_MISSING:'+marker)

SIMPLE.write_text(text,encoding='utf-8')
print('READER_V70_PROGRESS_RECOVERY=PASS')
