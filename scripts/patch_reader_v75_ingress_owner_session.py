from pathlib import Path

P=Path('cloudflare/runner3-core/artifact-library-reader-v7-github-audio-entry.js')
s=P.read_text(encoding='utf-8')
if "R3_READER_INGRESS_SESSION_V75='v75'" in s:
    print('READER_V75_INGRESS_OWNER_SESSION=ALREADY_APPLIED')
    raise SystemExit(0)

anchor='const EBOOK_AUDIO_INTERNAL_PREFIX = "/api/internal/ebook-reader-audio/";\n'
if anchor not in s: raise SystemExit('V75_CONST_ANCHOR_MISSING')
s=s.replace(anchor,anchor+'''const R3_READER_INGRESS_SESSION_V75='v75';
const R3_LIBRARY_COOKIE_V75='r3_artifact_library';
''',1)

helper_anchor='''function safeEqual(a, b) {
  const left = String(a || "");
  const right = String(b || "");
  if (!left || left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i++) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}
'''
if helper_anchor not in s: raise SystemExit('V75_SAFE_EQUAL_ANCHOR_MISSING')
helpers=helper_anchor+'''
function r3BrowserCookieV75(request,name){
  const raw=String(request.headers.get('cookie')||'');
  for(const part of raw.split(';')){const i=part.indexOf('=');if(i>=0&&part.slice(0,i).trim()===name)return part.slice(i+1).trim()}
  return '';
}
async function r3ExpectedLibrarySessionV75(env){
  const token=String(env.RUNNER3_CORE_TOKEN||'').trim();if(!token)return '';
  const bytes=new TextEncoder().encode('runner3-artifact-library-v1:'+token);
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
}
async function r3HasOwnerSessionV75(request,env){
  const expected=await r3ExpectedLibrarySessionV75(env);
  return Boolean(expected)&&safeEqual(r3BrowserCookieV75(request,R3_LIBRARY_COOKIE_V75),expected);
}
function r3OwnerLoginRedirectV75(request){
  const url=new URL(request.url);const target=new URL('/artifact-library',url);
  return new Response(null,{status:303,headers:{Location:target.toString(),'Cache-Control':'private, no-store','X-R3-Session-Bound-Sync':'v75-login-required','X-Robots-Tag':ROBOTS}});
}
'''
s=s.replace(helper_anchor,helpers,1)

fetch_anchor='''  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/healthz") {'''
fetch_repl='''  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/artifact-library/read' && !(await r3HasOwnerSessionV75(request,env))) {
      return r3OwnerLoginRedirectV75(request);
    }
    if (request.method === "GET" && url.pathname === "/healthz") {'''
if fetch_anchor not in s: raise SystemExit('V75_FETCH_ANCHOR_MISSING')
s=s.replace(fetch_anchor,fetch_repl,1)

for m in ["R3_READER_INGRESS_SESSION_V75='v75'",'r3HasOwnerSessionV75','v75-login-required',"url.pathname === '/artifact-library/read'"]:
    if m not in s: raise SystemExit('V75_MARKER_MISSING:'+m)
P.write_text(s,encoding='utf-8')
print('READER_V75_INGRESS_OWNER_SESSION=PASS')
