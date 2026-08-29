import app from "./reader-media-entry.js";

const POLL_HARDEN_VERSION = "rss-audio-poll-adaptive-v1";
const LEARNING_THRESHOLD_VERSION = "rss-deep-read-adaptive-v2";

const ADAPTIVE_POLL = `  function pollSleep(ms){return new Promise(function(resolve){setTimeout(resolve,ms)})}
  async function poll(view){
    var serial=++pollSerial;
    var attempt=0;
    var delays=[2000,3000,5000,8000,13000,21000,30000];
    try{
      while(!stopped&&serial===pollSerial){
        if(currentView()!==view)return;
        if(document.visibilityState==='hidden'){
          await pollSleep(30000);
          continue;
        }
        var info=await readState('GET',view);
        var status=String(info.status||'missing');
        if(status==='ready'){
          if(rememberReady(info,view))state('Nam Minh · sẵn sàng · bấm ▶');
          else state('Audio lỗi · thiếu URL');
          return;
        }
        if(status==='error')throw new Error(info.error||'Không thể tạo audio');
        state(status==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');
        var delay=delays[Math.min(attempt,delays.length-1)];
        attempt+=1;
        await pollSleep(delay);
      }
    }catch(error){
      if(!stopped&&serial===pollSerial){
        state('Audio lỗi');
        toast(error&&error.message?error.message:'Không tạo được audio');
      }
    }
  }
`;

function hardenNamMinhPolling(html) {
  let source = String(html || "");
  let changed = 0;

  const declaration = "  var polling=false;\n  var stopped=false;";
  if (source.includes(declaration)) {
    source = source.replace(declaration, "  var stopped=false;\n  var pollSerial=0;");
    changed += 1;
  }

  const pollStart = source.indexOf("  async function poll(view){");
  const pollEnd = pollStart >= 0 ? source.indexOf("  async function resolveStateFromTap(view){", pollStart) : -1;
  if (pollStart >= 0 && pollEnd > pollStart) {
    source = source.slice(0, pollStart) + ADAPTIVE_POLL + source.slice(pollEnd);
    changed += 1;
  }

  const refreshMarker = "  async function refresh(){\n    var view=currentView();\n";
  if (source.includes(refreshMarker)) {
    source = source.replace(refreshMarker, "  async function refresh(){\n    pollSerial+=1;\n    var view=currentView();\n");
    changed += 1;
  }

  const pagehide = "window.addEventListener('pagehide',function(){stopped=true;resetMedia()});";
  if (source.includes(pagehide)) {
    source = source.replace(pagehide, "window.addEventListener('pagehide',function(){stopped=true;pollSerial+=1;resetMedia()});");
    changed += 1;
  }

  return { html: source, applied: changed === 4, changed };
}

function adaptDeepReadThreshold(html) {
  let source = String(html || "");
  let changed = 0;
  if (source.includes('rssDeepRead:v1:')) {
    source = source.replace('rssDeepRead:v1:', 'rssDeepRead:v2:');
    changed += 1;
  }
  const activity = 'var activeMs=0,last=Date.now(),maxDepth=0;';
  if (source.includes(activity)) {
    source = source.replace(activity,
      'var activeMs=0,last=Date.now(),maxDepth=0;var words=Math.max(1,String((document.querySelector("main")||document.body||{}).innerText||"").trim().split(/\\s+/).length);var estimatedMs=words/220*60000;var needMs=Math.max(25000,Math.min(90000,estimatedMs*0.35));var depthNeed=words<600?0.70:(words>1800?0.45:0.55);var audioNeed=Math.max(30000,Math.min(90000,estimatedMs*0.25));');
    changed += 1;
  }
  const mark = 'var listened=!!(audio&&Number(audio.currentTime||0)>=45);if(activeMs<45000||(maxDepth<0.55&&!listened))return;';
  if (source.includes(mark)) {
    source = source.replace(mark, 'var listened=!!(audio&&Number(audio.currentTime||0)*1000>=audioNeed);if(activeMs<needMs||(maxDepth<depthNeed&&!listened))return;');
    changed += 1;
  }
  return { html: source, applied: changed === 3, changed };
}

function isReaderArticleHtml(request, url, response) {
  if (request.method !== "GET") return false;
  if (!/^\/rss\/article\/[^/]+$/.test(url.pathname)) return false;
  return String(response?.headers?.get("content-type") || "").includes("text/html");
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (!response || !isReaderArticleHtml(request, url, response)) return response;

    const poll = hardenNamMinhPolling(await response.text());
    const learning = adaptDeepReadThreshold(poll.html);
    const headers = new Headers(response.headers);
    headers.delete("content-length");
    headers.set("cache-control", "no-store");
    headers.set("content-type", "text/html; charset=utf-8");
    headers.set("x-rss-audio-poll", poll.applied ? POLL_HARDEN_VERSION : `legacy-markers-${poll.changed}`);
    headers.set("x-rss-learning-threshold", learning.applied ? LEARNING_THRESHOLD_VERSION : `legacy-markers-${learning.changed}`);
    if (!poll.applied) console.warn("rss audio adaptive poll markers incomplete", poll.changed);
    if (!learning.applied) console.warn("rss learning adaptive threshold markers incomplete", learning.changed);

    return new Response(learning.html, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
