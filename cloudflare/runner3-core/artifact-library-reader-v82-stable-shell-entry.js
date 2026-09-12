import app from "./artifact-library-reader-v36-home-screen-safe-area-entry.js";
import cleanIosApp from "./artifact-library-reader-ios-clean-entry.js";
import { patchReaderV82 } from "./artifact-library-reader-v82-patch.js";
export { r3StableEarlyV82, r3StableRuntimeV82, patchReaderV82 } from "./artifact-library-reader-v82-patch.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const R3_READER_TRACE_V113 = 'v113';
let r3TraceInitV113 = null;
function r3TraceSafeEqualV113(a,b){const x=String(a||''),y=String(b||'');if(!x||x.length!==y.length)return false;let d=0;for(let i=0;i<x.length;i++)d|=x.charCodeAt(i)^y.charCodeAt(i);return d===0}
function r3TraceCookieV113(request,name){const raw=String(request.headers.get('cookie')||'');for(const part of raw.split(';')){const i=part.indexOf('=');if(i>=0&&part.slice(0,i).trim()===name)return part.slice(i+1).trim()}return ''}
async function r3TraceExpectedSessionV113(env){const token=String(env.RUNNER3_CORE_TOKEN||'').trim();if(!token)return '';const bytes=new TextEncoder().encode('runner3-artifact-library-v1:'+token);const digest=await crypto.subtle.digest('SHA-256',bytes);return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('')}
async function r3TraceAuthorizedV113(request,env){const expected=await r3TraceExpectedSessionV113(env);return Boolean(expected)&&r3TraceSafeEqualV113(r3TraceCookieV113(request,'r3_artifact_library'),expected)}
function r3TraceJsonV113(data,status=200){return new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'private, no-store','x-r3-reader-trace':R3_READER_TRACE_V113,'x-robots-tag':ROBOTS}})}
async function r3EnsureTraceTableV113(env){
  if(!env.DB)throw new Error('DB_BINDING_MISSING');
  if(!r3TraceInitV113)r3TraceInitV113=(async()=>{
    await env.DB.prepare(`CREATE TABLE IF NOT EXISTS ebook_reader_trace_v113(
      trace_id TEXT NOT NULL,seq INTEGER NOT NULL,created_at INTEGER NOT NULL,
      scope TEXT NOT NULL DEFAULT '',mode TEXT NOT NULL DEFAULT '',event TEXT NOT NULL DEFAULT '',payload TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(trace_id,seq))`).run();
    await env.DB.prepare('CREATE INDEX IF NOT EXISTS idx_ebook_reader_trace_v113_created ON ebook_reader_trace_v113(created_at DESC)').run();
  })().catch(error=>{r3TraceInitV113=null;throw error});
  return r3TraceInitV113;
}
function r3TraceScopeV113(key){const p=String(key||'').split('/');return p[0]==='core'&&p[1]==='ebook'?String(p[2]||'').slice(0,120):''}
async function r3HandleTraceV113(request,env){
  if(request.method!=='POST')return r3TraceJsonV113({ok:false,error:'METHOD_NOT_ALLOWED'},405);
  if(!(await r3TraceAuthorizedV113(request,env)))return r3TraceJsonV113({ok:false,error:'UNAUTHORIZED'},401);
  let body;try{body=await request.json()}catch{return r3TraceJsonV113({ok:false,error:'INVALID_JSON'},400)}
  const traceId=String(body&&body.trace_id||'').slice(0,80),seq=Math.max(0,Math.min(1000,Math.trunc(Number(body&&body.seq||0)))),event=String(body&&body.event||'').replace(/[^a-zA-Z0-9_.:-]/g,'').slice(0,80),mode=String(body&&body.mode||'').replace(/[^a-zA-Z0-9_.:-]/g,'').slice(0,40),createdAt=Math.max(1,Math.trunc(Number(body&&body.created_at||Date.now()))),scope=r3TraceScopeV113(body&&body.book_key);
  if(!/^[a-zA-Z0-9_-]{12,80}$/.test(traceId)||!event)return r3TraceJsonV113({ok:false,error:'INVALID_TRACE'},400);
  let payload='{}';try{payload=JSON.stringify(body&&body.payload&&typeof body.payload==='object'?body.payload:{}).slice(0,3500)}catch{}
  try{
    await r3EnsureTraceTableV113(env);
    await env.DB.prepare('INSERT OR REPLACE INTO ebook_reader_trace_v113(trace_id,seq,created_at,scope,mode,event,payload) VALUES(?1,?2,?3,?4,?5,?6,?7)').bind(traceId,seq,createdAt,scope,mode,event,payload).run();
    if(seq===0||seq%20===0){try{await env.DB.prepare('DELETE FROM ebook_reader_trace_v113 WHERE created_at < ?1').bind(Date.now()-172800000).run()}catch{}}
    return r3TraceJsonV113({ok:true,trace_version:R3_READER_TRACE_V113});
  }catch(error){return r3TraceJsonV113({ok:false,error:'TRACE_WRITE_FAILED',detail:String(error&&error.message||error).slice(0,160)},503)}
}


export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if(url.pathname==='/artifact-library/api/client-trace') return r3HandleTraceV113(request,env);
    const ua = String(request.headers.get('user-agent') || '');
    const cleanIos = request.method === 'GET' && url.pathname === '/artifact-library/read' && url.searchParams.get('legacy') !== '1' && (url.searchParams.get('clean') === '1' || /iPhone|iPad|iPod/i.test(ua));
    const response = cleanIos ? await cleanIosApp.fetch(request, env, ctx) : await app.fetch(request, env, ctx);
    if (request.method !== 'GET' || url.pathname !== '/artifact-library/read' || cleanIos) return response;
    const type = response.headers.get('Content-Type') || '';
    if (response.status !== 200 || !type.toLowerCase().includes('text/html')) return response;
    try {
      const updated = patchReaderV82(await response.text());
      const headers = new Headers(response.headers);
      headers.delete('Content-Length');
      headers.set('X-Robots-Tag', ROBOTS);
      headers.set('X-R3-Reader-Stable-Shell', 'v82');
      headers.set('X-R3-Reader-Pagination-Owner', 'v82');
      headers.set('X-R3-Reader-Restore-Guard', 'nonblocking-v89');
      headers.set('X-R3-Reader-Layout-Owner', 'converged-v90');
      headers.set('X-R3-Reader-Interaction-Owner', 'single-v92');
      headers.set('X-R3-Reader-WebKit-Runtime', 'compat-v93');
      headers.set('X-R3-Reader-Frame-Bind', 'relocated-v94');
      headers.set('X-R3-Reader-Touch-Owner', 'hybrid-v96');
      headers.set('X-R3-Reader-Input-Unblock', 'source-v98');
      headers.set('X-R3-Reader-Responsiveness', 'event-driven-v100');
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader stable shell v82 patch failed', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-R3-Reader-Stable-Shell': 'v82-patch-failed', 'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 200) } });
    }
  },
  async scheduled(controller, env, ctx) { if (typeof app.scheduled === 'function') return app.scheduled(controller, env, ctx); },
};
