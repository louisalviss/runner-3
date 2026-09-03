const app=(await import('../cloudflare/runner3-core/artifact-library-simple-entry.js?fast-index-smoke')).default;

const INDEX='core/ebook/_system/library-index-v65.json';
const rows=new Map([
  ['core/ebook/alpha/final/Alpha.epub',{key:'core/ebook/alpha/final/Alpha.epub',size:100,uploaded:new Date('2026-09-03T00:00:00Z')}],
  ['core/ebook/beta/final/Beta-v2.epub',{key:'core/ebook/beta/final/Beta-v2.epub',size:200,uploaded:new Date('2026-09-03T01:00:00Z')}],
]);
let listCalls=0;
const r2={
  async list({prefix='',cursor,limit=1000}={}){
    listCalls++;
    const objects=[...rows.values()].filter(x=>String(x.key||'').startsWith(prefix)).slice(0,limit);
    return {objects,truncated:false,cursor:undefined};
  },
  async get(key){
    const row=rows.get(key);if(!row)return null;
    if(key===INDEX){return {async json(){return JSON.parse(String(row.body||''))}}}
    return null;
  },
  async put(key,body){
    let value=body;
    if(typeof body!=='string')value=String(body??'');
    rows.set(key,{key,body:value,size:Buffer.byteLength(value),uploaded:new Date()});
    return {etag:'smoke'};
  },
  async delete(key){rows.delete(key)},
  async head(key){return rows.has(key)?rows.get(key):null},
};
const env={ARTIFACTS:r2,RUNNER3_CORE_TOKEN:'fast-index-smoke'};
const ctx={waitUntil(){}};
async function list(path='/artifact-library/api/list'){
  const response=await app.fetch(new Request('http://r3.local'+path),env,ctx);
  if(!response.ok)throw new Error('LIST_HTTP_'+response.status+':'+await response.text());
  return response.json();
}

const first=await list();
if(first.source!=='rebuild')throw new Error('FIRST_NOT_REBUILD:'+JSON.stringify(first));
if(first.objects.length!==2)throw new Error('FIRST_COUNT:'+first.objects.length);
const afterFirst=listCalls;
if(afterFirst<1)throw new Error('FIRST_DID_NOT_SCAN_R2');
if(!rows.has(INDEX))throw new Error('INDEX_NOT_WRITTEN');

const second=await list();
if(second.source!=='index')throw new Error('SECOND_NOT_INDEX:'+JSON.stringify(second));
if(listCalls!==afterFirst)throw new Error('INDEX_HIT_SCANNED_R2');

const forced=await list('/artifact-library/api/list?refresh=1');
if(forced.source!=='rebuild')throw new Error('FORCE_NOT_REBUILD:'+JSON.stringify(forced));
if(listCalls<=afterFirst)throw new Error('FORCE_DID_NOT_SCAN_R2');

rows.set(INDEX,{key:INDEX,body:'{"schema":1,"generated_at_ms":1,"objects":"broken"}',size:1,uploaded:new Date()});
const beforeBroken=listCalls;
const recovered=await list();
if(recovered.source!=='rebuild')throw new Error('BROKEN_INDEX_DID_NOT_REBUILD:'+JSON.stringify(recovered));
if(listCalls<=beforeBroken)throw new Error('BROKEN_INDEX_DID_NOT_SCAN_R2');

console.log('READER_V65_FAST_LIBRARY_INDEX_RUNTIME=PASS');
console.log('INDEX_HIT_ZERO_R2_LIST_SCAN=PASS');
console.log('INDEX_CORRUPTION_FALLBACK_REBUILD=PASS');
