import app from "./artifact-library-reader-v15-viewport-word-sync-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const BLOCK_VISIBLE_NEEDLE = `  function blockVisible(el){
    try{
      const doc=el.ownerDocument,win=doc.defaultView;
      const w=win&&win.innerWidth||doc.documentElement.clientWidth||1;
      const h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      const rects=[...el.getClientRects()];
      return rects.some(rect=>rectVisible(rect,w,h));
    }catch{return false;}
  }
`;

const BLOCK_VISIBLE_PATCH = `  function outerRectVisible(rect,doc){
    try{
      if(!rect||!doc)return false;
      const payload=framePayload();
      const frame=payload&&payload.doc===doc?payload.frame:null;
      const viewer=document.getElementById('viewer');
      if(frame&&viewer){
        const fr=frame.getBoundingClientRect(),vr=viewer.getBoundingClientRect();
        const left=fr.left+rect.left,top=fr.top+rect.top,right=fr.left+rect.right,bottom=fr.top+rect.bottom;
        return right>vr.left+2&&left<vr.right-2&&bottom>vr.top+2&&top<vr.bottom-2;
      }
      const win=doc.defaultView,w=win&&win.innerWidth||doc.documentElement.clientWidth||1,h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      return rectVisible(rect,w,h);
    }catch{return false;}
  }
  function blockVisible(el){
    try{
      const doc=el.ownerDocument;
      return [...el.getClientRects()].some(rect=>outerRectVisible(rect,doc));
    }catch{return false;}
  }
`;

const RANGE_VISIBLE_NEEDLE = `  function rangeVisibleExact(range){
    try{
      if(!range)return false;
      const doc=range.commonAncestorContainer&&range.commonAncestorContainer.ownerDocument||activeDoc;
      const win=doc&&doc.defaultView;
      const w=win&&win.innerWidth||doc.documentElement.clientWidth||1;
      const h=win&&win.innerHeight||doc.documentElement.clientHeight||1;
      return [...range.getClientRects()].some(rect=>rectVisible(rect,w,h));
    }catch{return false;}
  }
`;

const RANGE_VISIBLE_PATCH = `  function rangeVisibleExact(range){
    try{
      if(!range)return false;
      const node=range.commonAncestorContainer;
      const doc=node&&node.nodeType===9?node:node&&node.ownerDocument||activeDoc;
      return [...range.getClientRects()].some(rect=>outerRectVisible(rect,doc));
    }catch{return false;}
  }
`;

const MARKER_NEEDLE = `  window.__r3AudioViewportWordV15=true;\n`;
const MARKER_PATCH = `  window.__r3AudioViewportWordV15=true;\n  window.__r3AudioOuterGeometryV16=true;\n`;

function patchOuterViewportGeometry(html) {
  let out = html;
  if (out.includes(BLOCK_VISIBLE_NEEDLE)) out = out.replace(BLOCK_VISIBLE_NEEDLE, BLOCK_VISIBLE_PATCH);
  if (out.includes(RANGE_VISIBLE_NEEDLE)) out = out.replace(RANGE_VISIBLE_NEEDLE, RANGE_VISIBLE_PATCH);
  if (out.includes(MARKER_NEEDLE) && !out.includes("window.__r3AudioOuterGeometryV16=true")) out = out.replace(MARKER_NEEDLE, MARKER_PATCH);
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
    const updated = patchOuterViewportGeometry(original);
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v16-outer-viewport-word-geometry");
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
