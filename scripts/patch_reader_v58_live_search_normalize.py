from pathlib import Path

p=Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
s=p.read_text(encoding='utf-8')
old='<div class="r3-live-library-tools"><input id="r3LiveLibrarySearch" class="r3-live-library-search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books"><button id="r3LiveLibraryUpload" class="r3-live-library-upload" type="button">＋ EPUB</button><input id="r3LiveLibraryUploadInput" type="file" accept=".epub,application/epub+zip" hidden></div>'
new='<input id="r3LiveLibrarySearch" class="r3-live-library-search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books">\n    <div class="r3-live-library-tools"><button id="r3LiveLibraryUpload" class="r3-live-library-upload" type="button">＋ EPUB</button><input id="r3LiveLibraryUploadInput" type="file" accept=".epub,application/epub+zip" hidden></div>'
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('V58_LIVE_SEARCH_TOOLS_MARKER_MISSING')
p.write_text(s,encoding='utf-8')
print('READER_V58_LIVE_SEARCH_NORMALIZE=PASS')
