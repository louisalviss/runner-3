from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
text=SIMPLE.read_text(encoding='utf-8')
if 'R3_LIBRARY_META_SAFE_INDEX_V71' in text:
    print('READER_V71_META_SAFE_INDEX=ALREADY_APPLIED')
    raise SystemExit(0)
old="""    const objects=data.objects.filter(r3ValidFastLibraryRowV65).map(row=>({key:String(row.key),size:Number(row.size||0),uploaded:row.uploaded||null,scope:String(row.scope||scopeOf(String(row.key))||'')}));"""
new="""    const R3_LIBRARY_META_SAFE_INDEX_V71='v71';
    const objects=data.objects.filter(r3ValidFastLibraryRowV65).map(row=>({key:String(row.key),size:Number(row.size||0),uploaded:row.uploaded||null,scope:String(row.scope||scopeOf(String(row.key))||''),title:typeof row.title==='string'?row.title:null,creator:typeof row.creator==='string'?row.creator:null,cover_key:typeof row.cover_key==='string'?row.cover_key:null}));"""
if old not in text:
    raise SystemExit('V71_FAST_INDEX_MAP_ANCHOR_MISSING')
text=text.replace(old,new,1)
SIMPLE.write_text(text,encoding='utf-8')
print('READER_V71_META_SAFE_INDEX=PASS')
