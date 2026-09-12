import app from './artifact-library-reader-v2-entry.js';

const ROBOTS='noindex, nofollow, noarchive, nosnippet, noimageindex';
const CLEAN_VERSION='v112';

function cleanIosCsp(csp){
  let value=String(csp||'');
  if(!value)return value;
  if(!/connect-src[^;]*\bblob:/.test(value))value=/connect-src[^;]*/.test(value)?value.replace(/connect-src([^;]*)/,(_m,rest)=>`connect-src${rest} blob:`):value+`; connect-src 'self' https: blob:`;
  if(!/style-src[^;]*\bblob:/.test(value))value=/style-src[^;]*/.test(value)?value.replace(/style-src([^;]*)/,(_m,rest)=>`style-src${rest} blob:`):value+`; style-src 'self' 'unsafe-inline' blob:`;
  if(/base-uri[^;]*/.test(value))value=value.replace(/base-uri[^;]*/,`base-uri 'self'`);else value+=`; base-uri 'self'`;
  return value;
}

const CLEAN_STYLE=`<style data-r3-clean-ios-v112="1">
html[data-r3-clean-ios="v112"],html[data-r3-clean-ios="v112"] body{overscroll-behavior:none}
html[data-r3-clean-ios="v112"] #viewer{bottom:calc(70px + env(safe-area-inset-bottom,0px))!important}
html[data-r3-clean-ios="v112"] .bottom-status{bottom:calc(76px + env(safe-area-inset-bottom,0px))!important}
#r3CleanAudio{position:fixed;left:6px;right:6px;bottom:max(6px,env(safe-area-inset-bottom,0px));z-index:10000;min-height:58px;border:1px solid var(--line,rgba(127,127,127,.24));border-radius:16px;background:var(--panel,rgba(252,251,248,.97));color:var(--fg,inherit);box-shadow:0 12px 36px rgba(0,0,0,.22);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);font:13px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:grid;grid-template-columns:46px minmax(0,1fr) 48px 42px;gap:7px;align-items:center;padding:7px 8px;touch-action:manipulation}
#r3CleanAudio *{box-sizing:border-box}
#r3CleanAudio button{appearance:none;-webkit-appearance:none;border:1px solid var(--line,rgba(127,127,127,.2));background:transparent;color:inherit;border-radius:11px;height:42px;font:inherit;font-weight:750;touch-action:manipulation}
#r3CleanAudio button:disabled{opacity:.55}
#r3CleanPlay{font-size:17px!important;background:var(--fg,currentColor)!important;color:var(--bg,#fff)!important;border-radius:999px!important}
#r3CleanAudioCopy{min-width:0;overflow:hidden}
#r3CleanAudioTitle{font-size:12px;font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#r3CleanAudioStatus{margin-top:3px;color:var(--muted,#777);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#r3CleanAudio.r3-expanded{grid-template-columns:46px minmax(0,1fr) 48px 42px;min-height:112px;padding-bottom:48px}
#r3CleanTransport{display:none;position:absolute;left:8px;right:8px;bottom:7px;grid-template-columns:1fr 1fr;gap:8px}
#r3CleanAudio.r3-expanded #r3CleanTransport{display:grid}
#r3CleanTransport button{height:34px}
html[data-r3-clean-ios="v112"] body.settings #r3CleanAudio{visibility:hidden;pointer-events:none}
@media(min-width:700px){#r3CleanAudio{left:50%;right:auto;width:540px;transform:translateX(-50%)}}
</style>`;

const CLEAN_SCRIPT=`<script data-r3-clean-ios-runtime-v112="1">
(()=>{
  if(window.__r3CleanIosV112)return;
  window.__r3CleanIosV112={version:'v112',audioRequests:0,lastAction:'boot',lastError:''};
  const debug=window.__r3CleanIosV112;
  const root=document.documentElement;root.dataset.r3CleanIos='v112';
  // Keep chrome reachable on physical iPhone; v2's document gesture remains the only reader gesture owner.
  document.body.classList.add('controls');
  const params=new URLSearchParams(location.search);const bookKey=params.get('key')||'';
  const dock=document.createElement('section');dock.id='r3CleanAudio';dock.setAttribute('aria-label','Audio chương hiện tại');
  dock.innerHTML='<button id="r3CleanPlay" type="button" aria-label="Phát audio">▶</button><div id="r3CleanAudioCopy"><div id="r3CleanAudioTitle">Audio chương hiện tại</div><div id="r3CleanAudioStatus">Nam Minh · nhấn phát</div></div><button id="r3CleanSpeed" type="button" aria-label="Tốc độ">1×</button><button id="r3CleanExpand" type="button" aria-label="Mở rộng">⌃</button><div id="r3CleanTransport"><button id="r3CleanBack" type="button">↶ 15 giây</button><button id="r3CleanForward" type="button">15 giây ↷</button></div><audio id="r3CleanAudioElement" preload="metadata"></audio>';
  document.body.appendChild(dock);
  const play=dock.querySelector('#r3CleanPlay'),speed=dock.querySelector('#r3CleanSpeed'),expand=dock.querySelector('#r3CleanExpand'),back=dock.querySelector('#r3CleanBack'),forward=dock.querySelector('#r3CleanForward'),status=dock.querySelector('#r3CleanAudioStatus'),title=dock.querySelector('#r3CleanAudioTitle'),audio=dock.querySelector('#r3CleanAudioElement');
  const rates=[1,1.25,1.5,1.75,2];let rateIndex=0,currentId='',loadedSignature='',requestSeq=0;
  function setStatus(v){status.textContent=String(v||'Nam Minh').slice(0,100)}
  function setPlay(mode){play.disabled=mode==='loading';play.textContent=mode==='loading'?'…':mode==='pause'?'Ⅱ':'▶'}
  function framePayload(){let best=null;for(const frame of document.querySelectorAll('#viewer iframe')){try{const doc=frame.contentDocument,body=doc&&doc.body,text=String(body&&body.innerText||'').trim();if(text.length<80)continue;if(!best||text.length>best.text.length){const h=doc.querySelector('h1,h2,h3,.chapter-title');best={text,chapterTitle:String(h&&h.textContent||doc.title||'').trim().slice(0,240),chapterHref:String(frame.getAttribute('src')||'').slice(0,600)}}}catch{}}if(!best)return null;best.signature=best.text.length+'|'+best.text.slice(0,160)+'|'+best.text.slice(-160);return best}
  async function readState(id){const q=new URLSearchParams({id,bookKey});const r=await fetch('/artifact-library/audio?'+q,{cache:'no-store'});const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.error||('HTTP '+r.status));return data}
  async function waitReady(id,seq){for(let n=0;n<240;n++){if(seq!==requestSeq)return null;const data=await readState(id);if(data.status==='ready')return data;if(data.status==='error')throw new Error(data.error||'Tạo audio thất bại');setStatus(data.status==='processing'?'Nam Minh · đang tổng hợp…':'Nam Minh · đang xếp hàng…');await new Promise(r=>setTimeout(r,1500))}throw new Error('Audio chưa sẵn sàng')}
  async function toggleAudio(){
    debug.lastAction='audio';const payload=framePayload();if(!payload){setStatus('Chưa lấy được nội dung chương');return}
    title.textContent=payload.chapterTitle||'Chương hiện tại';
    if(audio.src&&loadedSignature===payload.signature){if(audio.paused)await audio.play().catch(()=>{});else audio.pause();return}
    const seq=++requestSeq;debug.audioRequests++;setPlay('loading');setStatus('Nam Minh · đang chuẩn bị…');
    try{const r=await fetch('/artifact-library/audio',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',clientVersion:'reader-clean-ios-v112'})});let data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.error||('HTTP '+r.status));currentId=data.id||'';if(!currentId)throw new Error('AUDIO_ID_MISSING');if(data.status!=='ready')data=await waitReady(currentId,seq);if(!data||seq!==requestSeq)return;if(!data.mediaUrl)throw new Error('AUDIO_MEDIA_URL_MISSING');loadedSignature=payload.signature;audio.src=data.mediaUrl;audio.playbackRate=rates[rateIndex];await audio.play()}catch(error){debug.lastError=String(error&&error.message||error);setPlay('play');setStatus(debug.lastError.slice(0,90))}
  }
  play.addEventListener('click',toggleAudio);
  speed.addEventListener('click',()=>{rateIndex=(rateIndex+1)%rates.length;audio.playbackRate=rates[rateIndex];speed.textContent=rates[rateIndex]+'×';debug.lastAction='speed'});
  expand.addEventListener('click',()=>{dock.classList.toggle('r3-expanded');const on=dock.classList.contains('r3-expanded');expand.textContent=on?'⌄':'⌃';debug.lastAction='expand'});
  back.addEventListener('click',()=>{if(Number.isFinite(audio.duration))audio.currentTime=Math.max(0,(audio.currentTime||0)-15)});
  forward.addEventListener('click',()=>{if(Number.isFinite(audio.duration))audio.currentTime=Math.min(audio.duration||Infinity,(audio.currentTime||0)+15)});
  audio.addEventListener('play',()=>{setPlay('pause');setStatus('Nam Minh · đang phát')});
  audio.addEventListener('pause',()=>{if(audio.src&&!audio.ended){setPlay('play');setStatus('Nam Minh · tạm dừng')}});
  audio.addEventListener('ended',()=>{setPlay('play');setStatus('Nam Minh · hết chương')});
  audio.addEventListener('loadedmetadata',()=>setStatus('Nam Minh · sẵn sàng'));
  window.addEventListener('pagehide',()=>{try{audio.pause()}catch{}},{once:true});
})();
</script>`;

export function patchCleanIosV110(html){
  let out=String(html||'');
  if(out.includes('data-r3-clean-ios-v112="1"'))return out;
  if(!out.includes('id="viewer"')||!out.includes('</head>')||!out.includes('</body>'))throw new Error('CLEAN_IOS_BASE_MARKERS_MISSING');

  // Physical iPhone must never pre-generate EPUB locations. On very large books
  // (1498 chapters in the affected case), epub.js locations.generate(1600) can
  // monopolize WebKit's main thread for a long time. Structural spine/page
  // percentage is already available and D1 stores the canonical CFI.
  const locationsStart=out.indexOf('  async function r3EnsureLocationsV55(){');
  const locationsEnd=out.indexOf('\n\n  const R3_BOOK_INFO_V54=',locationsStart);
  if(locationsStart<0||locationsEnd<0)throw new Error('CLEAN_IOS_LOCATIONS_RANGE_MISSING');
  out=out.slice(0,locationsStart)+`  async function r3EnsureLocationsV55(){
    window.__r3IosLocationsV112={disabled:true,reason:'large-book-main-thread',at:Date.now()};
    return false;
  }`+out.slice(locationsEnd);

  // Replace the entire accumulated v49/v58/v61/v62/v67/v68/v69 boot sequence.
  // No full-EPUB IndexedDB read/write, no buffer.slice() duplicate, no viewport
  // polling, no 100ms cold-boot clamp loop, and no legacy layout observers.
  const openStart=out.indexOf('  async function openBook(){');
  const openEnd=out.indexOf("\n\n  $('settingsButton').addEventListener",openStart);
  if(openStart<0||openEnd<0)throw new Error('CLEAN_IOS_OPENBOOK_RANGE_MISSING');
  const minimalOpenBook=`  async function openBook(){
    window.__r3IosLocationsV112={disabled:true,reason:'large-book-main-thread',at:Date.now()};
    const boot=window.__r3IosMinimalBootV112={version:'v112',phase:'start',startedAt:Date.now(),fetchMs:0,displayMs:0,target:'',after:'',error:''};
    let loadingTimer=0;
    try{
      if(typeof window.ePub!=='function')throw new Error('Reader engine failed to load');
      loadingTimer=setTimeout(()=>{try{$('loading').classList.remove('hidden')}catch{}},250);
      const fetchStarted=performance.now();
      const url=await signedUrl();
      const response=await fetch(url,{cache:'no-store'});
      if(!response.ok)throw new Error('EPUB HTTP '+response.status);
      const buffer=await response.arrayBuffer();
      boot.fetchMs=Math.round(performance.now()-fetchStarted);boot.bytes=buffer.byteLength;
      book=window.ePub(buffer);
      rendition=book.renderTo('viewer',{width:'100%',height:'100%',spread:'none',flow:'paginated',manager:'default'});
      registerThemes();applyReaderSettings();
      rendition.on('rendered',()=>{bindEpubContents();try{$('loading').classList.add('hidden')}catch{}});
      rendition.on('relocated',loc=>{
        const cfi=String(loc&&loc.start&&loc.start.cfi||'');
        if(cfi)persist(keys.position,cfi);
        const pct=r3PercentFromCfiV55(cfi,loc);
        r3WriteProgressV55(pct,cfi);
        $('position').textContent=pct===null?'Đã lưu vị trí':pct+'% · đã lưu';
        setTimeout(bindEpubContents,0);
      });
      await r3MergeRemoteProgressV65();
      const saved=String(localStorage.getItem(keys.position)||'');boot.target=saved;
      try{localStorage.setItem('r3-reader-last-open:'+key,String(Date.now()))}catch{}
      window.__R3_BASE_READER_BOOT_PENDING=true;window.__R3_BASE_READER_BOOT_DONE=false;
      window.__r3BaseReaderBootV47={phase:'display',target:saved,startedAt:Date.now(),after:'',error:'',owner:'minimal-ios-v112'};
      const displayStarted=performance.now();
      try{await rendition.display(saved||undefined)}catch(error){
        window.__r3BaseReaderBootV47.error=String(error&&error.message||error||'display failed').slice(0,180);
        try{localStorage.removeItem(keys.position)}catch{}
        await rendition.display();
      }
      boot.displayMs=Math.round(performance.now()-displayStarted);
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      try{boot.after=String(rendition.currentLocation()?.start?.cfi||'')}catch{}
      window.__r3BaseReaderBootV47.after=boot.after;window.__r3BaseReaderBootV47.phase='done';window.__r3BaseReaderBootV47.finishedAt=Date.now();
      window.__R3_BASE_READER_BOOT_PENDING=false;window.__R3_BASE_READER_BOOT_DONE=true;
      boot.phase='done';boot.finishedAt=Date.now();boot.totalMs=boot.finishedAt-boot.startedAt;
      bindEpubContents();clearTimeout(loadingTimer);$('loading').classList.add('hidden');document.body.classList.add('controls');
      try{window.dispatchEvent(new CustomEvent('r3-base-reader-boot-done-v47',{detail:{target:saved,cfi:boot.after,owner:'minimal-ios-v112'}}))}catch{}
    }catch(error){
      clearTimeout(loadingTimer);boot.phase='error';boot.error=String(error&&error.message||error);boot.finishedAt=Date.now();
      $('loading').classList.remove('hidden');$('loading').textContent='Không mở được EPUB: '+boot.error;$('position').textContent='Reader error';showControls();
    }
  }`;
  out=out.slice(0,openStart)+minimalOpenBook+out.slice(openEnd);
  out=out.replace('</head>',CLEAN_STYLE+'</head>');
  out=out.replace('</body>',CLEAN_SCRIPT+'</body>');
  return out;
}

export default {
  async fetch(request,env,ctx){
    const url=new URL(request.url);
    const response=await app.fetch(request,env,ctx);
    if(request.method!=='GET'||url.pathname!=='/artifact-library/read')return response;
    const type=response.headers.get('Content-Type')||'';
    if(response.status!==200||!type.toLowerCase().includes('text/html'))return response;
    try{
      const updated=patchCleanIosV110(await response.text());
      const headers=new Headers(response.headers);headers.delete('Content-Length');headers.set('X-Robots-Tag',ROBOTS);headers.set('X-R3-Reader-IOS-Clean',CLEAN_VERSION);headers.set('X-R3-Reader-Legacy-Chain','bypassed-v112');
      const csp=cleanIosCsp(headers.get('Content-Security-Policy'));if(csp)headers.set('Content-Security-Policy',csp);
      return new Response(updated,{status:200,headers});
    }catch(error){return new Response('Clean iOS Reader patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-IOS-Clean':'failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}})}
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==='function')return app.scheduled(controller,env,ctx);},
};
