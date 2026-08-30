import app from "./artifact-library-reader-v16-outer-viewport-geometry-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const MARKER_NEEDLE = `  window.__r3AudioOuterGeometryV16=true;\n`;
const MARKER_PATCH = `  window.__r3AudioOuterGeometryV16=true;
  window.__r3AudioFrozenViewportV17=true;
  function captureViewportAnchorV17(){
    const payload=framePayload();
    if(!payload)return null;
    try{
      const rows=collectBlocks(payload);
      for(let bi=0;bi<rows.length;bi++){
        const items=tokenRangesForElement(rows[bi]);
        for(let ti=0;ti<items.length;ti++){
          if(!rangeVisibleExact(items[ti].range))continue;
          return {
            signature:payload.signature,
            doc:payload.doc,
            el:rows[bi],
            blockIndex:bi,
            tokenIndex:ti,
            token:items[ti].token||'',
            cfi:cfiForRange(items[ti].range)||cfiForNode(rows[bi])||''
          };
        }
      }
    }catch{}
    return null;
  }
  function secondsForFrozenAnchorV17(anchor){
    if(!anchor||!timingWords.length)return NaN;
    const payload=framePayload();
    if(!payload||payload.signature!==anchor.signature)return NaN;
    if(activeDoc!==payload.doc||activeSignature!==payload.signature)buildAlignment(true);
    let row=blockRanges.find(item=>item.el===anchor.el)||null;
    if(!row&&Number.isInteger(anchor.blockIndex))row=blockRanges[anchor.blockIndex]||null;
    if(!row)return NaN;
    const exact=exactMapForRow(row);
    if(!exact||!exact.items.length)return NaN;
    let index=Math.max(0,Math.min(Number(anchor.tokenIndex)||0,exact.items.length-1));
    if(anchor.token&&exact.items[index]&&exact.items[index].token!==anchor.token){
      const start=Math.max(0,index-12),end=Math.min(exact.items.length-1,index+12);
      let found=-1;
      for(let i=start;i<=end;i++)if(exact.items[i]&&exact.items[i].token===anchor.token){found=i;break;}
      if(found>=0)index=found;
    }
    const wi=nearestMappedWord(exact.mapped,index);
    if(wi===null)return NaN;
    return Math.max(0,(Number(timingWords[wi]&&timingWords[wi].startMs)||0)/1000);
  }
`;

const PREPARE_START_NEEDLE = `  async function prepareCurrentChapter(payload,visible){\n    const seq=++requestSeq;`;
const PREPARE_START_PATCH = `  async function prepareCurrentChapter(payload,visible){
    const frozenViewportV17=captureViewportAnchorV17();
    window.__r3AudioAnchorApplyingV17=true;
    const seq=++requestSeq;`;

const PREPARE_TARGET_NEEDLE = `      const exactVisible=firstVisibleTokenTarget();
      const freshVisible=firstVisibleRange()||visible;
      const target=exactVisible&&Number.isFinite(exactVisible.seconds)?exactVisible.seconds:startSecondsForRange(freshVisible);
      try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}
      await audio.play();`;
const PREPARE_TARGET_PATCH = `      const frozenTargetV17=secondsForFrozenAnchorV17(frozenViewportV17);
      const exactVisible=firstVisibleTokenTarget();
      const freshVisible=firstVisibleRange()||visible;
      const target=Number.isFinite(frozenTargetV17)?frozenTargetV17:(exactVisible&&Number.isFinite(exactVisible.seconds)?exactVisible.seconds:startSecondsForRange(freshVisible));
      try{audio.currentTime=Math.min(target,Math.max(0,(Number(audio.duration)||target)-.05));}catch{}
      if(frozenViewportV17&&frozenViewportV17.cfi){
        try{await safeDisplay(frozenViewportV17.cfi);await delay(70);buildAlignment(true);}catch{}
      }
      window.__r3AudioAnchorApplyingV17=false;
      await audio.play();`;

const SAVE_NEEDLE = `  function saveState(force=false){\n    const now=Date.now();`;
const SAVE_PATCH = `  function saveState(force=false){
    if(window.__r3AudioAnchorApplyingV17)return;
    const now=Date.now();`;

const FINALLY_NEEDLE = `    }finally{if(seq===requestSeq)busy=false;}\n  }`;
const FINALLY_PATCH = `    }finally{window.__r3AudioAnchorApplyingV17=false;if(seq===requestSeq)busy=false;}\n  }`;

function patchFrozenViewportAnchor(html) {
  let out = html;
  if (out.includes(MARKER_NEEDLE) && !out.includes("window.__r3AudioFrozenViewportV17=true")) out = out.replace(MARKER_NEEDLE, MARKER_PATCH);
  if (out.includes(PREPARE_START_NEEDLE)) out = out.replace(PREPARE_START_NEEDLE, PREPARE_START_PATCH);
  if (out.includes(PREPARE_TARGET_NEEDLE)) out = out.replace(PREPARE_TARGET_NEEDLE, PREPARE_TARGET_PATCH);
  if (out.includes(SAVE_NEEDLE)) out = out.replace(SAVE_NEEDLE, SAVE_PATCH);
  if (out.includes(FINALLY_NEEDLE)) out = out.replace(FINALLY_NEEDLE, FINALLY_PATCH);
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
    const updated = patchFrozenViewportAnchor(original);
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v17-frozen-viewport-anchor");
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
