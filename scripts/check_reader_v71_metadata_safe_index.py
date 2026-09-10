from pathlib import Path
s=Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
for m in ["R3_LIBRARY_META_SAFE_INDEX_V71='v71'","title:typeof row.title==='string'?row.title:null","creator:typeof row.creator==='string'?row.creator:null","cover_key:typeof row.cover_key==='string'?row.cover_key:null"]:
    assert m in s,m
print('READER_V71_META_SAFE_INDEX_CHECK=PASS')
