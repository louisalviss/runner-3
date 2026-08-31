import app from "./artifact-library-reader-v21-page-step-follow-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const FOLLOW_OLD = `  async function followToken(target,force=false){
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

const FOLLOW_NEW = `  async function followToken(target,force=false){
    if(!target)return false;
    if(!force&&(audio.paused||audio.ended))return false;
    const b=bridge();
    const startLoc=b&&typeof b.current==='function'?b.current():null;
    const debug={phase:'enter',ok:false,steps:0,targetWord:Number(target.wordIndex),visibleWord:null,direction:0,beforeCfi:startLoc&&startLoc.start&&startLoc.start.cfi||'',afterCfi:'',visibleAtEnd:false};
    window.__r3AudioFollowV22Debug=debug;window.__r3AudioFollowV21Debug=debug;
    if(rangeVisibleExact(target.range)){debug.phase='already-visible';debug.ok=true;debug.visibleAtEnd=true;return true;}
    const now=Date.now();
    if(!force&&now-lastFollowAt<280){debug.phase='throttled';return false;}
    lastFollowAt=now;
    if(!b){debug.phase='no-bridge';return false;}
    for(let steps=0;steps<16&&!rangeVisibleExact(target.range);steps++){
      const visibleNow=firstVisibleTokenTarget();
      const visibleWord=visibleNow&&Number.isFinite(Number(visibleNow.wordIndex))?Number(visibleNow.wordIndex):null;
      let direction=0;
      if(visibleWord!==null&&Number.isFinite(Number(target.wordIndex))){
        if(Number(target.wordIndex)>visibleWord)direction=1;
        else if(Number(target.wordIndex)<visibleWord)direction=-1;
      }
      if(!direction)direction=tokenPageDirectionV21(target.range);
      debug.visibleWord=visibleWord;debug.direction=direction;debug.phase='stepping';
      if(!direction)break;
      try{
        const move=direction>0&&typeof b.next==='function'?b.next():direction<0&&typeof b.prev==='function'?b.prev():null;
        if(!move)break;
        await Promise.race([Promise.resolve(move),delay(700)]);
      }catch(error){debug.moveError=String(error&&error.message||error);break;}
      debug.steps=steps+1;
      await delay(90);
    }
    const visible=rangeVisibleExact(target.range);
    debug.visibleAtEnd=visible;
    if(visible){
      if(typeof b.persist==='function')try{b.persist();}catch{}
      const after=typeof b.current==='function'?b.current():null;
      debug.afterCfi=after&&after.start&&after.start.cfi||'';debug.ok=true;debug.phase='landed';
      buildAlignment(true);
      return true;
    }
    debug.phase='not-landed';
    const after=typeof b.current==='function'?b.current():null;
    debug.afterCfi=after&&after.start&&after.start.cfi||'';
    return false;
  }
`;

const MARKER_OLD = `  window.__r3AudioPageStepFollowV21=true;`;
const MARKER_NEW = `  window.__r3AudioPageStepFollowV21=true;
  window.__r3AudioWordIndexFollowV22=true;`;

function replaceOnce(source,needle,replacement,label){
  const first=source.indexOf(needle);
  if(first<0)throw new Error(`READER_V22_PATCH_MISSING:${label}`);
  if(source.indexOf(needle,first+needle.length)>=0)throw new Error(`READER_V22_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0,first)+replacement+source.slice(first+needle.length);
}

function patchWordIndexFollow(html){
  let out=String(html||'');
  if(out.includes('window.__r3AudioWordIndexFollowV22=true'))return out;
  out=replaceOnce(out,FOLLOW_OLD,FOLLOW_NEW,'wordIndexFollow');
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
      const updated=patchWordIndexFollow(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v22-word-index-page-follow");
      headers.set("X-R3-Reader-Patch-Proof","v21+v22:visible-word-direction+page-step");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v22 patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v22-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
