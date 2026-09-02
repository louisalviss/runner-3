import app from "./artifact-library-reader-v27-boot-cfi-restore-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const EPUB_MARKER = '<script src="/artifact-library/vendor/epub.min.js"></script>\n<script>';
const PRIME = `<script data-r3-audio-prime-base-position-v28="1" data-r3-direct-restore-v45="1" data-r3-atomic-reveal-v48="1">
(()=>{
  window.__r3AudioPrimeBasePositionV28=true;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;
  const baseKey='r3-reader-position:'+bookKey;
  let target='';
  try{target=String(localStorage.getItem(baseKey)||'');}catch{}
  let source='reader-position';
  if(!target){
    let saved=null;
    try{saved=JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:'+bookKey)||'null');}catch{}
    target=String(saved&&saved.cfi||'');
    source='audio-fallback';
    if(target)try{localStorage.setItem(baseKey,target);}catch{}
  }
  window.__r3AudioPrimeBasePositionV28Debug={phase:target?'restore-pending':'no-target',baseKey,target,source};
  if(!target)return;

  window.__R3_READER_RESTORE_PENDING=true;
  window.__r3ReaderRestoreTargetV45=target;
  document.documentElement.classList.add('r3-restore-pending-v45');
  const style=document.createElement('style');
  style.id='r3ReaderDirectRestoreV45Style';
  style.textContent=[
    "html.r3-restore-pending-v45 #viewer{visibility:hidden!important;opacity:0!important;transition:none!important;animation:none!important;scroll-behavior:auto!important}",
    "html.r3-restore-pending-v45 #viewer .epub-container,html.r3-restore-pending-v45 #viewer .epub-view,html.r3-restore-pending-v45 #viewer iframe{transition:none!important;animation:none!important;scroll-behavior:auto!important;will-change:auto!important}",
    "html.r3-restore-pending-v45 #r3AudioDock{opacity:0!important;pointer-events:none!important;transition:none!important;animation:none!important}",
    "html.r3-restore-pending-v45 body::before{content:'';position:fixed;z-index:2147483600;inset:0;background:var(--bg,#fff);pointer-events:auto}",
    "html.r3-restore-pending-v45 body::after{content:'Đang mở vị trí gần nhất…';position:fixed;z-index:2147483601;left:50%;top:48%;transform:translate(-50%,-50%);padding:11px 16px;border-radius:999px;background:color-mix(in srgb,var(--fg,#222) 8%,var(--bg,#fff));color:var(--fg,#333);font:600 13px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;white-space:nowrap;box-shadow:0 8px 30px rgba(0,0,0,.08);pointer-events:none}"
  ].join('');
  (document.head||document.documentElement).appendChild(style);
  window.__r3ReaderDirectRestoreV45={phase:'primed',bookKey,target,source,startedAt:Date.now(),after:'',error:'',owner:'atomic-reveal-v48'};
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
      headers.set("X-R3-Reader-Patch-Proof","v27+v28:prime-base-reader-position-before-epub-boot+atomic-v48");
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
