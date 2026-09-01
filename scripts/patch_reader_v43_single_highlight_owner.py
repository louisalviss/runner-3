from pathlib import Path

core = Path('cloudflare/runner3-core/reader-audio-core/browser-production-integration.js')
v34 = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')

core_s = core.read_text(encoding='utf-8')
v34_s = v34.read_text(encoding='utf-8')

old_highlight = """  function highlight(target) {
    const el = mappedElements.get(String(target?.cfi || ''));
    if (!el || el === activeBlock) return;
    clearHighlight();
    activeBlock = el;
    try { el.setAttribute('data-r3-audio-reading-v11', '1'); } catch {}
  }
"""
new_highlight = """  function highlight(target) {
    // Sentence continuity runtime is the only visual highlight owner.
    // Keep v33 segment mapping/follow logic, but never paint the legacy block.
    if (window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER) {
      clearHighlight();
      return;
    }
    const el = mappedElements.get(String(target?.cfi || ''));
    if (!el || el === activeBlock) return;
    clearHighlight();
    activeBlock = el;
    try { el.setAttribute('data-r3-audio-reading-v11', '1'); } catch {}
  }
"""
if old_highlight not in core_s:
    raise SystemExit('v43: v33 highlight function marker missing')
core_s = core_s.replace(old_highlight, new_highlight, 1)

robots = "const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';\n"
owner_consts = """const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';
const SENTENCE_OWNER_BOOT = `<script data-r3-sentence-highlight-owner-v43=\"1\">window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER=true;</script>`;
const LEGACY_DARK_BOOT = `<script data-r3-audio-dark-highlight-v30=\"1\">\n(()=>{`;
const LEGACY_DARK_SUPPRESSED_BOOT = `<script data-r3-audio-dark-highlight-v30=\"1\">\n(()=>{\n  if(window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER)return;`;
"""
if robots not in v34_s:
    raise SystemExit('v43: ROBOTS marker missing')
v34_s = v34_s.replace(robots, owner_consts, 1)

old_patch_head = """function patchV34(html) {
  let out = String(html || '');
  if (out.includes('data-r3-audio-continuity-v34=\\\"1\\\"')) return out;
  if (!out.includes(BRIDGE_RANGE_NEEDLE)) throw new Error('READER_V34_PATCH_MISSING:cfiFromRange');
"""
new_patch_head = """function patchV34(html) {
  let out = String(html || '');
  if (out.includes('data-r3-audio-continuity-v34=\\\"1\\\"')) return out;
  if (!out.includes(LEGACY_DARK_BOOT)) throw new Error('READER_V43_PATCH_MISSING:v30-dark-highlight');
  // The owner flag executes before legacy v30 and before the v33 browser core.
  // This prevents the old whole-block bold/background painter from ever starting.
  out = out.replace(LEGACY_DARK_BOOT, SENTENCE_OWNER_BOOT + LEGACY_DARK_SUPPRESSED_BOOT);
  if (!out.includes(BRIDGE_RANGE_NEEDLE)) throw new Error('READER_V34_PATCH_MISSING:cfiFromRange');
"""
if old_patch_head not in v34_s:
    raise SystemExit('v43: patchV34 head marker missing')
v34_s = v34_s.replace(old_patch_head, new_patch_head, 1)

old_hooks = """  function ensureFrameHooks(doc){
    if(!doc)return;
    if(!doc.getElementById('r3AudioReadingStyleV34')){
"""
new_hooks = """  function ensureFrameHooks(doc){
    if(!doc)return;
    // Backstop for a page restored from BFCache or a retained rendition document.
    try{doc.getElementById('r3AudioDarkHighlightV30Style')?.remove();}catch{}
    try{doc.querySelectorAll('[data-r3-audio-reading-v11]').forEach(el=>el.removeAttribute('data-r3-audio-reading-v11'));}catch{}
    if(!doc.getElementById('r3AudioReadingStyleV34')){
"""
if old_hooks not in v34_s:
    raise SystemExit('v43: ensureFrameHooks marker missing')
v34_s = v34_s.replace(old_hooks, new_hooks, 1)

checks = [
    '__R3_READER_SENTENCE_HIGHLIGHT_OWNER',
    'data-r3-sentence-highlight-owner-v43',
    'READER_V43_PATCH_MISSING:v30-dark-highlight',
    "getElementById('r3AudioDarkHighlightV30Style')?.remove()",
]
for needle in checks:
    if needle not in core_s and needle not in v34_s:
        raise SystemExit(f'v43: missing post-patch marker: {needle}')

core.write_text(core_s, encoding='utf-8')
v34.write_text(v34_s, encoding='utf-8')
