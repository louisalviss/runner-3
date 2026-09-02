from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
simple = (ROOT / 'artifact-library-simple-entry.js').read_text(encoding='utf-8')
router = (ROOT / 'opportunity-router-entry.js').read_text(encoding='utf-8')
v2 = (ROOT / 'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

required_simple = [
    'function publicClientVersionV63',
    "reader_client_version:'v63'",
    'p === "/artifact-library/api/client-version"',
    "'cache-control':'no-store'",
]
required_router = [
    'r3IsLibraryFastPathV57',
    '"/artifact-library/api/client-version"',
    'return (await r3LoadLibraryFastAppV57()).fetch(request, env, ctx);',
]
required_reader = [
    "R3_READER_CLIENT_VERSION_V63='v63'",
    'window.__R3_READER_CLIENT_VERSION=R3_READER_CLIENT_VERSION_V63',
    'function r3RenderLiveLibraryCoreV63(){',
    'R3_LIBRARY_RENDER_RECOVERY_V63',
    'async function r3FetchLiveLibraryListV63(attempt=0)',
    "headers:{'accept':'application/json','x-runner3-library':'1'}",
    'Library API returned invalid data',
    'response.status===503',
    'Array.isArray(data.items)',
    'Array.isArray(data.objects)',
    'async function r3EnsureFreshReaderClientV63()',
    "sessionStorage.setItem(once,'1')",
    'location.reload();return false',
    'clientVersion:R3_READER_CLIENT_VERSION_V63',
]
for marker in required_simple:
    if marker not in simple:
        raise SystemExit('V63_SIMPLE_CHECK_MISSING:' + marker)
for marker in required_router:
    if marker not in router:
        raise SystemExit('V63_ROUTER_CHECK_MISSING:' + marker)
for marker in required_reader:
    if marker not in v2:
        raise SystemExit('V63_READER_CHECK_MISSING:' + marker)

# v57 anti-1102 architecture must still be present.
if 'import app from "./mailbox-entry.js";' in router:
    raise SystemExit('V63_REGRESSION_STATIC_CORE_IMPORT')
if 'import app from "./artifact-test-cleanup-entry.js";' in simple:
    raise SystemExit('V63_REGRESSION_STATIC_LEGACY_IMPORT')

# Do not regress R2 streaming upload into whole-body buffering.
if 'async function handleLibraryUpload' in simple:
    upload = simple.split('async function handleLibraryUpload',1)[1].split('\n}',1)[0]
    if 'request.arrayBuffer()' in upload or 'request.formData()' in upload:
        raise SystemExit('V63_REGRESSION_UPLOAD_BUFFERING')

print('READER_V63_LIBRARY_RECOVERY_CHECK=PASS')
