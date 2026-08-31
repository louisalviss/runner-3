import app from "./artifact-library-reader-v28-prime-base-position-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

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
  const hasUsableFrame=()=>{
    for(const frame of document.querySelectorAll('#viewer iframe')){
      try{if(String(frame.contentDocument?.body?.innerText||'').trim().length>=80)return true;}catch{}
    }
    return false;
  };
  const validMedia=()=>Boolean(audio.getAttribute('src')&&(audio.currentSrc||audio.getAttribute('src')));

  // Window capture runs before the older document-capture handlers. Only own the click
  // when the current EPUB page is sparse/unreadable but a valid media source already exists.
  window.addEventListener('click',event=>{
    const target=event.target&&event.target.closest?event.target.closest('#r3AudioMain'):null;
    if(!target||!validMedia()||hasUsableFrame())return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const duration=Number(audio.duration)||0;
    const atEnd=Boolean(audio.ended||(duration>0&&(Number(audio.currentTime)||0)>=duration-.08));
    if(atEnd){pauseUi();set('Nam Minh · đã hết đoạn');return;}
    if(!audio.paused){audio.pause();pauseUi();set('Nam Minh · tạm dừng');return;}
    audio.play().then(()=>{playUi();set('Nam Minh · đang phát');}).catch(()=>{pauseUi();set('Nam Minh · nhấn phát lại');});
  },true);

  audio.addEventListener('loadedmetadata',()=>{if(validMedia()&&!audio.ended)set('Nam Minh · sẵn sàng');});
  audio.addEventListener('playing',()=>{playUi();set('Nam Minh · đang phát');});
  audio.addEventListener('play',()=>{playUi();set('Nam Minh · đang phát');});
  audio.addEventListener('pause',()=>{if(!audio.ended){pauseUi();set('Nam Minh · tạm dừng');}});
  audio.addEventListener('ended',()=>{pauseUi();set('Nam Minh · đã hết đoạn');});
})();
</script>`;

function patchMediaStateGuard(html) {
  const out = String(html || '');
  if (out.includes('data-r3-audio-media-state-guard-v29="1"')) return out;
  if (!out.includes('</body>')) throw new Error('READER_V29_BODY_MARKER_MISSING');
  return out.replace('</body>', STATUS_GUARD + '</body>');
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
      headers.set("X-R3-Reader-Patch-Proof", "v28+v29:sparse-page-valid-media-window-capture");
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
