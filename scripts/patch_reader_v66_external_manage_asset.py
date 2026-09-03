from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
V2=ROOT/'artifact-library-reader-v2-entry.js'
simple=SIMPLE.read_text(encoding='utf-8')
v2=V2.read_text(encoding='utf-8')

# v66 identity: keep the v65 sync table/backend, but advance client/server handshake for this UI architecture.
if "reader_client_version:'v66'" not in simple:
    if simple.count("reader_client_version:'v65'")!=1:
        raise SystemExit('V66_SIMPLE_VERSION_ANCHOR_COUNT:'+str(simple.count("reader_client_version:'v65'")))
    simple=simple.replace("reader_client_version:'v65'","reader_client_version:'v66'",1)
if "'x-r3-reader-client-version':'v66'" not in simple:
    if simple.count("'x-r3-reader-client-version':'v65'")!=1:
        raise SystemExit('V66_SIMPLE_HEADER_ANCHOR_COUNT:'+str(simple.count("'x-r3-reader-client-version':'v65'")))
    simple=simple.replace("'x-r3-reader-client-version':'v65'","'x-r3-reader-client-version':'v66'",1)
if "const R3_READER_CLIENT_VERSION_V63='v66';" not in v2:
    if v2.count("const R3_READER_CLIENT_VERSION_V63='v65';")!=1:
        raise SystemExit('V66_READER_VERSION_ANCHOR_COUNT:'+str(v2.count("const R3_READER_CLIENT_VERSION_V63='v65';")))
    v2=v2.replace("const R3_READER_CLIENT_VERSION_V63='v65';","const R3_READER_CLIENT_VERSION_V63='v66';",1)

IMPORT='import { READER_MANAGE_UI_V66_SOURCE } from "./reader-manage-ui-v66-asset-source.js";\n'
if IMPORT not in simple:
    # Earlier build patches may replace the first import target. Prepending an ESM import is stable regardless of that chain.
    simple=IMPORT+simple

helpers=r'''
function r3ManageUiAssetV66(request) {
  if (request.method !== "GET" && request.method !== "HEAD") return json({ ok:false, error:"METHOD_NOT_ALLOWED" },405);
  const h=headers({
    "Content-Type":"application/javascript; charset=utf-8",
    "Cache-Control":"private, no-store, max-age=0",
    "X-Content-Type-Options":"nosniff"
  });
  return new Response(request.method === "HEAD" ? null : READER_MANAGE_UI_V66_SOURCE,{status:200,headers:h});
}

function r3InjectExternalManageAssetV66(html) {
  const marker='<script src="/artifact-library/assets/manage-v66.js" defer data-r3-manage-ui-v66="1"></script>';
  const source=String(html||'');
  if(source.includes('data-r3-manage-ui-v66="1"'))return source;
  return source.includes('</body>')?source.replace('</body>',marker+'</body>'):source+marker;
}

'''
if 'function r3ManageUiAssetV66' not in simple:
    anchor='async function publicDelivery(request, env, ctx) {'
    if simple.count(anchor)!=1:
        raise SystemExit('V66_HELPER_ANCHOR_COUNT:'+str(simple.count(anchor)))
    simple=simple.replace(anchor,helpers+anchor,1)

old_library='return new Response(libraryPage(), { status: 200, headers: headers({' 
new_library='return new Response(r3InjectExternalManageAssetV66(libraryPage()), { status: 200, headers: headers({' 
if new_library not in simple:
    if simple.count(old_library)!=1:
        raise SystemExit('V66_LIBRARY_RESPONSE_ANCHOR_COUNT:'+str(simple.count(old_library)))
    simple=simple.replace(old_library,new_library,1)

old_reader='const updated = injectIframeSwipe(original);'
new_reader='const updated = r3InjectExternalManageAssetV66(injectIframeSwipe(original));'
if new_reader not in simple:
    if simple.count(old_reader)!=1:
        raise SystemExit('V66_READER_RESPONSE_ANCHOR_COUNT:'+str(simple.count(old_reader)))
    simple=simple.replace(old_reader,new_reader,1)

asset_route='    if (p === "/artifact-library/assets/manage-v66.js") return r3ManageUiAssetV66(request);\n'
if asset_route not in simple:
    anchor='    if (p === "/artifact-library") {\n'
    if simple.count(anchor)!=1:
        raise SystemExit('V66_ROUTE_ANCHOR_COUNT:'+str(simple.count(anchor)))
    simple=simple.replace(anchor,asset_route+anchor,1)

# Main Library previously had only inline JS. External same-origin asset must be explicitly allowed by CSP.
simple=simple.replace("script-src 'unsafe-inline';","script-src 'self' 'unsafe-inline';")

for marker in [
    "reader_client_version:'v66'",
    "'x-r3-reader-client-version':'v66'",
    'READER_MANAGE_UI_V66_SOURCE',
    'function r3ManageUiAssetV66',
    'function r3InjectExternalManageAssetV66',
    '/artifact-library/assets/manage-v66.js',
    'data-r3-manage-ui-v66="1"',
    'r3InjectExternalManageAssetV66(libraryPage())',
    'r3InjectExternalManageAssetV66(injectIframeSwipe(original))',
]:
    if marker not in simple:
        raise SystemExit('V66_SIMPLE_MISSING:'+marker)
if "const R3_READER_CLIENT_VERSION_V63='v66';" not in v2:
    raise SystemExit('V66_READER_VERSION_MISSING')

# Safety rule: UI runtime itself must never be embedded into Reader/Library inline scripts.
if 'window.__R3_MANAGE_UI_V66=true' in simple or 'window.__R3_MANAGE_UI_V66=true' in v2:
    raise SystemExit('V66_RUNTIME_WAS_INLINED')

SIMPLE.write_text(simple,encoding='utf-8')
V2.write_text(v2,encoding='utf-8')
print('READER_V66_EXTERNAL_MANAGE_ASSET=PASS')
