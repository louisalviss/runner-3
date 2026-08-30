import app from "./artifact-library-reader-v5-entry.js";
import { handleEbookReaderAudio } from "./src/ebook-reader-audio.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function patchEbookAudio(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-ebook-audio-v6="1"')) return html;

  const css = `<style data-r3-ebook-audio-v6="1">
#r3AudioDock{position:fixed;right:12px;bottom:calc(72px + env(safe-area-inset-bottom,0px));z-index:90;display:flex;align-items:center;gap:6px;padding:6px 7px;border:1px solid rgba(127,127,127,.28);border-radius:18px;background:color-mix(in srgb,var(--panel,#161616) 92%,transparent);box-shadow:0 5px 20px rgba(0,0,0,.2);font:12px/1.2 system-ui,-apple-system,sans-serif;max-width:min(86vw,320px);user-select:none;-webkit-user-select:none}
#r3AudioDock button{appearance:none;border:0;border-radius:14px;min-height:32px;padding:0 10px;background:rgba(127,127,127,.16);color:inherit;font:600 12px/1 system-ui,-apple-system,sans-serif;touch-action:manipulation}
#r3AudioDock button:active{transform:scale(.97)}
#r3AudioMain{font-size:15px!important;min-width:38px!important;padding:0 9px!important}
#r3AudioStatus{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:170px;opacity:.86}
#r3AudioSpeed{min-width:42px;padding:0 7px!important}
@media(max-width:520px){#r3AudioDock{right:8px;bottom:calc(66px + env(safe-area-inset-bottom,0px))}#r3AudioStatus{max-width:130px}}
</style>`;

  const script = `<script data-r3-ebook-audio-v6="1">
(()=>{
  const VERSION='ebook-reader-audio-v1';
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;

  const dock=document.createElement('div');
  dock.id='r3AudioDock';
  dock.innerHTML='<button id="r3AudioMain" type="button" aria-label="Audio Nam Minh">🎧</button><span id="r3AudioStatus">Nam Minh</span><button id="r3AudioSpeed" type="button">1×</button><audio id="r3AudioElement" preload="metadata"></audio>';
  document.body.appendChild(dock);
  const main=dock.querySelector('#r3AudioMain');
  const status=dock.querySelector('#r3AudioStatus');
  const speed=dock.querySelector('#r3AudioSpeed');
  const audio=dock.querySelector('#r3AudioElement');
  const rates=[1,1.25,1.5,1.75,2];
  let rateIndex=0,requestSeq=0,loadedSignature='',currentId='';

  const block=(event)=>{event.stopPropagation();};
  ['pointerdown','pointerup','touchstart','touchend','mousedown','mouseup','click'].forEach(type=>dock.addEventListener(type,block));

  function setStatus(text){status.textContent=text||'Nam Minh';}
  function framePayload(){
    const frames=[...document.querySelectorAll('#viewer iframe')];
    let best=null;
    for(const frame of frames){
      try{
        const doc=frame.contentDocument;
        const body=doc&&doc.body;
        const text=(body&&body.innerText||'').replace(/\r/g,'').replace(/\n{3,}/g,'\n\n').trim();
        if(text.length<80)continue;
        if(!best||text.length>best.text.length){
          const heading=doc.querySelector('h1,h2,h3');
          best={
            text,
            chapterTitle:(heading&&heading.textContent||doc.title||'').trim().slice(0,240),
            chapterHref:String(frame.getAttribute('src')||'').slice(0,600),
          };
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
    main.textContent='🎧';
    setStatus('Nam Minh');
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
      setStatus(data.status==='processing'?'Đang đọc…':'Đang tạo…');
      await new Promise(resolve=>setTimeout(resolve,1500));
    }
    throw new Error('Audio chưa sẵn sàng');
  }

  async function createOrPlay(){
    const payload=framePayload();
    if(!payload){setStatus('Chưa lấy được chương');return;}
    if(audio.src&&loadedSignature===payload.signature){
      if(audio.paused){await audio.play().catch(()=>{});main.textContent='⏸';setStatus('Đang phát');}
      else{audio.pause();main.textContent='▶';setStatus('Tạm dừng');}
      return;
    }

    const seq=++requestSeq;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    main.textContent='…';
    setStatus('Đang gửi…');
    try{
      const response=await fetch('/artifact-library/audio',{
        method:'POST',
        headers:{'content-type':'application/json'},
        body:JSON.stringify({
          bookKey,
          text:payload.text,
          chapterTitle:payload.chapterTitle,
          chapterHref:payload.chapterHref,
          bookTitle:document.title||'Ebook',
          clientVersion:VERSION,
        }),
      });
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
      await audio.play();
      main.textContent='⏸';
      setStatus('Đang phát');
    }catch(error){
      if(seq!==requestSeq)return;
      main.textContent='🎧';
      setStatus(String(error&&error.message||error||'Lỗi audio').slice(0,80));
    }
  }

  main.addEventListener('click',(event)=>{event.preventDefault();createOrPlay();});
  speed.addEventListener('click',(event)=>{
    event.preventDefault();
    rateIndex=(rateIndex+1)%rates.length;
    audio.playbackRate=rates[rateIndex];
    speed.textContent=rates[rateIndex]+'×';
  });
  audio.addEventListener('play',()=>{main.textContent='⏸';setStatus('Đang phát');});
  audio.addEventListener('pause',()=>{if(audio.src&&!audio.ended){main.textContent='▶';setStatus('Tạm dừng');}});
  audio.addEventListener('ended',()=>{main.textContent='▶';setStatus('Đã hết chương');});
  audio.addEventListener('error',()=>{main.textContent='🎧';setStatus('Lỗi phát audio');});

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
