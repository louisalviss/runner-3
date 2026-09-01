from pathlib import Path

core = Path('cloudflare/runner3-core/reader-audio-core/browser-production-integration.js')
v30 = Path('cloudflare/runner3-core/artifact-library-reader-v30-dark-highlight-entry.js')
v34 = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')

core_s = core.read_text(encoding='utf-8')
v30_s = v30.read_text(encoding='utf-8')
v34_s = v34.read_text(encoding='utf-8')

# v33 remains responsible for timing/mapping/follow, but it must never paint the
# old whole-block attribute highlight. v34 sentence CSS Highlight is visual owner.
old_highlight = """  function highlight(target) {
    const el = mappedElements.get(String(target?.cfi || ''));
    if (!el || el === activeBlock) return;
    clearHighlight();
    activeBlock = el;
    try { el.setAttribute('data-r3-audio-reading-v11', '1'); } catch {}
  }
"""
new_highlight = """  function highlight(target) {
    // v43: sentence continuity is the only visual highlight owner.
    window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER = true;
    clearHighlight();
  }
"""
if 'v43: sentence continuity is the only visual highlight owner' not in core_s:
    if old_highlight not in core_s:
        raise SystemExit('v43: v33 highlight function marker missing')
    core_s = core_s.replace(old_highlight, new_highlight, 1)

# v30 must not even install its font-weight:900/background stylesheet once the
# sentence owner boot flag is present.
v30_guard = "  if(window.__r3AudioDarkHighlightV30)return;\n"
v30_replacement = """  if(window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER){
    window.__r3AudioDarkHighlightV30Suppressed=true;
    return;
  }
  if(window.__r3AudioDarkHighlightV30)return;
"""
if '__r3AudioDarkHighlightV30Suppressed' not in v30_s:
    if v30_guard not in v30_s:
        raise SystemExit('v43: v30 guard marker missing')
    v30_s = v30_s.replace(v30_guard, v30_replacement, 1)

# v34 patches the completed HTML. Put the owner flag before the earliest audio
# script (v6), therefore before v30 and the v33 browser bundle execute.
robots = "const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';\n"
owner_consts = """const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';
const SENTENCE_OWNER_BOOT = `<script data-r3-sentence-highlight-owner-v43=\"1\">window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER=true;</script>`;
"""
if 'data-r3-sentence-highlight-owner-v43' not in v34_s:
    if robots not in v34_s:
        raise SystemExit('v43: ROBOTS marker missing')
    v34_s = v34_s.replace(robots, owner_consts, 1)

bridge_guard = "  if (!out.includes(BRIDGE_RANGE_NEEDLE)) throw new Error('READER_V34_PATCH_MISSING:cfiFromRange');\n"
owner_patch = """  const ownerMarker = '<script data-r3-ebook-audio-v6=\"2\">';
  if (!out.includes(ownerMarker)) throw new Error('READER_V43_PATCH_MISSING:v30-dark-highlight');
  out = out.replace(ownerMarker, SENTENCE_OWNER_BOOT + ownerMarker);
  if (!out.includes(BRIDGE_RANGE_NEEDLE)) throw new Error('READER_V34_PATCH_MISSING:cfiFromRange');
"""
if 'READER_V43_PATCH_MISSING:v30-dark-highlight' not in v34_s:
    if bridge_guard not in v34_s:
        raise SystemExit('v43: stable bridge guard marker missing')
    v34_s = v34_s.replace(bridge_guard, owner_patch, 1)

old_hooks = """  function ensureFrameHooks(doc){
    if(!doc)return;
    if(!doc.getElementById('r3AudioReadingStyleV34')){
"""
new_hooks = """  function ensureFrameHooks(doc){
    if(!doc)return;
    // v43 backstop for BFCache/retained rendition documents created pre-fix.
    try{doc.getElementById('r3AudioDarkHighlightV30Style')?.remove();}catch{}
    try{doc.querySelectorAll('[data-r3-audio-reading-v11]').forEach(el=>el.removeAttribute('data-r3-audio-reading-v11'));}catch{}
    if(!doc.getElementById('r3AudioReadingStyleV34')){
"""
if 'v43 backstop for BFCache/retained rendition documents' not in v34_s:
    if old_hooks not in v34_s:
        raise SystemExit('v43: ensureFrameHooks marker missing')
    v34_s = v34_s.replace(old_hooks, new_hooks, 1)

checks = [
    (core_s, '__R3_READER_SENTENCE_HIGHLIGHT_OWNER', 'v33 owner disable'),
    (v30_s, '__R3_READER_SENTENCE_HIGHLIGHT_OWNER', 'v30 owner suppression'),
    (v34_s, 'data-r3-sentence-highlight-owner-v43', 'early owner boot'),
    (v34_s, 'READER_V43_PATCH_MISSING:v30-dark-highlight', 'patch proof'),
    (v34_s, "getElementById('r3AudioDarkHighlightV30Style')?.remove()", 'stale style cleanup'),
]
for source, needle, label in checks:
    if needle not in source:
        raise SystemExit(f'v43: missing post-patch marker: {label}')

core.write_text(core_s, encoding='utf-8')
v30.write_text(v30_s, encoding='utf-8')
v34.write_text(v34_s, encoding='utf-8')
