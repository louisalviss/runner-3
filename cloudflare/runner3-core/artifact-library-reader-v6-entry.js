import app from "./artifact-library-reader-v5-entry.js";
import { handleEbookReaderAudio } from "./src/ebook-reader-audio.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function patchEbookAudio(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-ebook-audio-v6="2"')) return html;

  const css = `<style data-r3-ebook-audio-v6="2">
#r3AudioDock{position:fixed;left:50%;bottom:max(6px,env(safe-area-inset-bottom,0px));z-index:90;width:min(560px,calc(100vw - 12px));transform:translateX(-50%);border:1px solid var(--line,rgba(127,127,127,.24));border-radius:18px;background:var(--panel,rgba(20,23,28,.96));color:var(--fg,inherit);box-shadow:0 14px 42px rgba(0,0,0,.24);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);font:13px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;user-select:none;-webkit-user-select:none;overflow:hidden;transition:opacity .16s ease,transform .16s ease}
#r3AudioDock *{box-sizing:border-box}
#r3AudioDock button{appearance:none;-webkit-appearance:none;border:0;background:transparent;color:inherit;font:inherit;touch-action:manipulation}
#r3AudioDock button:active{transform:scale(.96)}
#r3AudioHead{min-height:54px;display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px;padding:8px 9px 7px 62px}
#r3AudioCopy{min-width:0}
#r3AudioTitle{font-size:12px;font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#r3AudioStatus{margin-top:3px;color:var(--muted,#888);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#r3AudioSpeed,#r3AudioExpand{height:36px;min-width:42px;border:1px solid var(--line,rgba(127,127,127,.22))!important;border-radius:11px!important;background:color-mix(in srgb,var(--fg,currentColor) 7%,transparent)!important;font-weight:750!important}
#r3AudioExpand{min-width:36px;font-size:17px!important}
#r3AudioTimeline{display:none;grid-template-columns:40px minmax(0,1fr) 40px;align-items:center;gap:8px;padding:0 12px 2px;color:var(--muted,#888);font-size:10px;font-variant-numeric:tabular-nums}
#r3AudioSeek{width:100%;height:28px;margin:0;padding:0;accent-color:var(--fg,currentColor);touch-action:manipulation}
#r3AudioTransport{position:absolute;left:9px;top:7px;height:40px;display:flex;align-items:center;justify-content:center;gap:24px}
#r3AudioBack,#r3AudioForward{display:none;width:44px;height:44px;border-radius:999px!important;font-weight:800!important;font-size:11px!important;color:var(--muted,#888)!important}
#r3AudioMain{width:40px;height:40px;border-radius:999px!important;background:var(--fg,currentColor)!important;color:var(--bg,#fff)!important;font-size:17px!important;font-weight:900!important;box-shadow:0 5px 15px rgba(0,0,0,.18);display:grid;place-items:center;padding:0!important}
#r3AudioDock.r3-expanded #r3AudioHead{padding-left:12px;min-height:48px}
#r3AudioDock.r3-expanded #r3AudioTimeline{display:grid}
#r3AudioDock.r3-expanded #r3AudioTransport{position:static;height:52px;padding:1px 12px 9px;gap:22px}
#r3AudioDock.r3-expanded #r3AudioBack,#r3AudioDock.r3-expanded #r3AudioForward{display:block}
#r3AudioDock.r3-expanded #r3AudioMain{width:48px;height:48px;font-size:19px}
body.r3-audio-ui #viewer{bottom:calc(66px + env(safe-area-inset-bottom,0px))!important}
body.r3-audio-ui .bottom-status{bottom:calc(72px + env(safe-area-inset-bottom,0px))!important}
body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(66px + env(safe-area-inset-bottom,0px))!important}
body.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:calc(72px + env(safe-area-inset-bottom,0px))!important}
body.settings #r3AudioDock{opacity:0;pointer-events:none;transform:translate(-50%,14px)}
@media(min-width:700px){#r3AudioDock{bottom:10px}}
@media(prefers-reduced-motion:reduce){#r3AudioDock{transition:none}}
</style>`;

  const script = `<script data-r3-ebook-audio-v6="2">
(()=>{
  const VERSION='ebook-reader-audio-v1';
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;

  const dock=document.createElement('section');
  dock.id='r3AudioDock';
  dock.setAttribute('aria-label','Trình phát audio chương');
  dock.innerHTML='<div id="r3AudioHead"><div id="r3AudioCopy"><div id="r3AudioTitle">Audio chương hiện tại</div><div id="r3AudioStatus" aria-live="polite">Nam Minh · nhấn phát để tạo audio</div></div><button id="r3AudioSpeed" type="button" aria-label="Tốc độ phát">1×</button><button id="r3AudioExpand" type="button" aria-label="Mở rộng trình phát">⌃</button></div><div id="r3AudioTimeline"><span id="r3AudioCurrent">0:00</span><input id="r3AudioSeek" type="range" min="0" max="1000" value="0" step="1" aria-label="Vị trí phát"><span id="r3AudioDuration">--:--</span></div><div id="r3AudioTransport"><button id="r3AudioBack" type="button" aria-label="Lùi 15 giây">↶ 15</button><button id="r3AudioMain" type="button" aria-label="Phát audio">▶</button><button id="r3AudioForward" type="button" aria-label="Tua tới 15 giây">15 ↷</button></div><audio id="r3AudioElement" preload="metadata"></audio>';
  document.body.appendChild(dock);
  document.body.classList.add('r3-audio-ui');

  const main=dock.querySelector('#r3AudioMain');
  const back=dock.querySelector('#r3AudioBack');
  const forward=dock.querySelector('#r3AudioForward');
  const status=dock.querySelector('#r3AudioStatus');
  const title=dock.querySelector('#r3AudioTitle');
  const speed=dock.querySelector('#r3AudioSpeed');
  const expand=dock.querySelector('#r3AudioExpand');
  const seek=dock.querySelector('#r3AudioSeek');
  const current=dock.querySelector('#r3AudioCurrent');
  const duration=dock.querySelector('#r3AudioDuration');
  const audio=dock.querySelector('#r3AudioElement');
  const rates=[1,1.25,1.5,1.75,2];
  let rateIndex=0,requestSeq=0,loadedSignature='',currentId='',seeking=false;
  let expanded=false;

  try{expanded=localStorage.getItem('r3-reader-audio-expanded')==='1';}catch{}

  const block=(event)=>{event.stopPropagation();};
  ['pointerdown','pointerup','touchstart','touchend','mousedown','mouseup','click'].forEach(type=>dock.addEventListener(type,block));

  function formatTime(value){
    const seconds=Math.max(0,Number(value)||0);
    if(!Number.isFinite(seconds))return '--:--';
    const whole=Math.floor(seconds);
    const h=Math.floor(whole/3600);
    const m=Math.floor((whole%3600)/60);
    const s=whole%60;
    return h?String(h)+':'+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0'):String(m)+':'+String(s).padStart(2,'0');
  }

  function setStatus(text){status.textContent=text||'Nam Minh';}
  function setTitle(text){title.textContent=String(text||'Audio chương hiện tại').slice(0,120);}
  function setExpanded(value,persist=true){
    expanded=Boolean(value);
    dock.classList.toggle('r3-expanded',expanded);
    document.body.classList.toggle('r3-audio-expanded',expanded);
    expand.textContent=expanded?'⌄':'⌃';
    expand.setAttribute('aria-label',expanded?'Thu gọn trình phát':'Mở rộng trình phát');
    if(persist){try{localStorage.setItem('r3-reader-audio-expanded',expanded?'1':'0');}catch{}}
  }

  function syncTimeline(){
    const total=Number(audio.duration);
    const now=Number(audio.currentTime)||0;
    current.textContent=formatTime(now);
    duration.textContent=Number.isFinite(total)&&total>0?formatTime(total):'--:--';
    if(!seeking)seek.value=Number.isFinite(total)&&total>0?String(Math.max(0,Math.min(1000,Math.round(now/total*1000)))):'0';
    seek.disabled=!(Number.isFinite(total)&&total>0);
  }

  function setMain(mode){
    if(mode==='loading'){main.textContent='…';main.setAttribute('aria-label','Đang tạo audio');main.disabled=true;return;}
    main.disabled=false;
    if(mode==='pause'){main.textContent='Ⅱ';main.setAttribute('aria-label','Tạm dừng audio');}
    else{main.textContent='▶';main.setAttribute('aria-label','Phát audio');}
  }

  function framePayload(){
    const frames=[...document.querySelectorAll('#viewer iframe')];
    let best=null;
    for(const frame of frames){
      try{
        const doc=frame.contentDocument;
        const body=doc&&doc.body;
        const text=String(body&&body.innerText||'').trim();
        if(text.length<80)continue;
        if(!best||text.length>best.text.length){
          const heading=doc.querySelector('h1,h2,h3');
          best={text,chapterTitle:(heading&&heading.textContent||doc.title||'').trim().slice(0,240),chapterHref:String(frame.getAttribute('src')||'').slice(0,600)};
        }
      }catch{}
    }
    if(!best)return null;
    best.signature=best.text.length+'|'+best.text.slice(0,180)+'|'+best.text.slice(-180);
    return best;
  }

  function resetForChapter(){
    requestSeq++;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    currentId='';
    loadedSignature='';
    setMain('play');
    setTitle('Audio chương hiện tại');
    setStatus('Nam Minh · nhấn phát để tạo audio');
    seek.value='0';current.textContent='0:00';duration.textContent='--:--';seek.disabled=true;
  }

  async function readState(id){
    const q=new URLSearchParams({id,bookKey});
    const response=await fetch('/artifact-library/audio?'+q.toString(),{cache:'no-store'});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||('HTTP '+response.status));
    return data;
  }

  async function waitReady(id,seq){
    for(let n=0;n<240;n++){
      if(seq!==requestSeq)return null;
      const data=await readState(id);
      if(data.status==='ready')return data;
      if(data.status==='error')throw new Error(data.error||'Tạo audio thất bại');
      setStatus(data.status==='processing'?'Nam Minh · đang tổng hợp…':'Nam Minh · đang xếp hàng…');
      await new Promise(resolve=>setTimeout(resolve,1500));
    }
    throw new Error('Audio chưa sẵn sàng');
  }

  function mediaSessionUpdate(payload){
    if(!('mediaSession' in navigator))return;
    try{
      navigator.mediaSession.metadata=new MediaMetadata({title:payload.chapterTitle||document.title||'Ebook',artist:'Nam Minh · Ebook Library',album:document.title||'Ebook'});
    }catch{}
  }

  async function createOrPlay(){
    const payload=framePayload();
    if(!payload){setStatus('Chưa lấy được nội dung chương');return;}
    setTitle(payload.chapterTitle||'Chương hiện tại');
    if(audio.getAttribute('src')&&loadedSignature===payload.signature){
      if(audio.paused)await audio.play().catch(()=>{});else audio.pause();
      return;
    }

    setExpanded(true);
    const seq=++requestSeq;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    setMain('loading');
    setStatus('Nam Minh · đang gửi chương…');
    try{
      const response=await fetch('/artifact-library/audio',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',clientVersion:VERSION})});
      let data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.error||('HTTP '+response.status));
      currentId=data.id||'';
      if(!currentId)throw new Error('AUDIO_ID_MISSING');
      if(data.status!=='ready')data=await waitReady(currentId,seq);
      if(seq!==requestSeq||!data)return;
      if(!data.mediaUrl)throw new Error('AUDIO_MEDIA_URL_MISSING');
      loadedSignature=payload.signature;
      audio.src=data.mediaUrl;
      audio.playbackRate=rates[rateIndex];
      mediaSessionUpdate(payload);
      await audio.play();
    }catch(error){
      if(seq!==requestSeq)return;
      setMain('play');
      setStatus(String(error&&error.message||error||'Lỗi audio').slice(0,90));
    }
  }

  main.addEventListener('click',(event)=>{event.preventDefault();createOrPlay();});
  back.addEventListener('click',(event)=>{event.preventDefault();if(Number.isFinite(audio.duration))audio.currentTime=Math.max(0,(audio.currentTime||0)-15);});
  forward.addEventListener('click',(event)=>{event.preventDefault();if(Number.isFinite(audio.duration))audio.currentTime=Math.min(audio.duration,(audio.currentTime||0)+15);});
  speed.addEventListener('click',(event)=>{event.preventDefault();rateIndex=(rateIndex+1)%rates.length;audio.playbackRate=rates[rateIndex];speed.textContent=rates[rateIndex]+'×';setStatus('Nam Minh · tốc độ '+rates[rateIndex]+'×');});
  expand.addEventListener('click',(event)=>{event.preventDefault();setExpanded(!expanded);});
  seek.addEventListener('input',()=>{seeking=true;const total=Number(audio.duration);if(Number.isFinite(total)&&total>0)current.textContent=formatTime(total*Number(seek.value)/1000);});
  seek.addEventListener('change',()=>{const total=Number(audio.duration);if(Number.isFinite(total)&&total>0)audio.currentTime=total*Number(seek.value)/1000;seeking=false;syncTimeline();});

  audio.addEventListener('loadedmetadata',()=>{syncTimeline();setStatus('Nam Minh · sẵn sàng');});
  audio.addEventListener('durationchange',syncTimeline);
  audio.addEventListener('timeupdate',syncTimeline);
  audio.addEventListener('play',()=>{setMain('pause');setStatus('Nam Minh · đang phát');if('mediaSession' in navigator)try{navigator.mediaSession.playbackState='playing';}catch{}});
  audio.addEventListener('pause',()=>{if(audio.getAttribute('src')&&!audio.ended){setMain('play');setStatus('Nam Minh · tạm dừng');}if('mediaSession' in navigator)try{navigator.mediaSession.playbackState='paused';}catch{}});
  audio.addEventListener('waiting',()=>{if(audio.getAttribute('src'))setStatus('Nam Minh · đang tải audio…');});
  audio.addEventListener('playing',()=>setStatus('Nam Minh · đang phát'));
  audio.addEventListener('ended',()=>{setMain('play');setStatus('Nam Minh · đã hết chương');syncTimeline();});
  audio.addEventListener('error',()=>{if(!audio.getAttribute('src'))return;setMain('play');setStatus('Lỗi phát audio');});

  if('mediaSession' in navigator){
    try{navigator.mediaSession.setActionHandler('play',()=>audio.play());}catch{}
    try{navigator.mediaSession.setActionHandler('pause',()=>audio.pause());}catch{}
    try{navigator.mediaSession.setActionHandler('seekbackward',details=>{audio.currentTime=Math.max(0,(audio.currentTime||0)-(details.seekOffset||15));});}catch{}
    try{navigator.mediaSession.setActionHandler('seekforward',details=>{audio.currentTime=Math.min(audio.duration||Infinity,(audio.currentTime||0)+(details.seekOffset||15));});}catch{}
    try{navigator.mediaSession.setActionHandler('seekto',details=>{if(Number.isFinite(details.seekTime))audio.currentTime=details.seekTime;});}catch{}
  }

  setExpanded(expanded,false);
  syncTimeline();
  setInterval(()=>{
    if(!loadedSignature)return;
    const payload=framePayload();
    if(payload&&payload.signature!==loadedSignature)resetForChapter();
  },1500);
})();
</script>`;

  return html.replace('</head>', css + '</head>').replace('</body>', script + '</body>');
}

export default {
  async fetch(request, env, ctx) {
    const audioResponse = await handleEbookReaderAudio(request, env);
    if (audioResponse) return audioResponse;

    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;
    const original = await response.text();
    const updated = patchEbookAudio(original);
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("X-Robots-Tag", ROBOTS);
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
