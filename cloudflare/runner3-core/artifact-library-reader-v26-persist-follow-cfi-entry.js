import app from "./artifact-library-reader-v25-reuse-restored-media-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const V11_FOLLOW_OLD = `    if(moved){
      const b=bridge();if(b&&typeof b.persist==='function')try{b.persist();}catch{}
      await delay(90);
      buildAlignment(true);
      syncReading(false);
    }`;
const V11_FOLLOW_NEW = `    if(moved){
      const b=bridge();if(b&&typeof b.persist==='function')try{b.persist();}catch{}
      await delay(90);
      buildAlignment(true);
      syncReading(false);
      saveState(true);
      window.__r3AudioPersistFollowCfiV26Debug={phase:'v11-follow',cfi:(bridge()&&typeof bridge().current==='function'&&bridge().current()&&bridge().current().start&&bridge().current().start.cfi)||'',time:Number(audio.currentTime)||0};
    }`;

const V22_EARLY_OLD = `    if(rangeVisibleExact(target.range)){debug.phase='already-visible';debug.ok=true;debug.visibleAtEnd=true;return true;}`;
const V22_EARLY_NEW = `    if(rangeVisibleExact(target.range)){
      debug.phase='already-visible';debug.ok=true;debug.visibleAtEnd=true;
      if(b&&typeof b.persist==='function')try{b.persist();}catch{}
      saveState(true);
      window.__r3AudioPersistFollowCfiV26Debug={phase:'v22-already-visible',cfi:(b&&typeof b.current==='function'&&b.current()&&b.current().start&&b.current().start.cfi)||'',time:Number(audio.currentTime)||0};
      return true;
    }`;

const V22_LANDED_OLD = `      debug.afterCfi=after&&after.start&&after.start.cfi||'';debug.ok=true;debug.phase='landed';
      buildAlignment(true);
      return true;`;
const V22_LANDED_NEW = `      debug.afterCfi=after&&after.start&&after.start.cfi||'';debug.ok=true;debug.phase='landed';
      buildAlignment(true);
      saveState(true);
      window.__r3AudioPersistFollowCfiV26Debug={phase:'v22-landed',cfi:debug.afterCfi||'',time:Number(audio.currentTime)||0};
      return true;`;

const MARKER_OLD = `  window.__r3AudioReuseRestoredMediaV25=true;`;
const MARKER_NEW = `  window.__r3AudioReuseRestoredMediaV25=true;
  window.__r3AudioPersistFollowCfiV26=true;`;

function replaceOnce(source, needle, replacement, label) {
  const first = source.indexOf(needle);
  if (first < 0) throw new Error(`READER_V26_PATCH_MISSING:${label}`);
  if (source.indexOf(needle, first + needle.length) >= 0) throw new Error(`READER_V26_PATCH_AMBIGUOUS:${label}`);
  return source.slice(0, first) + replacement + source.slice(first + needle.length);
}

function patchPersistFollowCfi(html) {
  let out = String(html || '');
  if (out.includes('window.__r3AudioPersistFollowCfiV26=true')) return out;
  out = replaceOnce(out, V11_FOLLOW_OLD, V11_FOLLOW_NEW, 'v11FollowPersist');
  out = replaceOnce(out, V22_EARLY_OLD, V22_EARLY_NEW, 'v22AlreadyVisiblePersist');
  out = replaceOnce(out, V22_LANDED_OLD, V22_LANDED_NEW, 'v22LandedPersist');
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
      const updated = patchPersistFollowCfi(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-Runtime", "v26-persist-follow-cfi");
      headers.set("X-R3-Reader-Patch-Proof", "v25+v26:persist-reader-cfi-after-audio-follow");
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v26 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v26-patch-failed',
          'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 180),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
