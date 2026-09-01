import app from './artifact-library-reader-v34-continuous-range-sync-entry.js';

const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';
const V34_MARKER = '<script data-r3-audio-continuity-v34="1">';
const V35_FLAG = `<script data-r3-audio-continuity-v35="1">window.__r3AudioContinuityV35={owner:'reader-audio-continuity-v35',singleAudioListenerOwner:true};</script>`;
const V35_LAYOUT_STABILIZER = `<script data-r3-reader-layout-stabilize-v35="1">
(()=>{
  if(window.__r3ReaderLayoutStabilizeV35)return;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const vv=window.visualViewport||null;
  const debug=window.__r3ReaderLayoutStabilizeV35={phase:'boot',reason:'',repairs:0,lastGeometry:null,lastCfi:'',lastError:''};
  let activeUntil=Date.now()+4500;
  let timer=0;
  let running=false;
  let pendingReason='';

  function bridge(){return window.r3ReaderBridge||null;}
  function currentCfi(){
    try{
      const b=bridge();
      const loc=b&&typeof b.current==='function'?b.current():null;
      return String(loc&&loc.start&&loc.start.cfi||'');
    }catch{return '';}
  }
  function savedCfi(){
    if(!bookKey)return '';
    const keys=['r3-reader-audio-state-v11:'+bookKey,'r3-reader-audio-core-v1:'+bookKey];
    for(const key of keys){
      try{
        const row=JSON.parse(localStorage.getItem(key)||'null');
        const cfi=String(row&&row.cfi||'');
        if(cfi)return cfi;
      }catch{}
    }
    return '';
  }
  function geometry(){
    const viewer=document.getElementById('viewer');
    return {
      vw:Math.round(Number(vv&&vv.width||window.innerWidth||0)),
      vh:Math.round(Number(vv&&vv.height||window.innerHeight||0)),
      w:Math.round(Number(viewer&&viewer.clientWidth||0)),
      h:Math.round(Number(viewer&&viewer.clientHeight||0)),
    };
  }
  function sameGeometry(a,b){
    return Boolean(a&&b&&Math.abs(a.vw-b.vw)<=1&&Math.abs(a.vh-b.vh)<=1&&Math.abs(a.w-b.w)<=1&&Math.abs(a.h-b.h)<=1);
  }
  async function waitBridge(){
    for(let n=0;n<40;n++){
      if(document.hidden)return null;
      const b=bridge();
      if(b&&typeof b.display==='function'&&currentCfi())return b;
      await delay(80);
    }
    return bridge();
  }
  async function waitLegacyRestore(target){
    if(!target||!window.__r3AudioBootCfiRestoreV27)return;
    for(let n=0;n<24;n++){
      const state=window.__r3AudioBootCfiV27Debug;
      if(state&&(state.phase==='restored'||state.phase==='timeout'))return;
      await delay(100);
    }
  }
  async function waitStableGeometry(){
    let last=null;
    let stable=0;
    for(let n=0;n<28;n++){
      if(document.hidden)return null;
      const next=geometry();
      if(next.w>100&&next.h>100&&next.vw>100&&next.vh>100){
        stable=sameGeometry(last,next)?stable+1:0;
        if(stable>=3)return next;
      }else stable=0;
      last=next;
      await delay(80);
    }
    return last;
  }
  async function repair(reason){
    if(running){pendingReason=reason;return;}
    running=true;
    try{
      debug.phase='waiting';debug.reason=reason;
      if(document.hidden)return;
      const fontReady=document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve();
      await Promise.race([Promise.resolve(fontReady).catch(()=>{}),delay(900)]);
      const b=await waitBridge();
      if(!b||typeof b.display!=='function')return;
      const target=savedCfi()||currentCfi();
      await waitLegacyRestore(target);
      const stable=await waitStableGeometry();
      if(!stable)return;
      debug.lastGeometry=stable;
      const before=currentCfi();
      const wanted=target||before;
      debug.phase='reflow';
      try{window.dispatchEvent(new Event('resize'));}catch{}
      await delay(180);
      if(wanted){
        try{await Promise.race([Promise.resolve(b.display(wanted)),delay(1400)]);}catch(error){debug.lastError=String(error&&error.message||error).slice(0,180);}
      }
      await delay(180);
      try{window.dispatchEvent(new Event('resize'));}catch{}
      await delay(120);
      try{if(typeof b.persist==='function')b.persist();}catch{}
      debug.repairs++;
      debug.lastCfi=currentCfi();
      debug.lastGeometry=geometry();
      debug.phase='stable';
    }finally{
      running=false;
      if(pendingReason){const next=pendingReason;pendingReason='';schedule(next,120);}
    }
  }
  function schedule(reason,ms=160){
    if(document.hidden)return;
    clearTimeout(timer);
    timer=setTimeout(()=>repair(reason),ms);
  }
  function activate(reason){
    activeUntil=Date.now()+4500;
    schedule(reason,180);
  }

  if(vv)vv.addEventListener('resize',()=>{if(Date.now()<=activeUntil)schedule('visual-viewport',180);},{passive:true});
  window.addEventListener('pageshow',event=>activate(event.persisted?'pageshow-bfcache':'pageshow'));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)activate('visible');});
  activate('boot');
})();
</script>`;

function replaceScoped(source, marker, needle, replacement, label) {
  const markerAt = source.indexOf(marker);
  if (markerAt < 0) throw new Error(`READER_V35_PATCH_MISSING:${label}:marker`);
  const at = source.indexOf(needle, markerAt);
  if (at < 0) throw new Error(`READER_V35_PATCH_MISSING:${label}:needle`);
  const nextMarker = source.indexOf('<script ', markerAt + marker.length);
  if (nextMarker >= 0 && at > nextMarker) throw new Error(`READER_V35_PATCH_SCOPE:${label}`);
  const duplicate = source.indexOf(needle, at + needle.length);
  if (duplicate >= 0 && (nextMarker < 0 || duplicate < nextMarker)) throw new Error(`READER_V35_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0, at) + replacement + source.slice(at + needle.length);
}

function patchSingleAudioOwner(html) {
  let out = String(html || '');
  if (out.includes('data-r3-audio-continuity-v35="1"')) return out;
  if (!out.includes(V34_MARKER)) throw new Error('READER_V35_PATCH_MISSING:v34');

  const debugNeedle = `    peek(offset=1){return bridge()&&bridge().peekReadableAhead?bridge().peekReadableAhead(offset):Promise.resolve(null);},`;
  out = replaceScoped(
    out,
    V34_MARKER,
    debugNeedle,
    `${debugNeedle}\n    primePrefetch(){schedulePrefetch();return prefetchOne(1);},`,
    'debug-prime-prefetch',
  );

  const oldRuntime = `  const tick=async()=>{
    installBridgeHooks();
    const id=currentId();
    if(id&&id!==timingId)await loadTimingForCurrent();
    if(timingWords.length&&!audio.ended){
      const index=wordIndexAt((Number(audio.currentTime)||0)*1000);
      if(index>=0)syncWord(index,false);
    }
  };

  audio.addEventListener('loadedmetadata',()=>{loadTimingForCurrent().then(()=>{tick();schedulePrefetch();});});
  audio.addEventListener('play',()=>{loadTimingForCurrent().then(()=>{tick();schedulePrefetch();});});
  audio.addEventListener('timeupdate',tick);
  audio.addEventListener('seeked',tick);
  audio.addEventListener('ended',()=>{for(const doc of [...document.querySelectorAll('#viewer iframe')].map(f=>{try{return f.contentDocument;}catch{return null;}}).filter(Boolean)){try{doc.defaultView&&doc.defaultView.CSS&&doc.defaultView.CSS.highlights&&doc.defaultView.CSS.highlights.delete(highlightName);}catch{}}});
  window.addEventListener('pagehide',()=>{try{relocatedOff&&relocatedOff();}catch{}},{once:true});

  const boot=setInterval(()=>{
    if(installBridgeHooks()){
      clearInterval(boot);
      setTimeout(()=>{manualArmedAt=Date.now();tick();if(currentId())schedulePrefetch();},700);
    }
  },100);`;

  const newRuntime = `  let tickBusy=false;
  let armedMediaId='';
  let wasEnded=Boolean(audio.ended);
  let rafId=0;
  let lastRafAt=0;

  function clearRangeHighlight(){
    for(const doc of [...document.querySelectorAll('#viewer iframe')].map(f=>{try{return f.contentDocument;}catch{return null;}}).filter(Boolean)){
      try{doc.defaultView&&doc.defaultView.CSS&&doc.defaultView.CSS.highlights&&doc.defaultView.CSS.highlights.delete(highlightName);}catch{}
    }
  }

  const tick=async()=>{
    if(tickBusy)return;
    tickBusy=true;
    try{
      installBridgeHooks();
      const id=currentId();
      if(id&&id!==timingId)await loadTimingForCurrent();
      if(timingWords.length&&!audio.ended){
        const index=wordIndexAt((Number(audio.currentTime)||0)*1000);
        if(index>=0)await syncWord(index,false);
      }
    }finally{tickBusy=false;}
  };

  function armCurrentMedia(){
    const id=currentId();
    if(!id||id===armedMediaId)return false;
    armedMediaId=id;
    loadTimingForCurrent().then(()=>tick()).catch(()=>{});
    schedulePrefetch();
    return true;
  }

  const srcObserver=new MutationObserver(()=>armCurrentMedia());
  try{srcObserver.observe(audio,{attributes:true,attributeFilter:['src']});}catch{}

  const continuityFrame=stamp=>{
    if(stamp-lastRafAt>=100){
      lastRafAt=stamp;
      armCurrentMedia();
      tick();
      const endedNow=Boolean(audio.ended);
      if(endedNow&&!wasEnded)clearRangeHighlight();
      wasEnded=endedNow;
    }
    rafId=requestAnimationFrame(continuityFrame);
  };
  rafId=requestAnimationFrame(continuityFrame);

  window.addEventListener('pagehide',()=>{
    try{relocatedOff&&relocatedOff();}catch{}
    try{srcObserver.disconnect();}catch{}
    try{cancelAnimationFrame(rafId);}catch{}
  },{once:true});

  const boot=setInterval(()=>{
    if(installBridgeHooks()){
      clearInterval(boot);
      setTimeout(()=>{manualArmedAt=Date.now();tick();armCurrentMedia();},700);
    }
  },100);`;

  out = replaceScoped(out, V34_MARKER, oldRuntime, newRuntime, 'single-audio-owner');
  if (!out.includes('</body>')) throw new Error('READER_V35_BODY_MARKER_MISSING');
  out = out.replace('</body>', V35_FLAG + V35_LAYOUT_STABILIZER + '</body>');
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== '/artifact-library/read' || request.method !== 'GET') return response;
    const type = response.headers.get('Content-Type') || '';
    if (!type.toLowerCase().includes('text/html') || response.status !== 200) return response;
    try {
      const updated = patchSingleAudioOwner(await response.text());
      const headers = new Headers(response.headers);
      headers.delete('Content-Length');
      headers.set('X-Robots-Tag', ROBOTS);
      headers.set('X-R3-Reader-Runtime', 'v35-continuity-single-owner');
      headers.set('X-R3-Reader-Patch-Proof', 'v34+v35:ahead-prefetch+range-follow+single-audio-owner');
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v35 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v35-patch-failed',
          'X-R3-Reader-Patch-Error': String(error?.message || error).slice(0, 220),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === 'function') return app.scheduled(controller, env, ctx);
  },
};
