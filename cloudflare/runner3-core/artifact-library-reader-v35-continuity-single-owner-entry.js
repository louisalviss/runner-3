import app from './artifact-library-reader-v34-continuous-range-sync-entry.js';

const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';
const V34_MARKER = '<script data-r3-audio-continuity-v34="1">';
const V35_FLAG = `<script data-r3-audio-continuity-v35="1">window.__r3AudioContinuityV35={owner:'reader-audio-continuity-v35',singleAudioListenerOwner:true};</script>`;
const V35_LAYOUT_STABILIZER = `<script data-r3-reader-layout-stabilize-v35="1" data-r3-observe-only-v46="1">
(()=>{
  if(window.__r3ReaderLayoutStabilizeV35)return;
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const vv=window.visualViewport||null;
  const debug=window.__r3ReaderLayoutStabilizeV35={phase:'boot',reason:'',repairs:0,lastGeometry:null,lastCfi:'',lastError:'',owner:'observe-only-v46'};
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
    for(let n=0;n<45;n++){
      if(document.hidden)return null;
      const b=bridge();
      if(b&&currentCfi())return b;
      await delay(80);
    }
    return bridge();
  }
  async function waitStableGeometry(){
    let last=null;
    let stable=0;
    for(let n=0;n<30;n++){
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
  async function waitStableCfi(){
    let last='';
    let stable=0;
    for(let n=0;n<24;n++){
      const cfi=currentCfi();
      if(cfi){
        stable=cfi===last?stable+1:0;
        if(stable>=2)return cfi;
        last=cfi;
      }else stable=0;
      await delay(90);
    }
    return currentCfi();
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
      if(!b)return;
      const stableGeometry=await waitStableGeometry();
      if(!stableGeometry)return;
      debug.phase='settling';
      const cfi=await waitStableCfi();
      if(!cfi)return;
      debug.lastGeometry=stableGeometry;
      debug.lastCfi=cfi;
      debug.repairs++;
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

const V35_EARLY_AUDIO_RESERVE = `<style data-r3-reader-audio-reserve-v40="1">
#viewer{bottom:calc(210px + env(safe-area-inset-bottom,0px))!important}
</style>`;

const V35_PLAYER_CHAPTERS = `<style data-r3-player-chapters-v38="1">
#r3AudioHead{grid-template-columns:minmax(0,1fr) 32px 50px 32px 36px!important;gap:5px!important}
#r3AudioSpeedDown,#r3AudioSpeedUp{height:36px;min-width:32px!important;border:1px solid var(--line,rgba(127,127,127,.22))!important;border-radius:11px!important;background:color-mix(in srgb,var(--fg,currentColor) 7%,transparent)!important;font-size:18px!important;font-weight:800!important;padding:0!important}
#r3AudioSpeedDown:disabled,#r3AudioSpeedUp:disabled{opacity:.32}
#r3AudioChapterMeta{margin-top:2px;color:var(--muted,#888);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#r3AudioChapterNav{display:none;grid-template-columns:42px minmax(0,1fr) 42px;gap:7px;align-items:center;padding:2px 12px 8px}
#r3AudioDock.r3-expanded #r3AudioChapterNav{display:grid}
#r3AudioChapterPrev,#r3AudioChapterNext,#r3AudioChapterSelect{height:36px;border:1px solid var(--line,rgba(127,127,127,.22))!important;border-radius:10px!important;background:color-mix(in srgb,var(--fg,currentColor) 5%,transparent)!important;color:var(--fg,inherit)!important;font:inherit!important;font-size:11px!important;font-weight:700!important}
#r3AudioChapterPrev,#r3AudioChapterNext{min-width:42px!important;font-size:20px!important;padding:0!important}
#r3AudioChapterSelect{min-width:0;width:100%;padding:0 9px;text-overflow:ellipsis}
#r3ReaderChapterBadge{position:fixed;z-index:21;left:76px;right:76px;top:calc(max(10px,env(safe-area-inset-top)) + 30px);text-align:center;color:var(--muted,#888);font:600 10px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none;opacity:0;transition:opacity .16s ease}
body.controls #r3ReaderChapterBadge{opacity:1}
body.r3-audio-ui #viewer,body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(210px + env(safe-area-inset-bottom,0px))!important}
body.r3-audio-ui .bottom-status,body.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:calc(216px + env(safe-area-inset-bottom,0px))!important}
</style>
<script data-r3-player-chapters-v38="1">
(()=>{
  if(window.__r3PlayerChaptersV38)return;
  window.__r3PlayerChaptersV38={version:'v38',chapterMoves:0};
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  const dock=document.getElementById('r3AudioDock');
  const audio=document.getElementById('r3AudioElement');
  const speed=document.getElementById('r3AudioSpeed');
  const status=document.getElementById('r3AudioStatus');
  const title=document.getElementById('r3AudioTitle');
  const copy=document.getElementById('r3AudioCopy');
  const timeline=document.getElementById('r3AudioTimeline');
  if(!bookKey||!dock||!audio||!speed||!status)return;
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const bridge=()=>window.r3ReaderBridge||null;
  const rates=[.75,1,1.25,1.5,1.75,2,2.25,2.5,2.75,3];
  let changing=false;
  let chapterSig='';
  let offRelocated=null;

  const down=document.createElement('button');
  down.id='r3AudioSpeedDown';down.type='button';down.textContent='−';down.setAttribute('aria-label','Giảm tốc độ');
  const up=document.createElement('button');
  up.id='r3AudioSpeedUp';up.type='button';up.textContent='+';up.setAttribute('aria-label','Tăng tốc độ');
  speed.before(down);speed.after(up);

  const meta=document.createElement('div');
  meta.id='r3AudioChapterMeta';meta.textContent='Đang đọc chapter…';
  if(copy)copy.appendChild(meta);

  const nav=document.createElement('div');
  nav.id='r3AudioChapterNav';
  nav.innerHTML='<button id="r3AudioChapterPrev" type="button" aria-label="Chapter trước">‹</button><select id="r3AudioChapterSelect" aria-label="Danh sách chapter"></select><button id="r3AudioChapterNext" type="button" aria-label="Chapter sau">›</button>';
  if(timeline)dock.insertBefore(nav,timeline);else dock.appendChild(nav);
  const prev=nav.querySelector('#r3AudioChapterPrev');
  const next=nav.querySelector('#r3AudioChapterNext');
  const select=nav.querySelector('#r3AudioChapterSelect');

  const badge=document.createElement('div');
  badge.id='r3ReaderChapterBadge';
  document.body.appendChild(badge);

  function labelRate(value){const n=Number(value)||1;return String(n).replace(/\.00$/,'').replace(/(\.\d)0$/,'$1')+'×';}
  function currentRate(){const fromAudio=Number(audio.playbackRate);if(Number.isFinite(fromAudio)&&fromAudio>0)return fromAudio;return Number(String(speed.textContent||'1').replace('×',''))||1;}
  function updateRateButtons(){const rate=currentRate();down.disabled=rate<=rates[0]+.001;up.disabled=rate>=rates[rates.length-1]-.001;}
  function setRate(value){const nextRate=Math.max(rates[0],Math.min(rates[rates.length-1],Math.round(Number(value)*4)/4));const setter=window.__r3AudioCoreSetRate;if(typeof setter==='function')setter(nextRate);else{audio.playbackRate=nextRate;speed.textContent=labelRate(nextRate);}updateRateButtons();}
  down.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();setRate(currentRate()-.25);},true);
  up.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();setRate(currentRate()+.25);},true);
  audio.addEventListener('ratechange',updateRateButtons);
  speed.addEventListener('click',()=>setTimeout(updateRateButtons,0));
  updateRateButtons();

  async function refreshChapters(force=false){
    try{
      const b=bridge();
      if(!b||typeof b.chapterInfo!=='function')return false;
      const info=await b.chapterInfo();
      const chapters=Array.isArray(info&&info.chapters)?info.chapters:[];
      if(!chapters.length){meta.textContent='Chapter chưa có TOC';badge.textContent='';return false;}
      const sig=chapters.map(row=>String(row.href||'')+'|'+String(row.label||'')).join('¦');
      if(force||sig!==chapterSig||select.options.length!==chapters.length){
        chapterSig=sig;select.innerHTML='';
        chapters.forEach((row,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=String(row.label||('Chapter '+(index+1)));select.appendChild(option);});
      }
      const index=Math.max(0,Math.min(chapters.length-1,Number(info.index)>=0?Number(info.index):0));
      select.value=String(index);
      prev.disabled=index<=0;next.disabled=index>=chapters.length-1;
      const row=chapters[index]||{};
      meta.textContent='Chương '+(index+1)+' / '+chapters.length;
      badge.textContent=String(row.label||('Chương '+(index+1)))+' · '+(index+1)+'/'+chapters.length;
      return true;
    }catch{return false;}
  }

  async function moveChapter(target,mode){
    if(changing)return;
    const b=bridge();
    if(!b)return;
    changing=true;
    const wasPlaying=!audio.paused&&!audio.ended;
    try{
      audio.pause();
      status.textContent='Nam Minh · chuyển chapter…';
      let ok=false;
      if(mode==='step'&&typeof b.stepChapter==='function')ok=await b.stepChapter(Number(target));
      else if(mode==='index'&&typeof b.displayChapter==='function')ok=await b.displayChapter(Number(target));
      if(!ok){status.textContent='Không chuyển được chapter';return;}
      window.__r3PlayerChaptersV38.chapterMoves++;
      await delay(260);
      await refreshChapters(true);
      const prepare=window.__r3AudioCorePrepareCurrent;
      if(typeof prepare==='function')await prepare({autoplay:wasPlaying,allowSaved:false});
      else status.textContent=wasPlaying?'Nam Minh · nhấn phát lại':'Nam Minh · sẵn sàng';
    }catch(error){status.textContent=String(error&&error.message||'Lỗi chapter').slice(0,90);}
    finally{changing=false;}
  }

  prev.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();moveChapter(-1,'step');},true);
  next.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();moveChapter(1,'step');},true);
  select.addEventListener('change',event=>{event.stopImmediatePropagation();moveChapter(Number(select.value),'index');},true);

  const hook=()=>{const b=bridge();if(b&&typeof b.onRelocated==='function'&&!offRelocated){offRelocated=b.onRelocated(()=>setTimeout(()=>refreshChapters(false),100));return true;}return false;};
  let tries=0;const boot=setInterval(()=>{hook();refreshChapters(false);if(++tries>40){clearInterval(boot);}},150);
  window.addEventListener('pagehide',()=>{clearInterval(boot);try{offRelocated&&offRelocated();}catch{}},{once:true});
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
      setTimeout(()=>{manualArmedAt=Date.now();tick();warmCurrentChapter();if(currentId())schedulePrefetch();},700);
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
      setTimeout(()=>{manualArmedAt=Date.now();tick();warmCurrentChapter();armCurrentMedia();},700);
    }
  },100);`;

  out = replaceScoped(out, V34_MARKER, oldRuntime, newRuntime, 'single-audio-owner');
  if (!out.includes('</head>')) throw new Error('READER_V35_HEAD_MARKER_MISSING');
  out = out.replace('</head>', V35_EARLY_AUDIO_RESERVE + '</head>');
  if (!out.includes('</body>')) throw new Error('READER_V35_BODY_MARKER_MISSING');
  out = out.replace('</body>', V35_FLAG + V35_LAYOUT_STABILIZER + V35_PLAYER_CHAPTERS + '</body>');
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
