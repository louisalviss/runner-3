import app from "./artifact-library-reader-v18-verified-outer-anchor-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const SYNC_OLD = `  function syncReading(forceDisplay=false){
    installBridgeGuard();`;
const SYNC_NEW = `  function syncReading(forceDisplay=false){
    if(window.__r3AudioAnchorApplyingV18)return;
    installBridgeGuard();`;

const TARGET_OLD = `      const frozenTargetV18=secondsForFrozenAnchorV18(frozenViewportV18);
      const exactVisible=firstVisibleTokenTarget();
      const freshVisible=firstVisibleRange()||visible;
      const target=Number.isFinite(frozenTargetV18)?frozenTargetV18:(exactVisible&&Number.isFinite(exactVisible.seconds)?exactVisible.seconds:startSecondsForRange(freshVisible));
      window.__r3AudioV18Debug.resolvedTarget=target;
      try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}
      if(frozenViewportV18&&frozenViewportV18.cfi){
        try{await safeDisplay(frozenViewportV18.cfi);await delay(80);buildAlignment(true);}catch(error){window.__r3AudioV18Debug.displayError=String(error&&error.message||error);}
      }
      window.__r3AudioAnchorApplyingV18=false;
      await audio.play();`;
const TARGET_NEW = `      const frozenTargetV18=secondsForFrozenAnchorV18(frozenViewportV18);
      const exactVisible=firstVisibleTokenTarget();
      const freshVisible=firstVisibleRange()||visible;
      const target=Number.isFinite(frozenTargetV18)?frozenTargetV18:(exactVisible&&Number.isFinite(exactVisible.seconds)?exactVisible.seconds:startSecondsForRange(freshVisible));
      window.__r3AudioV18Debug.resolvedTarget=target;
      if(frozenViewportV18&&frozenViewportV18.cfi){
        try{await safeDisplay(frozenViewportV18.cfi);await delay(120);buildAlignment(true);}catch(error){window.__r3AudioV18Debug.displayError=String(error&&error.message||error);}
      }
      const boundedTarget=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));
      try{audio.currentTime=boundedTarget;}catch(error){window.__r3AudioV18Debug.seekError=String(error&&error.message||error);}
      await delay(80);
      let seekActual=Number(audio.currentTime)||0;
      if(Math.abs(seekActual-boundedTarget)>.35){
        try{audio.currentTime=boundedTarget;}catch{}
        await delay(45);
        seekActual=Number(audio.currentTime)||0;
      }
      window.__r3AudioV18Debug.afterFinalSeek={target:boundedTarget,actual:seekActual};
      window.__r3AudioAnchorApplyingV18=false;
      await audio.play();`;

const MARKER_OLD = `  window.__r3AudioVerifiedOuterAnchorV18=true;`;
const MARKER_NEW = `  window.__r3AudioVerifiedOuterAnchorV18=true;
  window.__r3AudioStableFinalSeekV19=true;`;

function replaceOnce(source, needle, replacement, label) {
  const first=source.indexOf(needle);
  if(first<0)throw new Error(`READER_V19_PATCH_MISSING:${label}`);
  if(source.indexOf(needle,first+needle.length)>=0)throw new Error(`READER_V19_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0,first)+replacement+source.slice(first+needle.length);
}

function patchStableFinalSeek(html){
  let out=String(html||'');
  if(out.includes('window.__r3AudioStableFinalSeekV19=true'))return out;
  out=replaceOnce(out,SYNC_OLD,SYNC_NEW,'syncGuard');
  out=replaceOnce(out,TARGET_OLD,TARGET_NEW,'finalSeek');
  out=replaceOnce(out,MARKER_OLD,MARKER_NEW,'marker');
  return out;
}

export default {
  async fetch(request,env,ctx){
    const url=new URL(request.url);
    const response=await app.fetch(request,env,ctx);
    if(url.pathname!=="/artifact-library/read"||request.method!=="GET")return response;
    const type=response.headers.get("Content-Type")||"";
    if(!type.toLowerCase().includes("text/html"))return response;
    if(response.status!==200)return response;
    try{
      const updated=patchStableFinalSeek(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v19-stable-final-seek");
      headers.set("X-R3-Reader-Patch-Proof","v18:block+range+prepare+target+save2+finally;v19:syncguard+finalseek");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v19 patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v19-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
