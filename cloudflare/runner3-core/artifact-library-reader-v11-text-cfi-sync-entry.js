import app from "./artifact-library-reader-v10-runtime-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function patchReaderSync(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-audio-text-sync-v11="1"')) return html;

  const style = `<style data-r3-audio-text-sync-v11="1">
[data-r3-audio-reading-v11="1"],[data-r3-audio-reading-v11="1"] *{font-weight:900!important}
</style>`;

  const script = `<script data-r3-audio-text-sync-v11="1">
(()=>{
  if(window.__r3AudioTextSyncV11)return;
  window.__r3AudioTextSyncV11=true;

  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;

  const audio=document.getElementById('r3AudioElement');
  const main=document.getElementById('r3AudioMain');
  const status=document.getElementById('r3AudioStatus');
  const title=document.getElementById('r3AudioTitle');
  const speed=document.getElementById('r3AudioSpeed');
  if(!audio||!main||!status)return;

  const VERSION='reader-v11-text-cfi-sync';
  const STORAGE_KEY='r3-reader-audio-state-v11:'+bookKey;
  const rates=[1,1.25,1.5,1.75,2];
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  let timingWords=[];
  let timingTokens=[];
  let blocks=[];
  let blockRanges=[];
  let activeDoc=null;
  let activeSignature='';
  let loadedSignature='';
  let currentId='';
  let activeBlock=null;
  let busy=false;
  let requestSeq=0;
  let lastSavedAt=0;
  let lastFollowAt=0;
  let lastFollowCfi='';
  let allowBridgeDisplay=0;
  let originalBridgeDisplay=null;
  let alignmentCoverage=0;

  const setStatus=text=>{status.textContent=String(text||'Nam Minh').slice(0,120);};
  const setTitle=text=>{if(title)title.textContent=String(text||'Chương hiện tại').slice(0,120);};
  function setMain(mode){
    if(mode==='loading'){main.textContent='…';main.disabled=true;main.setAttribute('aria-label','Đang chuẩn bị audio');return;}
    main.disabled=false;
    if(mode==='pause'){main.textContent='Ⅱ';main.setAttribute('aria-label','Tạm dừng audio');}
    else{main.textContent='▶';main.setAttribute('aria-label','Phát audio');}
  }
  function bridge(){return window.r3ReaderBridge||null;}
  function enablePlaybackSession(){
    try{if(navigator.audioSession&&'type' in navigator.audioSession)navigator.audioSession.type='playback';}catch{}
  }
  function installBridgeGuard(){
    const b=bridge();
    if(!b||b.__r3V11DisplayGuard)return;
    if(typeof b.display!=='function')return;
    originalBridgeDisplay=b.display.bind(b);
    b.__r3V11DisplayGuard=true;
    b.display=(target)=>{
      if(allowBridgeDisplay>0&&originalBridgeDisplay)return originalBridgeDisplay(target);
      return Promise.resolve(false);
    };
  }
  async function safeDisplay(target){
    if(!target)return false;
    installBridgeGuard();
    const b=bridge();
    const fn=originalBridgeDisplay||(b&&typeof b.display==='function'?b.display.bind(b):null);
    if(!fn)return false;
    allowBridgeDisplay++;
    try{await fn(target);return true;}catch{return false;}finally{allowBridgeDisplay=Math.max(0,allowBridgeDisplay-1);}
  }

  function normalizeText(value){
    return String(value||'').normalize('NFC').replace(/\\r/g,'').replace(/\\u00a0/g,' ').replace(/[\\u200b-\\u200d\\u2060\\ufeff]/g,'').replace(/https?:\\/\\/\\S+/g,'').replace(/\\s+/g,' ').trim();
  }
  function tokensOf(value){
    const text=normalizeText(value).normalize('NFKC').toLocaleLowerCase('vi-VN');
    if(!text)return [];
    try{return text.match(/[\\p{L}\\p{M}\\p{N}]+/gu)||[];}catch{return text.split(/[^A-Za-z0-9À-ỹ]+/).filter(Boolean);}
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
          best={frame,doc,body,text,chapterTitle:(heading&&heading.textContent||doc.title||'').trim().slice(0,240),chapterHref:String(frame.getAttribute('src')||'').slice(0,600)};
        }
      }catch{}
    }
    if(!best)return null;
    best.signature=best.text.length+'|'+best.text.slice(0,180)+'|'+best.text.slice(-180);
    return best;
  }
  function collectBlocks(payload){
    if(!payload)return [];
    const selector='p,li,h1,h2,h3,h4,h5,h6,blockquote';
    let rows=[...payload.doc.querySelectorAll(selector)].filter(el=>normalizeText(el.innerText||el.textContent).length>0);
    rows=rows.filter(el=>{
      if(String(el.tagName||'').toUpperCase()!=='BLOCKQUOTE')return true;
      return !el.querySelector('p,li,h1,h2,h3,h4,h5,h6');
    });
    if(!rows.length)rows=[...payload.body.children].filter(el=>normalizeText(el.innerText||el.textContent).length>0);
    if(!rows.length)rows=[payload.body];
    return rows;
  }
  function clearLegacyHighlight(doc){
    try{for(const el of doc.querySelectorAll('[data-r3-audio-reading]'))el.removeAttribute('data-r3-audio-reading');}catch{}
  }
  function clearHighlight(){
    if(activeBlock){try{activeBlock.removeAttribute('data-r3-audio-reading-v11');}catch{}}
    activeBlock=null;
  }
  function ensureFrameStyle(doc){
    if(!doc||doc.getElementById('r3AudioReadingStyleV11'))return;
    const node=doc.createElement('style');
    node.id='r3AudioReadingStyleV11';
    node.textContent='[data-r3-audio-reading-v11="1"],[data-r3-audio-reading-v11="1"] *{font-weight:900!important}';
    (doc.head||doc.documentElement).appendChild(node);
  }
  function buildAlignment(force=false){
    const payload=framePayload();
    if(!payload||!timingWords.length)return false;
    if(!force&&activeDoc===payload.doc&&activeSignature===payload.signature&&blockRanges.length)return true;

    clearHighlight();
    clearLegacyHighlight(payload.doc);
    ensureFrameStyle(payload.doc);
    activeDoc=payload.doc;
    activeSignature=payload.signature;
    blocks=collectBlocks(payload);
    blockRanges=blocks.map((el,index)=>({el,index,first:null,last:null,matches:0,tokens:tokensOf(el.innerText||el.textContent).length}));

    timingTokens=[];
    for(let wi=0;wi<timingWords.length;wi++){
      const parts=tokensOf(timingWords[wi]&&timingWords[wi].text);
      for(const token of parts)timingTokens.push({token,wi});
    }
    const domTokens=[];
    for(let bi=0;bi<blockRanges.length;bi++){
      for(const token of tokensOf(blockRanges[bi].el.innerText||blockRanges[bi].el.textContent))domTokens.push({token,bi});
    }

    let ti=0,matched=0;
    const LOOKAHEAD=18;
    for(const row of domTokens){
      if(ti>=timingTokens.length)break;
      let found=-1;
      if(timingTokens[ti].token===row.token)found=ti;
      else{
        const end=Math.min(timingTokens.length,ti+LOOKAHEAD+1);
        for(let probe=ti+1;probe<end;probe++){
          if(timingTokens[probe].token===row.token){found=probe;break;}
        }
      }
      if(found<0)continue;
      const wi=timingTokens[found].wi;
      const range=blockRanges[row.bi];
      if(range.first===null)range.first=wi;
      range.last=wi;
      range.matches++;
      matched++;
      ti=found+1;
    }

    const denom=Math.max(1,Math.min(domTokens.length,timingTokens.length));
    alignmentCoverage=matched/denom;
    return blockRanges.some(row=>row.first!==null);
  }
  function wordIndexAt(ms){
    if(!timingWords.length)return -1;
    let lo=0,hi=timingWords.length-1,ans=0;
    while(lo<=hi){
      const mid=(lo+hi)>>1;
      const start=Number(timingWords[mid]&&timingWords[mid].startMs)||0;
      if(start<=ms){ans=mid;lo=mid+1;}else hi=mid-1;
    }
    return ans;
  }
  function rangeForWord(index){
    if(index<0||!blockRanges.length)return null;
    let previous=null;
    for(const row of blockRanges){
      if(row.first===null)continue;
      if(index>=row.first&&index<=row.last)return row;
      if(index<row.first)return previous||row;
      previous=row;
    }
    return previous;
  }
  function rectVisible(rect,w,h){return rect&&rect.right>2&&rect.left<w-2&&rect.bottom>2&&rect.top<h-2;}
  function blockVisible(el){
    try{
      const doc=el.ownerDocument,win=doc.defaultView;
      const w=win&&win.innerWidth||doc.documentElement.clientWidth||1;
      const h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      const rects=[...el.getClientRects()];
      return rects.some(rect=>rectVisible(rect,w,h));
    }catch{return false;}
  }
  function firstVisibleRange(){
    const payload=framePayload();
    if(!payload)return null;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    for(const row of blockRanges)if(blockVisible(row.el))return row;
    return blockRanges.find(row=>row.first!==null)||null;
  }
  function nearestMappedRange(index){
    if(index<0||index>=blockRanges.length)return null;
    if(blockRanges[index]&&blockRanges[index].first!==null)return blockRanges[index];
    for(let radius=1;radius<blockRanges.length;radius++){
      const before=index-radius,after=index+radius;
      if(before>=0&&blockRanges[before].first!==null)return blockRanges[before];
      if(after<blockRanges.length&&blockRanges[after].first!==null)return blockRanges[after];
    }
    return null;
  }
  function startSecondsForRange(row){
    if(!row)return 0;
    const mapped=row.first!==null?row:nearestMappedRange(row.index);
    if(!mapped||mapped.first===null)return 0;
    return Math.max(0,(Number(timingWords[mapped.first]&&timingWords[mapped.first].startMs)||0)/1000);
  }
  function cfiForNode(el){
    const b=bridge();
    if(!b||typeof b.cfiFromNode!=='function')return '';
    try{return b.cfiFromNode(el)||'';}catch{return '';}
  }
  async function followRange(row,force=false){
    if(!row||audio.paused||audio.ended)return;
    if(!force&&blockVisible(row.el))return;
    const now=Date.now();
    if(!force&&now-lastFollowAt<450)return;
    const cfi=cfiForNode(row.el);
    if(!cfi||(!force&&cfi===lastFollowCfi))return;
    lastFollowAt=now;lastFollowCfi=cfi;
    const moved=await safeDisplay(cfi);
    if(moved){
      const b=bridge();if(b&&typeof b.persist==='function')try{b.persist();}catch{}
      await delay(90);
      buildAlignment(true);
      syncReading(false);
    }
  }
  function syncReading(forceDisplay=false){
    installBridgeGuard();
    if(!timingWords.length)return;
    const payload=framePayload();
    if(!payload)return;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    clearLegacyHighlight(payload.doc);
    const row=rangeForWord(wordIndexAt((Number(audio.currentTime)||0)*1000));
    if(!row)return;
    if(row.el!==activeBlock){
      clearHighlight();
      activeBlock=row.el;
      try{activeBlock.setAttribute('data-r3-audio-reading-v11','1');}catch{}
    }
    if(forceDisplay||!blockVisible(row.el))followRange(row,forceDisplay);
  }

  function idFromAudio(){
    try{
      const raw=audio.currentSrc||audio.getAttribute('src')||'';
      if(!raw)return '';
      const u=new URL(raw,location.href);
      return u.searchParams.get('id')||'';
    }catch{return '';}
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
      await delay(1500);
    }
    throw new Error('Audio chưa sẵn sàng');
  }
  async function loadTiming(state,signature=''){
    timingWords=[];timingTokens=[];blockRanges=[];clearHighlight();activeDoc=null;activeSignature='';
    if(!state||!state.timingUrl)return false;
    const response=await fetch(state.timingUrl,{cache:'no-store'});
    const data=await response.json().catch(()=>({}));
    if(!response.ok||!Array.isArray(data.words))return false;
    timingWords=data.words;
    loadedSignature=signature||loadedSignature;
    buildAlignment(true);
    syncReading(false);
    return true;
  }
  function mediaSessionUpdate(payload){
    if(!('mediaSession' in navigator))return;
    try{navigator.mediaSession.metadata=new MediaMetadata({title:payload.chapterTitle||document.title||'Ebook',artist:'Nam Minh · Ebook Library',album:document.title||'Ebook'});}catch{}
  }
  function waitMetadata(timeout=10000){
    if(Number.isFinite(audio.duration)&&audio.duration>0)return Promise.resolve(true);
    return new Promise(resolve=>{
      let done=false;
      const finish=value=>{if(done)return;done=true;audio.removeEventListener('loadedmetadata',onload);clearTimeout(timer);resolve(value);};
      const onload=()=>finish(true);
      const timer=setTimeout(()=>finish(false),timeout);
      audio.addEventListener('loadedmetadata',onload,{once:true});
    });
  }
  function currentRate(){
    const value=Number(audio.playbackRate)||1;
    return rates.includes(value)?value:1;
  }
  function savedState(){
    try{const row=JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');return row&&typeof row==='object'?row:null;}catch{return null;}
  }
  function saveState(force=false){
    const now=Date.now();
    if(!force&&now-lastSavedAt<800)return;
    const payload=framePayload();
    const id=idFromAudio()||currentId;
    if(!payload||!id)return;
    const b=bridge();
    let cfi='';
    try{cfi=b&&typeof b.persist==='function'?b.persist()||'':'';}catch{}
    const row={version:11,id,signature:payload.signature,chapterTitle:payload.chapterTitle||'',chapterHref:payload.chapterHref||'',time:Math.max(0,Number(audio.currentTime)||0),rate:currentRate(),wasPlaying:!audio.paused&&!audio.ended,cfi,coverage:Math.round(alignmentCoverage*1000)/1000,updatedAt:new Date().toISOString()};
    try{localStorage.setItem(STORAGE_KEY,JSON.stringify(row));lastSavedAt=now;}catch{}
  }
  async function restoreOwnState(){
    const saved=savedState();
    if(!saved||!saved.id||!Number.isFinite(Number(saved.time)))return;
    for(let n=0;n<70;n++){
      const payload=framePayload();
      if(payload){
        if(saved.signature&&payload.signature!==saved.signature)return;
        if(audio.getAttribute('src')){
          currentId=idFromAudio()||saved.id;
          loadedSignature=payload.signature;
          try{const state=await readState(currentId);if(state.status==='ready')await loadTiming(state,payload.signature);}catch{}
          if((Number(audio.currentTime)||0)<0.2&&Number(saved.time)>0.2){await waitMetadata();try{audio.currentTime=Math.min(Number(saved.time),Math.max(0,(Number(audio.duration)||Number(saved.time))-.05));}catch{}}
          syncReading(false);
          return;
        }
        try{
          const state=await readState(saved.id);
          if(state.status!=='ready'||!state.mediaUrl)return;
          currentId=saved.id;loadedSignature=payload.signature;
          audio.src=state.mediaUrl;
          audio.preload='auto';
          audio.playbackRate=rates.includes(Number(saved.rate))?Number(saved.rate):1;
          if(speed)speed.textContent=audio.playbackRate+'×';
          setTitle(saved.chapterTitle||payload.chapterTitle||'Chương hiện tại');
          await loadTiming(state,payload.signature);
          await waitMetadata();
          try{audio.currentTime=Math.min(Math.max(0,Number(saved.time)||0),Math.max(0,(Number(audio.duration)||Number(saved.time)||0)-.05));}catch{}
          setStatus('Nam Minh · tiếp tục từ vị trí đã lưu · nhấn phát');
          setMain('play');
          syncReading(false);
        }catch{}
        return;
      }
      await delay(150);
    }
  }

  async function prepareCurrentChapter(payload,visible){
    const seq=++requestSeq;
    busy=true;setMain('loading');setTitle(payload.chapterTitle||'Chương hiện tại');setStatus('Nam Minh · đang chuẩn bị chương…');
    try{
      const response=await fetch('/artifact-library/audio',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',clientVersion:VERSION})});
      let state=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(state.error||('HTTP '+response.status));
      currentId=state.id||'';
      if(!currentId)throw new Error('AUDIO_ID_MISSING');
      if(state.status!=='ready')state=await waitReady(currentId,seq);
      if(seq!==requestSeq||!state)return false;
      if(!state.mediaUrl)throw new Error('AUDIO_MEDIA_URL_MISSING');
      loadedSignature=payload.signature;
      audio.pause();audio.src=state.mediaUrl;audio.preload='auto';
      mediaSessionUpdate(payload);enablePlaybackSession();
      await loadTiming(state,payload.signature);
      await waitMetadata();
      buildAlignment(true);
      const freshVisible=firstVisibleRange()||visible;
      const target=startSecondsForRange(freshVisible);
      try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}
      await audio.play();
      setMain('pause');
      syncReading(false);saveState(true);
      return true;
    }catch(error){
      if(seq===requestSeq){setMain('play');setStatus(String(error&&error.message||error||'Lỗi audio').slice(0,100));}
      return false;
    }finally{if(seq===requestSeq)busy=false;}
  }

  async function handleMain(){
    if(busy)return;
    installBridgeGuard();enablePlaybackSession();
    const payload=framePayload();
    if(!payload){setStatus('Chưa lấy được nội dung chương');return;}
    setTitle(payload.chapterTitle||'Chương hiện tại');

    const id=idFromAudio();
    if(id&&audio.getAttribute('src')&&loadedSignature===payload.signature){
      currentId=id;
      if(!timingWords.length){try{const state=await readState(id);if(state.status==='ready')await loadTiming(state,payload.signature);}catch{}}
      buildAlignment(false);
      if(!audio.paused){audio.pause();saveState(true);return;}
      const currentRange=rangeForWord(wordIndexAt((Number(audio.currentTime)||0)*1000));
      if(!currentRange||!blockVisible(currentRange.el)){
        const visible=firstVisibleRange();
        if(visible){const target=startSecondsForRange(visible);try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}}
      }
      try{await audio.play();setMain('pause');syncReading(false);saveState(true);}catch{setStatus('Nam Minh · nhấn phát lại');}
      return;
    }

    const visible=firstVisibleRange();
    await prepareCurrentChapter(payload,visible);
  }

  document.addEventListener('click',event=>{
    const target=event.target&&event.target.closest?event.target.closest('#r3AudioMain'):null;
    if(!target)return;
    event.preventDefault();event.stopImmediatePropagation();
    handleMain();
  },true);

  audio.addEventListener('loadedmetadata',()=>{enablePlaybackSession();syncReading(false);});
  audio.addEventListener('timeupdate',()=>{syncReading(false);saveState(false);});
  audio.addEventListener('seeked',()=>{syncReading(true);saveState(true);});
  audio.addEventListener('play',()=>{enablePlaybackSession();setMain('pause');syncReading(false);});
  audio.addEventListener('pause',()=>{if(!audio.ended)setMain('play');saveState(true);});
  audio.addEventListener('ended',()=>{saveState(true);clearHighlight();});
  window.addEventListener('pagehide',()=>saveState(true));
  window.addEventListener('pageshow',()=>setTimeout(()=>syncReading(true),120));
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='hidden')saveState(true);
    else setTimeout(()=>{installBridgeGuard();syncReading(true);saveState(true);},120);
  });

  const observer=new MutationObserver(()=>installBridgeGuard());
  observer.observe(document.documentElement,{childList:true,subtree:true});
  installBridgeGuard();enablePlaybackSession();
  setTimeout(restoreOwnState,900);
})();
</script>`;

  const addition = `${style}${script}`;
  return html.includes("</body>") ? html.replace("</body>", `${addition}</body>`) : html + addition;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;

    const html = await response.text();
    const updated = patchReaderSync(html);
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v11-wordboundary-text-cfi-sync");
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
