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

const STATUS_GUARD = `<script data-r3-audio-media-state-guard-v29="1">
(()=>{
  if(window.__r3AudioMediaStateGuardV29)return;
  window.__r3AudioMediaStateGuardV29=true;
  const audio=document.getElementById('r3AudioElement');
  const main=document.getElementById('r3AudioMain');
  const status=document.getElementById('r3AudioStatus');
  if(!audio||!main||!status)return;
  const set=text=>{status.textContent=String(text||'Nam Minh').slice(0,120);};
  const playUi=()=>{main.textContent='Ⅱ';main.disabled=false;main.setAttribute('aria-label','Tạm dừng audio');};
  const pauseUi=()=>{main.textContent='▶';main.disabled=false;main.setAttribute('aria-label','Phát audio');};
  audio.addEventListener('loadedmetadata',()=>{if(audio.getAttribute('src')&&!audio.ended)set('Nam Minh · sẵn sàng');});
  audio.addEventListener('playing',()=>{playUi();set('Nam Minh · đang phát');});
  audio.addEventListener('play',()=>{playUi();set('Nam Minh · đang phát');});
  audio.addEventListener('pause',()=>{if(!audio.ended){pauseUi();set('Nam Minh · tạm dừng');}});
  audio.addEventListener('ended',()=>{pauseUi();set('Nam Minh · đã hết đoạn');});
})();
</script>`;

function replaceOnce(source, needle, replacement, label) {
  const first = source.indexOf(needle);
  if (first < 0) throw new Error(`READER_V29_PATCH_MISSING:${label}`);
  if (source.indexOf(needle, first + needle.length) >= 0) throw new Error(`READER_V29_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0, first) + replacement + source.slice(first + needle.length);
}

function patchMediaStateGuard(html) {
  let out = String(html || '');
  if (out.includes('data-r3-audio-media-state-guard-v29="1"')) return out;
  out = replaceOnce(out, NO_PAYLOAD_OLD, NO_PAYLOAD_NEW, 'noPayloadMediaGuard');
  if (!out.includes('</body>')) throw new Error('READER_V29_BODY_MARKER_MISSING');
  out = out.replace('</body>', STATUS_GUARD + '</body>');
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
