import app from "./opportunity-router-entry.js";
import { handleRssReader } from "./src/rss-reader.js";
import { handleRssReaderPlus } from "./src/rss-reader-plus.js";
import { renderReaderArticlePageV3 } from "./src/rss-reader-page-v3.js";
import { repairGeneratedReaderHtml } from "./src/rss-reader-page-v4.js";
import { addNamMinhReaderAudio } from "./src/rss-reader-page-v5.js";
import { addNamMinhTiming } from "./src/rss-reader-page-v6.js";
import { addIsolatedNamMinhPlayer } from "./src/rss-reader-page-v8.js";

const POLL_HARDEN_VERSION = "rss-audio-poll-adaptive-v1";
const LEARNING_THRESHOLD_VERSION = "rss-deep-read-adaptive-v2";
const FASTPATH_VERSION = "rss-article-fast-v1";
const API_FASTPATH_VERSION = "rss-reader-api-fast-v2";
const READER_TOKEN_SHA256 = "a4efd86ada61ed4398ec259b7f46262f10d4e2f7fa4f123c5619eb6366d0dd18";

const READER_LEARNING_SCRIPT = '<script>(function(){' +
  'var m=String(location.pathname||"").match(/^\\/rss\\/article\\/([^/]+)$/);if(!m)return;' +
  'var id="";try{id=decodeURIComponent(m[1])}catch(e){return}' +
  'var storeKey="rssDeepRead:v1:"+id;var sent=localStorage.getItem(storeKey)==="1";' +
  'var activeMs=0,last=Date.now(),maxDepth=0;' +
  'function measure(){var d=document.documentElement,b=document.body;var h=Math.max(d?d.scrollHeight:0,b?b.scrollHeight:0,1);var y=(window.scrollY||window.pageYOffset||0)+(window.innerHeight||0);maxDepth=Math.max(maxDepth,Math.min(1,y/h));}' +
  'async function mark(){if(sent)return;var audio=document.querySelector("audio");var listened=!!(audio&&Number(audio.currentTime||0)>=45);if(activeMs<45000||(maxDepth<0.55&&!listened))return;var token=localStorage.getItem("rssReaderToken")||"";if(!token)return;sent=true;try{var r=await fetch("/reader/rss/articles/"+encodeURIComponent(id)+"/deep-read",{method:"POST",headers:{Authorization:"Bearer "+token}});if(r.ok)localStorage.setItem(storeKey,"1");else sent=false}catch(e){sent=false}}' +
  'function tick(){var now=Date.now();if(!document.hidden&&document.hasFocus())activeMs+=Math.min(5000,Math.max(0,now-last));last=now;measure();mark()}' +
  'addEventListener("scroll",measure,{passive:true});addEventListener("focus",function(){last=Date.now()});document.addEventListener("visibilitychange",function(){last=Date.now()});measure();setInterval(tick,5000);' +
  '})();</script>';

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
          else state('Audio lội · thiếu URL');
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
        state('Audio lội');
        toast(error&&error.message?error.message:'Không tạo được audio');
      }
    }
  }
`;

function injectReaderLearning(html) {
  const source = String(html || "");
  if (source.includes("rssDeepRead:v1:")) return source;
  return source.includes("</body>")
    ? source.replace("</body>", READER_LEARNING_SCRIPT + "</body>")
    : source + READER_LEARNING_SCRIPT;
}

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

function jsonFast(value, status = 200, route = "direct") {
  return Response.json(value, {
    status,
    headers: {
      "cache-control": "private, no-store",
      "x-r3-rss-api-fastpath": API_FASTPATH_VERSION,
      "x-r3-rss-api-route": route,
    },
  });
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(text ?? "")));
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function readerAuthorizedFast(request) {
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied) return false;
  return (await sha256Hex(supplied)) === READER_TOKEN_SHA256;
}

async function fastCategories(request, env, url) {
  if (request.method !== "GET" || url.pathname !== "/reader/rss/categories") return null;
  if (!env.DB) return jsonFast({ ok: false, error: "D1_NOT_BOUND" }, 503, "categories");
  if (!(await readerAuthorizedFast(request))) return jsonFast({ ok: false, error: "UNAUTHORIZED" }, 401, "categories");

  const rows = await env.DB.prepare(`
    SELECT c.name, c.keywords, c.sort_order,
           COUNT(CASE WHEN s.category = c.name THEN 1 END) AS usage
    FROM rss_reader_categories c
    LEFT JOIN rss_reader_state s ON s.category = c.name
    GROUP BY c.name, c.keywords, c.sort_order
    ORDER BY c.sort_order, lower(c.name)
  `).all();
  const categories = (rows.results || []).map((row) => ({
    name: String(row.name || "").trim(),
    keywords: String(row.keywords || "").trim(),
    sort_order: Number(row.sort_order || 100),
    usage: Number(row.usage || 0),
  })).filter((item) => item.name);
  return jsonFast({ ok: true, categories }, 200, "categories");
}

async function fastNeighbors(request, env, url) {
  if (request.method !== "GET") return null;
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/neighbors$/);
  if (!match) return null;
  if (!env.DB) return jsonFast({ ok: false, error: "D1_NOT_BOUND" }, 503, "neighbors");
  if (!(await readerAuthorizedFast(request))) return jsonFast({ ok: false, error: "UNAUTHORIZED" }, 401, "neighbors");

  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return jsonFast({ ok: false, error: "INVALID_ARTICLE_ID" }, 400, "neighbors"); }
  const current = await env.DB.prepare(`
    SELECT a.article_id, a.published_at
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE a.article_id = ? AND COALESCE(s.lifecycle, 'active') != 'deleted'
    LIMIT 1
  `).bind(articleId).first();
  if (!current) return jsonFast({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404, "neighbors");

  const publishedAt = String(current.published_at || "");
  const [previous, next] = await env.DB.batch([
    env.DB.prepare(`
      SELECT a.article_id, a.title
      FROM rss_articles a
      LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
      WHERE COALESCE(s.lifecycle, 'active') != 'deleted'
        AND (a.published_at > ? OR (a.published_at = ? AND a.article_id > ?))
      ORDER BY a.published_at ASC, a.article_id ASC
      LIMIT 1
    `).bind(publishedAt, publishedAt, articleId),
    env.DB.prepare(`
      SELECT a.article_id, a.title
      FROM rss_articles a
      LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
      WHERE COALESCE(s.lifecycle, 'active') != 'deleted'
        AND (a.published_at < ? OR (a.published_at = ? AND a.article_id < ?))
      ORDER BY a.published_at DESC, a.article_id DESC
      LIMIT 1
    `).bind(publishedAt, publishedAt, articleId),
  ]);

  return jsonFast({
    ok: true,
    previous: previous?.results?.[0] || null,
    next: next?.results?.[0] || null,
  }, 200, "neighbors");
}

function markApiFastPath(response, route) {
  if (!response) return null;
  headers = new Headers(response.headers);
  headers.set("x-r3-rss-api-fastpath", API_FASTPATH_VERSION);
  headers.set("x-r3-rss-api-route", route);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function routeReaderApiFast(request, env, url) {
  if (!url.pathname.startsWith("/reader/rss/")) return null;

  const categoriesResponse = await fastCategories(request, env, url);
  if (categoriesResponse) return categoriesResponse;

  const neighborsResponse = await fastNeighbors(request, env, url);
  if (neighborsResponse) return neighborsResponse;

  const plusResponse = await handleRssReaderPlus(request, env, url);
  if (plusResponse) return markApiFastPath(plusResponse, "plus");

  const readerResponse = await handleRssReader(request, env, url);
  if (readerResponse) return markApiFastPath(readerResponse, "core");

  return null;
}

async function renderFastArticle(request, url) {
  const response = renderReaderArticlePageV3(request, url);
  if (!response) return null;

  let html = await response.text();
  html = repairGeneratedReaderHtml(html);
  html = addNamMinhReaderAudio(html);
  html = addNamMinhTiming(html);
  html = addIsolatedNamMinhPlayer(html);
  html = injectReaderLearning(html);

  const poll = hardenNamMinhPolling(html);
  const learning = adaptDeepReadThreshold(poll.html);
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  headers.set("content-type", "text/html; charset=utf-8");
  headers.set("x-r3-rss-fastpath", FASTPATH_VERSION);
  headers.set("x-rss-audio-poll", poll.applied ? POLL_HARDEN_VERSION : `legacy-markers-${poll.changed}`);
  headers.set("x-rss-learning-threshold", learning.applied ? LEARNING_THRESHOLD_VERSION : `legacy-markers-${learning.changed}`);

  if (!poll.applied) console.warn("rss fastpath adaptive poll markers incomplete", poll.changed);
  if (!learning.applied) console.warn("rss fastpath learning markers incomplete", learning.changed);

  return new Response(learning.html, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    const apiResponse = await routeReaderApiFast(request, env, url);
    if (apiResponse) return apiResponse;

    if (request.method === "GET" && /^\/rss\/article\/[^/]+$/.test(url.pathname)) {
      const response = await renderFastArticle(request, url);
      if (response) return response;
    }
    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
