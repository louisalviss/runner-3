from pathlib import Path

PATH = Path('cloudflare/runner3-core/artifact-library-simple-entry.js')
text = PATH.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)


if 'SIMPLE_EPUB_UPLOAD_MAX_BYTES' not in text:
    text = replace_once(
        text,
        'const ROBOTS = "noindex, nofollow, noarchive, nosnippet,noimageindex";\n' if 'const ROBOTS = "noindex, nofollow,noarchive,nosnippet,noimageindex";' in text else 'const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";\n',
        ('const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";\n'
         'const SIMPLE_EPUB_UPLOAD_MAX_BYTES = 90 * 1024 * 1024;\n'),
        'upload constant',
    )

if 'function browserCookie(' not in text:
    marker = 'function mergeCookie(raw, name, value) {\n'
    helper = '''function browserCookie(request, name) {\n  const raw = request.headers.get("Cookie") || "";\n  for (const part of raw.split(";")) {\n    const i = part.indexOf("=");\n    if (i >= 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();\n  }\n  return "";\n}\n\nasync function hasBrowserLibrarySession(request, env) {\n  const expected = await sessionValue(env);\n  return Boolean(expected) && browserCookie(request, LIBRARY_COOKIE) === expected;\n}\n\n'''
    text = replace_once(text, marker, helper + marker, 'browser session helper')

if 'id="uploadEpub"' not in text:
    old = '<body><main class="shell"><form id="searchForm" class="tools" role="search"><input id="search" class="search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books"><button class="icon" type="submit" aria-label="Search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.6-3.6"></path></svg></button><button id="refresh" class="icon" type="button" aria-label="Refresh R2"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v5h-5"></path><path d="M19 11a8 8 0 1 0 1 5"></path></svg></button></form><div id="status" class="status"></div>'
    new = '<body><main class="shell"><form id="searchForm" class="tools" role="search"><input id="search" class="search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books"><button class="icon" type="submit" aria-label="Search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.6-3.6"></path></svg></button><button id="refresh" class="icon" type="button" aria-label="Refresh R2"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v5h-5"></path><path d="M19 11a8 8 0 1 0 1 5"></path></svg></button></form><button id="uploadEpub" class="upload-epub" type="button">＋ Upload EPUB</button><input id="uploadEpubInput" type="file" accept=".epub,application/epub+zip" hidden><div id="status" class="status"></div>'
    text = replace_once(text, old, new, 'visible upload controls')

if '.upload-epub{' not in text:
    text = replace_once(
        text,
        '.status{display:none;color:#8793a0;font-size:12px;padding:6px 2px 10px}',
        '.upload-epub{width:100%;appearance:none;border:1px solid #33404d;background:#eaf0f6;color:#090c10;border-radius:12px;min-height:44px;padding:10px 14px;font:inherit;font-weight:850;margin:0 0 10px;cursor:pointer}.upload-epub:disabled{opacity:.55}.status{display:none;color:#8793a0;font-size:12px;padding:6px 2px 10px}',
        'visible upload css',
    )

upload_browser = r'''
  function uploadEpub(file){
    if(!file)return;
    if(!/\.epub$/i.test(file.name||'')){status('Only .epub files are accepted.');return;}
    if(Number(file.size||0)>90*1024*1024){status('EPUB is larger than 90 MiB.');return;}
    const button=$('uploadEpub');
    button.disabled=true;button.textContent='Uploading…';status('Uploading '+file.name+'…');
    const xhr=new XMLHttpRequest();
    xhr.open('POST','/artifact-library/api/upload',true);
    xhr.setRequestHeader('x-runner3-library','1');
    xhr.setRequestHeader('x-r3-filename',encodeURIComponent(file.name));
    xhr.setRequestHeader('content-type','application/epub+zip');
    xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.max(0,Math.min(100,Math.round(e.loaded/e.total*100)));status('Uploading '+file.name+' · '+pct+'%');}};
    xhr.onerror=()=>{button.disabled=false;button.textContent='＋ Upload EPUB';status('Upload failed: network error');};
    xhr.onload=()=>{let data={};try{data=JSON.parse(xhr.responseText||'{}')}catch(_){}button.disabled=false;button.textContent='＋ Upload EPUB';if(xhr.status===401){status('Upload requires your Library PIN session. Open/re-login Library, then try again.');return;}if(xhr.status<200||xhr.status>=300||data.ok!==true){status('Upload failed: '+(data.error||('HTTP '+xhr.status)));return;}status('Uploaded to R2: '+file.name);load();};
    xhr.send(file);
  }
'''
if 'function uploadEpub(file)' not in text:
    text = replace_once(
        text,
        "  $('searchForm').addEventListener('submit',e=>{e.preventDefault();query=$('search').value;render();});",
        upload_browser + "\n  $('uploadEpub').addEventListener('click',()=>$('uploadEpubInput').click());\n  $('uploadEpubInput').addEventListener('change',e=>{const file=e.target.files&&e.target.files[0];e.target.value='';uploadEpub(file);});\n  $('searchForm').addEventListener('submit',e=>{e.preventDefault();query=$('search').value;render();});",
        'upload browser runtime',
    )

server = r'''
function simpleDecodeUploadFilename(request) {
  const encoded = String(request.headers.get('x-r3-filename') || '').trim();
  if (!encoded || encoded.length > 1200) return '';
  let value = '';
  try { value = decodeURIComponent(encoded); } catch { return ''; }
  value = value.normalize('NFC').replace(/[\u0000-\u001f\u007f]/g, '').replace(/[\\/]/g, '-').trim();
  if (!value || !/\.epub$/i.test(value)) return '';
  if (value.length > 180) value = value.slice(0, 175).replace(/\.+$/g, '') + '.epub';
  return value;
}

function simpleUploadHash(value) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) { hash ^= value.charCodeAt(i); hash = Math.imul(hash, 16777619) >>> 0; }
  return hash.toString(36);
}

function simpleUploadScope(filename) {
  const stem = filename.replace(/\.epub$/i, '');
  const ascii = stem.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const slug = ascii.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'book';
  return (slug + '-' + simpleUploadHash(stem.toLowerCase())).slice(0, 80);
}

async function publicUpload(request, env) {
  if (request.method !== 'POST') return json({ ok: false, error: 'METHOD_NOT_ALLOWED' }, 405);
  if (!(await hasBrowserLibrarySession(request, env))) return json({ ok: false, error: 'UNAUTHORIZED' }, 401);
  if (request.headers.get('x-runner3-library') !== '1') return json({ ok: false, error: 'BAD_LIBRARY_REQUEST' }, 400);
  if (!env.ARTIFACTS) return json({ ok: false, error: 'R2_NOT_BOUND' }, 503);
  const filename = simpleDecodeUploadFilename(request);
  if (!filename) return json({ ok: false, error: 'EPUB_FILENAME_REQUIRED' }, 400);
  const lengthHeader = request.headers.get('content-length');
  const size = lengthHeader ? Number(lengthHeader) : null;
  if (Number.isFinite(size) && size <= 0) return json({ ok: false, error: 'EMPTY_EPUB' }, 400);
  if (Number.isFinite(size) && size > SIMPLE_EPUB_UPLOAD_MAX_BYTES) return json({ ok: false, error: 'EPUB_TOO_LARGE', max_bytes: SIMPLE_EPUB_UPLOAD_MAX_BYTES }, 413);
  if (!request.body) return json({ ok: false, error: 'EMPTY_EPUB' }, 400);
  const key = ROOT + simpleUploadScope(filename) + '/final/' + filename;
  if (await env.ARTIFACTS.head(key)) return json({ ok: false, error: 'EPUB_ALREADY_EXISTS', key }, 409);
  try {
    const stored = await env.ARTIFACTS.put(key, request.body, { httpMetadata: { contentType: 'application/epub+zip' }, customMetadata: { source: 'artifact-library-upload-v53' } });
    return json({ ok: true, key, size: Number.isFinite(size) ? size : null, etag: stored?.httpEtag || stored?.etag || null }, 201);
  } catch (error) {
    return json({ ok: false, error: 'R2_UPLOAD_FAILED', detail: String(error?.message || error) }, 502);
  }
}

'''
if 'async function publicUpload(request, env)' not in text:
    text = replace_once(text, 'async function publicDelivery(request, env, ctx) {', server + 'async function publicDelivery(request, env, ctx) {', 'simple upload handler')

if 'p === "/artifact-library/api/upload"' not in text:
    route_marker = '    if (p === "/artifact-library/api/list") return publicList(request, env);\n'
    if route_marker not in text:
        raise SystemExit('simple upload route marker missing')
    text = text.replace(route_marker, route_marker + '    if (p === "/artifact-library/api/upload") return publicUpload(request, env);\n', 1)

for marker in [
    'id="uploadEpub"', 'id="uploadEpubInput"', 'function uploadEpub(file)',
    'async function publicUpload(request, env)', 'hasBrowserLibrarySession(request, env)',
    "env.ARTIFACTS.put(key, request.body", 'EPUB_ALREADY_EXISTS',
    'p === "/artifact-library/api/upload"',
]:
    if marker not in text:
        raise SystemExit('READER_V53_SIMPLE_UPLOAD_MISSING:' + marker)

PATH.write_text(text, encoding='utf-8')
print('READER_V53_SIMPLE_LIBRARY_UPLOAD=PASS')
