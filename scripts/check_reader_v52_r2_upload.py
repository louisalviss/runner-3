from pathlib import Path

root = Path('cloudflare/runner3-core')
artifact = (root / 'artifact-list-entry.js').read_text(encoding='utf-8')
reader = (root / 'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

artifact_markers = [
    'EPUB_UPLOAD_MAX_BYTES = 90 * 1024 * 1024',
    'async function handleLibraryUpload(request, env)',
    "if (!(await hasLibrarySession(request, env)))",
    "request.headers.get('x-runner3-library') !== '1'",
    "env.ARTIFACTS.head(key)",
    "env.ARTIFACTS.put(key, request.body",
    "const key = 'core/ebook/' + scope + '/final/' + filename",
    "error: 'EPUB_ALREADY_EXISTS'",
    '"/artifact-library/api/upload"',
    'id="uploadFile"',
    'function uploadEpub(file)',
]
reader_markers = [
    'id="r3LiveLibraryUpload"',
    'id="r3LiveLibraryUploadInput"',
    'function r3LiveUploadEpub(file)',
    "xhr.open('POST','/artifact-library/api/upload',true)",
    "r3LiveLibraryBooks=null",
]

for marker in artifact_markers:
    if marker not in artifact:
        raise SystemExit('V52_ARTIFACT_UPLOAD_MISSING:' + marker)
for marker in reader_markers:
    if marker not in reader:
        raise SystemExit('V52_READER_UPLOAD_MISSING:' + marker)

if "env.ARTIFACTS.put(key, request.body" not in artifact:
    raise SystemExit('V52_UPLOAD_NOT_STREAMING')
if "await request.arrayBuffer()" in artifact or "await request.formData()" in artifact[artifact.find('async function handleLibraryUpload'):artifact.find('async function handleLibraryDelivery')]:
    raise SystemExit('V52_UPLOAD_BUFFERS_BODY')

print('READER_V52_R2_UPLOAD_CHECK=PASS')
