import app from "./artifact-library-reader-v19-stable-final-seek-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const MARKER_OLD = `  window.__r3AudioStableFinalSeekV19=true;`;
const MARKER_NEW = `  window.__r3AudioStableFinalSeekV19=true;
  window.__r3AudioSeekableAnchorV20=true;
  function seekableEndV20(){
    try{
      if(!audio.seekable||audio.seekable.length<1)return 0;
      let end=0;
      for(let i=0;i<audio.seekable.length;i++)end=Math.max(end,Number(audio.seekable.end(i))||0);
      return end;
    }catch{return 0;}
  }
  async function waitSeekableV20(target,timeout=8000){
    const started=Date.now();
    let snapshot=null;
    while(Date.now()-started<timeout){
      const end=seekableEndV20();
      snapshot={readyState:Number(audio.readyState)||0,networkState:Number(audio.networkState)||0,duration:Number(audio.duration)||0,seekableEnd:end,currentTime:Number(audio.currentTime)||0};
      if((end>=Math.max(.1,target-.05))||(snapshot.readyState>=3&&snapshot.duration>target))return {ok:true,...snapshot,waitedMs:Date.now()-started};
      try{audio.load();}catch{}
      await delay(100);
    }
    const end=seekableEndV20();
    return {ok:false,readyState:Number(audio.readyState)||0,networkState:Number(audio.networkState)||0,duration:Number(audio.duration)||0,seekableEnd:end,currentTime:Number(audio.currentTime)||0,waitedMs:Date.now()-started};
  }
  async function landSeekV20(target,timeout=2500){
    const started=Date.now();
    let attempts=0;
    while(Date.now()-started<timeout){
      attempts++;
      try{audio.currentTime=target;}catch(error){window.__r3AudioV18Debug.seekError=String(error&&error.message||error);}
      await delay(70);
      const actual=Number(audio.currentTime)||0;
      if(Math.abs(actual-target)<=.35)return {ok:true,target,actual,attempts,readyState:Number(audio.readyState)||0,seekableEnd:seekableEndV20(),waitedMs:Date.now()-started};
      if(typeof audio.fastSeek==='function'){try{audio.fastSeek(target);}catch{}}
      await delay(60);
    }
    return {ok:false,target,actual:Number(audio.currentTime)||0,attempts,readyState:Number(audio.readyState)||0,seekableEnd:seekableEndV20(),waitedMs:Date.now()-started};
  }`;

const TARGET_OLD = `      const boundedTarget=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));
      try{audio.currentTime=boundedTarget;}catch(error){window.__r3AudioV18Debug.seekError=String(error&&error.message||error);}
      await delay(80);
      let seekActual=Number(audio.currentTime)||0;
      if(Math.abs(seekActual-boundedTarget)>.35){
        try{audio.currentTime=boundedTarget;}catch{}
        await delay(45);
        seekActual=Number(audio.currentTime)||0;
      }
      window.__r3AudioV18Debug.afterFinalSeek={target:boundedTarget,actual:seekActual};
      window.__r3AudioAnchorApplyingV18=false;
      await audio.play();`;
const TARGET_NEW = `      const boundedTarget=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));
      const seekReadyV20=await waitSeekableV20(boundedTarget,8000);
      window.__r3AudioV18Debug.seekReadyV20=seekReadyV20;
      const landedV20=await landSeekV20(boundedTarget,2500);
      window.__r3AudioV18Debug.afterFinalSeek=landedV20;
      if(!landedV20.ok)throw new Error('AUDIO_SEEK_NOT_READY:'+JSON.stringify(landedV20));
      await audio.play();
      await delay(60);
      let postPlayActual=Number(audio.currentTime)||0;
      if(postPlayActual<boundedTarget-.5){
        const relandV20=await landSeekV20(boundedTarget,1200);
        window.__r3AudioV18Debug.postPlayRelandV20=relandV20;
        postPlayActual=Number(audio.currentTime)||0;
      }
      window.__r3AudioV18Debug.postPlayActualV20=postPlayActual;
      window.__r3AudioAnchorApplyingV18=false;
      syncReading(true);
      saveState(true);`;

function replaceOnce(source,needle,replacement,label){
  const first=source.indexOf(needle);
  if(first<0)throw new Error(`READER_V20_PATCH_MISSING:${label}`);
  if(source.indexOf(needle,first+needle.length)>=0)throw new Error(`READER_V20_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0,first)+replacement+source.slice(first+needle.length);
}
function patchSeekableAnchor(html){
  let out=String(html||'');
  if(out.includes('window.__r3AudioSeekableAnchorV20=true'))return out;
  out=replaceOnce(out,MARKER_OLD,MARKER_NEW,'markerHelpers');
  out=replaceOnce(out,TARGET_OLD,TARGET_NEW,'seekableFinalSeek');
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
      const updated=patchSeekableAnchor(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v20-seekable-anchor");
      headers.set("X-R3-Reader-Patch-Proof","v18+v19+v20:seekable+landing+postplay");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v20 patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v20-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
