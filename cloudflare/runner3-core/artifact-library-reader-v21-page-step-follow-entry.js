import app from "./artifact-library-reader-v20-seekable-anchor-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const CFI_OLD = `  function cfiForRange(range){
    const b=bridge();
    if(!b||typeof b.cfiFromRange!=='function')return '';
    try{return b.cfiFromRange(range)||'';}catch{return '';}
  }
`;
const CFI_NEW = `  function cfiForRange(range){
    const b=bridge();
    if(!b||typeof b.cfiFromRange!=='function')return '';
    try{
      const point=range&&typeof range.cloneRange==='function'?range.cloneRange():range;
      if(point&&typeof point.collapse==='function')point.collapse(true);
      return b.cfiFromRange(point)||'';
    }catch{return '';}
  }
  function tokenPageDirectionV21(range){
    try{
      if(!range)return 0;
      const node=range.commonAncestorContainer;
      const doc=node&&node.nodeType===9?node:(node&&node.ownerDocument)||activeDoc;
      const viewer=document.getElementById('viewer');
      let frame=null;
      for(const candidate of document.querySelectorAll('#viewer iframe')){
        try{if(candidate.contentDocument===doc){frame=candidate;break;}}catch{}
      }
      if(!viewer||!frame)return 0;
      const vr=viewer.getBoundingClientRect(),fr=frame.getBoundingClientRect();
      const rects=[...range.getClientRects()];
      if(!rects.length)return 0;
      let left=Infinity,right=-Infinity;
      for(const rect of rects){left=Math.min(left,fr.left+rect.left);right=Math.max(right,fr.left+rect.right);}
      if(left>=vr.right-2)return 1;
      if(right<=vr.left+2)return -1;
      return 0;
    }catch{return 0;}
  }
`;

const FOLLOW_OLD = `  async function followToken(target,force=false){
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
`;
const FOLLOW_NEW = `  async function followToken(target,force=false){
    if(!target)return false;
    if(!force&&(audio.paused||audio.ended))return false;
    if(rangeVisibleExact(target.range))return true;
    const now=Date.now();
    if(!force&&now-lastFollowAt<320)return false;
    lastFollowAt=now;
    const b=bridge();
    if(!b)return false;
    const before=b&&typeof b.current==='function'?b.current():null;
    const beforeCfi=before&&before.start&&before.start.cfi||'';
    let steps=0;
    let direction=tokenPageDirectionV21(target.range);
    while(direction&&steps<12&&!rangeVisibleExact(target.range)){
      try{
        if(direction>0&&typeof b.next==='function')await b.next();
        else if(direction<0&&typeof b.prev==='function')await b.prev();
        else break;
      }catch{break;}
      steps++;
      await delay(85);
      if(rangeVisibleExact(target.range))break;
      direction=tokenPageDirectionV21(target.range);
    }
    let visible=rangeVisibleExact(target.range);
    let cfi='';
    let fallbackMoved=false;
    if(!visible){
      cfi=cfiForRange(target.range)||cfiForNode(target.row&&target.row.el);
      if(cfi&&(!force&&cfi===lastFollowCfi)===false){
        lastFollowCfi=cfi;
        fallbackMoved=await safeDisplay(cfi);
        await delay(100);
        visible=rangeVisibleExact(target.range);
      }
    }
    if(visible){
      if(typeof b.persist==='function')try{b.persist();}catch{}
      const after=typeof b.current==='function'?b.current():null;
      const afterCfi=after&&after.start&&after.start.cfi||'';
      window.__r3AudioFollowV21Debug={ok:true,steps,direction,cfi,fallbackMoved,beforeCfi,afterCfi,wordIndex:target.wordIndex,tokenIndex:target.tokenIndex};
      buildAlignment(true);
      return true;
    }
    const after=typeof b.current==='function'?b.current():null;
    window.__r3AudioFollowV21Debug={ok:false,steps,direction,cfi,fallbackMoved,beforeCfi,afterCfi:after&&after.start&&after.start.cfi||'',wordIndex:target.wordIndex,tokenIndex:target.tokenIndex};
    return false;
  }
`;

const MARKER_OLD = `  window.__r3AudioSeekableAnchorV20=true;`;
const MARKER_NEW = `  window.__r3AudioSeekableAnchorV20=true;
  window.__r3AudioPageStepFollowV21=true;`;

function replaceOnce(source,needle,replacement,label){
  const first=source.indexOf(needle);
  if(first<0)throw new Error(`READER_V21_PATCH_MISSING:${label}`);
  if(source.indexOf(needle,first+needle.length)>=0)throw new Error(`READER_V21_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0,first)+replacement+source.slice(first+needle.length);
}

function patchPageStepFollow(html){
  let out=String(html||'');
  if(out.includes('window.__r3AudioPageStepFollowV21=true'))return out;
  out=replaceOnce(out,CFI_OLD,CFI_NEW,'pointCfi');
  out=replaceOnce(out,FOLLOW_OLD,FOLLOW_NEW,'pageStepFollow');
  out=replaceOnce(out,MARKER_OLD,MARKER_NEW,'marker');
  return out;
}

export default {
  async fetch(request,env,ctx){
    const url=new URL(request.url);
    const response=await app.fetch(request,env,ctx);
    if(url.pathname!=="/artifact-library/read"||request.method!=="GET")return response;
    const type=response.headers.get("Content-Type")||"";
    if(!type.toLowerCase().includes("text/html")||response.status!==200)return response;
    try{
      const updated=patchPageStepFollow(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v21-page-step-follow");
      headers.set("X-R3-Reader-Patch-Proof","v20+v21:point-cfi+page-step-follow");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v21 patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v21-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
