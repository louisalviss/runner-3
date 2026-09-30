#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { TelegramClient, sessions } = require('teleproto');

const HOST = '127.0.0.1';
const PORT = 18820;
const INDEX = '/var/lib/telegram-media/library/library-index.jsonl';
const CACHE = '/var/cache/telegram-library-reader';
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;
const MAX_CACHE_BYTES = 1024 * 1024 * 1024;
const MAX_EPUB_BYTES = 128 * 1024 * 1024;
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,239}$/;

function reqEnv(name) {
  const v = String(process.env[name] || '').trim();
  if (!v) throw new Error(`MISSING_${name}`);
  return v;
}
function coreToken() {
  const direct = String(process.env.RUNNER3_CORE_TOKEN || '').trim();
  if (direct) return direct;
  const encoded = reqEnv('RUNNER3_CORE_TOKEN_B64');
  const value = Buffer.from(encoded, 'base64').toString('utf8').trim();
  if (!value) throw new Error('RUNNER3_CORE_TOKEN_EMPTY');
  return value;
}
function safeEqual(a, b) {
  const x = Buffer.from(String(a || ''));
  const y = Buffer.from(String(b || ''));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}
function json(res, status, body) {
  const data = Buffer.from(JSON.stringify(body));
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': String(data.length),
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(data);
}
function authOk(req) {
  const raw = String(req.headers.authorization || '');
  const supplied = raw.startsWith('Bearer ') ? raw.slice(7).trim() : '';
  return supplied && safeEqual(supplied, TOKEN);
}
function cachePath(id) {
  return path.join(CACHE, crypto.createHash('sha256').update(id).digest('hex') + '.epub');
}

let indexMtime = 0;
let indexMap = new Map();
function refreshIndex(force = false) {
  const st = fs.statSync(INDEX);
  if (!force && st.mtimeMs === indexMtime) return;
  const next = new Map();
  for (const line of fs.readFileSync(INDEX, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    let row;
    try { row = JSON.parse(line); } catch { continue; }
    if (row?.category !== 'ebook' || String(row?.format || '').toLowerCase() !== 'epub') continue;
    const id = String(row.library_id || '');
    const msg = Number(row.message_id || 0);
    const chat = String(row.chat_id || '');
    if (!ID_RE.test(id) || !chat || !Number.isInteger(msg) || msg <= 0) continue;
    next.set(id, { library_id:id, chat_id:chat, message_id:msg, file_name:String(row.file_name || `${id}.epub`), size:Number(row.size || 0) });
  }
  indexMap = next;
  indexMtime = st.mtimeMs;
  console.log(JSON.stringify({event:'index_loaded', epub:indexMap.size}));
}
function pruneCache() {
  fs.mkdirSync(CACHE, {recursive:true, mode:0o700});
  const now = Date.now();
  const files = [];
  let total = 0;
  for (const name of fs.readdirSync(CACHE)) {
    const p = path.join(CACHE, name);
    let st;
    try { st = fs.statSync(p); } catch { continue; }
    if (!st.isFile()) continue;
    if (name.endsWith('.part') || now - st.mtimeMs > CACHE_TTL_MS) {
      try { fs.unlinkSync(p); } catch {}
      continue;
    }
    if (name.endsWith('.epub')) { files.push({p,mtime:st.mtimeMs,size:st.size}); total += st.size; }
  }
  files.sort((a,b)=>a.mtime-b.mtime);
  for (const f of files) {
    if (total <= MAX_CACHE_BYTES) break;
    try { fs.unlinkSync(f.p); total -= f.size; } catch {}
  }
}

async function openClient() {
  const apiId = Number(reqEnv('TG_API_ID'));
  if (!Number.isInteger(apiId) || apiId <= 0) throw new Error('INVALID_TG_API_ID');
  const next = new TelegramClient(new sessions.StringSession(reqEnv('TG_STRING_SESSION')), apiId, reqEnv('TG_API_HASH'), {
    connectionRetries: 5,
    autoReconnect: true,
  });
  await next.connect();
  if (!(await next.checkAuthorization())) throw new Error('SESSION_NOT_AUTHORIZED');
  // All EPUBs currently live in one private channel. Warming dialogs here
  // gives Teleproto the channel access_hash again after a reconnect/restart.
  await next.getDialogs({limit:100});
  entityWarmAt = Date.now();
  return next;
}

let entityWarmAt = 0;
let reconnecting = null;
async function ensureClientReady(force = false) {
  if (!force && client) {
    try {
      await client.connect();
      if (!(await client.checkAuthorization())) throw new Error('SESSION_NOT_AUTHORIZED');
      if (Date.now() - entityWarmAt > 10 * 60 * 1000) {
        await client.getDialogs({limit:100});
        entityWarmAt = Date.now();
      }
      return client;
    } catch (error) {
      console.warn(JSON.stringify({event:'client_reconnect_needed',error:String(error?.message || error).slice(0,180)}));
    }
  }
  if (reconnecting) return reconnecting;
  reconnecting = (async()=>{
    const previous = client;
    const next = await openClient();
    client = next;
    if (previous && previous !== next) {
      try { await previous.disconnect(); } catch {}
    }
    console.log(JSON.stringify({event:'client_reconnected'}));
    return next;
  })();
  try { return await reconnecting; }
  finally { reconnecting = null; }
}

async function fetchTelegramMessage(row) {
  let lastError = null;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const active = await ensureClientReady(attempt > 0);
      const found = await active.getMessages(row.chat_id, {ids:row.message_id});
      const msg = found?.[0];
      if (!msg) throw new Error('MESSAGE_NOT_FOUND');
      return msg;
    } catch (error) {
      lastError = error;
      console.warn(JSON.stringify({event:'telegram_message_retry',attempt:attempt+1,error:String(error?.message || error).slice(0,180)}));
      entityWarmAt = 0;
    }
  }
  throw lastError || new Error('MESSAGE_FETCH_FAILED');
}

const pending = new Map();
async function materialize(row) {
  const dest = cachePath(row.library_id);
  try {
    const st = fs.statSync(dest);
    if (st.isFile() && st.size > 0 && st.size <= MAX_EPUB_BYTES && Date.now() - st.mtimeMs < CACHE_TTL_MS) {
      fs.utimesSync(dest, new Date(), new Date());
      return dest;
    }
  } catch {}
  if (pending.has(row.library_id)) return pending.get(row.library_id);
  const task = (async()=>{
    const tmp = dest + `.part.${process.pid}.${Date.now()}`;
    try {
      const msg = await fetchTelegramMessage(row);
      const mediaName = String(msg?.file?.name || row.file_name || 'book.epub');
      if (!mediaName.toLowerCase().endsWith('.epub')) throw new Error('NOT_EPUB_MEDIA');
      await msg.downloadMedia({outputFile:tmp});
      const st = fs.statSync(tmp);
      if (!st.isFile() || st.size <= 0 || st.size > MAX_EPUB_BYTES) throw new Error('INVALID_EPUB_SIZE');
      fs.renameSync(tmp, dest);
      return dest;
    } finally {
      try { fs.unlinkSync(tmp); } catch {}
    }
  })();
  pending.set(row.library_id, task);
  try { return await task; } finally { pending.delete(row.library_id); }
}

function streamFile(req, res, file, row) {
  const st = fs.statSync(file);
  res.writeHead(200, {
    'Content-Type': 'application/epub+zip',
    'Content-Length': String(st.size),
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  fs.createReadStream(file).pipe(res);
}

const TOKEN = coreToken();
let client;
(async()=>{
  fs.mkdirSync(CACHE, {recursive:true, mode:0o700});
  refreshIndex(true);
  pruneCache();
  client = await openClient();
  const server = http.createServer(async (req,res)=>{
    try {
      const u = new URL(req.url, `http://${HOST}:${PORT}`);
      if (req.method === 'GET' && u.pathname === '/health') {
        return json(res, 200, {ok:true, authorized:true, epub:indexMap.size, pending:pending.size});
      }
      if (req.method !== 'GET' || u.pathname !== '/epub') return json(res,404,{ok:false,error:'NOT_FOUND'});
      if (!authOk(req)) return json(res,401,{ok:false,error:'UNAUTHORIZED'});
      refreshIndex();
      const id = String(u.searchParams.get('library_id') || '');
      if (!ID_RE.test(id)) return json(res,400,{ok:false,error:'INVALID_LIBRARY_ID'});
      const row = indexMap.get(id);
      if (!row) return json(res,404,{ok:false,error:'EPUB_NOT_INDEXED'});
      const file = await materialize(row);
      return streamFile(req,res,file,row);
    } catch (err) {
      console.error(JSON.stringify({event:'request_error',error:String(err?.message || err).slice(0,240)}));
      if (!res.headersSent) return json(res,502,{ok:false,error:'TELEGRAM_MEDIA_FETCH_FAILED'});
      try { res.destroy(); } catch {}
    }
  });
  server.listen(PORT, HOST, ()=>console.log(JSON.stringify({event:'listening',host:HOST,port:PORT,epub:indexMap.size})));
  setInterval(()=>{ try { refreshIndex(); pruneCache(); } catch (e) { console.error(JSON.stringify({event:'maintenance_error',error:String(e?.message||e)})); } }, 15*60*1000).unref();
})().catch(err=>{ console.error(String(err?.stack || err)); process.exit(1); });
