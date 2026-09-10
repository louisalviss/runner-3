from pathlib import Path

P=Path('cloudflare/runner3-core/artifact-library-simple-entry.js')
s=P.read_text(encoding='utf-8')
if "R3_SESSION_BOUND_SYNC_V74='v74'" in s:
    print('READER_V74_SESSION_BOUND_SYNC=ALREADY_APPLIED')
    raise SystemExit(0)

anchor="const SIMPLE_EPUB_UPLOAD_MAX_BYTES = 90 * 1024 * 1024;\n"
if anchor not in s: raise SystemExit('V74_CONST_ANCHOR_MISSING')
s=s.replace(anchor,anchor+"const R3_SESSION_BOUND_SYNC_V74='v74';\n",1)

old='''async function publicDelivery(request, env, ctx) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);'''
new='''async function publicDelivery(request, env, ctx) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!(await hasBrowserLibrarySession(request, env))) return json({ ok: false, error: "UNAUTHORIZED" }, 401);'''
if old not in s: raise SystemExit('V74_DELIVERY_ANCHOR_MISSING')
s=s.replace(old,new,1)

old='''async function publicReader(request, env, ctx) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  const url = new URL(request.url);
  const key = String(url.searchParams.get("key") || "");
  if (!isFinalEpub(key)) return redirectHome();
  const inner = await internalRequest(request, env);'''
new='''async function publicReader(request, env, ctx) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  const url = new URL(request.url);
  const key = String(url.searchParams.get("key") || "");
  if (!isFinalEpub(key)) return redirectHome();
  if (!(await hasBrowserLibrarySession(request, env))) {
    const target = "/artifact-library";
    return new Response(null, { status: 303, headers: headers({ Location: target, "X-R3-Session-Bound-Sync": "v74-login-required" }) });
  }
  const inner = await internalRequest(request, env);'''
if old not in s: raise SystemExit('V74_READER_ANCHOR_MISSING')
s=s.replace(old,new,1)

# Public list must also obey owner boundary. This prevents a no-session context
# from looking healthy while its state APIs are unauthorized.
old='''async function publicList(request, env) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);'''
new='''async function publicList(request, env) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!(await hasBrowserLibrarySession(request, env))) return json({ ok: false, error: "UNAUTHORIZED" }, 401);'''
if old not in s: raise SystemExit('V74_LIST_ANCHOR_MISSING')
s=s.replace(old,new,1)

for marker in ["R3_SESSION_BOUND_SYNC_V74='v74'",'v74-login-required','async function publicReader','async function publicDelivery','async function publicList']:
    if marker not in s: raise SystemExit('V74_MARKER_MISSING:'+marker)
P.write_text(s,encoding='utf-8')
print('READER_V74_SESSION_BOUND_SYNC=PASS')
