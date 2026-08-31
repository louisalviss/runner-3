import app from "./artifact-library-reader-v23-resume-cfi-id-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const SIGNATURE_OLD = `        if(saved.signature&&payload.signature!==saved.signature)return;`;
const SIGNATURE_NEW = `        if(saved.signature&&payload.signature!==saved.signature){
          window.__r3AudioResumeWaitV24Debug={phase:'signature-wait',savedSignature:saved.signature,currentSignature:payload.signature,attempt:n};
          await delay(150);
          continue;
        }`;

const MARKER_OLD = `  window.__r3AudioResumeCfiIdV23=true;`;
const MARKER_NEW = `  window.__r3AudioResumeCfiIdV23=true;
  window.__r3AudioResumeWaitMatchV24=true;`;

function replaceOnce(source, needle, replacement, label) {
  const first = source.indexOf(needle);
  if (first < 0) throw new Error(`READER_V24_PATCH_MISSING:${label}`);
  if (source.indexOf(needle, first + needle.length) >= 0) throw new Error(`READER_V24_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0, first) + replacement + source.slice(first + needle.length);
}

function patchResumeWaitMatch(html) {
  let out = String(html || '');
  if (out.includes('window.__r3AudioResumeWaitMatchV24=true')) return out;
  out = replaceOnce(out, SIGNATURE_OLD, SIGNATURE_NEW, 'signatureWait');
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
      const updated = patchResumeWaitMatch(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-Runtime", "v24-resume-wait-match");
      headers.set("X-R3-Reader-Patch-Proof", "v23+v24:wait-matching-signature-before-restore");
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v24 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v24-patch-failed',
          'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 180),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
