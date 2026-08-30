import app from "./artifact-library-reader-v15-viewport-word-sync-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const BLOCK_OLD = `  function blockVisible(el){
    try{
      const doc=el.ownerDocument,win=doc.defaultView;
      const w=win&&win.innerWidth||doc.documentElement.clientWidth||1;
      const h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      const rects=[...el.getClientRects()];
      return rects.some(rect=>rectVisible(rect,w,h));
    }catch{return false;}
  }
`;
const BLOCK_NEW = `  function r3OuterRectVisibleV18(rect,doc){
    try{
      if(!rect||!doc)return false;
      const viewer=document.getElementById('viewer');
      let frame=null;
      for(const candidate of document.querySelectorAll('#viewer iframe')){
        try{if(candidate.contentDocument===doc){frame=candidate;break;}}catch{}
      }
      if(frame&&viewer){
        const fr=frame.getBoundingClientRect(),vr=viewer.getBoundingClientRect();
        const left=fr.left+rect.left,right=fr.left+rect.right,top=fr.top+rect.top,bottom=fr.top+rect.bottom;
        return right>vr.left+2&&left<vr.right-2&&bottom>vr.top+2&&top<vr.bottom-2;
      }
      const win=doc.defaultView,w=win&&win.innerWidth||doc.documentElement.clientWidth||1,h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      return rectVisible(rect,w,h);
    }catch{return false;}
  }
  function blockVisible(el){
    try{return [...el.getClientRects()].some(rect=>r3OuterRectVisibleV18(rect,el.ownerDocument));}catch{return false;}
  }
`;

const RANGE_OLD = `  function rangeVisibleExact(range){
    try{
      if(!range)return false;
      const doc=range.commonAncestorContainer&&range.commonAncestorContainer.ownerDocument||activeDoc;
      const win=doc&&doc.defaultView;
      const w=win&&win.innerWidth||doc.documentElement.clientWidth||1;
      const h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      return [...range.getClientRects()].some(rect=>rectVisible(rect,w,h));
    }catch{return false;}
  }
`;
const RANGE_NEW = `  function rangeVisibleExact(range){
    try{
      if(!range)return false;
      const node=range.commonAncestorContainer;
      const doc=node&&node.nodeType===9?node:(node&&node.ownerDocument)||activeDoc;
      return [...range.getClientRects()].some(rect=>r3OuterRectVisibleV18(rect,doc));
    }catch{return false;}
  }
`;

const MARKER_OLD = `  window.__r3AudioViewportWordV15=true;
`;
const MARKER_NEW = `  window.__r3AudioViewportWordV15=true;
  window.__r3AudioVerifiedOuterAnchorV18=true;
  window.__r3AudioV18Debug={patches:{blockVisible:true,rangeVisible:true,prepareStart:true,prepareTarget:true,saveGuard:true,finallyGuard:true},captured:null,target:null};
  function captureViewportAnchorV18(){
    const payload=framePayload();
    if(!payload)return null;
    try{
      const rows=collectBlocks(payload);
      for(let bi=0;bi<rows.length;bi++){
        const items=tokenRangesForElement(rows[bi]);
        for(let ti=0;ti<items.length;ti++){
          if(!rangeVisibleExact(items[ti].range))continue;
          const anchor={signature:payload.signature,el:rows[bi],blockIndex:bi,tokenIndex:ti,token:items[ti].token||'',cfi:cfiForRange(items[ti].range)||cfiForNode(rows[bi])||''};
          window.__r3AudioV18Debug.captured={blockIndex:bi,tokenIndex:ti,token:anchor.token,cfi:anchor.cfi};
          return anchor;
        }
      }
    }catch(error){window.__r3AudioV18Debug.captureError=String(error&&error.message||error);}
    return null;
  }
  function secondsForFrozenAnchorV18(anchor){
    if(!anchor||!timingWords.length)return NaN;
    const payload=framePayload();
    if(!payload||payload.signature!==anchor.signature)return NaN;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    let row=blockRanges.find(item=>item.el===anchor.el)||null;
    if(!row&&Number.isInteger(anchor.blockIndex))row=blockRanges[anchor.blockIndex]||null;
    if(!row)return NaN;
    const exact=exactMapForRow(row);
    if(!exact||!exact.items.length)return NaN;
    let index=Math.max(0,Math.min(Number(anchor.tokenIndex)||0,exact.items.length-1));
    if(anchor.token&&exact.items[index]&&exact.items[index].token!==anchor.token){
      const start=Math.max(0,index-16),end=Math.min(exact.items.length-1,index+16);
      let found=-1;
      for(let i=start;i<=end;i++){if(exact.items[i]&&exact.items[i].token===anchor.token){found=i;break;}}
      if(found>=0)index=found;
    }
    const wi=nearestMappedWord(exact.mapped,index);
    if(wi===null)return NaN;
    const seconds=Math.max(0,(Number(timingWords[wi]&&timingWords[wi].startMs)||0)/1000);
    window.__r3AudioV18Debug.target={seconds,wordIndex:wi,blockIndex:row.index,tokenIndex:index,token:anchor.token};
    return seconds;
  }
`;

const PREPARE_START_OLD = `  async function prepareCurrentChapter(payload,visible){
    const seq=++requestSeq;`;
const PREPARE_START_NEW = `  async function prepareCurrentChapter(payload,visible){
    const frozenViewportV18=captureViewportAnchorV18();
    window.__r3AudioAnchorApplyingV18=true;
    const seq=++requestSeq;`;

const PREPARE_TARGET_OLD = `      const exactVisible=firstVisibleTokenTarget();
      const freshVisible=firstVisibleRange()||visible;
      const target=exactVisible&&Number.isFinite(exactVisible.seconds)?exactVisible.seconds:startSecondsForRange(freshVisible);
      try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}
      await audio.play();`;
const PREPARE_TARGET_NEW = `      const frozenTargetV18=secondsForFrozenAnchorV18(frozenViewportV18);
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

const SAVE_OLD = `  function saveState(force=false){
    const now=Date.now();`;
const SAVE_NEW = `  function saveState(force=false){
    if(window.__r3AudioAnchorApplyingV18)return;
    const now=Date.now();`;

const FINALLY_OLD = `    }finally{if(seq===requestSeq)busy=false;}
  }`;
const FINALLY_NEW = `    }finally{window.__r3AudioAnchorApplyingV18=false;if(seq===requestSeq)busy=false;}
  }`;

function replaceExactlyOnce(source, needle, replacement, label) {
  const first = source.indexOf(needle);
  if (first < 0) throw new Error(`READER_V18_PATCH_MISSING:${label}`);
  if (source.indexOf(needle, first + needle.length) >= 0) throw new Error(`READER_V18_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0, first) + replacement + source.slice(first + needle.length);
}

function patchVerifiedOuterAnchor(html) {
  let out=String(html||'');
  if(out.includes('window.__r3AudioVerifiedOuterAnchorV18=true'))return out;
  out=replaceExactlyOnce(out,BLOCK_OLD,BLOCK_NEW,'blockVisible');
  out=replaceExactlyOnce(out,RANGE_OLD,RANGE_NEW,'rangeVisibleExact');
  out=replaceExactlyOnce(out,MARKER_OLD,MARKER_NEW,'markerHelpers');
  out=replaceExactlyOnce(out,PREPARE_START_OLD,PREPARE_START_NEW,'prepareStart');
  out=replaceExactlyOnce(out,PREPARE_TARGET_OLD,PREPARE_TARGET_NEW,'prepareTarget');
  out=replaceExactlyOnce(out,SAVE_OLD,SAVE_NEW,'saveGuard');
  out=replaceExactlyOnce(out,FINALLY_OLD,FINALLY_NEW,'finallyGuard');
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url=new URL(request.url);
    const response=await app.fetch(request,env,ctx);
    if(url.pathname!=="/artifact-library/read"||request.method!=="GET")return response;
    const type=response.headers.get("Content-Type")||"";
    if(!type.toLowerCase().includes("text/html"))return response;
    try{
      const updated=patchVerifiedOuterAnchor(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v18-verified-outer-frozen-anchor");
      headers.set("X-R3-Reader-Patch-Proof","block+range+prepare+target+save+finally");
      return new Response(updated,{status:response.status,headers});
    }catch(error){
      console.error('Reader v18 patch failed',String(error&&error.message||error));
      return new Response('Reader runtime patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v18-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
