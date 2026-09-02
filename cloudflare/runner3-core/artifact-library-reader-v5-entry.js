import app from "./artifact-library-reader-v4-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function patchLiveReflow(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-live-reflow-v5="1"')) return html;

  let out = html;
  const viewerCss = '#viewer{position:absolute;inset:0;background:var(--bg);overflow:hidden;touch-action:pan-y}';
  const viewerCssFixed = '#viewer{position:absolute;inset:0;left:var(--r3-reader-edge,0px);right:var(--r3-reader-edge,0px);background:var(--bg);overflow:hidden;touch-action:pan-y}';
  out = out.replace(viewerCss, viewerCssFixed);

  const oldApply = `function applyReaderSettings(){
    syncUi();
    if(!rendition)return;
    rendition.themes.select(theme);
    rendition.themes.fontSize(font+'%');
    rendition.themes.override('line-height',String(line),true);
    rendition.themes.override('padding-left',margin+'%',true);
    rendition.themes.override('padding-right',margin+'%',true);
    rendition.themes.override('margin-left','0',true);
    rendition.themes.override('margin-right','0',true);
  }`;

  const newApply = `let r3ReflowTimer=0,r3ReflowSeq=0;
  function r3CurrentCfi(){
    try{
      const loc=rendition&&rendition.currentLocation&&rendition.currentLocation();
      return loc&&loc.start&&loc.start.cfi?loc.start.cfi:null;
    }catch{return null;}
  }
  function r3ApplyViewportMargin(){
    const viewer=$('viewer');
    if(!viewer)return;
    const edge=Math.max(8,Math.round(window.innerWidth*(margin/100)));
    viewer.style.setProperty('--r3-reader-edge',edge+'px');
  }
  function r3ScheduleReflow(anchor){
    clearTimeout(r3ReflowTimer);
    const seq=++r3ReflowSeq;
    r3ReflowTimer=setTimeout(async()=>{
      if(seq!==r3ReflowSeq||!rendition)return;
      const viewer=$('viewer');
      if(!viewer)return;
      try{rendition.resize(viewer.clientWidth,viewer.clientHeight);}catch{}
      if(anchor){
        try{await rendition.display(anchor);}catch{}
      }
    },90);
  }
  function applyReaderSettings(){
    syncUi();
    r3ApplyViewportMargin();
    if(!rendition)return;
    const anchor=r3CurrentCfi();
    rendition.themes.select(theme);
    rendition.themes.fontSize(font+'%');
    rendition.themes.override('line-height',String(line),true);
    // Never alter page geometry inside the EPUB columns. Margin belongs to the outer reader viewport.
    rendition.themes.override('padding-left','0',true);
    rendition.themes.override('padding-right','0',true);
    rendition.themes.override('margin-left','0',true);
    rendition.themes.override('margin-right','0',true);
    // During initial boot, rendition.display(savedCFI) owns pagination exclusively.
    // Reflow is only allowed after the base reader has declared BOOT_DONE.
    if(window.__R3_BASE_READER_BOOT_DONE&&anchor)r3ScheduleReflow(anchor);
  }`;

  if (out.includes(oldApply)) out = out.replace(oldApply, newApply);

  const marker = '<script data-r3-live-reflow-v5="1">document.documentElement.dataset.r3LiveReflowV5="1";</script>';
  out = out.replace('</body>', marker + '</body>');
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;
    const original = await response.text();
    const updated = patchLiveReflow(original);
    const h = new Headers(response.headers);
    h.delete("Content-Length");
    h.set("X-Robots-Tag", ROBOTS);
    return new Response(updated, { status: response.status, headers: h });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
