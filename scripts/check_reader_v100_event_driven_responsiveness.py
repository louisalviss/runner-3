from pathlib import Path
ROOT=Path('cloudflare/runner3-core')
v30=(ROOT/'artifact-library-reader-v30-dark-highlight-entry.js').read_text(encoding='utf-8')
v31=(ROOT/'artifact-library-reader-v31-high-speed-serialized-follow-entry.js').read_text(encoding='utf-8')
v35=(ROOT/'artifact-library-reader-v35-continuity-single-owner-entry.js').read_text(encoding='utf-8')
v82=(ROOT/'artifact-library-reader-v82-patch.js').read_text(encoding='utf-8')
shell=(ROOT/'artifact-library-reader-v82-stable-shell-entry.js').read_text(encoding='utf-8')
assert 'const timer=setInterval(()=>{sync();if(++ticks>120)' not in v30
assert 'viewerObserver' in v30
assert 'requestAnimationFrame(tick)' not in v31
assert "audio.addEventListener('play',syncClock)" in v31
assert "audio.addEventListener('pause',stopClock)" in v31
assert 'requestAnimationFrame(continuityFrame)' not in v35
assert "setInterval(()=>{hook();refreshChapters(false)" not in v35
assert "if(hook()){\n      clearInterval(boot);\n      refreshChapters(false);" in v35
assert "audio.addEventListener('timeupdate',onMediaTick)" in v35
assert "if(!audio.paused&&!audio.ended)tick()" in v35
assert 'setInterval(() => refreshChapterUi(bridge), 1200)' not in v82
assert 'window.__r3ChapterUiOffV100 = offChapterUi' in v82
assert "X-R3-Reader-Responsiveness', 'event-driven-v100'" in shell
print('READER_V100_EVENT_DRIVEN_RESPONSIVENESS=PASS')
