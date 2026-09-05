from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
ROUTER = ROOT / 'opportunity-router-entry.js'
simple = SIMPLE.read_text(encoding='utf-8')
router = ROUTER.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# ---------------------------------------------------------------------------
# 1) artifact-library-simple-entry: do not statically load the legacy backend.
# Library/list/cover/upload/enrich/raw stay lightweight. Legacy is loaded only
# for delivery/vendor/fallback paths that actually need it.
# ---------------------------------------------------------------------------
old_import = 'import app from "./artifact-test-cleanup-entry.js";\n\n'
lazy_import = '''let r3LegacyLibraryAppPromiseV57 = null;\nfunction r3LoadLegacyLibraryAppV57() {\n  if (!r3LegacyLibraryAppPromiseV57) {\n    r3LegacyLibraryAppPromiseV57 = import("./artifact-test-cleanup-entry.js").then((module) => module.default);\n  }\n  return r3LegacyLibraryAppPromiseV57;\n}\n\n'''
if old_import in simple:
    simple = replace_once(simple, old_import, lazy_import, 'simple lazy legacy import')
elif 'r3LoadLegacyLibraryAppV57' not in simple:
    raise SystemExit('simple legacy import marker missing')

simple = simple.replace('return app.fetch(forwarded, env, ctx);', 'return (await r3LoadLegacyLibraryAppV57()).fetch(forwarded, env, ctx);')
simple = simple.replace('const response = await app.fetch(inner, env, ctx);', 'const response = await (await r3LoadLegacyLibraryAppV57()).fetch(inner, env, ctx);')
simple = simple.replace('return app.fetch(request, env, ctx);', 'return (await r3LoadLegacyLibraryAppV57()).fetch(request, env, ctx);')
simple = simple.replace('if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);', 'const app = await r3LoadLegacyLibraryAppV57();\n    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);')

raw_handler = r'''
async function publicRawEpubV57(request, env) {
  if (request.method !== 'GET') return json({ ok: false, error: 'METHOD_NOT_ALLOWED' }, 405);
  if (!(await hasBrowserLibrarySession(request, env))) return json({ ok: false, error: 'UNAUTHORIZED' }, 401);
  if (!env.ARTIFACTS) return json({ ok: false, error: 'R2_NOT_BOUND' }, 503);
  const url = new URL(request.url);
  const key = String(url.searchParams.get('key') || '');
  if (!isFinalEpub(key)) return json({ ok: false, error: 'FINAL_EPUB_ONLY' }, 403);
  const object = await env.ARTIFACTS.get(key);
  if (!object) return json({ ok: false, error: 'EPUB_NOT_FOUND' }, 404);
  const h = headers({ 'Content-Type': object.httpMetadata?.contentType || 'application/epub+zip' });
  h.set('Cache-Control', 'private, max-age=300');
  if (object.httpEtag) h.set('ETag', object.httpEtag);
  h.set('X-R3-Library-Fast-Path', 'raw-r2-v57');
  return new Response(object.body, { status: 200, headers: h });
}

'''
if 'async function publicRawEpubV57' not in simple:
    simple = replace_once(simple, 'async function publicDelivery(request, env, ctx) {', raw_handler + 'async function publicDelivery(request, env, ctx) {', 'raw epub handler')

route_anchor = '    if (p === "/artifact-library/api/list") return publicList(request, env);\n'
if 'p === "/artifact-library/api/raw"' not in simple:
    simple = replace_once(simple, route_anchor, route_anchor + '    if (p === "/artifact-library/api/raw") return publicRawEpubV57(request, env);\n', 'raw epub route')

# v56 background migration no longer invokes the heavy delivery/signed-url chain.
old_migration_delivery = "async function deliveryEpubBufferV56(bookKey){const d=await fetch('/artifact-library/api/delivery',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key:bookKey,ttl_seconds:900})});const payload=await d.json();if(!d.ok||payload.ok!==true||!payload.delivery?.url)throw new Error(payload.error||('HTTP '+d.status));const r=await fetch(payload.delivery.url,{cache:'no-store'});if(!r.ok)throw new Error('EPUB HTTP '+r.status);return r.arrayBuffer()}"
new_migration_delivery = "async function deliveryEpubBufferV56(bookKey){const r=await fetch('/artifact-library/api/raw?key='+encodeURIComponent(bookKey),{cache:'no-store'});if(!r.ok)throw new Error('EPUB HTTP '+r.status);return r.arrayBuffer()}"
if old_migration_delivery in simple:
    simple = replace_once(simple, old_migration_delivery, new_migration_delivery, 'migration raw r2 path')
elif new_migration_delivery not in simple:
    raise SystemExit('v56 migration delivery marker missing')

# ---------------------------------------------------------------------------
# 2) top router: the normal Library surface bypasses mailbox/audio/Reader.
# Only /artifact-library/read enters the full Reader chain.
# ---------------------------------------------------------------------------
old_router_import = 'import app from "./mailbox-entry.js";\n'
router_lazy = '''let r3CoreAppPromiseV57 = null;\nlet r3LibraryFastAppPromiseV57 = null;\nfunction r3LoadCoreAppV57() {\n  if (!r3CoreAppPromiseV57) r3CoreAppPromiseV57 = import("./mailbox-entry.js").then((module) => module.default);\n  return r3CoreAppPromiseV57;\n}\nfunction r3LoadLibraryFastAppV57() {\n  if (!r3LibraryFastAppPromiseV57) r3LibraryFastAppPromiseV57 = import("./artifact-library-simple-entry.js").then((module) => module.default);\n  return r3LibraryFastAppPromiseV57;\n}\nfunction r3IsLibraryFastPathV57(pathname) {\n  if (pathname === "/artifact-library") return true;\n  if (pathname.startsWith("/artifact-library/vendor/")) return true;\n  return new Set([\n    "/artifact-library/api/list",\n    "/artifact-library/api/cover",\n    "/artifact-library/api/upload",\n    "/artifact-library/api/enrich-upload",\n    "/artifact-library/api/raw",\n    "/artifact-library/api/delivery",\n  ]).has(pathname);\n}\n'''
if old_router_import in router:
    router = replace_once(router, old_router_import, router_lazy, 'router lazy core import')
elif 'r3LoadCoreAppV57' not in router:
    # Newer router revisions already lazy-load mailbox/core so mailbox can stay
    # isolated from the Reader graph. Layer the v57 Library loader on top rather
    # than requiring the retired static import marker.
    existing_lazy_marker = 'function loadApp() {'
    if existing_lazy_marker not in router:
        raise SystemExit('router core import marker missing')
    compat_lazy = '''let r3LibraryFastAppPromiseV57 = null;
function r3LoadCoreAppV57() {
  return loadApp();
}
function r3LoadLibraryFastAppV57() {
  if (!r3LibraryFastAppPromiseV57) r3LibraryFastAppPromiseV57 = import("./artifact-library-simple-entry.js").then((module) => module.default);
  return r3LibraryFastAppPromiseV57;
}
function r3IsLibraryFastPathV57(pathname) {
  if (pathname === "/artifact-library") return true;
  if (pathname.startsWith("/artifact-library/vendor/")) return true;
  return new Set([
    "/artifact-library/api/list",
    "/artifact-library/api/cover",
    "/artifact-library/api/upload",
    "/artifact-library/api/enrich-upload",
    "/artifact-library/api/raw",
    "/artifact-library/api/delivery",
  ]).has(pathname);
}

'''
    router = router.replace('let appPromise = null;\n', 'let appPromise = null;\n' + compat_lazy, 1)

fetch_anchor = '    const url = new URL(request.url);\n\n'
fetch_anchor_compact = '    const url = new URL(request.url);\n'
fast_fetch = '    const url = new URL(request.url);\n\n    if (r3IsLibraryFastPathV57(url.pathname)) {\n      return (await r3LoadLibraryFastAppV57()).fetch(request, env, ctx);\n    }\n\n'
if 'r3IsLibraryFastPathV57(url.pathname)' not in router:
    if fetch_anchor in router:
        router = replace_once(router, fetch_anchor, fast_fetch, 'router fast fetch')
    else:
        router = replace_once(router, fetch_anchor_compact, fast_fetch, 'router fast fetch compact')

router = router.replace('    return app.fetch(request, env, ctx);', '    return (await r3LoadCoreAppV57()).fetch(request, env, ctx);')
router = router.replace('    if (typeof app.scheduled === "function") {\n      return app.scheduled(controller, env, ctx);\n    }', '    const app = await r3LoadCoreAppV57();\n    if (typeof app.scheduled === "function") {\n      return app.scheduled(controller, env, ctx);\n    }')

for marker in [
    'r3LoadLegacyLibraryAppV57', 'async function publicRawEpubV57',
    'p === "/artifact-library/api/raw"', "'/artifact-library/api/raw?key='+encodeURIComponent(bookKey)",
]:
    if marker not in simple:
        raise SystemExit('V57_SIMPLE_MISSING:' + marker)
for marker in [
    'r3LoadCoreAppV57', 'r3LoadLibraryFastAppPromiseV57' if False else 'r3LoadLibraryFastAppV57', 'r3IsLibraryFastPathV57',
    'return (await r3LoadLibraryFastAppV57()).fetch(request, env, ctx);',
]:
    if marker not in router:
        raise SystemExit('V57_ROUTER_MISSING:' + marker)
if 'import app from "./artifact-test-cleanup-entry.js";' in simple:
    raise SystemExit('V57_SIMPLE_STATIC_LEGACY_IMPORT_REMAINS')
if 'import app from "./mailbox-entry.js";' in router:
    raise SystemExit('V57_ROUTER_STATIC_CORE_IMPORT_REMAINS')

SIMPLE.write_text(simple, encoding='utf-8')
ROUTER.write_text(router, encoding='utf-8')
print('READER_V57_RESOURCE_FASTPATH=PASS')
