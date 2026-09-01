import app from "./artifact-library-reader-v27-boot-cfi-restore-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const EPUB_MARKER = '<script src="/artifact-library/vendor/epub.min.js"></script>\n<script>';
const PRIME = `<script data-r3-audio-prime-base-position-v28="1">
(()=>{
  window.__r3AudioPrimeBasePositionV28=true;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;
  const baseKey='r3-reader-position:'+bookKey;
  let previous='';
  try{previous=String(localStorage.getItem(baseKey)||'');}catch{}
  if(previous){
    window.__r3AudioPrimeBasePositionV28Debug={phase:'kept-reader-position',baseKey,previous};
    return;
  }
  let saved=null;
  try{saved=JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:'+bookKey)||'null');}catch{}
  const cfi=String(saved&&saved.cfi||'');
  if(!cfi)return;
  try{localStorage.setItem(baseKey,cfi);}catch{}
  window.__r3AudioPrimeBasePositionV28Debug={phase:'primed-audio-fallback',baseKey,previous,cfi};
})();
</script>`;

function patchPrimeBasePosition(html) {
  const source=String(html||'');
  if(source.includes('data-r3-audio-prime-base-position-v28="1"'))return source;
  const index=source.indexOf(EPUB_MARKER);
  if(index<0)throw new Error('READER_V28_EPUB_BOOT_MARKER_MISSING');
  if(source.indexOf(EPUB_MARKER,index+EPUB_MARKER.length)>=0)throw new Error('READER_V28_EPUB_BOOT_MARKER_AMBIGUOUS');
  return source.replace(EPUB_MARKER,'<script src="/artifact-library/vendor/epub.min.js"></script>\n'+PRIME+'\n<script>');
}

export default {
  async fetch(request, env, ctx) {
    const url=new URL(request.url);
    const response=await app.fetch(request,env,ctx);
    if(url.pathname!=="/artifact-library/read"||request.method!=="GET")return response;
    const type=response.headers.get("Content-Type")||"";
    if(!type.toLowerCase().includes("text/html")||response.status!==200)return response;
    try{
      const updated=patchPrimeBasePosition(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v28-prime-base-position");
      headers.set("X-R3-Reader-Patch-Proof","v27+v28:prime-base-reader-position-before-epub-boot");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v28 patch failed',{
        status:503,
        headers:{
          'Content-Type':'text/plain; charset=utf-8',
          'Cache-Control':'no-store',
          'X-R3-Reader-Runtime':'v28-patch-failed',
          'X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180),
        },
      });
    }
  },
  async scheduled(controller,env,ctx){
    if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);
  },
};
