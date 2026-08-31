import app from "./artifact-library-reader-v31-high-speed-serialized-follow-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const ENDED_OLD = `  audio.addEventListener('ended',()=>{saveState(true);clearHighlight();});`;
const ENDED_NEW = `  let r3AutoNextBusyV32=false;
  window.__r3AudioAutoNextChapterV32=true;
  window.__r3AudioAutoNextV32Debug={runs:0,moves:0,ok:false,reason:'idle',fromSignature:'',toSignature:'',beforeCfi:'',afterCfi:'',prepared:false,error:''};
  async function r3AdvanceToNextReadableV32(){
    if(r3AutoNextBusyV32)return false;
    r3AutoNextBusyV32=true;
    const debug=window.__r3AudioAutoNextV32Debug||(window.__r3AudioAutoNextV32Debug={runs:0,moves:0,ok:false,reason:'idle',fromSignature:'',toSignature:'',beforeCfi:'',afterCfi:'',prepared:false,error:''});
    debug.runs++;
    debug.moves=0;debug.ok=false;debug.prepared=false;debug.error='';debug.reason='starting';debug.toSignature='';debug.afterCfi='';
    const before=framePayload();
    const beforeSignature=String(before&&before.signature||loadedSignature||'');
    debug.fromSignature=beforeSignature;
    const b=bridge();
    if(!beforeSignature){debug.reason='no-current-payload';r3AutoNextBusyV32=false;return false;}
    if(!b||typeof b.next!=='function'){
      debug.reason='no-next-bridge';
      setMain('play');setStatus('Không thể chuyển sang phần tiếp theo');
      r3AutoNextBusyV32=false;
      return false;
    }
    try{
      setStatus('Nam Minh · chuyển sang phần tiếp theo…');
      try{syncReading(true);}catch{}
      await delay(260);
      let stagnant=0;
      for(let step=0;step<32;step++){
        const beforeLoc=typeof b.current==='function'?b.current():null;
        const beforeCfi=String(beforeLoc&&beforeLoc.start&&beforeLoc.start.cfi||'');
        if(step===0)debug.beforeCfi=beforeCfi;
        try{
          await Promise.race([Promise.resolve(b.next()),delay(900)]);
        }catch(error){
          debug.error=String(error&&error.message||error||'next failed').slice(0,160);
        }
        await delay(170);
        debug.moves=step+1;
        const afterLoc=typeof b.current==='function'?b.current():null;
        const afterCfi=String(afterLoc&&afterLoc.start&&afterLoc.start.cfi||'');
        debug.afterCfi=afterCfi;
        const payload=framePayload();
        if(payload&&payload.signature&&payload.signature!==beforeSignature){
          debug.toSignature=payload.signature;
          debug.reason='readable-next-found';
          try{if(typeof b.persist==='function')b.persist();}catch{}
          const visible=firstVisibleRange();
          const prepared=await prepareCurrentChapter(payload,visible);
          debug.prepared=Boolean(prepared);
          debug.ok=Boolean(prepared);
          debug.reason=prepared?'playing-next':'prepare-next-failed';
          if(prepared)setStatus('Nam Minh · đang phát');
          return Boolean(prepared);
        }
        if(afterCfi&&beforeCfi&&afterCfi===beforeCfi)stagnant++;
        else stagnant=0;
        if(stagnant>=2)break;
      }
      debug.reason='book-end-or-no-readable-next';
      setMain('play');setStatus('Đã hết sách');
      return false;
    }catch(error){
      debug.error=String(error&&error.message||error||'auto next failed').slice(0,180);
      debug.reason='exception';
      setMain('play');setStatus('Không thể chuyển sang phần tiếp theo');
      return false;
    }finally{
      r3AutoNextBusyV32=false;
    }
  }
  audio.addEventListener('ended',()=>{
    saveState(true);
    clearHighlight();
    r3AdvanceToNextReadableV32();
  });`;

function replaceOnce(source,needle,replacement,label){
  const first=source.indexOf(needle);
  if(first<0)throw new Error(`READER_V32_PATCH_MISSING:${label}`);
  if(source.indexOf(needle,first+needle.length)>=0)throw new Error(`READER_V32_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0,first)+replacement+source.slice(first+needle.length);
}

function patchAutoNextChapter(html){
  let out=String(html||'');
  if(out.includes('window.__r3AudioAutoNextChapterV32=true'))return out;
  out=replaceOnce(out,ENDED_OLD,ENDED_NEW,'endedListener');
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
      const updated=patchAutoNextChapter(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v32-auto-next-chapter");
      headers.set("X-R3-Reader-Patch-Proof","v31+v32:ended-next-readable-spine+autoplay");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v32 patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v32-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
