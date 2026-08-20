const ITEM_PREFIX = 'audio-library/items/';
const QUEUE_PREFIX = 'audio-library/queue/';
const MEDIA_PREFIX = 'audio-library/media/';
const MAX_ITEMS = 300;
const encoder = new TextEncoder();

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });
}
function html(body, status = 200) {
  return new Response(body, { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', 'referrer-policy': 'no-referrer', 'permissions-policy': 'camera=(), microphone=(), geolocation=()' } });
}
async function timingSafeEqualStrings(a, b) {
  const [aHash, bHash] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(a || '')),
    crypto.subtle.digest('SHA-256', encoder.encode(b || '')),
  ]);
  return crypto.subtle.timingSafeEqual(aHash, bHash);
}
async function runnerAuthorized(request, env) {
  const token = request.headers.get('x-runner-token') || '';
  return Boolean(token && env.RUNNER_SHARED_TOKEN && await timingSafeEqualStrings(token, env.RUNNER_SHARED_TOKEN));
}
function itemKey(id) { return `${ITEM_PREFIX}${id}.json`; }
function queueKey(id) { return `${QUEUE_PREFIX}${id}.json`; }
function publicItem(item) { const copy = { ...item }; delete copy.errorDetail; return copy; }
async function getJsonObject(bucket, key) {
  const object = await bucket.get(key);
  if (!object || !object.body) return null;
  try { return JSON.parse(await object.text()); } catch { return null; }
}
async function putJson(bucket, key, value) {
  await bucket.put(key, JSON.stringify(value), { httpMetadata: { contentType: 'application/json; charset=utf-8' } });
}
async function listKeys(bucket, prefix, max = MAX_ITEMS) {
  const keys = []; let cursor;
  do {
    const page = await bucket.list({ prefix, cursor, limit: Math.min(1000, max - keys.length) });
    for (const object of page.objects) { keys.push(object.key); if (keys.length >= max) return keys; }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor && keys.length < max);
  return keys;
}
async function listItems(env) {
  const keys = await listKeys(env.AUDIO_BUCKET, ITEM_PREFIX, MAX_ITEMS);
  const items = (await Promise.all(keys.map((key) => getJsonObject(env.AUDIO_BUCKET, key)))).filter(Boolean);
  items.sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  return items.map(publicItem);
}
async function deletePrefix(bucket, prefix) {
  let cursor;
  do {
    const page = await bucket.list({ prefix, cursor, limit: 1000 });
    const keys = page.objects.map((o) => o.key);
    if (keys.length) await bucket.delete(keys);
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
}
async function deleteItem(env, id) {
  const item = await getJsonObject(env.AUDIO_BUCKET, itemKey(id));
  await deletePrefix(env.AUDIO_BUCKET, item?.mediaPrefix || `${MEDIA_PREFIX}${id}/`);
  await env.AUDIO_BUCKET.delete([itemKey(id), queueKey(id)]);
}
function addDaysIso(days) { return new Date(Date.now() + days * 86400000).toISOString(); }
function sourceLabel(value) {
  try {
    const host = new URL(value).hostname.replace(/^www\./, '');
    if (host === 'youtu.be' || host.endsWith('youtube.com')) return 'YouTube';
    if (host.endsWith('reddit.com')) return 'Reddit';
    if (host === 'x.com' || host.endsWith('twitter.com')) return 'X';
    return host;
  } catch { return 'Web'; }
}
function validHttpUrl(value) {
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && u.hostname.length > 1; } catch { return false; }
}
async function addItem(request, env) {
  let body; try { body = await request.json(); } catch { return json({ error: 'JSON không hợp lệ' }, 400); }
  const sourceUrl = String(body?.url || '').trim();
  if (!validHttpUrl(sourceUrl)) return json({ error: 'Link không hợp lệ' }, 400);
  const existing = await listItems(env);
  const duplicate = existing.find((x) => x.sourceUrl === sourceUrl && ['pending', 'processing', 'ready'].includes(x.status));
  if (duplicate) return json({ item: duplicate, duplicate: true });
  const id = crypto.randomUUID(), now = new Date().toISOString();
  const item = { id, sourceUrl, sourceLabel: sourceLabel(sourceUrl), title: sourceLabel(sourceUrl), status: 'pending', createdAt: now, updatedAt: now, expiresAt: addDaysIso(Number(env.DEFAULT_RETENTION_DAYS || 30)), pinned: false, durationSeconds: null, progressSeconds: 0, audioUrl: null, transcriptUrl: null, mediaPrefix: `${MEDIA_PREFIX}${id}/`, error: null };
  await putJson(env.AUDIO_BUCKET, itemKey(id), item);
  await putJson(env.AUDIO_BUCKET, queueKey(id), { id, sourceUrl, createdAt: now });
  return json({ item: publicItem(item) }, 201);
}
async function updateProgress(request, env, id) {
  const item = await getJsonObject(env.AUDIO_BUCKET, itemKey(id)); if (!item) return json({ error: 'Không tìm thấy audio' }, 404);
  let body; try { body = await request.json(); } catch { return json({ error: 'JSON không hợp lệ' }, 400); }
  const seconds = Math.max(0, Number(body?.seconds || 0)); const duration = Math.max(0, Number(body?.duration || item.durationSeconds || 0));
  item.progressSeconds = Number.isFinite(seconds) ? seconds : 0; if (duration > 0) item.durationSeconds = duration;
  item.lastPlayedAt = new Date().toISOString(); item.updatedAt = item.lastPlayedAt;
  item.listened = Boolean(item.durationSeconds && item.progressSeconds >= item.durationSeconds - 3);
  if (item.listened) item.progressSeconds = item.durationSeconds;
  await putJson(env.AUDIO_BUCKET, itemKey(id), item); return json({ item: publicItem(item) });
}
async function updateItem(request, env, id) {
  const item = await getJsonObject(env.AUDIO_BUCKET, itemKey(id)); if (!item) return json({ error: 'Không tìm thấy audio' }, 404);
  let body; try { body = await request.json(); } catch { return json({ error: 'JSON không hợp lệ' }, 400); }
  if (typeof body?.pinned === 'boolean') { item.pinned = body.pinned; item.expiresAt = body.pinned ? null : addDaysIso(Number(env.DEFAULT_RETENTION_DAYS || 30)); }
  item.updatedAt = new Date().toISOString(); await putJson(env.AUDIO_BUCKET, itemKey(id), item); return json({ item: publicItem(item) });
}
async function runnerNext(env) {
  const keys = await listKeys(env.AUDIO_BUCKET, QUEUE_PREFIX, 100); keys.sort();
  for (const key of keys) {
    const queued = await getJsonObject(env.AUDIO_BUCKET, key); if (!queued?.id) continue;
    const item = await getJsonObject(env.AUDIO_BUCKET, itemKey(queued.id));
    if (!item || item.status !== 'pending') { await env.AUDIO_BUCKET.delete(key); continue; }
    item.status = 'processing'; item.updatedAt = new Date().toISOString(); item.error = null; await putJson(env.AUDIO_BUCKET, itemKey(item.id), item); return json({ item: publicItem(item) });
  }
  return new Response(null, { status: 204 });
}
async function runnerComplete(request, env) {
  let body; try { body = await request.json(); } catch { return json({ error: 'JSON không hợp lệ' }, 400); }
  const id = String(body?.id || ''), item = await getJsonObject(env.AUDIO_BUCKET, itemKey(id)); if (!item) return json({ error: 'Không tìm thấy item' }, 404);
  item.status = 'ready'; item.title = String(body.title || item.title || item.sourceLabel).slice(0, 240); item.sourceLabel = String(body.sourceLabel || item.sourceLabel || 'Web').slice(0, 80); item.durationSeconds = Math.max(0, Number(body.durationSeconds || 0)) || null; item.audioUrl = String(body.audioUrl || ''); item.transcriptUrl = body.transcriptUrl ? String(body.transcriptUrl) : null; item.truncated = Boolean(body.truncated); item.updatedAt = new Date().toISOString(); item.error = null;
  await putJson(env.AUDIO_BUCKET, itemKey(id), item); await env.AUDIO_BUCKET.delete(queueKey(id)); return json({ item: publicItem(item) });
}
async function runnerFail(request, env) {
  let body; try { body = await request.json(); } catch { return json({ error: 'JSON không hợp lệ' }, 400); }
  const id = String(body?.id || ''), item = await getJsonObject(env.AUDIO_BUCKET, itemKey(id)); if (!item) return json({ error: 'Không tìm thấy item' }, 404);
  item.status = 'error'; item.error = String(body.error || 'Không thể xử lý link').slice(0, 180); item.errorDetail = String(body.detail || '').slice(0, 1200); item.updatedAt = new Date().toISOString();
  await putJson(env.AUDIO_BUCKET, itemKey(id), item); await env.AUDIO_BUCKET.delete(queueKey(id)); return json({ item: publicItem(item) });
}
async function purgeExpired(env) {
  const now = Date.now();
  for (const item of await listItems(env)) if (!item.pinned && item.expiresAt && Date.parse(item.expiresAt) <= now) await deleteItem(env, item.id);
}

const APP_HTML = `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0b0d11"><title>Audio Library</title><style>
:root{color-scheme:dark;--bg:#0b0d11;--card:#151820;--line:#242833;--text:#f5f6f8;--muted:#939aa7;--accent:#8b5cf6;--danger:#ef6666}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}button,input{font:inherit}button{cursor:pointer}main{max-width:640px;margin:auto;padding:calc(18px + env(safe-area-inset-top)) 16px calc(135px + env(safe-area-inset-bottom))}.top{display:flex;align-items:center;justify-content:space-between;margin:4px 0 18px}.top h1{font-size:26px;margin:0}.add{width:100%;border:0;border-radius:13px;background:var(--accent);color:#fff;padding:14px 16px;font-weight:650;margin-bottom:16px}.tabs{display:flex;gap:6px;margin-bottom:12px}.tab{border:1px solid var(--line);background:transparent;color:var(--muted);padding:8px 11px;border-radius:10px}.tab.on{background:#201a31;color:#fff;border-color:#362954}.list{display:grid;gap:9px}.item{position:relative;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 42px 12px 13px}.item h3{font-size:16px;line-height:1.3;margin:0 0 5px;max-width:92%}.meta{font-size:13px;color:var(--muted)}.state{font-size:13px;margin-top:7px;color:#b6bdc9}.state.error{color:var(--danger)}.bar{height:4px;background:#272b35;border-radius:99px;overflow:hidden;margin-top:11px}.fill{height:100%;background:var(--accent)}.more{position:absolute;right:8px;top:8px;border:0;background:transparent;color:#aeb5c1;font-size:22px;padding:6px}.empty{text-align:center;color:var(--muted);padding:42px 12px}.player{position:fixed;left:50%;transform:translateX(-50%);bottom:0;width:min(640px,100%);background:#11141b;border-top:1px solid var(--line);padding:10px 16px calc(10px + env(safe-area-inset-bottom));display:none}.player.show{display:block}.ptitle{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:7px}.timeline{width:100%}.controls{display:flex;justify-content:center;gap:28px;align-items:center;margin-top:4px}.controls button{border:0;background:transparent;color:#fff;font-size:17px}.controls .play{width:46px;height:46px;border-radius:50%;background:var(--accent);font-size:19px}.sheet{position:fixed;inset:0;background:#0009;display:none;align-items:flex-end;justify-content:center;z-index:5}.sheet.show{display:flex}.panel{width:min(640px,100%);background:#171a21;border-radius:18px 18px 0 0;padding:18px 16px calc(18px + env(safe-area-inset-bottom))}.panel h3{margin:0 0 14px}.panel button{width:100%;border-radius:12px;padding:13px;margin-top:8px;border:1px solid var(--line);background:#20242d;color:#fff}.panel .danger{color:#ff7777}</style></head><body>
<main><div class="top"><h1>Thư viện</h1><span id="count" class="meta"></span></div><button class="add" id="add">＋ Thêm link</button><div class="tabs"><button class="tab on" data-filter="all">Tất cả</button><button class="tab" data-filter="listening">Đang nghe</button><button class="tab" data-filter="done">Đã nghe</button></div><div id="list" class="list"></div></main>
<div id="player" class="player"><div id="ptitle" class="ptitle"></div><input id="timeline" class="timeline" type="range" min="0" max="100" value="0"><div class="controls"><button id="back">−15</button><button id="play" class="play">▶</button><button id="forward">+15</button></div><audio id="audio" playsinline preload="metadata"></audio></div>
<div id="sheet" class="sheet"><div class="panel"><h3 id="sheetTitle"></h3><button id="pin"></button><button id="delete" class="danger">Xóa audio</button><button id="close">Đóng</button></div></div>
<script>
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];const audio=$('#audio'),player=$('#player'),timeline=$('#timeline');let items=[],playing=null,sheetItem=null,filter='all',saveTimer=0;
function fmt(s){s=Math.max(0,Math.round(Number(s)||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}function daysLeft(x){if(!x)return'';return Math.max(0,Math.ceil((Date.parse(x)-Date.now())/86400000))}function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function api(path,opt={}){const r=await fetch(path,{...opt,headers:{'content-type':'application/json',...(opt.headers||{})}});if(r.status===204)return null;const d=await r.json();if(!r.ok)throw new Error(d.error||'Lỗi');return d}
async function load(){try{const d=await api('/api/items');items=d.items||[];render()}catch(e){console.error(e)}}function visible(i){if(filter==='done')return i.listened;if(filter==='listening')return i.status==='ready'&&!i.listened&&(i.progressSeconds||0)>0;return true}
function render(){const rows=items.filter(visible),list=$('#list');$('#count').textContent=items.length?items.length+' audio':'';if(!rows.length){list.innerHTML='<div class="empty">Chưa có audio.</div>';return}list.innerHTML=rows.map(i=>{const p=i.durationSeconds?Math.min(100,(i.progressSeconds||0)/i.durationSeconds*100):0;const state=i.status==='pending'?'Đang chờ xử lý…':i.status==='processing'?'Đang tạo MP3…':i.status==='error'?'Lỗi: '+(i.error||'Không xử lý được'):i.listened?'Đã nghe xong':(i.progressSeconds||0)>0?'Đã nghe '+fmt(i.progressSeconds)+' / '+fmt(i.durationSeconds):'Chưa nghe';const exp=i.pinned?' · Giữ lại':i.expiresAt?' · Xóa sau '+daysLeft(i.expiresAt)+' ngày':'';return '<div class="item" data-id="'+i.id+'"><h3>'+esc(i.title||i.sourceLabel)+'</h3><div class="meta">'+esc(i.sourceLabel||'Web')+(i.durationSeconds?' · '+fmt(i.durationSeconds):'')+exp+'</div><div class="state '+(i.status==='error'?'error':'')+'">'+esc(state)+'</div>'+(i.status==='ready'?'<div class="bar"><div class="fill" style="width:'+p.toFixed(1)+'%"></div></div>':'')+'<button class="more" data-more="'+i.id+'">⋯</button></div>'}).join('');$$('.item').forEach(el=>el.onclick=e=>{if(e.target.dataset.more)return;const i=items.find(x=>x.id===el.dataset.id);if(i?.status==='ready')playItem(i)});$$('[data-more]').forEach(b=>b.onclick=e=>{e.stopPropagation();openSheet(items.find(x=>x.id===b.dataset.more))})}
async function addLink(){const url=prompt('Dán link cần chuyển thành MP3');if(!url)return;try{await api('/api/items',{method:'POST',body:JSON.stringify({url})});await load()}catch(e){alert(e.message)}}
function playItem(i){playing=i;$('#ptitle').textContent=i.title;audio.src=i.audioUrl;player.classList.add('show');audio.addEventListener('loadedmetadata',()=>{const pos=Math.min(i.progressSeconds||0,Math.max(0,audio.duration-3));if(pos>2)audio.currentTime=pos;timeline.max=Math.max(1,audio.duration||i.durationSeconds||1);timeline.value=audio.currentTime;audio.play()}, {once:true})}function syncPlay(){$('#play').textContent=audio.paused?'▶':'Ⅱ'}async function saveProgress(){if(!playing||!Number.isFinite(audio.currentTime))return;playing.progressSeconds=audio.currentTime;playing.durationSeconds=audio.duration||playing.durationSeconds;try{await api('/api/items/'+playing.id+'/progress',{method:'POST',body:JSON.stringify({seconds:audio.currentTime,duration:audio.duration})})}catch{}}
audio.ontimeupdate=()=>{timeline.max=Math.max(1,audio.duration||1);timeline.value=audio.currentTime;if(Date.now()-saveTimer>5000){saveTimer=Date.now();saveProgress()}};audio.onplay=syncPlay;audio.onpause=()=>{syncPlay();saveProgress()};audio.onended=()=>{saveProgress();load()};timeline.oninput=()=>audio.currentTime=Number(timeline.value);$('#play').onclick=()=>audio.paused?audio.play():audio.pause();$('#back').onclick=()=>audio.currentTime=Math.max(0,audio.currentTime-15);$('#forward').onclick=()=>audio.currentTime=Math.min(audio.duration||Infinity,audio.currentTime+15);window.addEventListener('pagehide',saveProgress);
function openSheet(i){if(!i)return;sheetItem=i;$('#sheetTitle').textContent=i.title;$('#pin').textContent=i.pinned?'Bỏ giữ lại':'Giữ lại (không tự xóa)';$('#sheet').classList.add('show')}$('#close').onclick=()=>$('#sheet').classList.remove('show');$('#pin').onclick=async()=>{if(!sheetItem)return;await api('/api/items/'+sheetItem.id,{method:'PATCH',body:JSON.stringify({pinned:!sheetItem.pinned})});$('#sheet').classList.remove('show');load()};$('#delete').onclick=async()=>{if(!sheetItem||!confirm('Xóa audio này?'))return;await api('/api/items/'+sheetItem.id,{method:'DELETE'});if(playing?.id===sheetItem.id){audio.pause();player.classList.remove('show')}$('#sheet').classList.remove('show');load()};$('#add').onclick=addLink;$$('.tab').forEach(b=>b.onclick=()=>{$$('.tab').forEach(x=>x.classList.remove('on'));b.classList.add('on');filter=b.dataset.filter;render()});load();setInterval(load,15000);
</script></body></html>`;

async function handleFetch(request, env) {
  const url = new URL(request.url);
  if (url.pathname === '/health') return json({ ok: true, service: 'runner3-audio-library', access: 'public' });
  if (url.pathname === '/' && request.method === 'GET') return html(APP_HTML);
  if (url.pathname.startsWith('/api/runner/')) {
    if (!(await runnerAuthorized(request, env))) return json({ error: 'Unauthorized' }, 401);
    if (url.pathname === '/api/runner/next' && request.method === 'GET') return runnerNext(env);
    if (url.pathname === '/api/runner/complete' && request.method === 'POST') return runnerComplete(request, env);
    if (url.pathname === '/api/runner/fail' && request.method === 'POST') return runnerFail(request, env);
    return json({ error: 'Not found' }, 404);
  }
  if (url.pathname === '/api/items' && request.method === 'GET') return json({ items: await listItems(env) });
  if (url.pathname === '/api/items' && request.method === 'POST') return addItem(request, env);
  const match = url.pathname.match(/^\/api\/items\/([0-9a-f-]+)(?:\/(progress))?$/i);
  if (match) {
    const [, id, sub] = match;
    if (sub === 'progress' && request.method === 'POST') return updateProgress(request, env, id);
    if (!sub && request.method === 'PATCH') return updateItem(request, env, id);
    if (!sub && request.method === 'DELETE') { await deleteItem(env, id); return new Response(null, { status: 204 }); }
  }
  return new Response('Not found', { status: 404 });
}
export default {
  async fetch(request, env) { try { return await handleFetch(request, env); } catch (error) { console.error(JSON.stringify({ event: 'audio_library_error', message: String(error?.stack || error) })); return json({ error: 'Internal error' }, 500); } },
  async scheduled(_controller, env, ctx) { ctx.waitUntil(purgeExpired(env)); },
};
