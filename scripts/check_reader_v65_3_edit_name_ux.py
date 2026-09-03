from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
simple=(ROOT/'artifact-library-simple-entry.js').read_text(encoding='utf-8')
v2=(ROOT/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
runtime=(ROOT/'reader-v65-3-edit-name-ux-runtime.js').read_text(encoding='utf-8')

for forbidden in ('`','${','</script>'):
    if forbidden in runtime:
        raise SystemExit('READER_V65_3_RUNTIME_FORBIDDEN:'+forbidden)
for marker in [
    'window.__R3_EDIT_NAME_UX_V653=true',
    'r3-edit-layer-v653',
    'Đổi tên sách',
    "request('rename',bookKey,next)",
    "event.stopImmediatePropagation()",
    "window.confirm('Xóa sách này khỏi Library?",
]:
    if marker not in runtime: raise SystemExit('READER_V65_3_RUNTIME_MISSING:'+marker)
for text,label in ((simple,'SIMPLE'),(v2,'READER')):
    if text.count('window.__R3_EDIT_NAME_UX_V653=true')!=1:
        raise SystemExit('READER_V65_3_'+label+'_INJECTION_COUNT:'+str(text.count('window.__R3_EDIT_NAME_UX_V653=true')))
    for marker in ['r3-edit-sheet-v653','r3-edit-input-v653','Tên này đã tồn tại. Chọn tên khác.']:
        if marker not in text: raise SystemExit('READER_V65_3_'+label+'_MISSING:'+marker)

# Existing v65 backend / Reader invariants stay intact.
for marker in ['async function publicManageBookV65','ebook_reader_progress_v65','r3InstallMainManageV65']:
    if marker not in simple: raise SystemExit('READER_V65_3_BASE_SIMPLE_MISSING:'+marker)
for marker in ['r3InstallLiveManageV65','__r3SafariBootGeometryV61','__r3PaginatedVerticalClampV62','function r3StructuralPercentV64']:
    if marker not in v2: raise SystemExit('READER_V65_3_BASE_READER_MISSING:'+marker)

print('READER_V65_3_EDIT_NAME_UX_CHECK=PASS')
