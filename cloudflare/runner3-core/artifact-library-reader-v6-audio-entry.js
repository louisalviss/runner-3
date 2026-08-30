import app from "./artifact-library-reader-v5-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const VOICE = "vi-VN-NamMinhNeural";
const VOICE_RATE = "+3%";
const AUDIO_VERSION = "ebook-reader-audio-v1";
const ITEM_PREFIX = "audio-library/items/";
const QUEUE_PREFIX = "audio-library/ebook-reader-queue/";
const MEDIA_PREFIX = "audio-library/media/";
const MAX_SCRIPT_CHARS = 180000;
const MEDIA_TICKET_VERSION = "ebook-audio-media-v1";
const MEDIA_TICKET_TTL_SECONDS = 4 * 60 * 60;

function headers(base = {}) {
  const h = new Headers(base);
  h.set("X-Robots-Tag", ROBOTS);
  h.set("Cache-Control", "private, no-store, max-age=0");
  h.set("Pragma", "no-cache");
  h.set("Referrer-Policy", "no-referrer");
  h.set("X-Content-Type-Options", "nosniff");
  return h;
}
function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: headers({ "Content-Type": "application/json; charset=utf-8" }) });
}
async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}
async function hmacHex(secret, value) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(String(secret || "")), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("HMAC", key, enc.encode(String(value || "")));
  return [...new Uint8Array(signature)].map((x) => x.toString(16).padStart(2, "0")).join("");
}
function safeEqualHex(a, b) {
  const l = String(a || ""), r = String(b || "");
  if (!l || l.length !== r.length) return false;
  let d = 0; for (let i = 0; i < l.length; i++) d |= l.charCodeAt(i) ^ r.charCodeAt(i);
  return d === 0;
}
function parseByteRange(header, size) {
  const value = String(header || "").trim();
  if (!value) return null;
  const m = value.match(/^bytes=(\d*)-(\d*)$/i);
  if (!m || (!m[1] && !m[2])) return { invalid: true };
  if (!m[1]) {
    const suffix = Number(m[2]);
    if (!Number.isInteger(suffix) || suffix <= 0) return { invalid: true };
    const length = Math.min(size, suffix);
    return { start: size - length, end: size - 1, length };
  }
  const start = Number(m[1]), requestedEnd = m[2] ? Number(m[2]) : size - 1;
  if (!Number.isInteger(start) || !Number.isInteger(requestedEnd) || start < 0 || start >= size || requestedEnd < start) return { invalid: true };
  const end = Math.min(size - 1, requestedEnd);
  return { start, end, length: end - start + 1 };
}
function normalizeSpeechText(value) {
  return String(value || "").normalize("NFC")
    .replace(/\r/g, "").replace(/\u00a0/g, " ").replace(/[\u200b-\u200d\u2060\ufeff]/g, "")
    .replace(/https?:\/\/\S+/g, "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n")
    .split(/\n\s*\n+/).map((p) => p.replace(/\s+/g, " ").trim()).filter(Boolean).join("\n\n").trim();
}
function parseAudioRoute(pathname) {
  const m = pathname.match(/^\/artifact-library\/api\/audio\/([^/]+)(?:\/(media|timing))?$/);
  if (!m) return null;
  try { return { id: decodeURIComponent(m[1]), kind: m[2] || "status" }; } catch { return null; }
}
function validId(id) { return /^[a-f0-9]{32}$/.test(String(id || "")); }
function itemKey(id) { return `${ITEM_PREFIX}ebook-${id}.json`; }
function queueKey(id) { return `${QUEUE_PREFIX}ebook-${id}.json`; }
function mediaPrefix(id) { return `${MEDIA_PREFIX}ebook-${id}/`; }
async function getJson(bucket, key) { const o = await bucket.get(key); if (!o) return null; try { return JSON.parse(await o.text()); } catch { return null; } }
async function putJson(bucket, key, value) { await bucket.put(key, JSON.stringify(value), { httpMetadata: { contentType: "application/json; charset=utf-8" }, customMetadata: { scope: "ebook-reader-audio" } }); }
function ticketPayload(id, expiresAt) { return `${MEDIA_TICKET_VERSION}\u0000${id}\u0000${expiresAt}`; }
async function issueTicket(env, id) {
  const secret = String(env.RUNNER3_CORE_TOKEN || ""); if (!secret) return null;
  const expiresAt = Math.floor(Date.now() / 1000) + MEDIA_TICKET_TTL_SECONDS;
  return `${expiresAt}.${await hmacHex(secret, ticketPayload(id, expiresAt))}`;
}
async function verifyTicket(env, token, id) {
  const secret = String(env.RUNNER3_CORE_TOKEN || ""), value = String(token || ""); if (!secret || !value) return false;
  const dot = value.indexOf("."); if (dot <= 0) return false;
  const exp = Number(value.slice(0, dot)), sig = value.slice(dot + 1), now = Math.floor(Date.now() / 1000);
  if (!Number.isInteger(exp) || exp < now || exp > now + MEDIA_TICKET_TTL_SECONDS + 60) return false;
  return safeEqualHex(sig, await hmacHex(secret, ticketPayload(id, exp)));
}
async function publicState(env, item, id) {
  const out = { ok: true, status: item?.status || "missing", audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, durationSeconds: Number.isFinite(Number(item?.durationSeconds)) ? Number(item.durationSeconds) : null, timingAvailable: Boolean(item?.timingUrl), updatedAt: item?.updatedAt || null, error: item?.status === "error" ? String(item.error || "Không thể tạo audio").slice(0, 180) : null };
  if (item?.status === "ready") {
    const ticket = await issueTicket(env, id);
    if (ticket) { out.mediaUrl = `/artifact-library/api/audio/${encodeURIComponent(id)}/media?ticket=${encodeURIComponent(ticket)}`; out.mediaTicketTtlSeconds = MEDIA_TICKET_TTL_SECONDS; }
  }
  return out;
}
async function serveMedia(request, env, id) {
  const key = `${mediaPrefix(id)}episode.mp3`, head = await env.AUDIO_MEDIA.head(key);
  if (!head) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
  const size = Number(head.size || 0), h = headers({ "Content-Type": "audio/mpeg", "Accept-Ranges": "bytes", "Content-Disposition": "inline" });
  if (head.etag) h.set("ETag", head.etag);
  if (request.method === "HEAD") { if (size) h.set("Content-Length", String(size)); return new Response(null, { status: 200, headers: h }); }
  const range = parseByteRange(request.headers.get("range"), size);
  if (range?.invalid) { h.set("Content-Range", `bytes */${size}`); return new Response(null, { status: 416, headers: h }); }
  if (range) {
    const o = await env.AUDIO_MEDIA.get(key, { range: { offset: range.start, length: range.length } });
    if (!o) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
    h.set("Content-Range", `bytes ${range.start}-${range.end}/${size}`); h.set("Content-Length", String(range.length));
    return new Response(o.body, { status: 206, headers: h });
  }
  const o = await env.AUDIO_MEDIA.get(key); if (!o) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
  if (size) h.set("Content-Length", String(size)); return new Response(o.body, { status: 200, headers: h });
}
async function handleAudio(request, env, url) {
  const route = parseAudioRoute(url.pathname); if (!route) return null;
  if (!env.AUDIO_MEDIA) return json({ ok: false, error: "AUDIO_MEDIA_NOT_BOUND" }, 503);
  if (!validId(route.id)) return json({ ok: false, error: "INVALID_AUDIO_ID" }, 400);
  const key = itemKey(route.id), existing = await getJson(env.AUDIO_MEDIA, key);
  if (route.kind === "media") {
    if (!await verifyTicket(env, url.searchParams.get("ticket"), route.id)) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
    if (!existing || existing.status !== "ready") return json({ ok: false, error: "AUDIO_NOT_READY" }, 409);
    if (request.method !== "GET" && request.method !== "HEAD") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    return serveMedia(request, env, route.id);
  }
  if (route.kind === "timing") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    if (!existing || existing.status !== "ready") return json({ ok: false, error: "AUDIO_NOT_READY" }, 409);
    const timing = await getJson(env.AUDIO_MEDIA, `${mediaPrefix(route.id)}timing.json`);
    return timing ? json(timing) : json({ ok: false, error: "AUDIO_TIMING_MISSING" }, 404);
  }
  if (request.method === "GET") return json(await publicState(env, existing, route.id));
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  let body; try { body = await request.json(); } catch { return json({ ok: false, error: "INVALID_JSON" }, 400); }
  const bookKey = String(body?.bookKey || ""), chapterKey = String(body?.chapterKey || ""), title = String(body?.title || "Ebook chapter").slice(0, 240);
  const script = normalizeSpeechText(body?.text || "");
  if (!bookKey.startsWith("core/ebook/") || !bookKey.includes("/final/") || !bookKey.toLowerCase().endsWith(".epub")) return json({ ok: false, error: "FINAL_EPUB_ONLY" }, 403);
  if (!chapterKey || chapterKey.length > 500) return json({ ok: false, error: "INVALID_CHAPTER" }, 400);
  if (script.length < 80) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_SHORT" }, 422);
  if (script.length > MAX_SCRIPT_CHARS) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_LONG" }, 413);
  const expectedId = (await sha256Hex(`${AUDIO_VERSION}\u0000${bookKey}\u0000${chapterKey}\u0000${VOICE}\u0000${VOICE_RATE}`)).slice(0, 32);
  if (expectedId !== route.id) return json({ ok: false, error: "AUDIO_ID_MISMATCH" }, 409);
  const textSha256 = await sha256Hex(script);
  if (existing && existing.textSha256 === textSha256 && existing.voice === VOICE && existing.voiceRate === VOICE_RATE && existing.audioVersion === AUDIO_VERSION && ["pending", "processing", "ready"].includes(existing.status)) return json(await publicState(env, existing, route.id));
  const now = new Date().toISOString(), prefix = mediaPrefix(route.id);
  if (existing?.status === "ready") await Promise.all([env.AUDIO_MEDIA.delete(`${prefix}episode.mp3`), env.AUDIO_MEDIA.delete(`${prefix}timing.json`)]);
  await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, { httpMetadata: { contentType: "text/plain; charset=utf-8" }, customMetadata: { scope: "ebook-reader-audio", voice: VOICE, version: AUDIO_VERSION } });
  const item = { id: `ebook-${route.id}`, kind: "ebook-reader", bookKey, chapterKey, title, status: "pending", createdAt: existing?.createdAt || now, updatedAt: now, durationSeconds: null, progressSeconds: 0, audioUrl: null, transcriptUrl: null, timingUrl: null, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, error: null };
  const queue = { id: `ebook-${route.id}`, kind: "ebook-reader", bookKey, chapterKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, createdAt: now };
  await putJson(env.AUDIO_MEDIA, key, item); await putJson(env.AUDIO_MEDIA, queueKey(route.id), queue);
  return json(await publicState(env, item, route.id), 202);
}
function injectAudioUi(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-ebook-audio-v1="1"')) return html;
  const patch = `<style data-r3-ebook-audio-v1="1">
#r3AudioBtn{font-size:18px}.r3-audio-dock{position:fixed;z-index:24;left:10px;right:10px;bottom:calc(max(10px,env(safe-area-inset-bottom)) + 2px);max-width:520px;margin:0 auto;display:none;grid-template-columns:auto auto minmax(0,1fr) auto;gap:8px;align-items:center;padding:9px 10px;border:1px solid var(--line);border-radius:16px;background:var(--panel);box-shadow:var(--shadow);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}body.r3-audio-open .r3-audio-dock{display:grid}.r3-audio-dock button,.r3-audio-dock select{height:36px;border:1px solid var(--line);border-radius:10px;background:transparent;color:var(--fg);font:inherit;font-size:12px;font-weight:750}.r3-audio-dock button{min-width:40px}.r3-audio-progress{width:100%}.r3-audio-state{position:fixed;left:50%;bottom:calc(max(10px,env(safe-area-inset-bottom)) + 58px);transform:translateX(-50%);z-index:24;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:6px 10px;font-size:11px;color:var(--muted);display:none;max-width:80vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}body.r3-audio-open .r3-audio-state{display:block}
</style>
<div id="r3AudioDock" class="r3-audio-dock"><button id="r3AudioPrev" type="button" aria-label="Lùi 15 giây">−15</button><button id="r3AudioPlay" type="button" aria-label="Phát audio">▶</button><input id="r3AudioProgress" class="r3-audio-progress" type="range" min="0" max="1" step="0.1" value="0" aria-label="Tiến trình audio"><select id="r3AudioSpeed" aria-label="Tốc độ"><option>.8×</option><option selected>1×</option><option>1.25×</option><option>1.5×</option><option>2×</option></select></div><div id="r3AudioState" class="r3-audio-state">Audio</div>
<script data-r3-ebook-audio-v1="1">(()=>{
const bookKey=${JSON.stringify("__BOOK_KEY__")};
const body=document.body,$=id=>document.getElementById(id);let audio=null,currentId='',pollTimer=0;
function state(t){$('r3AudioState').textContent=t||'Audio'}
function textFromCurrent(){try{const c=(rendition&&rendition.getContents&&rendition.getContents()||[])[0];if(!c||!c.document)return null;const doc=c.document.cloneNode(true);doc.querySelectorAll('script,style,nav,aside,svg,button,input,select,textarea').forEach(n=>n.remove());return {text:(doc.body?.innerText||'').trim(),chapterKey:String(c.section?.href||c.document?.location?.pathname||r3CurrentCfi?.()||'chapter'),title:(doc.querySelector('h1,h2,h3')?.textContent||document.title||'Ebook chapter').trim()}}catch{return null}}
async function hash(s){const d=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));return [...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,'0')).join('')}
async function chapterId(ch){return (await hash('ebook-reader-audio-v1\\0'+bookKey+'\\0'+ch+'\\0vi-VN-NamMinhNeural\\0+3%')).slice(0,32)}
function ensureAudio(){if(audio)return audio;audio=new Audio();audio.preload='metadata';audio.addEventListener('timeupdate',()=>{$('r3AudioProgress').max=String(audio.duration||1);$('r3AudioProgress').value=String(audio.currentTime||0);try{localStorage.setItem('r3-ebook-audio-pos:'+currentId,String(audio.currentTime||0))}catch{}});audio.addEventListener('play',()=>{$('r3AudioPlay').textContent='❚❚'});audio.addEventListener('pause',()=>{$('r3AudioPlay').textContent='▶'});return audio}
async function getStatus(id){const r=await fetch('/artifact-library/api/audio/'+encodeURIComponent(id),{cache:'no-store'});return r.json()}
async function requestCurrent(){const src=textFromCurrent();if(!src||src.text.length<80){state('Chương này không có đủ nội dung để đọc');return}const id=await chapterId(src.chapterKey);currentId=id;state('Đang kiểm tra audio…');let data=await getStatus(id);if(data.status==='missing'||data.status==='error'){const r=await fetch('/artifact-library/api/audio/'+encodeURIComponent(id),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bookKey,chapterKey:src.chapterKey,title:src.title,text:src.text})});data=await r.json()}await applyState(id,data)}
async function applyState(id,data){clearTimeout(pollTimer);if(data.status==='ready'&&data.mediaUrl){const a=ensureAudio();if(a.src!==new URL(data.mediaUrl,location.href).href){a.src=data.mediaUrl;try{const p=Number(localStorage.getItem('r3-ebook-audio-pos:'+id)||'0');if(p>0)a.currentTime=p}catch{}}state('Nam Minh · '+(data.durationSeconds?Math.round(data.durationSeconds/60)+' phút':'sẵn sàng'));return}if(data.status==='pending'||data.status==='processing'){state(data.status==='processing'?'Nam Minh đang tạo audio…':'Audio đang xếp hàng…');pollTimer=setTimeout(async()=>{try{await applyState(id,await getStatus(id))}catch{pollTimer=setTimeout(()=>requestCurrent(),3000)}},2500);return}state(data.error||'Chưa có audio')}
$('r3AudioPlay')?.addEventListener('click',async()=>{if(!currentId||!audio?.src){await requestCurrent();if(!audio?.src)return}audio.paused?audio.play():audio.pause()});$('r3AudioPrev')?.addEventListener('click',()=>{if(audio)audio.currentTime=Math.max(0,audio.currentTime-15)});$('r3AudioProgress')?.addEventListener('input',e=>{if(audio)audio.currentTime=Number(e.target.value||0)});$('r3AudioSpeed')?.addEventListener('change',e=>{if(audio)audio.playbackRate=parseFloat(String(e.target.value).replace('×',''))||1});
const topbar=document.querySelector('.topbar');if(topbar&&!$('r3AudioBtn')){const b=document.createElement('button');b.id='r3AudioBtn';b.className='round';b.type='button';b.setAttribute('aria-label','Audio Nam Minh');b.textContent='♫';b.addEventListener('click',e=>{e.stopPropagation();body.classList.toggle('r3-audio-open');if(body.classList.contains('r3-audio-open'))requestCurrent();});topbar.appendChild(b)}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&body.classList.contains('r3-audio-open'))body.classList.remove('r3-audio-open')});window.addEventListener('beforeunload',()=>{clearTimeout(pollTimer);try{audio?.pause()}catch{}},{once:true});
})();</script>`;
  const keyMatch = html.match(/const key=([^;]+);/);
  const keyLiteral = keyMatch ? keyMatch[1] : '""';
  return html.replace('</body>', patch.replace(JSON.stringify("__BOOK_KEY__"), keyLiteral) + '</body>');
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const audio = await handleAudio(request, env, url);
    if (audio) return audio;
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;
    const original = await response.text();
    const updated = injectAudioUi(original);
    const h = new Headers(response.headers); h.delete("Content-Length"); h.set("X-Robots-Tag", ROBOTS);
    return new Response(updated, { status: response.status, headers: h });
  },
  async scheduled(controller, env, ctx) { if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx); },
};
