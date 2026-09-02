from pathlib import Path

simple = Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
router = Path('cloudflare/runner3-core/opportunity-router-entry.js').read_text(encoding='utf-8')

for marker in [
    'r3LoadLegacyLibraryAppV57',
    'async function publicRawEpubV57',
    'p === "/artifact-library/api/raw"',
    "'/artifact-library/api/raw?key='+encodeURIComponent(bookKey)",
    "X-R3-Library-Fast-Path",
]:
    if marker not in simple:
        raise SystemExit('V57_SIMPLE_MISSING:' + marker)
for marker in [
    'r3LoadCoreAppV57',
    'r3LoadLibraryFastAppV57',
    'r3IsLibraryFastPathV57',
    'pathname.startsWith("/artifact-library/vendor/")',
    '"/artifact-library/api/delivery"',
]:
    if marker not in router:
        raise SystemExit('V57_ROUTER_MISSING:' + marker)
if 'import app from "./artifact-test-cleanup-entry.js";' in simple:
    raise SystemExit('V57_STATIC_SIMPLE_IMPORT')
if 'import app from "./mailbox-entry.js";' in router:
    raise SystemExit('V57_STATIC_ROUTER_IMPORT')
if "fetch('/artifact-library/api/delivery'" in simple and 'deliveryEpubBufferV56' in simple:
    # Delivery is still valid elsewhere; only ensure the migration function itself is raw-R2.
    start = simple.find('async function deliveryEpubBufferV56')
    end = simple.find('async function migrateLegacyBookV56', start)
    block = simple[start:end]
    if '/artifact-library/api/delivery' in block:
        raise SystemExit('V57_MIGRATION_STILL_USES_DELIVERY')
print('READER_V57_RESOURCE_FASTPATH_CHECK=PASS')
