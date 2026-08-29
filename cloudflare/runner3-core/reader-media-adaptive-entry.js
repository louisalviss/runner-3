import app from "./reader-media-entry.js";

const POLL_HARDEN_VERSION = "rss-audio-poll-adaptive-v1";

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
    source = source.replace(
      refreshMarker,
      "  async function refresh(){\n    pollSerial+=1;\n    var view=currentView();\n",
    );
    changed += 1;
  }

  const pagehide = "window.addEventListener('pagehide',function(){stopped=true;resetMedia()});";
  if (source.includes(pagehide)) {
    source = source.replace(
      pagehide,
      "window.addEventListener('pagehide',function(){stopped=true;pollSerial+=1;resetMedia()});",
    );
    changed += 1;
  }

  return { html: source, applied: changed === 4, changed };
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

    const result = hardenNamMinhPolling(await response.text());
    const headers = new Headers(response.headers);
    headers.delete("content-length");
    headers.set("cache-control", "no-store");
    headers.set("content-type", "text/html; charset=utf-8");
    headers.set("x-rss-audio-poll", result.applied ? POLL_HARDEN_VERSION : `legacy-markers-${result.changed}`);
    if (!result.applied) console.warn("rss audio adaptive poll markers incomplete", result.changed);

    return new Response(result.html, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
