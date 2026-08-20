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
async function downloadItem(env, id) {
  const item = await getJsonObject(env.AUDIO_BUCKET, itemKey(id));
  if (!item || item.status !== 'ready') return json({ error: 'Audio chưa sẵn sàng' }, 404);
  const prefix = item.mediaPrefix || `${MEDIA_PREFIX}${id}/`;
  const object = await env.AUDIO_BUCKET.get(prefix + 'episode.mp3');
  if (!object || !object.body) return json({ error: 'Không tìm thấy MP3' }, 404);
  const title = String(item.title || 'audio').replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 100) || 'audio';
  const headers = new Headers();
  headers.set('content-type', 'audio/mpeg');
  headers.set('content-disposition', `attachment; filename*=UTF-8''${encodeURIComponent(title + '.mp3')}`);
  headers.set('cache-control', 'private, max-age=0, no-store');
  if (object.size) headers.set('content-length', String(object.size));
  return new Response(object.body, { headers });
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

const APP_HTML = `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#000000"><title>Audio Library</title><style>
:root{color-scheme:dark;--bg:#000;--card:#090909;--card2:#0d0d0d;--line:#262626;--line2:#343434;--text:#f5f5f5;--muted:#8d8d93;--accent:#fff;--danger:#ff6b6b;--surface:#050505}*{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden;background:#000}body{color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%;overscroll-behavior:none}button,input,select{font:inherit}button{cursor:pointer}.app{width:100%;max-width:680px;height:100dvh;min-height:100%;margin:0 auto;display:flex;flex-direction:column;overflow:hidden;background:#000}.head{flex:0 0 auto;padding:calc(14px + env(safe-area-inset-top)) 14px 0;background:#000;z-index:2}.top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 2px 12px}.top h1{font-size:25px;line-height:1.15;margin:0;letter-spacing:-.03em}.topright{display:flex;align-items:center;gap:9px}.meta{font-size:12px;color:var(--muted);white-space:nowrap}.selectbtn{height:34px;border:1px solid var(--line2);border-radius:10px;background:#0a0a0a;color:#fff;padding:0 11px;font-weight:650}.selectbtn.on{background:#fff;color:#000;border-color:#fff}.addform{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;margin-bottom:12px}.urlinput{width:100%;min-width:0;height:46px;border:1px solid var(--line2);border-radius:12px;background:#080808;color:var(--text);padding:0 13px;outline:none}.urlinput:focus{border-color:#6b6b6b;box-shadow:0 0 0 3px #ffffff0d}.submit{height:46px;min-width:84px;border:0;border-radius:12px;background:#fff;color:#000;font-weight:750;padding:0 15px}.submit:disabled{opacity:.55;cursor:default}.tabs{display:flex;gap:6px;padding-bottom:10px;overflow-x:auto;scrollbar-width:none}.tabs::-webkit-scrollbar{display:none}.tab{flex:0 0 auto;border:1px solid var(--line);background:#030303;color:var(--muted);padding:8px 11px;border-radius:10px}.tab.on{background:#171717;color:#fff;border-color:#3a3a3a}.viewport{flex:1 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;padding:2px 14px 14px}.list{display:grid;gap:9px;min-width:0}.item{position:relative;min-width:0;background:var(--card);border:1px solid var(--line);border-radius:15px;padding:14px 13px 12px;transition:border-color .15s,background .15s}.item.selected{border-color:#777;background:#111}.itemmain{display:flex;gap:11px;align-items:flex-start;min-width:0}.check{display:none;flex:0 0 24px;width:24px;height:24px;border:1px solid #555;border-radius:50%;align-items:center;justify-content:center;margin-top:1px;color:#000;background:#060606;font-size:14px;font-weight:800}.selectmode .check{display:flex}.item.selected .check{background:#fff;border-color:#fff}.item.selected .check:after{content:'✓'}.itemcontent{min-width:0;flex:1}.item h3{font-size:16px;line-height:1.3;margin:0 0 5px;max-width:100%;overflow-wrap:anywhere}.state{font-size:13px;margin-top:7px;color:#b6b6bb}.state.error{color:var(--danger)}.bar{height:4px;background:#262626;border-radius:99px;overflow:hidden;margin-top:11px}.fill{height:100%;background:#e8e8e8}.actions{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-top:11px}.action{height:35px;border:1px solid var(--line);border-radius:10px;background:#0d0d0d;color:#d8d8dc;font-size:12px;padding:0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.action:active{background:#1b1b1b}.action.danger{color:#ff7777}.action.pinned{color:#fff;border-color:#555;background:#171717}.action:disabled{opacity:.35}.selectmode .actions{display:none}.empty{text-align:center;color:var(--muted);padding:34px 12px}.bulk{flex:0 0 auto;display:none;align-items:center;gap:6px;background:#080808;border-top:1px solid var(--line);padding:9px 10px;z-index:4}.bulk.show{display:flex}.bulkcount{min-width:54px;font-size:12px;color:var(--muted);padding-left:3px}.bulk button{flex:1;height:38px;border:1px solid var(--line);border-radius:10px;background:#111;color:#eee;font-size:12px;padding:0 5px}.bulk .danger{color:#ff7777}.player{flex:0 0 auto;display:none;background:#030303;border-top:1px solid #242424;box-shadow:0 -12px 32px #000c;padding:10px 14px calc(11px + env(safe-area-inset-bottom));z-index:3}.player.show{display:block}.playerhead{display:flex;align-items:center;gap:10px;margin-bottom:6px}.wave{width:38px;height:38px;border:1px solid #282828;border-radius:11px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:19px;background:#090909}.ptitle{flex:1;min-width:0;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.speed{height:32px;border:1px solid #303030;border-radius:9px;background:#111;color:#fff;padding:0 8px}.timeline{display:block;width:100%;margin:0;accent-color:#fff}.timebar{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:1px}.controls{display:flex;justify-content:center;gap:36px;align-items:center;margin-top:0}.controls button{border:0;background:transparent;color:#f5f5f5;font-size:14px;min-width:46px;height:44px}.controls .play{width:48px;height:48px;border-radius:50%;background:#fff;color:#000;font-size:18px;min-width:48px;font-weight:800}.toast{position:fixed;left:50%;bottom:calc(18px + env(safe-area-inset-bottom));transform:translate(-50%,20px);background:#fff;color:#000;border-radius:999px;padding:9px 14px;font-size:13px;font-weight:650;opacity:0;pointer-events:none;transition:.2s;z-index:20;white-space:nowrap}.toast.show{opacity:1;transform:translate(-50%,0)}@media(max-width:430px){.head{padding-left:12px;padding-right:12px}.viewport{padding-left:12px;padding-right:12px}.player{padding-left:12px;padding-right:12px}.top h1{font-size:23px}.submit{min-width:76px;padding:0 12px}.controls{gap:28px}.action{font-size:11px}.bulk button{font-size:11px}}
</style></head><body><div class="app" id="app">
<header class="head"><div class="top"><h1>Thư viện</h1><div class="topright"><span id="count" class="meta"></span><button id="selectBtn" class="selectbtn" type="button">Chọn</button></div></div><form id="addForm" class="addform"><input id="urlInput" class="urlinput" type="url" inputmode="url" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Dán link Reddit, YouTube, X, bài viết…" required><button id="submit" class="submit" type="submit">Thêm</button></form><div class="tabs"><button class="tab on" data-filter="all" type="button">Tất cả</button><button class="tab" data-filter="listening" type="button">Đang nghe</button><button class="tab" data-filter="done" type="button">Đã nghe</button></div></header>
<main class="viewport"><div id="list" class="list"></div></main>
<div id="bulk" class="bulk"><div id="bulkCount" class="bulkcount">0 chọn</div><button id="bulkShare" type="button">Chia sẻ</button><button id="bulkDownload" type="button">Tải</button><button id="bulkPin" type="button">Giữ lại</button><button id="bulkDelete" class="danger" type="button">Xóa</button></div>
<div id="player" class="player"><div class="playerhead"><div class="wave">▥</div><div id="ptitle" class="ptitle"></div><select id="speed" class="speed" aria-label="Tốc độ phát"><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="1.75">1.75×</option><option value="2">2×</option></select></div><input id="timeline" class="timeline" type="range" min="0" max="100" value="0" step="0.1"><div class="timebar"><span id="elapsed">0:00</span><span id="duration">0:00</span></div><div class="controls"><button id="back" type="button">↶ 15</button><button id="play" class="play" type="button">▶</button><button id="forward" type="button">15 ↷</button></div><audio id="audio" playsinline preload="metadata"></audio></div>
</div><div id="toast" class="toast"></div><script>
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];const app=$('#app'),audio=$('#audio'),player=$('#player'),timeline=$('#timeline'),speed=$('#speed'),urlInput=$('#urlInput'),submit=$('#submit'),bulk=$('#bulk');let items=[],playing=null,filter='all',saveTimer=0,selectMode=false,selected=new Set(),toastTimer=0;
function fmt(s){s=Math.max(0,Math.round(Number(s)||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}function daysLeft(x){if(!x)return'';return Math.max(0,Math.ceil((Date.parse(x)-Date.now())/86400000))}function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),1500)}
async function api(path,opt={}){const headers={...(opt.headers||{})};if(opt.body)headers['content-type']='application/json';const r=await fetch(path,{...opt,headers});if(r.status===204)return null;const ct=r.headers.get('content-type')||'';const d=ct.includes('application/json')?await r.json():null;if(!r.ok)throw new Error(d?.error||'Lỗi');return d}
async function load(){try{const d=await api('/api/items');items=d.items||[];for(const id of [...selected])if(!items.some(i=>i.id===id))selected.delete(id);render()}catch(e){console.error(e)}}function visible(i){if(filter==='done')return i.listened;if(filter==='listening')return i.status==='ready'&&!i.listened&&(i.progressSeconds||0)>0;return true}function selectedItems(){return items.filter(i=>selected.has(i.id))}
function render(){const rows=items.filter(visible),list=$('#list');$('#count').textContent=items.length?items.length+' audio':'';app.classList.toggle('selectmode',selectMode);$('#selectBtn').textContent=selectMode?'Xong':'Chọn';$('#selectBtn').classList.toggle('on',selectMode);bulk.classList.toggle('show',selectMode);$('#bulkCount').textContent=selected.size+' chọn';if(!rows.length){list.innerHTML='<div class="empty">Chưa có audio.</div>';return}list.innerHTML=rows.map(i=>{const p=i.durationSeconds?Math.min(100,(i.progressSeconds||0)/i.durationSeconds*100):0;const state=i.status==='pending'?'Đang chờ xử lý…':i.status==='processing'?'Đang tạo MP3…':i.status==='error'?'Lỗi: '+(i.error||'Không xử lý được'):i.listened?'Đã nghe xong':(i.progressSeconds||0)>0?'Đã nghe '+fmt(i.progressSeconds)+' / '+fmt(i.durationSeconds):'Chưa nghe';const exp=i.pinned?' · Giữ lại':i.expiresAt?' · Xóa sau '+daysLeft(i.expiresAt)+' ngày':'';const ready=i.status==='ready';return '<div class="item '+(selected.has(i.id)?'selected':'')+'" data-id="'+i.id+'"><div class="itemmain"><div class="check"></div><div class="itemcontent"><h3>'+esc(i.title||i.sourceLabel)+'</h3><div class="meta">'+esc(i.sourceLabel||'Web')+(i.durationSeconds?' · '+fmt(i.durationSeconds):'')+exp+'</div><div class="state '+(i.status==='error'?'error':'')+'">'+esc(state)+'</div>'+(ready?'<div class="bar"><div class="fill" style="width:'+p.toFixed(1)+'%"></div></div>':'')+'<div class="actions"><button class="action" data-act="share" data-id="'+i.id+'" '+(ready?'':'disabled')+'>Chia sẻ</button><button class="action" data-act="download" data-id="'+i.id+'" '+(ready?'':'disabled')+'>Tải</button><button class="action '+(i.pinned?'pinned':'')+'" data-act="pin" data-id="'+i.id+'">'+(i.pinned?'Bỏ giữ':'Giữ lại')+'</button><button class="action danger" data-act="delete" data-id="'+i.id+'">Xóa</button></div></div></div></div>'}).join('');$$('.item').forEach(el=>el.onclick=e=>{if(e.target.closest('[data-act]'))return;const i=items.find(x=>x.id===el.dataset.id);if(!i)return;if(selectMode){toggleSelect(i.id);return}if(i.status==='ready')playItem(i)});$$('[data-act]').forEach(b=>b.onclick=e=>{e.stopPropagation();const i=items.find(x=>x.id===b.dataset.id);if(!i)return;const a=b.dataset.act;if(a==='share')shareOne(i);if(a==='download')downloadOne(i);if(a==='pin')pinOne(i);if(a==='delete')deleteOne(i)})}
function toggleSelect(id){selected.has(id)?selected.delete(id):selected.add(id);render()}function setSelectMode(on){selectMode=on;if(!on)selected.clear();render()}
async function addLink(url){url=String(url||'').trim();if(!url)return;submit.disabled=true;const old=submit.textContent;submit.textContent='Đang thêm…';try{const d=await api('/api/items',{method:'POST',body:JSON.stringify({url})});urlInput.value='';await load();if(d?.duplicate)toast('Link đã có trong thư viện')}catch(e){alert(e.message)}finally{submit.disabled=false;submit.textContent=old}}
async function shareOne(i){const url=i.audioUrl||i.sourceUrl;try{if(navigator.share)await navigator.share({title:i.title||'Audio',text:i.title||'Audio',url});else{await navigator.clipboard.writeText(url);toast('Đã sao chép link')}}catch(e){if(e?.name!=='AbortError')console.error(e)}}
function downloadOne(i){if(i.status!=='ready')return;const a=document.createElement('a');a.href='/api/items/'+i.id+'/download';a.download='';document.body.appendChild(a);a.click();a.remove()}
async function pinOne(i){try{await api('/api/items/'+i.id,{method:'PATCH',body:JSON.stringify({pinned:!i.pinned})});await load();toast(i.pinned?'Đã bỏ giữ':'Đã giữ lại')}catch(e){alert(e.message)}}
async function deleteOne(i){if(!confirm('Xóa audio này?'))return;try{await api('/api/items/'+i.id,{method:'DELETE'});if(playing?.id===i.id){audio.pause();player.classList.remove('show');playing=null}await load()}catch(e){alert(e.message)}}
async function bulkShare(){const arr=selectedItems().filter(i=>i.status==='ready');if(!arr.length)return toast('Chưa chọn audio sẵn sàng');const nl=String.fromCharCode(10);const text=arr.map(i=>(i.title||'Audio')+nl+(i.audioUrl||i.sourceUrl)).join(nl+nl);try{if(navigator.share)await navigator.share({title:arr.length+' audio',text});else{await navigator.clipboard.writeText(text);toast('Đã sao chép '+arr.length+' link')}}catch(e){if(e?.name!=='AbortError')console.error(e)}}
function bulkDownload(){const arr=selectedItems().filter(i=>i.status==='ready');if(!arr.length)return toast('Chưa chọn audio sẵn sàng');arr.forEach((i,n)=>setTimeout(()=>{const f=document.createElement('iframe');f.style.display='none';f.src='/api/items/'+i.id+'/download';document.body.appendChild(f);setTimeout(()=>f.remove(),20000)},n*350));toast('Đang tải '+arr.length+' audio')}
async function bulkPin(){const arr=selectedItems();if(!arr.length)return toast('Chưa chọn audio');try{await Promise.all(arr.map(i=>api('/api/items/'+i.id,{method:'PATCH',body:JSON.stringify({pinned:true})})));await load();toast('Đã giữ '+arr.length+' audio')}catch(e){alert(e.message)}}
async function bulkDelete(){const arr=selectedItems();if(!arr.length)return toast('Chưa chọn audio');if(!confirm('Xóa '+arr.length+' audio đã chọn?'))return;try{for(const i of arr){await api('/api/items/'+i.id,{method:'DELETE'});if(playing?.id===i.id){audio.pause();player.classList.remove('show');playing=null}}selected.clear();await load();toast('Đã xóa '+arr.length+' audio')}catch(e){alert(e.message)}}
function applySpeed(){const r=Number(speed.value)||1;audio.playbackRate=r;localStorage.setItem('audio-library-speed',String(r))}function updateTimes(){$('#elapsed').textContent=fmt(audio.currentTime);$('#duration').textContent=fmt(audio.duration||playing?.durationSeconds||0)}
function playItem(i){playing=i;$('#ptitle').textContent=i.title;audio.src=i.audioUrl;player.classList.add('show');applySpeed();audio.addEventListener('loadedmetadata',()=>{const pos=Math.min(i.progressSeconds||0,Math.max(0,audio.duration-3));if(pos>2)audio.currentTime=pos;timeline.max=Math.max(1,audio.duration||i.durationSeconds||1);timeline.value=audio.currentTime;updateTimes();audio.play()}, {once:true})}function syncPlay(){$('#play').textContent=audio.paused?'▶':'Ⅱ'}async function saveProgress(){if(!playing||!Number.isFinite(audio.currentTime))return;playing.progressSeconds=audio.currentTime;playing.durationSeconds=audio.duration||playing.durationSeconds;try{await api('/api/items/'+playing.id+'/progress',{method:'POST',body:JSON.stringify({seconds:audio.currentTime,duration:audio.duration})})}catch{}}
audio.ontimeupdate=()=>{timeline.max=Math.max(1,audio.duration||1);timeline.value=audio.currentTime;updateTimes();if(Date.now()-saveTimer>5000){saveTimer=Date.now();saveProgress()}};audio.onloadedmetadata=updateTimes;audio.onplay=syncPlay;audio.onpause=()=>{syncPlay();saveProgress()};audio.onended=()=>{saveProgress();load()};timeline.oninput=()=>{audio.currentTime=Number(timeline.value);updateTimes()};speed.value=localStorage.getItem('audio-library-speed')||'1';speed.onchange=applySpeed;$('#play').onclick=()=>audio.paused?audio.play():audio.pause();$('#back').onclick=()=>audio.currentTime=Math.max(0,audio.currentTime-15);$('#forward').onclick=()=>audio.currentTime=Math.min(audio.duration||Infinity,audio.currentTime+15);window.addEventListener('pagehide',saveProgress);
$('#selectBtn').onclick=()=>setSelectMode(!selectMode);$('#bulkShare').onclick=bulkShare;$('#bulkDownload').onclick=bulkDownload;$('#bulkPin').onclick=bulkPin;$('#bulkDelete').onclick=bulkDelete;$('#addForm').onsubmit=e=>{e.preventDefault();addLink(urlInput.value)};$$('.tab').forEach(b=>b.onclick=()=>{$$('.tab').forEach(x=>x.classList.remove('on'));b.classList.add('on');filter=b.dataset.filter;render()});load();setInterval(load,15000);
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
  const match = url.pathname.match(/^\/api\/items\/([0-9a-f-]+)(?:\/(progress|download))?$/i);
  if (match) {
    const [, id, sub] = match;
    if (sub === 'progress' && request.method === 'POST') return updateProgress(request, env, id);
    if (sub === 'download' && request.method === 'GET') return downloadItem(env, id);
    if (!sub && request.method === 'PATCH') return updateItem(request, env, id);
    if (!sub && request.method === 'DELETE') { await deleteItem(env, id); return new Response(null, { status: 204 }); }
  }
  return new Response('Not found', { status: 404 });
}
export default {
  async fetch(request, env) { try { return await handleFetch(request, env); } catch (error) { console.error(JSON.stringify({ event: 'audio_library_error', message: String(error?.stack || error) })); return json({ error: 'Internal error' }, 500); } },
  async scheduled(_controller, env, ctx) { ctx.waitUntil(purgeExpired(env)); },
};