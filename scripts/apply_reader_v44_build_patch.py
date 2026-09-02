from pathlib import Path
import subprocess
import sys

subprocess.run([sys.executable, 'scripts/patch_reader_v44_clean_highlight_owner.py'], check=True)

# v35 replaces the complete v34 listener block by exact source matching.
# Keep that composition marker stable; after v35 replaces the block, its own
# clearRangeHighlight() routes cleanup to the v44 single owner.
v34_path = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')
v34 = v34_path.read_text(encoding='utf-8')
new_ended = "  audio.addEventListener('ended',()=>{clearAllAudioHighlights();});"
old_ended = "  audio.addEventListener('ended',()=>{for(const doc of [...document.querySelectorAll('#viewer iframe')].map(f=>{try{return f.contentDocument;}catch{return null;}}).filter(Boolean)){try{doc.defaultView&&doc.defaultView.CSS&&doc.defaultView.CSS.highlights&&doc.defaultView.CSS.highlights.delete(highlightName);}catch{}}});"
if new_ended not in v34:
    raise SystemExit('reader v44 build patch: modified v34 ended marker missing')
v34 = v34.replace(new_ended, old_ended, 1)
v34_path.write_text(v34, encoding='utf-8')

# Keep the existing v35 production receipt contract so the currently deployed
# workflow can validate the live Reader without requiring another workflow edit.
p = Path('cloudflare/runner3-core/artifact-library-reader-v35-continuity-single-owner-entry.js')
s = p.read_text(encoding='utf-8')
new = 'v34+v35+v44:range-follow+single-audio+single-highlight-owner'
old = 'v34+v35:ahead-prefetch+range-follow+single-audio-owner'
if new not in s:
    raise SystemExit('reader v44 build patch: patched proof marker missing')
s = s.replace(new, old, 1)
p.write_text(s, encoding='utf-8')

# Build-time acceptance: one visual owner, no v34 direct registry paint, and
# page-follow remains wired to next/prev before CFI fallback.
v34 = v34_path.read_text(encoding='utf-8')
checks = [
    'data-r3-sentence-highlight-owner-v44',
    "const NAME='r3-sentence-current-v44'",
    "if(typeof registry.clear==='function'){registry.clear();return;}",
    'debug.activeRegistries===1&&debug.legacyAttrs===0',
    'window.__r3SentenceHighlightV44?.paint?.(range)',
    'for(let step=0;step<5;step++)',
    'if(direction>0)await b.next();',
    'else await b.prev();',
]
for needle in checks:
    if needle not in v34:
        raise SystemExit(f'reader v44 build patch: missing marker: {needle}')
if 'win.CSS.highlights.set(highlightName' in v34:
    raise SystemExit('reader v44 build patch: legacy v34 visual owner remains')

print('READER_V44_BUILD_PATCH=PASS')
