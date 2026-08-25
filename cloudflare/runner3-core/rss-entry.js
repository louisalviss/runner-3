import legacy from "./rss-wrapper.js";
import { handleRssLibrary } from "./src/rss-library.js";
import { handleRssReader } from "./src/rss-reader.js";
import { enrichFetchedArticleImages } from "./src/rss-image-enrich.js";

const BLOCKED_INCOMPLETE_SOURCE_IDS = new Set([
  "projectsyndicate-url-26a9686e21ebe4fa865d",
  "projectsyndicate-url-db223b141f372578df3c",
]);

const STRICT_READER_ARTICLE_ID = "nghiencuuquocte-url-6cd04807aefc80d9be93";

function safeArticleHtml(articleId) {
  const encoded = JSON.stringify(articleId);
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#090909"><title>RSS Article</title><style>
:root{color-scheme:dark;--bg:#090909;--panel:#121212;--line:#2b2b2b;--text:#f4f4f5;--muted:#97979f;--danger:#ff7a7a}*{box-sizing:border-box}html,body{width:100%;max-width:100%;margin:0;overflow-x:hidden;background:var(--bg)}body{color:var(--text);font:17px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}.wrap{width:100%;max-width:760px;margin:0 auto;padding:0 14px 100px}.bar{position:sticky;top:0;z-index:6;margin:0 -14px;padding:calc(9px + env(safe-area-inset-top)) 14px 9px;background:#090909ee;backdrop-filter:blur(18px);border-bottom:1px solid #202020;display:flex;align-items:center;gap:8px}.bar a,.bar button{height:36px;border:1px solid #2d2d2d;border-radius:10px;background:#111;color:#eee;padding:0 10px;text-decoration:none;display:inline-flex;align-items:center}.source{margin-left:auto;max-width:44%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.title{font-size:30px;line-height:1.16;letter-spacing:-.025em;margin:22px 0 8px;overflow-wrap:anywhere}.meta{font-size:13px;color:var(--muted);overflow-wrap:anywhere}.id{font:11px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;color:#777780;overflow-wrap:anywhere;margin:5px 0 14px}.lang,.actions{display:flex;gap:7px;flex-wrap:wrap}.lang{margin:12px 0}.lang button,.actions button,.audio button,.audio select{min-height:38px;border:1px solid #303030;border-radius:10px;background:#171717;color:#ddd;padding:0 11px}.lang button.on,.actions button.on{background:#eee;color:#111;border-color:#eee}.state{margin:14px 0;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px}.category{display:grid;grid-template-columns:82px minmax(0,1fr);gap:8px;align-items:center;margin-top:9px}.category label{font-size:12px;color:var(--muted)}.category select{width:100%;height:38px;border:1px solid #303030;border-radius:10px;background:#151515;color:#ddd;padding:0 8px}.audio{margin:12px 0 18px;background:#111;border:1px solid #2b2b2b;border-radius:14px;padding:10px;display:flex;gap:7px;align-items:center;flex-wrap:wrap}.audio span{font-size:12px;color:var(--muted);margin-left:auto}.bad{color:var(--danger);overflow-wrap:anywhere}.images{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;width:100%;margin:18px 0 24px;overflow:hidden}.images figure{margin:0;min-width:0}.images img{display:block;width:100%;max-width:100%;height:auto;max-height:700px;object-fit:contain;border-radius:12px;background:#111}.images figcaption{font-size:13px;color:var(--muted);margin-top:6px;overflow-wrap:anywhere}.body{display:block;width:100%;max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;overflow-x:hidden;font:inherit;margin:18px 0 0;color:#ececee}@media(max-width:430px){.wrap{padding-left:13px;padding-right:13px}.bar{margin-left:-13px;margin-right:-13px}.title{font-size:27px}.source{max-width:46%}}
</style></head><body><main class="wrap"><div class="bar"><a href="/rss/library">‹ Library</a><a class="source" id="source" target="_blank" rel="noopener noreferrer">Bài gốc ↗</a></div><h1 class="title" id="title">Đang tải…</h1><div class="meta" id="meta"></div><div class="id" id="articleId"></div><div class="lang"><button id="vi">Tiếng Việt</button><button id="original">Original</button></div><section class="state"><div class="actions"><button id="like">Thích</button><button id="dislike">Không thích</button><button id="star">Nổi bật</button><button id="archive">Lưu trữ</button><button id="trash">Xoá</button></div><div class="category"><label>Phân loại</label><select id="category"><option value="">Chưa phân loại</option></select></div></section><section class="audio"><button id="prevAudio">Đoạn trước</button><button id="playAudio">Nghe</button><button id="stopAudio">Dừng</button><select id="rate"><option value="0.9">0.9×</option><option value="1" selected>1.0×</option><option value="1.1">1.1×</option><option value="1.2">1.2×</option></select><span id="audioState">Chưa phát</span></section><p class="bad" id="error"></p><section class="images" id="images"></section><div class="body" id="body">Đang tải nội dung…</div></main><script>
const KEY='rssReaderToken',id=${encoded};
const body=document.getElementById('body'),images=document.getElementById('images'),err=document.getElementById('error'),meta=document.getElementById('meta'),articleId=document.getElementById('articleId'),title=document.getElementById('title'),source=document.getElementById('source'),category=document.getElementById('category');
let article=null,artifact=null,activeKind='vi',chunks=[],audioIndex=0,currentUtterance=null;
function decodeText(value){const el=document.createElement('textarea');el.innerHTML=String(value==null?'':value);return el.value}
async function api(path,opt={}){const t=localStorage.getItem(KEY)||'';if(!t)throw new Error('MISSING_READER_TOKEN');const headers={Authorization:'Bearer '+t,...(opt.headers||{})};if(opt.body&&!headers['Content-Type'])headers['Content-Type']='application/json';const r=await fetch(path,{...opt,headers});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||String(r.status));return j}
function renderImages(value){images.textContent='';if(!Array.isArray(value))return;for(const item of value){const url=String(item&&item.url||'');if(!(url.startsWith('http://')||url.startsWith('https://')))continue;const f=document.createElement('figure'),img=document.createElement('img');img.src=url;img.loading='lazy';img.decoding='async';img.alt=decodeText(item.alt||'');f.append(img);const cap=decodeText(item.caption||item.alt||'').trim();if(cap){const c=document.createElement('figcaption');c.textContent=cap;f.append(c)}images.append(f)}}
function fillCategories(values){const current=article&&article.category||'';category.textContent='';const blank=document.createElement('option');blank.value='';blank.textContent='Chưa phân loại';category.append(blank);for(const x of [...new Set([...(values||[]),current].filter(Boolean))]){const o=document.createElement('option');o.value=x;o.textContent=x;o.selected=x===current;category.append(o)}category.value=current}
function syncState(){if(!article)return;document.getElementById('like').classList.toggle('on',article.preference==='like');document.getElementById('dislike').classList.toggle('on',article.preference==='dislike');document.getElementById('star').classList.toggle('on',!!article.featured);document.getElementById('archive').classList.toggle('on',article.lifecycle==='archived');document.getElementById('archive').textContent=article.lifecycle==='archived'?'Đưa về Inbox':'Lưu trữ';document.getElementById('trash').classList.toggle('on',article.lifecycle==='deleted');document.getElementById('trash').textContent=article.lifecycle==='deleted'?'Khôi phục':'Xoá';category.value=article.category||''}
async function patch(data){const j=await api('/reader/rss/articles/'+encodeURIComponent(id)+'/state',{method:'POST',body:JSON.stringify(data)});article=j.article;syncState();return j}
function buildChunks(text){const raw=String(text||'').trim();if(!raw)return [];const parts=raw.split(String.fromCharCode(10));const out=[];let current='';for(const part of parts){const p=part.trim();if(!p)continue;if((current+' '+p).length>1000){if(current)out.push(current);current=p}else current=current?current+' '+p:p}if(current)out.push(current);return out}
function audioKey(){return 'rssAudio:'+id+':'+activeKind}
function updateAudioState(label){document.getElementById('audioState').textContent=label||((audioIndex+1)+' / '+Math.max(chunks.length,1))}
function stopSpeech(){if('speechSynthesis' in window)window.speechSynthesis.cancel();currentUtterance=null}
function chooseVoice(){if(!('speechSynthesis' in window))return null;const voices=window.speechSynthesis.getVoices();const lang=activeKind==='vi'?'vi':'en';return voices.find(v=>String(v.lang||'').toLowerCase().startsWith(lang))||null}
function speakCurrent(){if(!('speechSynthesis' in window)){updateAudioState('Không hỗ trợ audio');return}if(!chunks.length){updateAudioState('Không có nội dung');return}if(audioIndex>=chunks.length)audioIndex=0;stopSpeech();const u=new SpeechSynthesisUtterance(chunks[audioIndex]);u.lang=activeKind==='vi'?'vi-VN':'en-US';u.rate=Number(document.getElementById('rate').value||1);const voice=chooseVoice();if(voice)u.voice=voice;currentUtterance=u;localStorage.setItem(audioKey(),String(audioIndex));updateAudioState('Đang nghe '+(audioIndex+1)+' / '+chunks.length);u.onend=()=>{if(currentUtterance!==u)return;audioIndex+=1;if(audioIndex<chunks.length)speakCurrent();else{audioIndex=0;localStorage.setItem(audioKey(),'0');updateAudioState('Đã nghe xong')}};u.onerror=()=>updateAudioState('Audio bị gián đoạn');window.speechSynthesis.speak(u)}
function rebuildAudio(){stopSpeech();chunks=buildChunks(artifact&&artifact.body||'');const saved=Number(localStorage.getItem(audioKey())||0);audioIndex=Number.isFinite(saved)&&saved>=0&&saved<chunks.length?saved:0;updateAudioState(chunks.length?(audioIndex+1)+' / '+chunks.length:'Không có nội dung')}
async function view(kind){err.textContent='';body.textContent='Đang tải nội dung…';images.textContent='';stopSpeech();try{const j=await api('/reader/rss/articles/'+encodeURIComponent(id)+'/'+kind);article=j.article;artifact=j.artifact;activeKind=kind;renderImages(artifact.images);body.textContent=decodeText(artifact.body||'');syncState();rebuildAudio();document.getElementById('vi').classList.toggle('on',kind==='vi');document.getElementById('original').classList.toggle('on',kind==='original')}catch(e){body.textContent='';err.textContent=e.message==='UNAUTHORIZED'?'Reader token không hợp lệ':e.message}}
async function init(){try{const j=await api('/reader/rss/articles/'+encodeURIComponent(id));article=j.article;title.textContent=decodeText(article.title);meta.textContent=[decodeText(article.source_name),article.published_at].filter(Boolean).join(' · ');articleId.textContent='ID: '+article.article_id;source.href=article.canonical_url||'#';fillCategories(j.suggestedCategories);syncState();const preferred=(article.source_language==='vi'||article.translation_status==='published'||article.translation_status==='native_vi')?'vi':'original';await view(preferred)}catch(e){body.textContent='';err.textContent=e.message==='MISSING_READER_TOKEN'?'Mở Library một lần để đăng nhập lại':e.message}}
document.getElementById('vi').onclick=()=>view('vi');document.getElementById('original').onclick=()=>view('original');document.getElementById('like').onclick=()=>patch({preference:article&&article.preference==='like'?null:'like'});document.getElementById('dislike').onclick=()=>patch({preference:article&&article.preference==='dislike'?null:'dislike'});document.getElementById('star').onclick=()=>patch({featured:!(article&&article.featured)});document.getElementById('archive').onclick=()=>patch({lifecycle:article&&article.lifecycle==='archived'?'active':'archived'});document.getElementById('trash').onclick=()=>patch({lifecycle:article&&article.lifecycle==='deleted'?'active':'deleted'});category.onchange=()=>patch({category:category.value||null});document.getElementById('playAudio').onclick=speakCurrent;document.getElementById('stopAudio').onclick=()=>{stopSpeech();updateAudioState('Đã dừng')};document.getElementById('prevAudio').onclick=()=>{stopSpeech();audioIndex=Math.max(0,audioIndex-1);localStorage.setItem(audioKey(),String(audioIndex));speakCurrent()};document.getElementById('rate').onchange=()=>{if(currentUtterance)speakCurrent()};window.addEventListener('pagehide',stopSpeech);init();
</script></body></html>`;
}

function articlePageId(request, url) {
  if (request.method !== "GET") return null;
  const match = url.pathname.match(/^\/rss\/article\/([^/]+)$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

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

async function postProcessReaderResponse(response, url) {
  if (!response?.ok || readerViewId(url) !== STRICT_READER_ARTICLE_ID) return response;
  const contentType = response.headers.get("content-type") || "";
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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/ui/rss") {
      return Response.redirect(new URL("/rss/library", url).toString(), 302);
    }

    const safeId = articlePageId(request, url);
    if (safeId) {
      return new Response(safeArticleHtml(safeId), {
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
      });
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
