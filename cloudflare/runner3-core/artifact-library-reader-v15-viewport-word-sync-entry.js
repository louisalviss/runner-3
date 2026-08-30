import app from "./artifact-library-reader-v14-media-id-all-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const BRIDGE_NEEDLE = `    cfiFromNode(node){\n`;
const BRIDGE_PATCH = `    cfiFromRange(range){
      try{
        const contents=rendition&&rendition.getContents?rendition.getContents()||[]:[];
        for(const content of contents){
          try{
            const doc=content&&content.document;
            if(doc&&range&&range.commonAncestorContainer&&doc.contains(range.commonAncestorContainer)&&typeof content.cfiFromRange==='function')return content.cfiFromRange(range);
          }catch{}
        }
      }catch{}
      return null;
    },
    cfiFromNode(node){
`;

const VISIBLE_RANGE_NEEDLE = `  function firstVisibleRange(){
    const payload=framePayload();
    if(!payload)return null;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    for(const row of blockRanges)if(blockVisible(row.el))return row;
    return blockRanges.find(row=>row.first!==null)||null;
  }
`;

const VIEWPORT_WORD_HELPERS = `  function firstVisibleRange(){
    const payload=framePayload();
    if(!payload)return null;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    for(const row of blockRanges)if(blockVisible(row.el))return row;
    return blockRanges.find(row=>row.first!==null)||null;
  }
  const viewportTokenCache=new WeakMap();
  const viewportMapCache=new WeakMap();
  function tokenRangesForElement(el){
    if(!el)return [];
    const cached=viewportTokenCache.get(el);
    if(cached)return cached;
    const out=[];
    try{
      const doc=el.ownerDocument;
      const walker=doc.createTreeWalker(el,NodeFilter.SHOW_TEXT);
      const re=/[\\p{L}\\p{M}\\p{N}]+/gu;
      let node;
      while((node=walker.nextNode())){
        const raw=String(node.nodeValue||'');
        re.lastIndex=0;
        let match;
        while((match=re.exec(raw))){
          const token=String(match[0]||'').normalize('NFKC').toLocaleLowerCase('vi-VN');
          if(!token)continue;
          const range=doc.createRange();
          range.setStart(node,match.index);
          range.setEnd(node,match.index+match[0].length);
          out.push({token,range});
        }
      }
    }catch{}
    viewportTokenCache.set(el,out);
    return out;
  }
  function exactMapForRow(row){
    if(!row||!row.el)return null;
    const cached=viewportMapCache.get(row.el);
    if(cached&&cached.timingRef===timingWords)return cached;
    const items=tokenRangesForElement(row.el);
    const mapped=new Array(items.length).fill(null);
    if(items.length&&timingTokens.length&&row.first!==null){
      let ti=0;
      while(ti<timingTokens.length&&timingTokens[ti].wi<row.first)ti++;
      const LOOKAHEAD=18;
      for(let di=0;di<items.length&&ti<timingTokens.length;di++){
        const token=items[di].token;
        let found=-1;
        const maxWi=row.last===null?Infinity:row.last+2;
        if(timingTokens[ti]&&timingTokens[ti].wi<=maxWi&&timingTokens[ti].token===token)found=ti;
        else{
          const end=Math.min(timingTokens.length,ti+LOOKAHEAD+1);
          for(let probe=ti+1;probe<end;probe++){
            if(timingTokens[probe].wi>maxWi)break;
            if(timingTokens[probe].token===token){found=probe;break;}
          }
        }
        if(found<0)continue;
        mapped[di]=timingTokens[found].wi;
        ti=found+1;
      }
    }
    const result={timingRef:timingWords,items,mapped};
    viewportMapCache.set(row.el,result);
    return result;
  }
  function rangeVisibleExact(range){
    try{
      if(!range)return false;
      const doc=range.commonAncestorContainer&&range.commonAncestorContainer.ownerDocument||activeDoc;
      const win=doc&&doc.defaultView;
      const w=win&&win.innerWidth||doc.documentElement.clientWidth||1;
      const h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      return [...range.getClientRects()].some(rect=>rectVisible(rect,w,h));
    }catch{return false;}
  }
  function nearestMappedWord(mapped,index){
    if(index>=0&&index<mapped.length&&mapped[index]!==null)return mapped[index];
    for(let radius=1;radius<mapped.length;radius++){
      const before=index-radius,after=index+radius;
      if(before>=0&&mapped[before]!==null)return mapped[before];
      if(after<mapped.length&&mapped[after]!==null)return mapped[after];
    }
    return null;
  }
  function firstVisibleTokenTarget(){
    const payload=framePayload();
    if(!payload||!timingWords.length)return null;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    for(const row of blockRanges){
      if(!blockVisible(row.el))continue;
      const exact=exactMapForRow(row);
      if(!exact)continue;
      for(let i=0;i<exact.items.length;i++){
        if(!rangeVisibleExact(exact.items[i].range))continue;
        const wi=nearestMappedWord(exact.mapped,i);
        if(wi===null)continue;
        return {row,range:exact.items[i].range,wordIndex:wi,seconds:Math.max(0,(Number(timingWords[wi]&&timingWords[wi].startMs)||0)/1000),tokenIndex:i};
      }
    }
    return null;
  }
  function tokenTargetForWord(row,wordIndex){
    const exact=exactMapForRow(row);
    if(!exact)return null;
    let previous=-1;
    for(let i=0;i<exact.mapped.length;i++){
      const wi=exact.mapped[i];
      if(wi===null)continue;
      if(wi>=wordIndex)return {row,range:exact.items[i].range,wordIndex:wi,tokenIndex:i};
      previous=i;
    }
    if(previous>=0)return {row,range:exact.items[previous].range,wordIndex:exact.mapped[previous],tokenIndex:previous};
    return null;
  }
  function cfiForRange(range){
    const b=bridge();
    if(!b||typeof b.cfiFromRange!=='function')return '';
    try{return b.cfiFromRange(range)||'';}catch{return '';}
  }
  async function followToken(target,force=false){
    if(!target)return false;
    if(!force&&(audio.paused||audio.ended))return false;
    if(!force&&rangeVisibleExact(target.range))return true;
    const now=Date.now();
    if(!force&&now-lastFollowAt<450)return false;
    const cfi=cfiForRange(target.range)||cfiForNode(target.row&&target.row.el);
    if(!cfi||(!force&&cfi===lastFollowCfi))return false;
    lastFollowAt=now;lastFollowCfi=cfi;
    const moved=await safeDisplay(cfi);
    if(moved){
      const b=bridge();if(b&&typeof b.persist==='function')try{b.persist();}catch{}
      await delay(90);
      buildAlignment(true);
      return true;
    }
    return false;
  }
  window.__r3AudioViewportWordV15=true;
`;

const SYNC_NEEDLE = `  function syncReading(forceDisplay=false){
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
`;

const SYNC_PATCH = `  function syncReading(forceDisplay=false){
    installBridgeGuard();
    if(!timingWords.length)return;
    const payload=framePayload();
    if(!payload)return;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    clearLegacyHighlight(payload.doc);
    const wordIndex=wordIndexAt((Number(audio.currentTime)||0)*1000);
    const row=rangeForWord(wordIndex);
    if(!row)return;
    if(row.el!==activeBlock){
      clearHighlight();
      activeBlock=row.el;
      try{activeBlock.setAttribute('data-r3-audio-reading-v11','1');}catch{}
    }
    const tokenTarget=tokenTargetForWord(row,wordIndex);
    if(tokenTarget)followToken(tokenTarget,forceDisplay);
    else if(forceDisplay||!blockVisible(row.el))followRange(row,forceDisplay);
  }
`;

const PREPARE_NEEDLE = `      const freshVisible=firstVisibleRange()||visible;
      const target=startSecondsForRange(freshVisible);
`;
const PREPARE_PATCH = `      const exactVisible=firstVisibleTokenTarget();
      const freshVisible=firstVisibleRange()||visible;
      const target=exactVisible&&Number.isFinite(exactVisible.seconds)?exactVisible.seconds:startSecondsForRange(freshVisible);
`;

const RESUME_NEEDLE = `        const visible=firstVisibleRange();
        if(visible){const target=startSecondsForRange(visible);try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}}
`;
const RESUME_PATCH = `        const exactVisible=firstVisibleTokenTarget();
        const visible=firstVisibleRange();
        if(exactVisible||visible){const target=exactVisible&&Number.isFinite(exactVisible.seconds)?exactVisible.seconds:startSecondsForRange(visible);try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}}
`;

function patchViewportWordSync(html) {
  let out = html;
  if (!out.includes("window.__r3AudioViewportWordV15=true")) {
    if (out.includes(BRIDGE_NEEDLE)) out = out.replace(BRIDGE_NEEDLE, BRIDGE_PATCH);
    if (out.includes(VISIBLE_RANGE_NEEDLE)) out = out.replace(VISIBLE_RANGE_NEEDLE, VIEWPORT_WORD_HELPERS);
    if (out.includes(SYNC_NEEDLE)) out = out.replace(SYNC_NEEDLE, SYNC_PATCH);
    if (out.includes(PREPARE_NEEDLE)) out = out.replace(PREPARE_NEEDLE, PREPARE_PATCH);
    if (out.includes(RESUME_NEEDLE)) out = out.replace(RESUME_NEEDLE, RESUME_PATCH);
  }
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;

    const original = await response.text();
    const updated = patchViewportWordSync(original);
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v15-viewport-word-cfi-sync");
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
