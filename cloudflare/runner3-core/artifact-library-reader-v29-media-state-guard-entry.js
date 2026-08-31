import app from "./artifact-library-reader-v28-prime-base-position-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const NO_PAYLOAD_OLD = `    if(!payload){setStatus('Chưa lấy được nội dung chương');return;}`;
const NO_PAYLOAD_NEW = `    if(!payload){
      const existingId=idFromAudio()||currentId||String(audio&&audio.dataset&&audio.dataset.r3AudioId||'');
      const hasMedia=Boolean(audio&&audio.getAttribute('src'));
      if(existingId&&hasMedia){
        currentId=existingId;
        try{audio.dataset.r3AudioId=existingId;}catch{}
        const duration=Number(audio.duration)||0;
        const atEnd=Boolean(audio.ended||(duration>0&&(Number(audio.currentTime)||0)>=duration-.08));
        if(atEnd){setMain('play');setStatus('Nam Minh · đã hết đoạn');return;}
        if(!audio.paused){audio.pause();setMain('play');setStatus('Nam Minh · tạm dừng');saveState(true);return;}
        try{await audio.play();setMain('pause');setStatus('Nam Minh · đang phát');}
        catch{setMain('play');setStatus('Nam Minh · nhấn phát lại');}
        return;
      }
      setStatus('Chưa lấy được nội dung chương');
      return;
    }`;

const EVENTS_OLD = `  audio.addEventListener('loadedmetadata',()=>{enablePlaybackSession();syncReading(false);});
  audio.addEventListener('timeupdate',()=>{syncReading(false);saveState(false);});
  audio.addEventListener('seeked',()=>{syncReading(true);saveState(true);});
  audio.addEventListener('play',()=>{enablePlaybackSession();setMain('pause');syncReading(false);});
  audio.addEventListener('pause',()=>{if(!audio.ended)setMain('play');saveState(true);});
  audio.addEventListener('ended',()=>{saveState(true);clearHighlight();});`;

const EVENTS_NEW = `  audio.addEventListener('loadedmetadata',()=>{enablePlaybackSession();if(audio.getAttribute('src')&&!audio.ended)setStatus('Nam Minh · sẵn sàng');syncReading(false);});
  audio.addEventListener('timeupdate',()=>{syncReading(false);saveState(false);});
  audio.addEventListener('seeked',()=>{syncReading(true);saveState(true);});
  audio.addEventListener('play',()=>{enablePlaybackSession();setMain('pause');setStatus('Nam Minh · đang phát');syncReading(false);});
  audio.addEventListener('pause',()=>{if(!audio.ended){setMain('play');setStatus('Nam Minh · tạm dừng');}saveState(true);});
  audio.addEventListener('ended',()=>{setMain('play');setStatus('Nam Minh · đã hết đoạn');saveState(true);clearHighlight();});`;

const MARKER_OLD = `  window.__r3AudioPrimeBasePositionV28=true;`;
const MARKER_NEW = `  window.__r3AudioPrimeBasePositionV28=true;
  window.__r3AudioMediaStateGuardV29=true;`;

function replaceOnce(source, needle, replacement, label) {
  const first = source.indexOf(needle);
  if (first < 0) throw new Error(`READER_V29_PATCH_MISSING:${label}`);
  if (source.indexOf(needle, first + needle.length) >= 0) throw new Error(`READER_V29_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0, first) + replacement + source.slice(first + needle.length);
}

function patchMediaStateGuard(html) {
  let out = String(html || '');
  if (out.includes('window.__r3AudioMediaStateGuardV29=true')) return out;
  out = replaceOnce(out, NO_PAYLOAD_OLD, NO_PAYLOAD_NEW, 'noPayloadMediaGuard');
  out = replaceOnce(out, EVENTS_OLD, EVENTS_NEW, 'mediaStatusEvents');
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
      const updated = patchMediaStateGuard(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-Runtime", "v29-media-state-guard");
      headers.set("X-R3-Reader-Patch-Proof", "v28+v29:valid-media-status-guard");
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v29 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v29-patch-failed',
          'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 180),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
