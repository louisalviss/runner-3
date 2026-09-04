from pathlib import Path
import runpy

V2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
text = V2.read_text(encoding='utf-8')

required = [
    '__r3StandaloneInnerTopV66',
    "owner:'standalone-inner-top-v66'",
    "r3StandaloneIphoneV66()",
    "body.style.setProperty('margin-top','0','important')",
    "rendition.hooks.content.register(contents=>r3NormalizeStandaloneInnerTopV66(contents,'content-hook'))",
    "r3NormalizeStandaloneInnerTopV66(c,'bind-rendered')",
    "r3NormalizeStandaloneInnerTopV66(c,'bind-settle-80')",
    "r3NormalizeStandaloneInnerTopV66(c,'bind-settle-240')",
    "root.dataset.r3StandaloneInnerTopV66='1'",
    "if(r3PxV66(cs.marginTop)>4)",
]
for marker in required:
    if marker not in text:
        raise SystemExit('READER_V66_STANDALONE_INNER_TOP_MISSING:' + marker)

padding_v66 = "body.style.setProperty('padding-top','8px','important')"
padding_v68 = "body.style.setProperty('padding-top',String(Math.max(8,Number(window.__r3FullBleedV68&&window.__r3FullBleedV68.safeTop||0)+8))+'px','important')"
if padding_v66 not in text and padding_v68 not in text:
    raise SystemExit('READER_V66_STANDALONE_INNER_TOP_PADDING_OWNER_MISSING')

for forbidden in ['r3-ios-standalone-forced-inset-v38', '--r3-ios-forced-top-v38']:
    if forbidden in text:
        raise SystemExit('READER_V66_OLD_FORCED_INSET_PRESENT:' + forbidden)

print('READER_V66_STANDALONE_INNER_TOP_CHECK=PASS')
runpy.run_path('scripts/check_reader_v67_stage_geometry_perf.py', run_name='__main__')
