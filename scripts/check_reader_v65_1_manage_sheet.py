from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
simple=(ROOT/'artifact-library-simple-entry.js').read_text(encoding='utf-8')
v2=(ROOT/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

for marker in [
    "reader_client_version:'v65.1'",
    "'x-r3-reader-client-version':'v65.1'",
    'r3ManageLayerV651',
    'r3CommitRenameV651',
    'r3CommitDeleteV651',
    'r3-ms-card-v651',
    'Tùy chọn sách',
    'Đổi tên',
    'Xóa sách',
]:
    if marker not in simple: raise SystemExit('READER_V651_SIMPLE_MISSING:'+marker)

for marker in [
    "R3_READER_CLIENT_VERSION_V63='v65.1'",
    'r3ReaderManageLayerV651',
    'r3CommitReaderRenameV651',
    'r3CommitReaderDeleteV651',
    'r3-rms-card-v651',
    '.r3-live-manage-v65{border:0!important',
    '__r3SafariBootGeometryV61',
    '__r3PaginatedVerticalClampV62',
    'r3MergeRemoteProgressV65',
]:
    if marker not in v2: raise SystemExit('READER_V651_V2_MISSING:'+marker)

for source,label in [(simple,'simple'),(v2,'reader')]:
    if "prompt('R = Rename" in source: raise SystemExit('READER_V651_NATIVE_PROMPT_REMAINS:'+label)
    if "confirm('Xóa sách này" in source: raise SystemExit('READER_V651_NATIVE_CONFIRM_REMAINS:'+label)

print('READER_V65_1_MANAGE_SHEET_CHECK=PASS')
