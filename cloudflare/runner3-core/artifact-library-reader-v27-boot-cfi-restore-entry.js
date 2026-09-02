import app from "./artifact-library-reader-v26-persist-follow-cfi-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const BOOT_SCRIPT = `<script data-r3-audio-boot-cfi-v27="1" data-r3-direct-restore-v45="1" data-r3-single-boot-owner-v46="1" data-r3-atomic-reveal-v48="1">
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
  async function waitLayoutStable(){
    for(let n=0;n<45;n++){
      const state=window.__r3ReaderLayoutStabilizeV35;
      if(state&&state.phase==='stable')return true;
      await delay(80);
    }
    return false;
  }
  async function waitEpubFonts(){
    const waits=[];
    try{if(document.fonts&&document.fonts.ready)waits.push(Promise.resolve(document.fonts.ready).catch(()=>{}));}catch{}
    for(const frame of document.querySelectorAll('#viewer iframe')){
      try{
        const fonts=frame.contentDocument&&frame.contentDocument.fonts;
        if(fonts&&fonts.ready)waits.push(Promise.resolve(fonts.ready).catch(()=>{}));
      }catch{}
    }
    if(!waits.length)return;
    await Promise.race([Promise.all(waits),delay(1400)]);
  }
  function visualSignature(){
    const viewer=document.getElementById('viewer');
    if(!viewer)return '';
    const vr=viewer.getBoundingClientRect();
    const parts=[
      currentCfi(),
      Math.round(vr.left),Math.round(vr.top),Math.round(vr.width),Math.round(vr.height),
      Math.round(window.innerWidth||0),Math.round(window.innerHeight||0),
    ];
    const frames=[...viewer.querySelectorAll('iframe')];
    parts.push(frames.length);
    for(const frame of frames){
      try{
        const r=frame.getBoundingClientRect();
        const doc=frame.contentDocument;
        const root=doc&&doc.documentElement;
        const body=doc&&doc.body;
        const fonts=doc&&doc.fonts;
        parts.push(
          Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height),
          Number(root&&root.scrollWidth||body&&body.scrollWidth||0),
          Number(root&&root.scrollHeight||body&&body.scrollHeight||0),
          fonts&&fonts.status?String(fonts.status):'na'
        );
      }catch{parts.push('x');}
    }
    return parts.join('|');
  }
  async function waitVisualQuiet(){
    let last='';
    let stable=0;
    for(let n=0;n<70;n++){
      const sig=visualSignature();
      if(sig&&sig===last)stable++;else stable=0;
      last=sig;
      if(stable>=5)return {ok:true,signature:sig,samples:stable+1};
      await delay(80);
    }
    return {ok:false,signature:last,samples:stable+1};
  }
  async function finish(phase){
    debug.phase=phase;
    debug.after=currentCfi();
    debug.finishedAt=Date.now();
    await nextPaint();
    window.__R3_READER_RESTORE_PENDING=false;
    document.documentElement.classList.remove('r3-restore-pending-v45');
    await nextPaint();
    try{window.dispatchEvent(new CustomEvent('r3-reader-restore-ready-v45',{detail:{phase,cfi:debug.after,target:debug.target||'',owner:'atomic-reveal-v48'}}));}catch{}
  }

  (async()=>{
    debug.phase='observe-base-reader';
    debug.target=String(window.__r3ReaderRestoreTargetV45||savedReaderCfi()||'');
    const initial=currentCfi();
    debug.phase='wait-base-display-promise';
    const bootDone=await waitBaseBootDone();
    if(!bootDone){
      window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',initial,current:currentCfi(),reason:'base-display-promise'};
      await finish('base-display-timeout');
      return;
    }
    debug.phase='wait-layout-stable';
    await waitLayoutStable();
    debug.phase='wait-epub-fonts';
    await waitEpubFonts();
    debug.phase='wait-visual-quiet';
    const quiet=await waitVisualQuiet();
    const after=currentCfi();
    debug.after=after;
    debug.visualQuiet=quiet;
    window.__r3AudioBootCfiV27Debug={phase:'restored',attempt:0,target:debug.target||'',initial,before:initial,after,stable:after,direct:false,owner:'base-reader-v47+atomic-reveal-v48',visualQuiet:quiet.ok,samples:quiet.samples};
    await finish(quiet.ok?'ready':'ready-timeout-quiet');
  })().catch(async error=>{
    debug.error=String(error&&error.message||error||'restore observe failed').slice(0,180);
    window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',current:currentCfi(),reason:'observer',error:debug.error};
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
      headers.set("X-R3-Reader-Patch-Proof", "v26+v27:boot-restore-saved-reader-cfi+atomic-v48");
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
