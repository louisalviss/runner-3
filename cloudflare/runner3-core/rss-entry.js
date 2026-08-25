import legacy from "./rss-wrapper.js";
import { handleRssLibrary } from "./src/rss-library.js";
import { handleRssReader } from "./src/rss-reader.js";
import { enrichFetchedArticleImages } from "./src/rss-image-enrich.js";

const BLOCKED_INCOMPLETE_SOURCE_IDS = new Set([
  "projectsyndicate-url-26a9686e21ebe4fa865d",
  "projectsyndicate-url-db223b141f372578df3c",
]);

const STRICT_READER_ARTICLE_ID = "nghiencuuquocte-url-6cd04807aefc80d9be93";

const READER_ICON_LAYER = `
<style id="reader-icon-layer">
.ui-icon{width:19px;height:19px;display:block;flex:0 0 auto;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.iconbtn,.act,.audiocontrols button{display:inline-flex!important;align-items:center;justify-content:center;gap:6px}
.navbtn span{height:22px;display:grid;place-items:center}
.navbtn .ui-icon{width:21px;height:21px}
.act .ui-icon{width:18px;height:18px}
.iconbtn .ui-icon{width:18px;height:18px}
.metric span{display:inline-flex;align-items:center;gap:6px}
.metric .ui-icon{width:16px;height:16px}
.bar a{gap:5px}
.bar a .ui-icon{width:17px;height:17px}
.act.on .ui-icon[data-icon="star"]{fill:currentColor}
.audiocontrols #playAudio .ui-icon{width:17px;height:17px}
.ui-label{font:inherit;line-height:1}
</style>
<script id="reader-icon-script">
(function(){
  var NS='http://www.w3.org/2000/svg';
  var defs={
    inbox:[['path','M4 4h16v13H4z'],['path','M4 13h4l2 3h4l2-3h4']],
    star:[['path','M12 3.7l2.5 5.05 5.57.81-4.03 3.93.95 5.55L12 16.4l-4.99 2.64.95-5.55-4.03-3.93 5.57-.81z']],
    archive:[['path','M4 7h16v13H4z'],['path','M3 4h18v3H3z'],['path','M10 11h4']],
    trash:[['path','M4 7h16'],['path','M9 7V4h6v3'],['path','M7 7l1 13h8l1-13'],['path','M10 11v5'],['path','M14 11v5']],
    up:[['path','M7 10v10H4V10z'],['path','M7 18h8.1a2 2 0 0 0 1.92-1.45l1.5-5.25A2 2 0 0 0 16.6 8.75H13l.65-3.05A2.2 2.2 0 0 0 11.5 3L7 10z']],
    down:[['path','M7 4v10H4V4z'],['path','M7 6h8.1a2 2 0 0 1 1.92 1.45l1.5 5.25a2 2 0 0 1-1.92 2.55H13l.65 3.05A2.2 2.2 0 0 1 11.5 21L7 14z']],
    sliders:[['path','M4 6h10'],['path','M18 6h2'],['circle','16','6','2'],['path','M4 12h2'],['path','M10 12h10'],['circle','8','12','2'],['path','M4 18h7'],['path','M15 18h5'],['circle','13','18','2']],
    refresh:[['path','M20 7v5h-5'],['path','M19 12a7 7 0 1 1-2-5']],
    close:[['path','M6 6l12 12'],['path','M18 6L6 18']],
    undo:[['path','M9 7H4v-5'],['path','M4 7a8 8 0 1 1 2.34 5.66']],
    play:[['path','M8 5l11 7-11 7z']],
    stop:[['path','M7 7h10v10H7z']],
    prev:[['path','M6 5v14'],['path','M18 6l-8 6 8 6z']],
    external:[['path','M14 4h6v6'],['path','M20 4l-9 9'],['path','M18 13v6H5V6h6']],
    back:[['path','M15 18l-6-6 6-6']],
    tag:[['path','M20 13l-7 7L4 11V4h7z'],['circle','8.5','8.5','1']]
  };
  function icon(name){
    var svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('ui-icon');svg.dataset.icon=name;
    var parts=defs[name]||defs.tag;
    for(var i=0;i<parts.length;i++){
      var p=parts[i],el=document.createElementNS(NS,p[0]);
      if(p[0]==='path')el.setAttribute('d',p[1]);
      else if(p[0]==='circle'){el.setAttribute('cx',p[1]);el.setAttribute('cy',p[2]);el.setAttribute('r',p[3]);}
      svg.appendChild(el);
    }
    return svg;
  }
  function decorateButton(el,name,label,text){
    if(!el||el.querySelector('svg.ui-icon'))return;
    el.textContent='';el.appendChild(icon(name));
    if(text){var s=document.createElement('span');s.className='ui-label';s.textContent=text;el.appendChild(s);}
    if(label){el.setAttribute('aria-label',label);el.title=label;}
  }
  function decorate(){
    decorateButton(document.getElementById('profileBtn'),'sliders','Gu đọc');
    decorateButton(document.getElementById('reload'),'refresh','Tải lại');
    decorateButton(document.getElementById('closeProfile'),'close','Đóng');
    var nav={active:['inbox','Inbox'],featured:['star','Nổi bật'],archived:['archive','Lưu trữ'],deleted:['trash','Đã xoá']};
    Object.keys(nav).forEach(function(k){var b=document.querySelector('.navbtn[data-view="'+k+'"] span');if(b&&!b.querySelector('svg.ui-icon')){b.textContent='';b.appendChild(icon(nav[k][0]));}});
    document.querySelectorAll('.act.like').forEach(function(b){decorateButton(b,'up','Hợp gu');});
    document.querySelectorAll('.act.dislike').forEach(function(b){decorateButton(b,'down','Không hợp');});
    document.querySelectorAll('.act.star,#star').forEach(function(b){decorateButton(b,'star','Nổi bật');});
    document.querySelectorAll('.act.archive').forEach(function(b){var restore=(b.textContent||'').indexOf('↩')>=0;decorateButton(b,restore?'undo':'archive',restore?'Đưa về Inbox':'Lưu trữ');});
    document.querySelectorAll('.act.restore').forEach(function(b){decorateButton(b,'undo','Khôi phục');});
    document.querySelectorAll('.act.trash').forEach(function(b){decorateButton(b,'trash','Xoá');});
    var archive=document.getElementById('archive');if(archive&&!archive.querySelector('svg.ui-icon'))decorateButton(archive,archive.classList.contains('on')?'undo':'archive',archive.classList.contains('on')?'Đưa về Inbox':'Lưu trữ');
    var trash=document.getElementById('trash');if(trash&&!trash.querySelector('svg.ui-icon'))decorateButton(trash,trash.classList.contains('on')?'undo':'trash',trash.classList.contains('on')?'Khôi phục':'Xoá');
    decorateButton(document.getElementById('prevAudio'),'prev','Đoạn trước');
    decorateButton(document.getElementById('playAudio'),'play','Nghe','Nghe');
    decorateButton(document.getElementById('stopAudio'),'stop','Dừng');
    var source=document.getElementById('source');if(source&&!source.querySelector('svg.ui-icon')){source.textContent='Bài gốc';source.appendChild(icon('external'));}
    var back=document.querySelector('.bar a[href="/rss/library"]');if(back&&!back.querySelector('svg.ui-icon')){back.textContent='';back.appendChild(icon('back'));var bs=document.createElement('span');bs.textContent='Library';back.appendChild(bs);}
    document.querySelectorAll('.metric span').forEach(function(s){if(s.querySelector('svg.ui-icon'))return;var t=(s.textContent||'').trim(),name=null;if(t.indexOf('👍')===0)name='up';else if(t.indexOf('👎')===0)name='down';else if(t.indexOf('★')===0)name='star';else if(t.indexOf('▣')===0)name='archive';if(!name)return;var count=t.replace(/^[^0-9]*/,'');s.textContent='';s.appendChild(icon(name));var n=document.createElement('span');n.textContent=count;s.appendChild(n);});
  }
  var queued=false;function schedule(){if(queued)return;queued=true;requestAnimationFrame(function(){queued=false;decorate();});}
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
  decorate();
})();
</script>`;

function fetchArticleId(request, url) {
  if (request.method !== "POST") return null;
  const match = url.pathname.match(/^\/api\/rss\/articles\/([^/]+)\/fetch$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

function blockedRestrictedFetch(request, url) {
  const articleId = fetchArticleId(request, url);
  if (!articleId || !BLOCKED_INCOMPLETE_SOURCE_IDS.has(articleId)) return null;
  return Response.json({
    ok: false,
    error: "INCOMPLETE_RESTRICTED_SOURCE_DIRECT_ONLY",
    articleId,
    message: "Full source is not available through the authorized direct route; refusing to store or translate an excerpt as a full article.",
  }, { status: 409, headers: { "cache-control": "private, no-store" } });
}

function previousParagraphBoundary(text, position) {
  const doubleBreak = text.lastIndexOf("\n\n", position);
  if (doubleBreak >= 0) return doubleBreak;
  const singleBreak = text.lastIndexOf("\n", position);
  return singleBreak >= 0 ? singleBreak : position;
}

export function strictTrimReferenceTail(value) {
  const text = String(value ?? "").replace(/\r/g, "").trim();
  const n = text.length;
  if (n < 3000) return text;

  const hardFloor = Math.floor(n * 0.55);
  const lower = text.toLowerCase();
  const explicit = [
    "tài liệu tham khảo", "nguồn tham khảo", "danh mục tài liệu", "danh sách tài liệu",
    "references", "reference list", "bibliography", "footnotes", "endnotes",
  ];
  let cut = n;
  for (const marker of explicit) {
    const pos = lower.indexOf(marker, hardFloor);
    if (pos >= 0 && pos < cut) cut = previousParagraphBoundary(text, pos);
  }

  // The source sometimes loses its references heading during HTML -> text extraction.
  // Detect a citation-dense tail instead. We only scan from 62% onward and require
  // multiple strong signals in a compact window, so ordinary inline sourcing is kept.
  if (cut === n) {
    const scanStart = Math.floor(n * 0.62);
    const tail = text.slice(scanStart);
    const signalPatterns = [
      { re: /https?:\/\/|www\./gi, weight: 4 },
      { re: /doi\.org\/|\bdoi\s*:/gi, weight: 5 },
      { re: /\[\d{1,3}\]/g, weight: 2 },
      { re: /(?:^|\n)\s*\[?\d{1,3}\]?\s*[.)-]\s+/g, weight: 3 },
      { re: /\((?:19|20)\d{2}[a-z]?\)/gi, weight: 1 },
    ];
    const signals = [];
    for (const { re, weight } of signalPatterns) {
      for (const match of tail.matchAll(re)) signals.push({ pos: scanStart + match.index, weight });
    }
    signals.sort((a, b) => a.pos - b.pos);

    let left = 0;
    let score = 0;
    const windowChars = 4200;
    for (let right = 0; right < signals.length; right++) {
      score += signals[right].weight;
      while (signals[right].pos - signals[left].pos > windowChars) {
        score -= signals[left].weight;
        left++;
      }
      const distinct = right - left + 1;
      if (score >= 16 && distinct >= 5) {
        cut = previousParagraphBoundary(text, signals[left].pos);
        break;
      }
    }
  }

  // Final fallback for bibliography-style references without links: a dense run of
  // publication years in the final 30% is extremely unlikely to be editorial prose.
  if (cut === n) {
    const scanStart = Math.floor(n * 0.70);
    const tail = text.slice(scanStart);
    const years = [...tail.matchAll(/\((?:19|20)\d{2}[a-z]?\)/gi)].map((m) => scanStart + m.index);
    let left = 0;
    for (let right = 0; right < years.length; right++) {
      while (years[right] - years[left] > 4500) left++;
      if (right - left + 1 >= 8) {
        cut = previousParagraphBoundary(text, years[left]);
        break;
      }
    }
  }

  if (cut >= n) return text;
  return text.slice(0, cut).replace(/\n{3,}/g, "\n\n").trim();
}

function readerViewId(url) {
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/(?:original|vi)$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

async function decorateReaderHtml(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!response.ok || !contentType.includes("text/html")) return response;
  const body = await response.text();
  const html = body.includes("reader-icon-layer")
    ? body
    : body.replace("</body>", READER_ICON_LAYER + "</body>");
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  return new Response(html, { status: response.status, statusText: response.statusText, headers });
}

async function postProcessReaderResponse(response, url) {
  if (!response) return response;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("text/html")) return decorateReaderHtml(response);
  if (!response.ok || readerViewId(url) !== STRICT_READER_ARTICLE_ID) return response;
  if (!contentType.includes("application/json")) return response;
  const payload = await response.json().catch(() => null);
  if (!payload?.artifact || typeof payload.artifact.body !== "string") {
    return Response.json(payload ?? { ok: false, error: "READER_PAYLOAD_INVALID" }, {
      status: response.status,
      headers: { "cache-control": "private, no-store" },
    });
  }
  payload.artifact.body = strictTrimReferenceTail(payload.artifact.body);
  return Response.json(payload, {
    status: response.status,
    headers: { "cache-control": "private, no-store" },
  });
}

// Preserve the production-proven /v1/rss/* and private /api/rss/* routes.
// The browser reader is a separate read-only surface with its own token and
// never receives RUNNER3_CORE_TOKEN.
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/ui/rss") {
      return Response.redirect(new URL("/rss/library", url).toString(), 302);
    }

    const integrityResponse = blockedRestrictedFetch(request, url);
    if (integrityResponse) return integrityResponse;

    const readerResponse = await handleRssReader(request, env, url);
    if (readerResponse) return postProcessReaderResponse(readerResponse, url);

    const articleId = fetchArticleId(request, url);
    const rssResponse = await handleRssLibrary(request, env, url);
    if (rssResponse) {
      if (articleId && rssResponse.ok) {
        try {
          await enrichFetchedArticleImages(env, articleId);
        } catch (error) {
          console.warn("rss image enrichment failed", articleId, String(error?.message || error));
        }
      }
      return rssResponse;
    }
    return legacy.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof legacy.scheduled === "function") {
      return legacy.scheduled(controller, env, ctx);
    }
  },
};
