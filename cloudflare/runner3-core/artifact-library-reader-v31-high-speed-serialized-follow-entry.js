import app from "./artifact-library-reader-v30-dark-highlight-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const FOLLOW_HEAD = `  async function followToken(target,force=false){`;
const FOLLOW_MARKER = `  window.__r3AudioPageStepFollowV21=true;`;

const FOLLOW_WRAPPER = `  let r3FollowInFlightV31=false;
  let r3FollowPendingV31=false;
  let r3FollowPendingForceV31=false;
  async function followToken(target,force=false){
    const v31debug=window.__r3AudioHighSpeedV31Debug||(window.__r3AudioHighSpeedV31Debug={ticks:0,followRuns:0,queued:0,currentConcurrent:0,maxConcurrent:0,lastTickAt:0,lastRate:1});
    if(r3FollowInFlightV31){
      r3FollowPendingV31=true;
      r3FollowPendingForceV31=r3FollowPendingForceV31||Boolean(force);
      v31debug.queued++;
      return false;
    }
    r3FollowInFlightV31=true;
    v31debug.followRuns++;
    v31debug.currentConcurrent++;
    v31debug.maxConcurrent=Math.max(v31debug.maxConcurrent,v31debug.currentConcurrent);
    try{
      return await r3FollowTokenOriginalV31(target,force);
    }finally{
      r3FollowInFlightV31=false;
      v31debug.currentConcurrent=Math.max(0,v31debug.currentConcurrent-1);
      const pending=r3FollowPendingV31;
      const pendingForce=r3FollowPendingForceV31;
      r3FollowPendingV31=false;
      r3FollowPendingForceV31=false;
      if(pending&&(pendingForce||(!audio.paused&&!audio.ended))){
        queueMicrotask(()=>{try{syncReading(pendingForce);}catch{}});
      }
    }
  }
`;

const CLOCK_SCRIPT = `<script data-r3-audio-high-speed-v31="1">
(()=>{
  if(window.__r3AudioHighSpeedFollowV31)return;
  window.__r3AudioHighSpeedFollowV31=true;
  const audio=document.getElementById('r3AudioElement');
  if(!audio)return;
  const debug=window.__r3AudioHighSpeedV31Debug||(window.__r3AudioHighSpeedV31Debug={ticks:0,followRuns:0,queued:0,currentConcurrent:0,maxConcurrent:0,lastTickAt:0,lastRate:1});
  let raf=0,lastWall=0;
  function tick(wall){
    const rate=Number(audio.playbackRate)||1;
    debug.lastRate=rate;
    if(!audio.paused&&!audio.ended&&rate>1.05&&wall-lastWall>=75){
      lastWall=wall;
      debug.ticks++;
      debug.lastTickAt=Number(audio.currentTime)||0;
      try{audio.dispatchEvent(new Event('timeupdate'));}catch{}
    }
    raf=requestAnimationFrame(tick);
  }
  raf=requestAnimationFrame(tick);
  window.addEventListener('pagehide',()=>{if(raf)cancelAnimationFrame(raf);},{once:true});
})();
</script>`;

function patchHighSpeedFollow(html){
  let out=String(html||'');
  if(out.includes('data-r3-audio-high-speed-v31="1"'))return out;

  const start=out.indexOf(FOLLOW_HEAD);
  if(start<0)throw new Error('READER_V31_PATCH_MISSING:followHead');
  if(out.indexOf(FOLLOW_HEAD,start+FOLLOW_HEAD.length)>=0)throw new Error('READER_V31_PATCH_AMBIGUOUS:followHead');
  const marker=out.indexOf(FOLLOW_MARKER,start+FOLLOW_HEAD.length);
  if(marker<0)throw new Error('READER_V31_PATCH_MISSING:followMarker');

  const original=out.slice(start,marker);
  const renamed=original.replace(FOLLOW_HEAD,`  async function r3FollowTokenOriginalV31(target,force=false){`);
  if(renamed===original)throw new Error('READER_V31_PATCH_RENAME_FAILED');
  out=out.slice(0,start)+renamed+FOLLOW_WRAPPER+out.slice(marker);

  if(!out.includes('</body>'))throw new Error('READER_V31_BODY_MARKER_MISSING');
  return out.replace('</body>',CLOCK_SCRIPT+'</body>');
}

export default {
  async fetch(request,env,ctx){
    const url=new URL(request.url);
    const response=await app.fetch(request,env,ctx);
    if(url.pathname!=="/artifact-library/read"||request.method!=="GET")return response;
    const type=response.headers.get("Content-Type")||"";
    if(!type.toLowerCase().includes("text/html")||response.status!==200)return response;
    try{
      const updated=patchHighSpeedFollow(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v31-high-speed-serialized-follow");
      headers.set("X-R3-Reader-Patch-Proof","v30+v31:75ms-high-speed-clock+single-flight-follow");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v31 patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v31-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
