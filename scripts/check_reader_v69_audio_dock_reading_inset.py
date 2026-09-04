from pathlib import Path
import runpy

V2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

required = [
    '__r3AudioDockInsetV69',
    "owner:'audio-dock-reading-inset-v69'",
    "document.getElementById('r3AudioDock')",
    'dock.getBoundingClientRect()',
    '--r3-reading-bottom-v69',
    'html.r3-full-bleed-v68.r3-audio-dock-inset-v69 #viewer',
    'bottom:var(--r3-reading-bottom-v69,0px)!important',
    'height:auto!important',
    'viewportBottom-Number(rect.top||0)',
    'Math.ceil(overlap+8)',
    'new ResizeObserver',
    'new MutationObserver',
    "r3InstallAudioDockInsetV69();",
    "r3ApplyAudioDockInsetV69('pre-render-enter',false)",
    'rendition.resize(stageW,stageH)',
    "r3ApplyAudioDockInsetV69('v68-viewport',false)",
    "requestAnimationFrame(()=>r3ResizeReadingStageV69(reason))",
]
for marker in required:
    if marker not in V2:
        raise SystemExit('READER_V69_AUDIO_DOCK_INSET_MISSING:' + marker)

# Keep all v68 full-bleed invariants available; v69 overrides only the reading stage.
for marker in [
    '__r3FullBleedV68',
    "owner:'full-bleed-autostretch-v68'",
    'html.r3-full-bleed-v68 #viewer{inset:0!important;width:100%!important;height:100%!important}',
    'rendition.resize(w,h)',
    'postResizeDisplay:false',
    'postRenderGeometryWait:false',
]:
    if marker not in V2:
        raise SystemExit('READER_V69_V68_REGRESSION:' + marker)

start = V2.index('  function r3AudioDockV69()')
end = V2.index('  async function r3WaitPreRenderStageV67()')
segment = V2[start:end]
for forbidden in [
    'rendition.display(',
    'r3-audio-fixed-height-v69',
    '--r3-audio-fixed-height-v69',
]:
    if forbidden in segment:
        raise SystemExit('READER_V69_AUDIO_DOCK_INSET_FORBIDDEN:' + forbidden)

print('READER_V69_AUDIO_DOCK_READING_INSET_CHECK=PASS')
runpy.run_path('scripts/check_reader_v68_full_bleed_autostretch.py', run_name='__main__')
