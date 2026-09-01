import app from "./artifact-library-reader-v26-persist-follow-cfi-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const BOOT_SCRIPT = `<script data-r3-audio-boot-cfi-v27="1">
(()=>{
  window.__r3AudioBootCfiRestoreV27=true;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;
  const baseKey='r3-reader-position:'+bookKey;
  let target='';
  try{target=String(localStorage.getItem(baseKey)||'');}catch{}
  if(!target){
    let saved=null;
    try{saved=JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:'+bookKey)||'null');}catch{}
    target=String(saved&&saved.cfi||'');
  }
  if(!target)return;
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const currentCfi=()=>{
    try{
      const b=window.r3ReaderBridge;
      const loc=b&&typeof b.current==='function'?b.current():null;
      return String(loc&&loc.start&&loc.start.cfi||'');
    }catch{return '';}
  };
  (async()=>{
    let initial='';
    for(let n=0;n<36;n++){
      const b=window.r3ReaderBridge;
      const before=currentCfi();
      if(before&&!initial)initial=before;
      if(!b||typeof b.display!=='function'||!before){await delay(120);continue;}
      try{await Promise.race([Promise.resolve(b.display(target)),delay(900)]);}catch{}
      await delay(140);
      const after=currentCfi();
      window.__r3AudioBootCfiV27Debug={phase:'attempt',attempt:n,target,initial,before,after};
      if(after&&after!==initial){
        await delay(420);
        const stable=currentCfi();
        if(stable&&stable!==initial){
          try{if(typeof b.persist==='function')b.persist();}catch{}
          window.__r3AudioBootCfiV27Debug={phase:'restored',attempt:n,target,initial,before,after,stable};
          return;
        }
      }
      await delay(100);
    }
    window.__r3AudioBootCfiV27Debug={phase:'timeout',target,initial,current:currentCfi()};
  })();
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
