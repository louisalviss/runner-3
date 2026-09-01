import app from './artifact-library-reader-v33-audio-core-entry.js';

const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';

const BRIDGE_RANGE_NEEDLE = `    cfiFromRange(range){\n`;
const BRIDGE_RANGE_PATCH = `    async peekReadableAhead(offset=1){
      try{
        if(!book||!book.spine)return null;
        const loc=rendition&&rendition.currentLocation?rendition.currentLocation():null;
        const href=String(loc&&loc.start&&loc.start.href||'');
        let section=null;
        try{section=book.spine.get(href||(loc&&loc.start&&loc.start.cfi)||undefined);}catch{}
        if(!section&&Number.isInteger(Number(loc&&loc.start&&loc.start.index))){
          const items=book.spine.spineItems||[];
          section=items[Number(loc.start.index)]||null;
        }
        if(!section)return null;
        const wanted=Math.max(1,Math.min(4,Math.floor(Number(offset)||1)));
        let readable=0;
        for(let step=0;step<40;step++){
          try{section=typeof section.next==='function'?section.next():null;}catch{section=null;}
          if(!section)return null;
          let loaded=false;
          try{
            if(typeof section.load==='function'){
              await section.load(book.load.bind(book));
              loaded=true;
            }
            const doc=section.document||null;
            const body=doc&&doc.body;
            if(!body)continue;
            const selector='p,li,h1,h2,h3,h4,h5,h6,blockquote';
            let blocks=[...body.querySelectorAll(selector)].filter(el=>String(el.textContent||'').replace(/\\s+/g,' ').trim().length>0);
            blocks=blocks.filter(el=>String(el.tagName||'').toUpperCase()!=='BLOCKQUOTE'||!el.querySelector('p,li,h1,h2,h3,h4,h5,h6'));
            const text=(blocks.length?blocks.map(el=>String(el.textContent||'').replace(/\\s+/g,' ').trim()).filter(Boolean).join('\\n\\n'):String(body.textContent||'').replace(/\\s+/g,' ').trim()).trim();
            if(text.length<80)continue;
            readable++;
            if(readable!==wanted)continue;
            const heading=doc.querySelector('h1,h2,h3');
            const chapterHref=String(section.href||section.canonical||'').slice(0,700);
            return {
              text,
              chapterTitle:String(heading&&heading.textContent||doc.title||'').replace(/\\s+/g,' ').trim().slice(0,240),
              chapterHref,
              chapter:chapterHref||String(section.index||''),
            };
          }finally{
            if(loaded&&section&&typeof section.unload==='function')try{section.unload();}catch{}
          }
        }
      }catch{}
      return null;
    },
    onRelocated(handler){
      try{
        if(!rendition||typeof rendition.on!=='function'||typeof handler!=='function')return ()=>{};
        rendition.on('relocated',handler);
        return ()=>{try{if(typeof rendition.off==='function')rendition.off('relocated',handler);}catch{}};
      }catch{return ()=>{};}
    },
    cfiFromRange(range){
`;

const OVERLAY = `<script data-r3-audio-continuity-v34="1">
(()=>{
  if(window.__r3AudioContinuityV34)return;

  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  const audio=document.getElementById('r3AudioElement');
  const status=document.getElementById('r3AudioStatus');
  if(!bookKey||!audio||!status)return;

  const rawFetch=window.fetch.bind(window);
  const stateKey='r3-reader-audio-core-v1:'+bookKey;
  const highlightName='r3-audio-reading-v34';
  const prefetchCache=new Map();
  const prefetching=new Map();
  let timingWords=[];
  let timingId='';
  let mappedWords=[];
  let activeDoc=null;
  let activeSignature='';
  let lastFollowAt=0;
  let programmaticUntil=Date.now()+1800;
  let suppressDisplayUntil=0;
  let manualArmedAt=Date.now()+1800;
  let relocatedOff=null;
  let locationTimer=0;

  const debug=window.__r3AudioContinuityV34={
    owner:'reader-audio-continuity-v34',
    prefetchRequests:0,
    prefetchReady:0,
    cacheHits:0,
    exactFollowCalls:0,
    manualSyncs:0,
    mappedWords:0,
    lastPrefetchChapter:'',
    lastError:'',
    installTestTiming(words){timingId='test';timingWords=Array.isArray(words)?words:[];buildWordMap(true);return mappedWords.filter(Boolean).length;},
    syncTestWord(index,force=true){return syncWord(Math.max(0,Number(index)||0),Boolean(force));},
    peek(offset=1){return bridge()&&bridge().peekReadableAhead?bridge().peekReadableAhead(offset):Promise.resolve(null);},
  };

  const bridge=()=>window.r3ReaderBridge||null;
  const normalize=value=>String(value||'').normalize('NFC').replace(/\\r/g,'').replace(/\\u00a0/g,' ').replace(/[\\u200b-\\u200d\\u2060\\ufeff]/g,'').replace(/https?:\\/\\/\\S+/g,'').replace(/\\s+/g,' ').trim();
  const token=value=>normalize(value).normalize('NFKC').toLocaleLowerCase('vi-VN');
  const tokenRe=()=>{try{return /[\\p{L}\\p{M}\\p{N}]+/gu;}catch{return /[A-Za-z0-9À-ỹ]+/g;}};
  const canonical=value=>normalize(value).toLocaleLowerCase('vi-VN');

  function currentState(){
    try{return JSON.parse(localStorage.getItem(stateKey)||'null')||{};}catch{return {};}
  }

  function currentId(){
    try{
      const raw=audio.currentSrc||audio.getAttribute('src')||'';
      if(!raw)return '';
      return new URL(raw,location.href).searchParams.get('id')||'';
    }catch{return '';}
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
          best={frame,doc,body,text,chapterTitle:String(heading&&heading.textContent||doc.title||'').trim().slice(0,240)};
        }
      }catch{}
    }
    if(!best)return null;
    const loc=bridge()&&bridge().current?bridge().current():null;
    best.chapterHref=String(loc&&loc.start&&loc.start.href||best.frame.getAttribute('src')||'').slice(0,700);
    best.chapter=best.chapterHref||'';
    best.signature=best.text.length+'|'+best.text.slice(0,160)+'|'+best.text.slice(-160);
    return best;
  }

  function collectBlocks(payload){
    let blocks=[...payload.doc.querySelectorAll('p,li,h1,h2,h3,h4,h5,h6,blockquote')].filter(el=>normalize(el.innerText||el.textContent).length>0);
    blocks=blocks.filter(el=>String(el.tagName||'').toUpperCase()!=='BLOCKQUOTE'||!el.querySelector('p,li,h1,h2,h3,h4,h5,h6'));
    if(!blocks.length)blocks=[...payload.body.children].filter(el=>normalize(el.innerText||el.textContent).length>0);
    if(!blocks.length)blocks=[payload.body];
    return blocks;
  }

  function ensureFrameHooks(doc){
    if(!doc)return;
    if(!doc.getElementById('r3AudioReadingStyleV34')){
      const style=doc.createElement('style');
      style.id='r3AudioReadingStyleV34';
      style.textContent='::highlight('+highlightName+'){background:rgba(245,196,67,.25);color:inherit;text-decoration:underline rgba(245,196,67,.75) 1px}';
      (doc.head||doc.documentElement).appendChild(style);
    }
    if(!doc.documentElement.dataset.r3AudioHighlightGuardV34){
      doc.documentElement.dataset.r3AudioHighlightGuardV34='1';
      const clear=()=>{try{doc.querySelectorAll('[data-r3-audio-reading-v11]').forEach(el=>el.removeAttribute('data-r3-audio-reading-v11'));}catch{}};
      clear();
      try{
        const observer=new MutationObserver(records=>{
          for(const record of records){
            const el=record.target;
            if(el&&el.removeAttribute&&el.hasAttribute('data-r3-audio-reading-v11'))el.removeAttribute('data-r3-audio-reading-v11');
          }
        });
        observer.observe(doc.documentElement,{subtree:true,attributes:true,attributeFilter:['data-r3-audio-reading-v11']});
      }catch{}
    }
  }

  function textTokensForElement(el){
    const out=[];
    try{
      const doc=el.ownerDocument;
      const walker=doc.createTreeWalker(el,NodeFilter.SHOW_TEXT);
      let node;
      while((node=walker.nextNode())){
        const raw=String(node.nodeValue||'');
        const re=tokenRe();
        let match;
        while((match=re.exec(raw))){
          const value=token(match[0]);
          if(!value)continue;
          const range=doc.createRange();
          range.setStart(node,match.index);
          range.setEnd(node,match.index+match[0].length);
          out.push({token:value,range});
        }
      }
    }catch{}
    return out;
  }

  function buildWordMap(force=false){
    const payload=framePayload();
    if(!payload||!timingWords.length)return 0;
    if(!force&&activeDoc===payload.doc&&activeSignature===payload.signature&&mappedWords.some(Boolean))return mappedWords.filter(Boolean).length;
    activeDoc=payload.doc;
    activeSignature=payload.signature;
    ensureFrameHooks(payload.doc);
    mappedWords=new Array(timingWords.length).fill(null);
    const timingTokens=[];
    for(let wi=0;wi<timingWords.length;wi++){
      const re=tokenRe();
      const raw=String(timingWords[wi]&&timingWords[wi].text||'');
      let match;
      while((match=re.exec(raw)))timingTokens.push({token:token(match[0]),wi});
    }
    const domTokens=[];
    for(const el of collectBlocks(payload))for(const item of textTokensForElement(el))domTokens.push(item);
    let ti=0;
    const lookahead=18;
    for(const item of domTokens){
      if(ti>=timingTokens.length)break;
      let found=-1;
      if(timingTokens[ti].token===item.token)found=ti;
      else{
        const end=Math.min(timingTokens.length,ti+lookahead+1);
        for(let probe=ti+1;probe<end;probe++)if(timingTokens[probe].token===item.token){found=probe;break;}
      }
      if(found<0)continue;
      const wi=timingTokens[found].wi;
      if(!mappedWords[wi])mappedWords[wi]=item.range;
      ti=found+1;
    }
    debug.mappedWords=mappedWords.filter(Boolean).length;
    return debug.mappedWords;
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

  function nearestMappedIndex(index){
    if(index>=0&&index<mappedWords.length&&mappedWords[index])return index;
    for(let radius=1;radius<mappedWords.length;radius++){
      const before=index-radius,after=index+radius;
      if(before>=0&&mappedWords[before])return before;
      if(after<mappedWords.length&&mappedWords[after])return after;
    }
    return -1;
  }

  function phraseRange(index){
    const center=nearestMappedIndex(index);
    if(center<0)return null;
    const phraseSpan=12;
    const bucket=Math.floor(center/phraseSpan)*phraseSpan;
    let first=-1,last=-1;
    for(let i=bucket;i<Math.min(mappedWords.length,bucket+phraseSpan);i++)if(mappedWords[i]){if(first<0)first=i;last=i;}
    if(first<0){first=center;last=center;}
    try{
      const start=mappedWords[first],end=mappedWords[last];
      if(!start||!end||start.startContainer.ownerDocument!==end.endContainer.ownerDocument)return mappedWords[center];
      const range=start.startContainer.ownerDocument.createRange();
      range.setStart(start.startContainer,start.startOffset);
      range.setEnd(end.endContainer,end.endOffset);
      return range;
    }catch{return mappedWords[center]||null;}
  }

  function rangeVisible(range){
    try{
      if(!range)return false;
      const doc=range.startContainer&&range.startContainer.ownerDocument;
      const win=doc&&doc.defaultView;
      const width=win&&win.innerWidth||doc.documentElement.clientWidth||1;
      const height=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      return [...range.getClientRects()].some(rect=>rect.right>2&&rect.left<width-2&&rect.bottom>2&&rect.top<height-2);
    }catch{return false;}
  }

  function applyExactHighlight(range){
    if(!range)return;
    const doc=range.startContainer&&range.startContainer.ownerDocument;
    ensureFrameHooks(doc);
    try{
      const win=doc.defaultView;
      if(win&&win.CSS&&win.CSS.highlights&&typeof win.Highlight==='function'){
        win.CSS.highlights.set(highlightName,new win.Highlight(range));
      }
    }catch{}
  }

  async function syncWord(index,force=false){
    if(!timingWords.length)return false;
    buildWordMap(false);
    const range=phraseRange(index);
    if(!range)return false;
    applyExactHighlight(range);
    if(!force&&rangeVisible(range))return true;
    if(Date.now()<suppressDisplayUntil)return true;
    const now=Date.now();
    if(!force&&now-lastFollowAt<450)return false;
    const b=bridge();
    if(!b||typeof b.cfiFromRange!=='function'||typeof b.display!=='function')return false;
    let cfi='';
    try{cfi=String(b.cfiFromRange(range)||'');}catch{}
    if(!cfi)return false;
    lastFollowAt=now;
    debug.exactFollowCalls++;
    try{await b.display(cfi);return true;}catch{return false;}
  }

  async function loadTimingForCurrent(){
    const id=currentId();
    if(!id||id===timingId&&timingWords.length)return timingWords.length;
    try{
      const stateResponse=await rawFetch('/artifact-library/audio?id='+encodeURIComponent(id)+'&bookKey='+encodeURIComponent(bookKey),{cache:'no-store'});
      const state=await stateResponse.json().catch(()=>({}));
      if(!stateResponse.ok||state.status!=='ready'||!state.timingUrl)return 0;
      const timingResponse=await rawFetch(state.timingUrl,{cache:'no-store'});
      const data=await timingResponse.json().catch(()=>({}));
      if(!timingResponse.ok||!Array.isArray(data.words))return 0;
      timingId=id;
      timingWords=data.words;
      activeDoc=null;activeSignature='';mappedWords=[];
      buildWordMap(true);
      return timingWords.length;
    }catch(error){debug.lastError=String(error&&error.message||error||'timing load failed').slice(0,180);return 0;}
  }

  async function waitPrefetchReady(id){
    for(let n=0;n<240;n++){
      const response=await rawFetch('/artifact-library/audio?id='+encodeURIComponent(id)+'&bookKey='+encodeURIComponent(bookKey),{cache:'no-store'});
      const state=await response.json().catch(()=>({}));
      if(response.ok&&state.status==='ready'&&state.mediaUrl&&state.timingUrl)return state;
      if(state.status==='error')throw new Error(state.error||'PREFETCH_FAILED');
      await new Promise(resolve=>setTimeout(resolve,1500));
    }
    throw new Error('PREFETCH_TIMEOUT');
  }

  async function prefetchOne(offset){
    const key='ahead:'+offset;
    if(prefetching.has(key))return prefetching.get(key);
    const task=(async()=>{
      const b=bridge();
      if(!b||typeof b.peekReadableAhead!=='function')return null;
      const payload=await b.peekReadableAhead(offset);
      if(!payload||!payload.text||String(payload.text).length<80||!payload.chapterHref)return null;
      const existing=prefetchCache.get(payload.chapterHref);
      if(existing&&existing.state&&existing.state.status==='ready')return existing;
      debug.prefetchRequests++;
      debug.lastPrefetchChapter=payload.chapterHref;
      const response=await rawFetch('/artifact-library/audio',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',clientVersion:'reader-audio-v34-prefetch'})});
      let state=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(state.error||('HTTP_'+response.status));
      if(!state.id)throw new Error('PREFETCH_ID_MISSING');
      if(state.status!=='ready')state=await waitPrefetchReady(state.id);
      const value={payload,state,canonical:canonical(payload.text)};
      prefetchCache.set(payload.chapterHref,value);
      debug.prefetchReady++;
      return value;
    })().catch(error=>{debug.lastError=String(error&&error.message||error||'prefetch failed').slice(0,180);return null;}).finally(()=>prefetching.delete(key));
    prefetching.set(key,task);
    return task;
  }

  function schedulePrefetch(){
    setTimeout(()=>prefetchOne(1),0);
    setTimeout(()=>prefetchOne(2),150);
  }

  const wrappedFetch=async(input,init)=>{
    try{
      const method=String(init&&init.method||'GET').toUpperCase();
      const u=new URL(typeof input==='string'?input:input&&input.url||'',location.href);
      if(method==='POST'&&u.pathname==='/artifact-library/audio'){
        const body=JSON.parse(String(init&&init.body||'{}'));
        const href=String(body&&body.chapterHref||'');
        const cached=prefetchCache.get(href);
        if(cached&&cached.state&&cached.state.status==='ready'&&canonical(body&&body.text)===cached.canonical){
          debug.cacheHits++;
          return new Response(JSON.stringify(cached.state),{status:200,headers:{'content-type':'application/json','cache-control':'private, no-store'}});
        }
      }
    }catch{}
    return rawFetch(input,init);
  };
  window.fetch=wrappedFetch;

  function firstVisibleMappedWord(){
    buildWordMap(false);
    for(let i=0;i<mappedWords.length;i++)if(mappedWords[i]&&rangeVisible(mappedWords[i]))return i;
    return -1;
  }

  async function handleManualRelocation(loc){
    if(Date.now()<manualArmedAt||Date.now()<programmaticUntil)return;
    const currentChapter=String(loc&&loc.start&&loc.start.href||'');
    const state=currentState();
    if(!audio.paused)try{audio.pause();}catch{}
    if(!state.chapter||!currentChapter||state.chapter!==currentChapter){
      status.textContent='Nam Minh · tạm dừng · nhấn phát để đồng bộ trang';
      return;
    }
    await new Promise(resolve=>setTimeout(resolve,120));
    await loadTimingForCurrent();
    buildWordMap(true);
    const index=firstVisibleMappedWord();
    if(index<0)return;
    const target=Math.max(0,(Number(timingWords[index]&&timingWords[index].startMs)||0)/1000);
    suppressDisplayUntil=Date.now()+650;
    try{audio.currentTime=target;}catch{}
    debug.manualSyncs++;
    status.textContent='Nam Minh · tạm dừng · đã đồng bộ trang';
    applyExactHighlight(phraseRange(index));
  }

  function installBridgeHooks(){
    const b=bridge();
    if(!b||b.__r3AudioContinuityV34Hooks)return false;
    b.__r3AudioContinuityV34Hooks=true;
    for(const name of ['display','next','prev']){
      if(typeof b[name]!=='function')continue;
      const original=b[name].bind(b);
      b[name]=(...args)=>{
        if(Date.now()<suppressDisplayUntil&&name==='display')return Promise.resolve(false);
        programmaticUntil=Date.now()+1100;
        return original(...args);
      };
    }
    if(typeof b.onRelocated==='function'){
      relocatedOff=b.onRelocated(loc=>{
        clearTimeout(locationTimer);
        locationTimer=setTimeout(()=>handleManualRelocation(loc),90);
      });
    }
    return true;
  }

  const tick=async()=>{
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
  },100);
})();
</script>`;

function patchV34(html) {
  let out = String(html || '');
  if (out.includes('data-r3-audio-continuity-v34="1"')) return out;
  if (!out.includes(BRIDGE_RANGE_NEEDLE)) throw new Error('READER_V34_PATCH_MISSING:cfiFromRange');
  out = out.replace(BRIDGE_RANGE_NEEDLE, BRIDGE_RANGE_PATCH);
  if (!out.includes('</body>')) throw new Error('READER_V34_BODY_MARKER_MISSING');
  out = out.replace('</body>', OVERLAY + '</body>');
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
      const updated = patchV34(await response.text());
      const headers = new Headers(response.headers);
      headers.delete('Content-Length');
      headers.set('X-Robots-Tag', ROBOTS);
      headers.set('X-R3-Reader-Runtime', 'v34-continuous-range-sync');
      headers.set('X-R3-Reader-Patch-Proof', 'v33+v34:ahead-prefetch+range-follow+manual-sync');
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v34 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v34-patch-failed',
          'X-R3-Reader-Patch-Error': String(error?.message || error).slice(0, 220),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === 'function') return app.scheduled(controller, env, ctx);
  },
};
