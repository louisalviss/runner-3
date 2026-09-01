import app from "./artifact-library-reader-v29-media-state-guard-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const HIGHLIGHT_SCRIPT = `<script data-r3-audio-dark-highlight-v30="1">
(()=>{
  if(window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER){
    window.__r3AudioDarkHighlightV30Suppressed=true;
    return;
  }
  if(window.__r3AudioDarkHighlightV30)return;
  window.__r3AudioDarkHighlightV30=true;
  const STYLE_ID='r3AudioDarkHighlightV30Style';
  const css='[data-r3-audio-reading-v11="1"]{font-weight:900!important;border-radius:5px!important;box-shadow:inset 3px 0 0 rgba(132,92,10,.72)!important;background:rgba(226,176,55,.13)!important}[data-r3-audio-reading-v11="1"] *{font-weight:900!important}:root[data-r3-outer-theme="dark"] [data-r3-audio-reading-v11="1"]{background:rgba(255,211,92,.22)!important;box-shadow:inset 3px 0 0 rgba(255,226,138,.96)!important;outline:1px solid rgba(255,226,138,.16)!important}:root[data-r3-outer-theme="brown"] [data-r3-audio-reading-v11="1"]{background:rgba(123,76,28,.12)!important;box-shadow:inset 3px 0 0 rgba(123,76,28,.75)!important}';
  const theme=()=>String(document.body&&document.body.dataset&&document.body.dataset.theme||'light');
  function install(doc){
    if(!doc||!doc.documentElement)return;
    try{
      doc.documentElement.dataset.r3OuterTheme=theme();
      let style=doc.getElementById(STYLE_ID);
      if(!style){style=doc.createElement('style');style.id=STYLE_ID;style.textContent=css;(doc.head||doc.documentElement).appendChild(style);}
    }catch{}
  }
  function sync(){
    for(const frame of document.querySelectorAll('#viewer iframe')){try{install(frame.contentDocument);}catch{}}
    try{for(const content of window.r3ReaderBridge?.contents?.()||[])install(content&&content.document);}catch{}
  }
  const themeObserver=new MutationObserver(sync);
  if(document.body)themeObserver.observe(document.body,{attributes:true,attributeFilter:['data-theme']});
  const viewer=document.getElementById('viewer');
  if(viewer)new MutationObserver(sync).observe(viewer,{childList:true,subtree:true});
  sync();
  let ticks=0;
  const timer=setInterval(()=>{sync();if(++ticks>120)clearInterval(timer);},500);
  window.addEventListener('pagehide',()=>{clearInterval(timer);themeObserver.disconnect();},{once:true});
})();
</script>`;

function patchDarkHighlight(html) {
  const out = String(html || '');
  if (out.includes('data-r3-audio-dark-highlight-v30="1"')) return out;
  if (!out.includes('</body>')) throw new Error('READER_V30_BODY_MARKER_MISSING');
  return out.replace('</body>', HIGHLIGHT_SCRIPT + '</body>');
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html") || response.status !== 200) return response;
    try {
      const updated = patchDarkHighlight(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-Runtime", "v30-dark-highlight");
      headers.set("X-R3-Reader-Patch-Proof", "v29+v30:dark-active-passage-contrast-no-layout");
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v30 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v30-patch-failed',
          'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 180),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
