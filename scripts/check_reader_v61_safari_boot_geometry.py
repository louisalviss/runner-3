from pathlib import Path

v2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v5 = Path('cloudflare/runner3-core/artifact-library-reader-v5-entry.js').read_text(encoding='utf-8')
v34 = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js').read_text(encoding='utf-8')

required = [
    '__r3SafariBootGeometryV61',
    'r3WaitStableBootGeometryV61',
    'r3NormalizeBootGeometryV61',
    "owner:'safari-boot-geometry-v61'",
    'Date.now()-started>=450',
    'rendition.resize(width,height)',
    'const r3BootAnchorV61=saved||r3CurrentBootCfiV61();',
    'window.__R3_READER_BOOT_QUIET_UNTIL_V58=Date.now()+650;',
]
for marker in required:
    if marker not in v2:
        raise SystemExit('READER_V61_MISSING:' + marker)

# v58 atomic reveal remains authoritative: intermediate epub.js render events
# must not reveal the Reader before geometry + saved CFI have settled.
if "rendition.on('rendered',()=>{bindEpubContents();$('loading').classList.add('hidden');});" in v2:
    raise SystemExit('READER_V61_EARLY_RENDER_REVEAL_REGRESSION')
if "owner:'atomic-v58'" not in v2:
    raise SystemExit('READER_V61_ATOMIC_V58_OWNER_MISSING')

# v5 stays gated during boot; v61 performs the one hidden resize/restore itself.
if '__R3_READER_BOOT_QUIET_UNTIL_V58' not in v5:
    raise SystemExit('READER_V61_V5_BOOT_GATE_MISSING')

# Audio continuity/prefetch is intentionally untouched by this layout patch.
for marker in ['reader-audio-v60-prefetch', 'reader-audio-v60-warm-current']:
    if marker not in v34:
        raise SystemExit('READER_V61_AUDIO_V60_MISSING:' + marker)

print('READER_V61_SAFARI_BOOT_GEOMETRY_CHECK=PASS')
