import app from "./artifact-library-reader-v24-resume-wait-match-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const HANDLE_OLD = `    const id=idFromAudio()||currentId;
    if(id&&audio.getAttribute('src')&&loadedSignature===payload.signature){
      currentId=id;
      if(!timingWords.length){try{const state=await readState(id);if(state.status==='ready')await loadTiming(state,payload.signature);}catch{}}
      buildAlignment(false);`;

const HANDLE_NEW = `    const id=idFromAudio()||currentId;
    const savedResume=savedState();
    const resumeMatches=Boolean(savedResume&&savedResume.id===id&&savedResume.signature===payload.signature);
    if(id&&audio.getAttribute('src')&&(loadedSignature===payload.signature||resumeMatches)){
      currentId=id;
      try{audio.dataset.r3AudioId=id;}catch{}
      if(resumeMatches&&loadedSignature!==payload.signature){
        if(savedResume.cfi){
          try{await safeDisplay(savedResume.cfi);await delay(140);}catch{}
        }
        try{
          const state=await readState(id);
          if(state.status==='ready')await loadTiming(state,payload.signature);
        }catch{}
        loadedSignature=payload.signature;
        const resumeTime=Math.max(0,Number(savedResume.time)||0);
        if(resumeTime>0.2&&Math.abs((Number(audio.currentTime)||0)-resumeTime)>.8){
          await waitMetadata();
          try{audio.currentTime=Math.min(resumeTime,Math.max(0,(Number(audio.duration)||resumeTime)-.05));}catch{}
        }
        buildAlignment(true);
        window.__r3AudioReuseV25Debug={id,resumeTime,cfi:savedResume.cfi||'',currentCfi:(bridge()&&typeof bridge().current==='function'&&bridge().current()&&bridge().current().start&&bridge().current().start.cfi)||'',loadedSignature};
      }else if(!timingWords.length){try{const state=await readState(id);if(state.status==='ready')await loadTiming(state,payload.signature);}catch{}}
      buildAlignment(false);`;

const MARKER_OLD = `  window.__r3AudioResumeWaitMatchV24=true;`;
const MARKER_NEW = `  window.__r3AudioResumeWaitMatchV24=true;
  window.__r3AudioReuseRestoredMediaV25=true;`;

function replaceOnce(source, needle, replacement, label) {
  const first = source.indexOf(needle);
  if (first < 0) throw new Error(`READER_V25_PATCH_MISSING:${label}`);
  if (source.indexOf(needle, first + needle.length) >= 0) throw new Error(`READER_V25_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0, first) + replacement + source.slice(first + needle.length);
}

function patchReuseRestoredMedia(html) {
  let out = String(html || '');
  if (out.includes('window.__r3AudioReuseRestoredMediaV25=true')) return out;
  out = replaceOnce(out, HANDLE_OLD, HANDLE_NEW, 'reuseRestoredMedia');
  out = replaceOnce(out, MARKER_OLD, MARKER_NEW, 'marker');
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html") || response.status !== 200) return response;
    try {
      const updated = patchReuseRestoredMedia(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-Runtime", "v25-reuse-restored-media");
      headers.set("X-R3-Reader-Patch-Proof", "v24+v25:saved-signature-media-reuse-before-hydration");
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v25 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v25-patch-failed',
          'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 180),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
