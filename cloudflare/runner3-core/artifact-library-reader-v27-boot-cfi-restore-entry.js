import app from "./artifact-library-reader-v26-persist-follow-cfi-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const BOOT_SCRIPT = `<script data-r3-audio-boot-cfi-v27="1" data-r3-direct-restore-v45="1" data-r3-single-boot-owner-v46="1" data-r3-fast-reveal-v50="1">
(()=>{
  if(window.__r3AudioBootCfiRestoreV27)return;
  window.__r3AudioBootCfiRestoreV27=true;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;
  const baseKey='r3-reader-position:'+bookKey;
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const nextPaint=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const debug=window.__r3ReaderDirectRestoreV45||{phase:'boot',bookKey,startedAt:Date.now(),target:'',after:'',error:''};
  window.__r3ReaderDirectRestoreV45=debug;

  function currentCfi(){
    try{
      const b=window.r3ReaderBridge;
      const loc=b&&typeof b.current==='function'?b.current():null;
      return String(loc&&loc.start&&loc.start.cfi||'');
    }catch{return '';}
  }
  function savedReaderCfi(){
    try{return String(localStorage.getItem(baseKey)||'');}catch{return '';}
  }
  async function waitBaseBootDone(){
    for(let n=0;n<140;n++){
      if(window.__R3_BASE_READER_BOOT_DONE===true)return true;
      await delay(80);
    }
    return window.__R3_BASE_READER_BOOT_DONE===true;
  }
  async function finish(phase){
    debug.phase=phase;
    debug.after=currentCfi();
    debug.finishedAt=Date.now();
    await nextPaint();
    window.__R3_READER_RESTORE_PENDING=false;
    document.documentElement.classList.remove('r3-restore-pending-v45');
    try{window.dispatchEvent(new CustomEvent('r3-reader-restore-ready-v45',{detail:{phase,cfi:debug.after,target:debug.target||'',owner:'fast-reveal-v50'}}));}catch{}
  }

  (async()=>{
    debug.phase='observe-base-reader';
    debug.target=String(window.__r3ReaderRestoreTargetV45||savedReaderCfi()||'');
    const initial=currentCfi();
    debug.phase='wait-base-display-promise';
    const bootDone=await waitBaseBootDone();
    if(!bootDone){
      window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',initial,current:currentCfi(),reason:'base-display-promise',owner:'fast-reveal-v50'};
      await finish('base-display-timeout');
      return;
    }
    const after=currentCfi();
    debug.after=after;
    window.__r3AudioBootCfiV27Debug={phase:'restored',attempt:0,target:debug.target||'',initial,before:initial,after,stable:after,direct:false,owner:'base-reader-v47+fast-reveal-v50'};
    await finish('ready');
  })().catch(async error=>{
    debug.error=String(error&&error.message||error||'restore observe failed').slice(0,180);
    window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',current:currentCfi(),reason:'observer',error:debug.error,owner:'fast-reveal-v50'};
    await finish('fallback-current-page');
  });
})();
</script>`;

function patchBootCfiRestore(html) {
  const source = String(html || '');
  if (source.includes('data-r3-audio-boot-cfi-v27="1"')) return source;
  return source.includes('</body>') ? source.replace('</body>', BOOT_SCRIPT + '</body>') : source + BOOT_SCRIPT;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html") || response.status !== 200) return response;
    try {
      const updated = patchBootCfiRestore(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-Runtime", "v27-boot-cfi-restore");
      headers.set("X-R3-Reader-Patch-Proof", "v26+v27:boot-restore-saved-reader-cfi+fast-reveal-v50");
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v27 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v27-patch-failed',
          'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 180),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
