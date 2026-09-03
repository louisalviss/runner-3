from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
V2=ROOT/'artifact-library-reader-v2-entry.js'
RUNTIME=ROOT/'reader-v65-3-edit-name-ux-runtime.js'

simple=SIMPLE.read_text(encoding='utf-8')
v2=V2.read_text(encoding='utf-8')
runtime=RUNTIME.read_text(encoding='utf-8').strip()

for forbidden in ('`','${','</script>'):
    if forbidden in runtime:
        raise SystemExit('V65_3_RUNTIME_FORBIDDEN:'+forbidden)
if 'window.__R3_EDIT_NAME_UX_V653=true' not in runtime:
    raise SystemExit('V65_3_RUNTIME_MARKER_MISSING')

main_anchor='r3InstallMainManageV65();load();'
reader_anchor='syncUi();hideControls();r3InstallLiveManageV65();openBook();'

if 'window.__R3_EDIT_NAME_UX_V653=true' not in simple:
    if simple.count(main_anchor)!=1:
        raise SystemExit('V65_3_MAIN_ANCHOR_COUNT:'+str(simple.count(main_anchor)))
    simple=simple.replace(main_anchor,runtime+'\n'+main_anchor,1)
if 'window.__R3_EDIT_NAME_UX_V653=true' not in v2:
    if v2.count(reader_anchor)!=1:
        raise SystemExit('V65_3_READER_ANCHOR_COUNT:'+str(v2.count(reader_anchor)))
    v2=v2.replace(reader_anchor,runtime+'\n'+reader_anchor,1)

for text,label in ((simple,'simple'),(v2,'reader')):
    for marker in ('window.__R3_EDIT_NAME_UX_V653=true','r3-edit-layer-v653','Đổi tên sách','Tên này đã tồn tại. Chọn tên khác.','.r3-manage-v65,.r3-live-manage-v65'):
        if marker not in text:
            raise SystemExit('V65_3_'+label.upper()+'_MISSING:'+marker)

SIMPLE.write_text(simple,encoding='utf-8')
V2.write_text(v2,encoding='utf-8')
print('READER_V65_3_EDIT_NAME_UX=PASS')
