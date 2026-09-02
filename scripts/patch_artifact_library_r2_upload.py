from pathlib import Path

PATH = Path('cloudflare/runner3-core/artifact-list-entry.js')
text = PATH.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)


if 'EPUB_UPLOAD_MAX_BYTES' not in text:
    text = replace_once(
        text,
        'const LIBRARY_SESSION_SECONDS = 12 * 60 * 60;\n',
        'const LIBRARY_SESSION_SECONDS = 12 * 60 * 60;\nconst EPUB_UPLOAD_MAX_BYTES = 90 * 1024 * 1024;\n',
        'upload size constant',
    )

if 'id="uploadFile"' not in text:
    text = replace_once(
        text,
        '.toolbar{display:grid;grid-template-columns:minmax(260px,1fr) minmax(180px,.55fr) auto;gap:10px}',
        '.toolbar{display:grid;grid-template-columns:minmax(260px,1fr) minmax(180px,.55fr) auto auto;gap:10px}',
        'toolbar columns',
    )
    old_toolbar = '<section class="panel"><div class="toolbar"><input id="prefix" class="input" value="core/ebook/" aria-label="R2 prefix"><input id="search" class="input" placeholder="Search filename or path" aria-label="Search"><button id="refresh" class="button primary">Refresh R2</button></div><div class="chips">'
    new_toolbar = '<section class="panel"><div class="toolbar"><input id="prefix" class="input" value="core/ebook/" aria-label="R2 prefix"><input id="search" class="input" placeholder="Search filename or path" aria-label="Search"><button id="refresh" class="button primary">Refresh R2</button><button id="upload" class="button" type="button">＋ Upload EPUB</button><input id="uploadFile" type="file" accept=".epub,application/epub+zip" hidden></div><div class="chips">'
    text = replace_once(text, old_toolbar, new_toolbar, 'upload controls')

upload_js = r'''
function setUploadBusy(busy){const btn=el('upload');if(btn){btn.disabled=busy;btn.textContent=busy?'Uploading…':'＋ Upload EPUB'}}
function uploadEpub(file){
  if(!file)return;
  if(!/\.epub$/i.test(file.name||'')){alert('Chỉ nhận file .epub');return}
  if(Number(file.size||0)>90*1024*1024){alert('EPUB vượt giới hạn 90 MiB.');return}
  const xhr=new XMLHttpRequest();
  setUploadBusy(true);el('status').textContent='Uploading '+file.name+'…';
  xhr.open('POST','/artifact-library/api/upload',true);
  xhr.setRequestHeader('x-runner3-library','1');
  xhr.setRequestHeader('x-r3-filename',encodeURIComponent(file.name));
  xhr.setRequestHeader('content-type','application/epub+zip');
  xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.max(0,Math.min(100,Math.round((e.loaded/e.total)*100)));el('status').textContent='Uploading '+file.name+' · '+pct+'%'}};
  xhr.onerror=()=>{setUploadBusy(false);el('status').textContent='Upload failed: network error';alert('Upload failed: network error')};
  xhr.onload=()=>{let body={};try{body=JSON.parse(xhr.responseText||'{}')}catch(_){body={}}if(xhr.status===401){location.reload();return}if(xhr.status<200||xhr.status>=300||body.ok!==true){setUploadBusy(false);const message=body.error==='EPUB_ALREADY_EXISTS'?'File này đã có trong R2.':(body.error||('HTTP '+xhr.status));el('status').textContent='Upload failed: '+message;alert('Upload failed: '+message);return}el('status').textContent='Uploaded to R2 · '+body.key;setUploadBusy(false);state.mode='latest';document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x.dataset.mode==='latest'));load()};
  xhr.send(file);
}
'''
if 'function uploadEpub(file)' not in text:
    text = replace_once(
        text,
        "el('refresh').addEventListener('click',load);",
        upload_js + "\nel('upload').addEventListener('click',()=>el('uploadFile').click());el('uploadFile').addEventListener('change',e=>{const file=e.target.files&&e.target.files[0];e.target.value='';uploadEpub(file)});\nel('refresh').addEventListener('click',load);",
        'upload browser runtime',
    )

server_code = r'''
function decodeUploadFilename(request) {
  const encoded = String(request.headers.get('x-r3-filename') || '').trim();
  if (!encoded || encoded.length > 1200) return '';
  let value = '';
  try { value = decodeURIComponent(encoded); } catch { return ''; }
  value = value.normalize('NFC').replace(/[\u0000-\u001f\u007f]/g, '').replace(/[\\/]/g, '-').trim();
  if (!value || !/\.epub$/i.test(value)) return '';
  if (value.length > 180) value = value.slice(0, 175).replace(/\.+$/g, '') + '.epub';
  return value;
}

function stableUploadHash(value) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash.toString(36);
}

function uploadScopeForFilename(filename) {
  const stem = filename.replace(/\.epub$/i, '');
  const ascii = stem.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const slug = ascii.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'book';
  return (slug + '-' + stableUploadHash(stem.toLowerCase())).slice(0, 80);
}

async function handleLibraryUpload(request, env) {
  if (request.method !== 'POST') return json({ ok: false, error: 'METHOD_NOT_ALLOWED' }, 405);
  if (!(await hasLibrarySession(request, env))) return json({ ok: false, error: 'UNAUTHORIZED' }, 401);
  if (request.headers.get('x-runner3-library') !== '1') return json({ ok: false, error: 'BAD_LIBRARY_REQUEST' }, 400);
  if (!env.ARTIFACTS) return json({ ok: false, error: 'R2_NOT_BOUND' }, 503);
  const filename = decodeUploadFilename(request);
  if (!filename) return json({ ok: false, error: 'EPUB_FILENAME_REQUIRED' }, 400);
  const type = String(request.headers.get('content-type') || '').split(';', 1)[0].trim().toLowerCase();
  if (type !== 'application/epub+zip' && type !== 'application/octet-stream' && type !== 'application/zip') {
    return json({ ok: false, error: 'EPUB_CONTENT_TYPE_REQUIRED' }, 415);
  }
  const rawLength = request.headers.get('content-length');
  const size = rawLength ? Number(rawLength) : null;
  if (Number.isFinite(size) && size <= 0) return json({ ok: false, error: 'EMPTY_EPUB' }, 400);
  if (Number.isFinite(size) && size > EPUB_UPLOAD_MAX_BYTES) return json({ ok: false, error: 'EPUB_TOO_LARGE', max_bytes: EPUB_UPLOAD_MAX_BYTES }, 413);
  if (!request.body) return json({ ok: false, error: 'EMPTY_EPUB' }, 400);

  const scope = uploadScopeForFilename(filename);
  const key = 'core/ebook/' + scope + '/final/' + filename;
  const existing = await env.ARTIFACTS.head(key);
  if (existing) return json({ ok: false, error: 'EPUB_ALREADY_EXISTS', key }, 409);

  let stored;
  try {
    stored = await env.ARTIFACTS.put(key, request.body, {
      httpMetadata: { contentType: 'application/epub+zip' },
      customMetadata: { source: 'artifact-library-upload' },
    });
  } catch (error) {
    return json({ ok: false, error: 'R2_UPLOAD_FAILED', detail: String(error && error.message || error) }, 502);
  }
  return json({
    ok: true,
    key,
    size: Number.isFinite(size) ? size : null,
    etag: stored && (stored.httpEtag || stored.etag) || null,
    source: 'library-upload',
  }, 201);
}

'''
if 'async function handleLibraryUpload(request, env)' not in text:
    text = replace_once(
        text,
        'async function handleLibraryDelivery(request, env, ctx) {',
        server_code + 'async function handleLibraryDelivery(request, env, ctx) {',
        'upload server handler',
    )

if '"/artifact-library/api/upload"' not in text:
    text = replace_once(
        text,
        '    if (url.pathname === "/artifact-library/api/list") return handleLibraryList(request, env);\n',
        '    if (url.pathname === "/artifact-library/api/list") return handleLibraryList(request, env);\n    if (url.pathname === "/artifact-library/api/upload") return handleLibraryUpload(request, env);\n',
        'upload route',
    )

for marker in [
    'EPUB_UPLOAD_MAX_BYTES',
    'id="uploadFile"',
    'function uploadEpub(file)',
    'async function handleLibraryUpload(request, env)',
    "env.ARTIFACTS.put(key, request.body",
    "env.ARTIFACTS.head(key)",
    'EPUB_ALREADY_EXISTS',
    '"/artifact-library/api/upload"',
]:
    if marker not in text:
        raise SystemExit('ARTIFACT_LIBRARY_R2_UPLOAD_MISSING:' + marker)

PATH.write_text(text, encoding='utf-8')
print('ARTIFACT_LIBRARY_R2_UPLOAD=PASS')
