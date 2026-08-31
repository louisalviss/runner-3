import app from "./artifact-library-reader-v22-word-index-follow-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const HANDLE_OLD = `    setTitle(payload.chapterTitle||'Chương hiện tại');

    const id=idFromAudio();
    if(id&&audio.getAttribute('src')&&loadedSignature===payload.signature){`;
const HANDLE_NEW = `    setTitle(payload.chapterTitle||'Chương hiện tại');

    const id=idFromAudio()||currentId;
    if(id&&audio.getAttribute('src')&&loadedSignature===payload.signature){`;

const RESTORE_OLD = `      if(payload){
        if(saved.signature&&payload.signature!==saved.signature)return;
        if(audio.getAttribute('src')){`;
const RESTORE_NEW = `      if(payload){
        if(saved.signature&&payload.signature!==saved.signature)return;
        if(saved.cfi){
          try{await safeDisplay(saved.cfi);await delay(140);buildAlignment(true);}catch{}
        }
        window.__r3AudioResumeV23Debug={savedId:saved.id,savedTime:Number(saved.time)||0,savedCfi:saved.cfi||'',displayedCfi:saved.cfi||'',currentCfi:(bridge()&&typeof bridge().current==='function'&&bridge().current()&&bridge().current().start&&bridge().current().start.cfi)||''};
        if(audio.getAttribute('src')){`;

const RESTORE_SRC_OLD = `          currentId=saved.id;loadedSignature=payload.signature;
          audio.src=state.mediaUrl;`;
const RESTORE_SRC_NEW = `          currentId=saved.id;loadedSignature=payload.signature;
          try{audio.dataset.r3AudioId=saved.id;}catch{}
          audio.src=state.mediaUrl;`;

const RESTORE_EXISTING_OLD = `          currentId=idFromAudio()||saved.id;
          loadedSignature=payload.signature;`;
const RESTORE_EXISTING_NEW = `          currentId=idFromAudio()||saved.id;
          try{audio.dataset.r3AudioId=currentId;}catch{}
          loadedSignature=payload.signature;`;

const PREP_ID_OLD = `      currentId=state.id||'';
      if(!currentId)throw new Error('AUDIO_ID_MISSING');`;
const PREP_ID_NEW = `      currentId=state.id||'';
      if(!currentId)throw new Error('AUDIO_ID_MISSING');
      try{audio.dataset.r3AudioId=currentId;}catch{}`;

const ID_RAW_OLD = `      const raw=audio.currentSrc||audio.getAttribute('src')||'';
      if(!raw)return '';`;
const ID_RAW_NEW = `      const datasetId=audio.dataset&&audio.dataset.r3AudioId||'';
      if(datasetId)return datasetId;
      const raw=audio.currentSrc||audio.getAttribute('src')||'';
      if(!raw)return '';`;

const MARKER_OLD = `  window.__r3AudioWordIndexFollowV22=true;`;
const MARKER_NEW = `  window.__r3AudioWordIndexFollowV22=true;
  window.__r3AudioResumeCfiIdV23=true;`;

function replaceOnce(source,needle,replacement,label){
  const first=source.indexOf(needle);
  if(first<0)throw new Error(`READER_V23_PATCH_MISSING:${label}`);
  if(source.indexOf(needle,first+needle.length)>=0)throw new Error(`READER_V23_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0,first)+replacement+source.slice(first+needle.length);
}
function replaceAllCount(source,needle,replacement,label,minCount=1){
  const parts=source.split(needle);
  const count=parts.length-1;
  if(count<minCount)throw new Error(`READER_V23_PATCH_MISSING:${label}:${count}`);
  return parts.join(replacement);
}

function patchResumeCfiId(html){
  let out=String(html||'');
  if(out.includes('window.__r3AudioResumeCfiIdV23=true'))return out;
  out=replaceOnce(out,HANDLE_OLD,HANDLE_NEW,'handleCurrentIdFallback');
  out=replaceOnce(out,RESTORE_OLD,RESTORE_NEW,'restoreCfi');
  out=replaceOnce(out,RESTORE_EXISTING_OLD,RESTORE_EXISTING_NEW,'restoreExistingDatasetId');
  out=replaceOnce(out,RESTORE_SRC_OLD,RESTORE_SRC_NEW,'restoreNewDatasetId');
  out=replaceOnce(out,PREP_ID_OLD,PREP_ID_NEW,'prepareDatasetId');
  out=replaceAllCount(out,ID_RAW_OLD,ID_RAW_NEW,'idDatasetFirst',1);
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
      const updated=patchResumeCfiId(await response.text());
      const headers=new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag",ROBOTS);
      headers.set("X-R3-Reader-Runtime","v23-resume-cfi-media-id");
      headers.set("X-R3-Reader-Patch-Proof","v22+v23:current-id-fallback+saved-cfi+dataset-id");
      return new Response(updated,{status:200,headers});
    }catch(error){
      return new Response('Reader runtime v23 patch failed',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store','X-R3-Reader-Runtime':'v23-patch-failed','X-R3-Reader-Patch-Error':String(error&&error.message||error).slice(0,180)}});
    }
  },
  async scheduled(controller,env,ctx){if(typeof app.scheduled==="function")return app.scheduled(controller,env,ctx);},
};
