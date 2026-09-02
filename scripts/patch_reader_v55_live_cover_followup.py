from pathlib import Path

PATH = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
text = PATH.read_text(encoding='utf-8')

old = "const meta=r3LibraryMetaCacheV54.get(String(row&&row.key||''))||{};if(meta.coverBlob instanceof Blob&&meta.coverBlob.size){const img=document.createElement('img');const u=URL.createObjectURL(meta.coverBlob);r3LibraryCoverUrlsV54.push(u);img.src=u;img.alt='';cover.appendChild(img);}"
new = "const meta=r3LibraryMetaCacheV54.get(String(row&&row.key||''))||{};if(row&&row.cover_key){const img=document.createElement('img');img.src='/artifact-library/api/cover?key='+encodeURIComponent(row.cover_key);img.alt='';img.loading='lazy';img.decoding='async';img.addEventListener('error',()=>img.remove());cover.appendChild(img);}else if(meta.coverBlob instanceof Blob&&meta.coverBlob.size){const img=document.createElement('img');const u=URL.createObjectURL(meta.coverBlob);r3LibraryCoverUrlsV54.push(u);img.src=u;img.alt='';cover.appendChild(img);}"

if 'row&&row.cover_key' not in text:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'V55_LIVE_COVER_EXPECTED_1_GOT_{count}')
    text = text.replace(old, new, 1)

for marker in ["row&&row.cover_key", "'/artifact-library/api/cover?key='+encodeURIComponent(row.cover_key)", 'r3LibraryCoverUrlsV54.push(u)']:
    if marker not in text:
        raise SystemExit('V55_LIVE_COVER_MISSING:' + marker)

PATH.write_text(text, encoding='utf-8')
print('READER_V55_LIVE_REAL_COVER=PASS')
