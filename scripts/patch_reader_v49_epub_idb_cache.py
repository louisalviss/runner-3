from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
V2 = ROOT / 'artifact-library-reader-v2-entry.js'
text = V2.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# Avoid a loading-label flash on fast/cache-hit opens. A delayed indicator is armed in openBook().
old_loading = '<main id="viewer"><div id="loading">Đang mở EPUB…</div></main>'
new_loading = '<main id="viewer"><div id="loading" class="hidden">Đang mở EPUB…</div></main>'
if old_loading in text:
    text = replace_once(text, old_loading, new_loading, 'loading hidden by default')

old_block = """  async function signedUrl(){
    const r=await fetch('/artifact-library/api/delivery',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key,ttl_seconds:3600})});
    const data=await r.json();if(!r.ok||data.ok!==true||!data.delivery?.url)throw new Error(data.error||('HTTP '+r.status));return data.delivery.url;
  }

  async function openBook(){
    try{
      if(typeof window.ePub!=='function')throw new Error('Reader engine failed to load');
      const url=await signedUrl();
      const response=await fetch(url);if(!response.ok)throw new Error('EPUB HTTP '+response.status);
      const buffer=await response.arrayBuffer();
      book=window.ePub(buffer);"""

new_block = """  const R3_EPUB_CACHE_DB='r3-reader-epub-cache-v49';
  const R3_EPUB_CACHE_STORE='books';
  const R3_EPUB_CACHE_LIMIT=4;
  let r3EpubCacheDbPromise=null;

  function r3OpenEpubCache(){
    if(r3EpubCacheDbPromise)return r3EpubCacheDbPromise;
    r3EpubCacheDbPromise=new Promise((resolve,reject)=>{
      if(!('indexedDB' in window)){reject(new Error('INDEXEDDB_UNAVAILABLE'));return;}
      const req=indexedDB.open(R3_EPUB_CACHE_DB,1);
      req.onupgradeneeded=()=>{
        const db=req.result;
        if(!db.objectStoreNames.contains(R3_EPUB_CACHE_STORE))db.createObjectStore(R3_EPUB_CACHE_STORE,{keyPath:'key'});
      };
      req.onsuccess=()=>resolve(req.result);
      req.onerror=()=>reject(req.error||new Error('INDEXEDDB_OPEN_FAILED'));
    }).catch(error=>{r3EpubCacheDbPromise=null;throw error;});
    return r3EpubCacheDbPromise;
  }

  async function r3ReadCachedEpub(){
    try{
      const db=await r3OpenEpubCache();
      const row=await new Promise((resolve,reject)=>{
        const tx=db.transaction(R3_EPUB_CACHE_STORE,'readonly');
        const req=tx.objectStore(R3_EPUB_CACHE_STORE).get(key);
        req.onsuccess=()=>resolve(req.result||null);
        req.onerror=()=>reject(req.error||new Error('INDEXEDDB_READ_FAILED'));
      });
      const buffer=row&&row.buffer;
      if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<64)return null;
      try{
        const tx=db.transaction(R3_EPUB_CACHE_STORE,'readwrite');
        tx.objectStore(R3_EPUB_CACHE_STORE).put({...row,at:Date.now()});
      }catch{}
      return buffer;
    }catch{return null;}
  }

  async function r3TrimEpubCache(db){
    try{
      const rows=await new Promise((resolve,reject)=>{
        const tx=db.transaction(R3_EPUB_CACHE_STORE,'readonly');
        const req=tx.objectStore(R3_EPUB_CACHE_STORE).getAll();
        req.onsuccess=()=>resolve(Array.isArray(req.result)?req.result:[]);
        req.onerror=()=>reject(req.error||new Error('INDEXEDDB_LIST_FAILED'));
      });
      rows.sort((a,b)=>Number(b&&b.at||0)-Number(a&&a.at||0));
      const stale=rows.slice(R3_EPUB_CACHE_LIMIT);
      if(!stale.length)return;
      const tx=db.transaction(R3_EPUB_CACHE_STORE,'readwrite');
      for(const row of stale){if(row&&row.key)tx.objectStore(R3_EPUB_CACHE_STORE).delete(row.key);}
    }catch{}
  }

  async function r3WriteCachedEpub(buffer){
    if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<64)return;
    try{
      const db=await r3OpenEpubCache();
      await new Promise((resolve,reject)=>{
        const tx=db.transaction(R3_EPUB_CACHE_STORE,'readwrite');
        tx.oncomplete=()=>resolve();
        tx.onerror=()=>reject(tx.error||new Error('INDEXEDDB_WRITE_FAILED'));
        tx.objectStore(R3_EPUB_CACHE_STORE).put({key,buffer,at:Date.now(),size:buffer.byteLength});
      });
      r3TrimEpubCache(db);
    }catch{}
  }

  async function signedUrl(){
    const r=await fetch('/artifact-library/api/delivery',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key,ttl_seconds:3600})});
    const data=await r.json();if(!r.ok||data.ok!==true||!data.delivery?.url)throw new Error(data.error||('HTTP '+r.status));return data.delivery.url;
  }

  async function r3LoadEpubBuffer(){
    const cached=await r3ReadCachedEpub();
    if(cached){
      window.__r3EpubCacheV49={hit:true,key,bytes:cached.byteLength,at:Date.now()};
      return cached;
    }
    const url=await signedUrl();
    const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error('EPUB HTTP '+response.status);
    const buffer=await response.arrayBuffer();
    window.__r3EpubCacheV49={hit:false,key,bytes:buffer.byteLength,at:Date.now()};
    r3WriteCachedEpub(buffer.slice(0));
    return buffer;
  }

  async function openBook(){
    let r3LoadingTimer=0;
    try{
      if(typeof window.ePub!=='function')throw new Error('Reader engine failed to load');
      r3LoadingTimer=setTimeout(()=>{
        try{if(!document.documentElement.classList.contains('r3-restore-pending-v45'))$('loading').classList.remove('hidden');}catch{}
      },350);
      const buffer=await r3LoadEpubBuffer();
      book=window.ePub(buffer);"""

if "const R3_EPUB_CACHE_DB='r3-reader-epub-cache-v49';" not in text:
    text = replace_once(text, old_block, new_block, 'epub indexeddb cache block')

old_rendered = "rendition.on('rendered',()=>{bindEpubContents();$('loading').classList.add('hidden');});"
new_rendered = "rendition.on('rendered',()=>{clearTimeout(r3LoadingTimer);bindEpubContents();$('loading').classList.add('hidden');});"
if old_rendered in text:
    text = replace_once(text, old_rendered, new_rendered, 'clear delayed loading on rendered')

old_error = """    }catch(error){$('loading').classList.remove('hidden');$('loading').textContent='Không mở được EPUB: '+String(error?.message||error);$('position').textContent='Reader error';showControls();}
  }"""
new_error = """    }catch(error){clearTimeout(r3LoadingTimer);$('loading').classList.remove('hidden');$('loading').textContent='Không mở được EPUB: '+String(error?.message||error);$('position').textContent='Reader error';showControls();}
  }"""
if old_error in text:
    text = replace_once(text, old_error, new_error, 'clear delayed loading on error')

V2.write_text(text, encoding='utf-8')

smoke = ROOT / 'reader-audio-core' / 'reader-v49-epub-cache-smoke.mjs'
smoke.write_text("""import fs from 'node:fs';
const src=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v2-entry.js','utf8');
for(const marker of [
  "const R3_EPUB_CACHE_DB='r3-reader-epub-cache-v49';",
  "async function r3ReadCachedEpub()",
  "async function r3WriteCachedEpub(buffer)",
  "async function r3LoadEpubBuffer()",
  "window.__r3EpubCacheV49={hit:true",
  "r3LoadingTimer=setTimeout",
  '<div id="loading" class="hidden">Đang mở EPUB…</div>'
])if(!src.includes(marker))throw new Error('V49_MISSING:'+marker);
if(src.includes('const response=await fetch(url);if(!response.ok)'))throw new Error('V49_LEGACY_ALWAYS_NETWORK_PATH');
console.log('READER_V49_EPUB_IDB_CACHE=PASS');
""", encoding='utf-8')

print('READER_V49_PATCH=PASS')
