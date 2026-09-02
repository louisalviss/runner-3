import app from "./artifact-library-reader-v26-persist-follow-cfi-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const BOOT_SCRIPT = `<script data-r3-audio-boot-cfi-v27="1" data-r3-direct-restore-v45="1">
(()=>{
  if(window.__r3AudioBootCfiRestoreV27)return;
  window.__r3AudioBootCfiRestoreV27=true;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;
  const baseKey='r3-reader-position:'+bookKey;
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const debug=window.__r3ReaderDirectRestoreV45||{phase:'boot',bookKey,startedAt:Date.now(),target:'',after:'',error:''};
  window.__r3ReaderDirectRestoreV45=debug;

  function readCfi(key){
    try{const row=JSON.parse(localStorage.getItem(key)||'null');return String(row&&row.cfi||'');}catch{return '';}
  }
  function uniqueTargets(){
    const out=[];
    const push=value=>{value=String(value||'');if(value&&!out.includes(value))out.push(value);};
    push(window.__r3ReaderRestoreTargetV45);
    try{push(localStorage.getItem(baseKey)||'');}catch{}
    push(readCfi('r3-reader-audio-state-v11:'+bookKey));
    push(readCfi('r3-reader-audio-core-v1:'+bookKey));
    return out.slice(0,3);
  }
  function currentCfi(){
    try{
      const b=window.r3ReaderBridge;
      const loc=b&&typeof b.current==='function'?b.current():null;
      return String(loc&&loc.start&&loc.start.cfi||'');
    }catch{return '';}
  }
  async function waitBridge(){
    for(let n=0;n<45;n++){
      const b=window.r3ReaderBridge;
      if(b&&typeof b.display==='function')return b;
      await delay(70);
    }
    return window.r3ReaderBridge||null;
  }
  async function waitLayoutStable(){
    for(let n=0;n<34;n++){
      const state=window.__r3ReaderLayoutStabilizeV35;
      if(state&&state.phase==='stable')return true;
      await delay(80);
    }
    return false;
  }
  function finish(phase){
    debug.phase=phase;
    debug.after=currentCfi();
    debug.finishedAt=Date.now();
    window.__R3_READER_RESTORE_PENDING=false;
    document.documentElement.classList.remove('r3-restore-pending-v45');
    try{window.dispatchEvent(new CustomEvent('r3-reader-restore-ready-v45',{detail:{phase,cfi:debug.after,target:debug.target||''}}));}catch{}
  }

  (async()=>{
    const targets=uniqueTargets();
    if(!targets.length){finish('no-target');return;}
    const b=await waitBridge();
    if(!b||typeof b.display!=='function'){
      window.__r3AudioBootCfiV27Debug={phase:'timeout',target:targets[0]||'',current:currentCfi(),reason:'bridge'};
      finish('bridge-timeout');
      return;
    }

    const initial=currentCfi();
    let restored=false;
    let error='';
    for(const candidate of targets){
      debug.phase='direct-display';
      debug.target=candidate;
      try{
        // One direct CFI relocation per candidate. Never walk pages with next()/prev().
        await Promise.resolve(b.display(candidate));
        await delay(120);
        const after=currentCfi();
        if(after){
          restored=true;
          debug.after=after;
          try{if(typeof b.persist==='function')b.persist();}catch{}
          break;
        }
      }catch(err){error=String(err&&err.message||err||'display failed').slice(0,180);}
    }

    debug.error=error;
    if(restored){
      window.__r3AudioBootCfiV27Debug={phase:'restored',attempt:0,target:debug.target,initial,before:initial,after:debug.after,stable:debug.after,direct:true};
      await waitLayoutStable();
      await delay(80);
      finish('ready');
      return;
    }

    window.__r3AudioBootCfiV27Debug={phase:'timeout',target:targets[0]||'',initial,current:currentCfi(),reason:'display',error};
    await waitLayoutStable();
    finish('fallback-current-page');
  })().catch(error=>{
    debug.error=String(error&&error.message||error||'restore failed').slice(0,180);
    window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',current:currentCfi(),reason:'exception',error:debug.error};
    finish('fallback-current-page');
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
      headers.set("X-R3-Reader-Patch-Proof", "v26+v27:boot-restore-saved-reader-cfi");
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
