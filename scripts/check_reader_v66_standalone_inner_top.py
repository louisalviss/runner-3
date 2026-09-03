from pathlib import Path

V2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
text = V2.read_text(encoding='utf-8')

required = [
    '__r3StandaloneInnerTopV66',
    "owner:'standalone-inner-top-v66'",
    "r3StandaloneIphoneV66()",
    "body.style.setProperty('margin-top','0','important')",
    "body.style.setProperty('padding-top','8px','important')",
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

# Do not regress to an outer forced safe-area offset; v66 owns only the EPUB
# document's duplicate top spacing and leaves v39 outer viewport policy intact.
for forbidden in ['r3-ios-standalone-forced-inset-v38', '--r3-ios-forced-top-v38']:
    if forbidden in text:
        raise SystemExit('READER_V66_OLD_FORCED_INSET_PRESENT:' + forbidden)

print('READER_V66_STANDALONE_INNER_TOP_CHECK=PASS')
