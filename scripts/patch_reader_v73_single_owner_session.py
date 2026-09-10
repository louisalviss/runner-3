from pathlib import Path
ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
text=SIMPLE.read_text(encoding='utf-8')
if "R3_SINGLE_OWNER_SESSION_V73='v73'" in text:
    print('READER_V73_SINGLE_OWNER_SESSION=ALREADY_APPLIED')
    raise SystemExit(0)
anchor='const SIMPLE_EPUB_UPLOAD_MAX_BYTES = 90 * 1024 * 1024;\n'
if anchor not in text: raise SystemExit('V73_CONSTANT_ANCHOR_MISSING')
text=text.replace(anchor,anchor+"const R3_SINGLE_OWNER_SESSION_V73='v73';\nconst R3_SINGLE_OWNER_SESSION_SECONDS_V73=90*24*60*60;\n",1)
helper_anchor='''async function hasBrowserLibrarySession(request, env) {
  const expected = await sessionValue(env);
  return Boolean(expected) && browserCookie(request, LIBRARY_COOKIE) === expected;
}
'''
if helper_anchor not in text: raise SystemExit('V73_SESSION_HELPER_ANCHOR_MISSING')
helper=helper_anchor+'''\nfunction r3SingleOwnerCookieV73(value) {
  return `${LIBRARY_COOKIE}=${value}; Path=/artifact-library; Max-Age=${R3_SINGLE_OWNER_SESSION_SECONDS_V73}; HttpOnly; Secure; SameSite=Strict`;
}
'''
text=text.replace(helper_anchor,helper,1)
old='''    if (p === "/artifact-library") {
      if (request.method !== "GET") return redirectHome();
      if (!(await hasBrowserLibrarySession(request, env))) return (await r3LoadLegacyLibraryAppV57()).fetch(request, env, ctx);
      return new Response(libraryPage(), { status: 200, headers: headers({ "X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68", "X-R3-Progress-Recovery": "v70", "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" }) });
    }'''
new='''    if (p === "/artifact-library") {
      if (request.method !== "GET") return redirectHome();
      if (!(await hasBrowserLibrarySession(request, env))) return (await r3LoadLegacyLibraryAppV57()).fetch(request, env, ctx);
      const ownerSession = await sessionValue(env);
      return new Response(libraryPage(), { status: 200, headers: headers({ "Set-Cookie": r3SingleOwnerCookieV73(ownerSession), "X-R3-Owner-Session": "single-owner-v73", "X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68", "X-R3-Progress-Recovery": "v72", "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" }) });
    }'''
if old not in text: raise SystemExit('V73_LIBRARY_ROOT_ANCHOR_MISSING')
text=text.replace(old,new,1)
for marker in ["R3_SINGLE_OWNER_SESSION_V73='v73'",'R3_SINGLE_OWNER_SESSION_SECONDS_V73=90*24*60*60','r3SingleOwnerCookieV73(ownerSession)','single-owner-v73','"X-R3-Progress-Recovery": "v72"']:
    if marker not in text: raise SystemExit('V73_MARKER_MISSING:'+marker)
SIMPLE.write_text(text,encoding='utf-8')
print('READER_V73_SINGLE_OWNER_SESSION=PASS')
