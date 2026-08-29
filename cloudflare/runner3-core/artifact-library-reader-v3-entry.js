import app from "./artifact-library-reader-v2-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function headers(base = {}) {
  const h = new Headers(base);
  h.set("X-Robots-Tag", ROBOTS);
  h.set("Cache-Control", "private, no-store, max-age=0");
  h.set("Pragma", "no-cache");
  h.set("Referrer-Policy", "no-referrer");
  h.set("X-Frame-Options", "DENY");
  return h;
}

function injectReliableTouchLayer(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-touch-layer-v3="1"')) return html;

  const patch = `<style data-r3-touch-layer-v3="1">
#r3GestureLayer{position:fixed;inset:0;z-index:8;background:transparent;pointer-events:auto;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
body.settings #r3GestureLayer{pointer-events:none}
body.controls .topbar,body.controls .bottom-status{z-index:21}
</style>
<div id="r3GestureLayer" aria-hidden="true"></div>
<script data-r3-touch-layer-v3="1">
(()=>{
  const layer=document.getElementById('r3GestureLayer');
  if(!layer)return;
  let sx=0,sy=0,st=0,moved=false,lastTouch=0,hideTimer=0;

  const navMode=()=>document.body.dataset.nav==='tap'?'tap':'swipe';
  const fireKey=key=>document.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true}));
  const prev=()=>fireKey('ArrowLeft');
  const next=()=>fireKey('ArrowRight');

  function clearHide(){if(hideTimer){clearTimeout(hideTimer);hideTimer=0;}}
  function hideControls(){clearHide();document.body.classList.remove('controls','settings');}
  function scheduleHide(){clearHide();if(document.body.classList.contains('controls')&&!document.body.classList.contains('settings'))hideTimer=setTimeout(hideControls,3000);}
  function showControls(){document.body.classList.add('controls');scheduleHide();}
  function toggleControls(){
    if(document.body.classList.contains('settings'))return;
    if(document.body.classList.contains('controls'))hideControls();else showControls();
  }

  function actTap(x){
    const ratio=x/Math.max(1,window.innerWidth);
    if(navMode()==='tap'){
      if(ratio<.33){prev();hideControls();return;}
      if(ratio>.67){next();hideControls();return;}
    }
    if(ratio>=.33&&ratio<=.67)toggleControls();
  }

  layer.addEventListener('touchstart',e=>{
    const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
    sx=t.clientX;sy=t.clientY;st=Date.now();moved=false;
  },{passive:true});

  layer.addEventListener('touchmove',e=>{
    const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
    if(Math.abs(t.clientX-sx)>8||Math.abs(t.clientY-sy)>8)moved=true;
    if(e.cancelable)e.preventDefault();
  },{passive:false});

  layer.addEventListener('touchend',e=>{
    const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
    lastTouch=Date.now();
    const dx=t.clientX-sx,dy=t.clientY-sy,dt=Date.now()-st;
    if(navMode()==='swipe'&&Math.abs(dx)>=34&&Math.abs(dx)>Math.abs(dy)*1.05){
      if(e.cancelable)e.preventDefault();
      dx<0?next():prev();hideControls();return;
    }
    if(Math.abs(dx)<20&&Math.abs(dy)<20&&dt<700)actTap(t.clientX);
  },{passive:false});

  layer.addEventListener('click',e=>{
    if(Date.now()-lastTouch<800)return;
    actTap(e.clientX);
  });

  // Keep this fallback timer authoritative even when v2 controls are shown by other handlers.
  const observer=new MutationObserver(()=>{
    if(document.body.classList.contains('settings'))clearHide();
    else if(document.body.classList.contains('controls'))scheduleHide();
    else clearHide();
  });
  observer.observe(document.body,{attributes:true,attributeFilter:['class']});

  window.addEventListener('beforeunload',()=>{clearHide();observer.disconnect();},{once:true});
})();
</script>`;

  return html.replace("</body>", patch + "</body>");
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;
    const original = await response.text();
    const updated = injectReliableTouchLayer(original);
    const h = new Headers(response.headers);
    h.delete("Content-Length");
    h.set("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; font-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
    return new Response(updated, { status: response.status, headers: h });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
