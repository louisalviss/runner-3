from pathlib import Path
ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
PIN=ROOT/'artifact-library-pin-v2-entry.js'
HARD=ROOT/'artifact-library-hardening-entry.js'
V7=ROOT/'artifact-library-reader-v7-github-audio-entry.js'

simple=SIMPLE.read_text(encoding='utf-8')
pin=PIN.read_text(encoding='utf-8')
hard=HARD.read_text(encoding='utf-8')
v7=V7.read_text(encoding='utf-8')

if "R3_PERSISTENT_OWNER_SESSION_V87='v87'" not in simple:
    old="const R3_SINGLE_OWNER_SESSION_SECONDS_V73=90*24*60*60;"
    new="const R3_PERSISTENT_OWNER_SESSION_V87='v87';\nconst R3_PERSISTENT_OWNER_SESSION_SECONDS_V87=10*365*24*60*60;\nconst R3_SINGLE_OWNER_SESSION_SECONDS_V73=R3_PERSISTENT_OWNER_SESSION_SECONDS_V87;"
    if old not in simple: raise SystemExit('V87_SIMPLE_SESSION_ANCHOR_MISSING')
    simple=simple.replace(old,new,1)
    old_header='"X-R3-Owner-Session": "single-owner-v73"'
    new_header='"X-R3-Owner-Session": "single-owner-v87-persistent", "X-R3-Owner-Session-Max-Age": String(R3_PERSISTENT_OWNER_SESSION_SECONDS_V87)'
    if old_header not in simple: raise SystemExit('V87_SIMPLE_HEADER_ANCHOR_MISSING')
    simple=simple.replace(old_header,new_header,1)


if "R3_READER_PERSISTENT_SESSION_V87='v87'" not in v7:
    const_anchor="const R3_LIBRARY_COOKIE_V75='r3_artifact_library';"
    if const_anchor not in v7: raise SystemExit('V87_V7_CONST_ANCHOR_MISSING')
    v7=v7.replace(const_anchor,const_anchor+"\nconst R3_READER_PERSISTENT_SESSION_V87='v87';\nconst R3_READER_PERSISTENT_SESSION_SECONDS_V87=10*365*24*60*60;",1)
    helper_anchor="function r3OwnerLoginRedirectV75(request){\n"
    helper="""function r3PersistentOwnerCookieV87(value){
  return `${R3_LIBRARY_COOKIE_V75}=${value}; Path=/artifact-library; Max-Age=${R3_READER_PERSISTENT_SESSION_SECONDS_V87}; HttpOnly; Secure; SameSite=Strict`;
}
"""
    if helper_anchor not in v7: raise SystemExit('V87_V7_HELPER_ANCHOR_MISSING')
    v7=v7.replace(helper_anchor,helper+helper_anchor,1)
    old="    const routedRequest = canonicalizeEbookAudioInternalRequest(request, env, url);\n    return ebookAudio.fetch(routedRequest, env, ctx, app);"
    new="""    const routedRequest = canonicalizeEbookAudioInternalRequest(request, env, url);
    const routedResponse = await ebookAudio.fetch(routedRequest, env, ctx, app);
    if (request.method === 'GET' && url.pathname === '/artifact-library/read' && await r3HasOwnerSessionV75(request,env)) {
      const ownerSession = await r3ExpectedLibrarySessionV75(env);
      const h = new Headers(routedResponse.headers);
      h.set('Set-Cookie', r3PersistentOwnerCookieV87(ownerSession));
      h.set('X-R3-Owner-Session', 'single-owner-v87-persistent');
      h.set('X-R3-Owner-Session-Max-Age', String(R3_READER_PERSISTENT_SESSION_SECONDS_V87));
      return new Response(routedResponse.body,{status:routedResponse.status,statusText:routedResponse.statusText,headers:h});
    }
    return routedResponse;"""
    if old not in v7: raise SystemExit('V87_V7_RETURN_ANCHOR_MISSING')
    v7=v7.replace(old,new,1)

for name,text in [('pin',pin),('hard',hard)]:
    old='const REMEMBER_SECONDS = 30 * 24 * 60 * 60;'
    new='const REMEMBER_SECONDS = 10 * 365 * 24 * 60 * 60; // v87 persistent owner session, rolling on use'
    if old in text:
        text=text.replace(old,new,1)
    elif new not in text:
        raise SystemExit(f'V87_{name.upper()}_REMEMBER_ANCHOR_MISSING')
    text=text.replace('This device keeps an HttpOnly session for 30 days after a successful login.', 'This device stays signed in with a long-lived HttpOnly owner session that is renewed whenever the Library is used.')
    text=text.replace('After login, this device keeps an HttpOnly session for 30 days.', 'After login, this device stays signed in with a long-lived HttpOnly owner session that is renewed whenever the Library is used.')
    if name=='pin': pin=text
    else: hard=text

SIMPLE.write_text(simple,encoding='utf-8')
PIN.write_text(pin,encoding='utf-8')
HARD.write_text(hard,encoding='utf-8')
V7.write_text(v7,encoding='utf-8')
print('READER_V87_PERSISTENT_OWNER_SESSION=PASS')
