#!/usr/bin/env python3
import json
import os
import pathlib
import posixpath
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

BUCKET = os.environ.get('R3_ARTIFACT_BUCKET', 'runner3-artifacts')
INDEX_KEY = 'core/ebook/_index/library-books.json'
ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '').strip()
API_TOKEN = os.environ.get('CLOUDFLARE_API_TOKEN', '').strip()


def auth_headers(extra=None):
    h = {'Authorization': f'Bearer {API_TOKEN}'}
    if extra:
        h.update(extra)
    return h


def cf_json(url):
    req = urllib.request.Request(url, headers=auth_headers({'Accept': 'application/json'}))
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.load(response)
    if not data.get('success'):
        raise RuntimeError('CLOUDFLARE_API_FAILED:' + json.dumps(data.get('errors') or []))
    return data


def object_url(key):
    encoded = urllib.parse.quote(key, safe='/')
    return f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/r2/buckets/{BUCKET}/objects/{encoded}'


def get_object_bytes(key):
    req = urllib.request.Request(object_url(key), headers=auth_headers())
    with urllib.request.urlopen(req, timeout=180) as response:
        return response.read()


def object_exists(key):
    if not key:
        return False
    try:
        req = urllib.request.Request(object_url(key), headers=auth_headers({'Range': 'bytes=0-0'}))
        with urllib.request.urlopen(req, timeout=60) as response:
            response.read(1)
            return 200 <= response.status < 300
    except Exception:
        return False


def put_object_bytes(key, data, content_type):
    req = urllib.request.Request(object_url(key), data=data, method='PUT', headers=auth_headers({'Content-Type': content_type}))
    with urllib.request.urlopen(req, timeout=180) as response:
        body = response.read()
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f'R2_PUT_FAILED:{response.status}:{key}')
        if body:
            try:
                payload = json.loads(body.decode('utf-8'))
                if payload.get('success') is False:
                    raise RuntimeError('R2_PUT_API_FAILED:' + json.dumps(payload.get('errors') or []))
            except UnicodeDecodeError:
                pass


def list_final_epubs():
    if not ACCOUNT_ID or not API_TOKEN:
        raise RuntimeError('CLOUDFLARE_CREDENTIALS_MISSING')
    base = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/r2/buckets/{BUCKET}/objects'
    cursor = ''
    objects = []
    while True:
        query = {'prefix': 'core/ebook/', 'per_page': '1000'}
        if cursor:
            query['cursor'] = cursor
        data = cf_json(base + '?' + urllib.parse.urlencode(query))
        for obj in data.get('result') or []:
            key = str(obj.get('key') or '')
            if '/final/' not in key or not key.lower().endswith('.epub'):
                continue
            parts = key.split('/')
            scope = parts[2] if len(parts) > 3 else ''
            if scope:
                objects.append({'key': key, 'scope': scope, 'last_modified': obj.get('last_modified'), 'size': obj.get('size')})
        info = data.get('result_info') or {}
        if not info.get('is_truncated'):
            break
        cursor = str(info.get('cursor') or '')
        if not cursor:
            break

    latest = {}
    for obj in objects:
        scope = obj['scope']
        cur = latest.get(scope)
        if not cur or str(obj.get('last_modified') or '') > str(cur.get('last_modified') or ''):
            latest[scope] = obj
    rows = sorted(latest.values(), key=lambda x: x['scope'])
    print(f'R2_LIST_FINAL_EPUBS={len(rows)}', flush=True)
    return rows


def text_content(node):
    if node is None:
        return ''
    return ''.join(node.itertext()).strip()


def first_local(root, local):
    for node in root.iter():
        if node.tag.split('}')[-1].lower() == local.lower():
            value = text_content(node)
            if value:
                return value
    return ''


def read_existing_catalog():
    try:
        raw = get_object_bytes(INDEX_KEY)
        data = json.loads(raw.decode('utf-8'))
        if isinstance(data, dict) and isinstance(data.get('books'), dict):
            return data
    except Exception as exc:
        print(f'WARN existing catalog unavailable: {exc}', flush=True)
    return {'version': 1, 'books': {}}


def merge_text(existing, extracted):
    existing = str(existing or '').strip()
    return existing if existing else str(extracted or '').strip()


def merge_entry(existing, extracted, key):
    previous = dict(existing or {})
    entry = dict(previous)
    entry['epub_key'] = key
    entry['title'] = merge_text(previous.get('title'), extracted.get('title'))
    entry['creator'] = merge_text(previous.get('creator'), extracted.get('creator'))
    return entry


def first_image_from_spine(zf, opf, rootfile, manifest):
    first_idref = ''
    for node in opf.iter():
        if node.tag.split('}')[-1] == 'itemref':
            first_idref = str(node.attrib.get('idref', '')).strip()
            if first_idref:
                break
    if not first_idref or first_idref not in manifest:
        return '', ''
    href, media, _ = manifest[first_idref]
    if not href:
        return '', ''
    opf_dir = posixpath.dirname(rootfile)
    page_path = posixpath.normpath(posixpath.join(opf_dir, urllib.parse.unquote(href)))
    try:
        page = ET.fromstring(zf.read(page_path))
    except Exception:
        return '', ''
    image_href = ''
    for node in page.iter():
        if node.tag.split('}')[-1].lower() == 'img':
            image_href = str(node.attrib.get('src', '')).strip()
            if image_href:
                break
    if not image_href:
        return '', ''
    image_path = posixpath.normpath(posixpath.join(posixpath.dirname(page_path), urllib.parse.unquote(image_href)))
    for _, (candidate_href, candidate_media, _) in manifest.items():
        candidate_path = posixpath.normpath(posixpath.join(opf_dir, urllib.parse.unquote(candidate_href)))
        if candidate_path == image_path and candidate_media.startswith('image/'):
            return candidate_href, candidate_media
    ext = pathlib.PurePosixPath(image_path).suffix.lower()
    media = {'.png':'image/png','.webp':'image/webp','.gif':'image/gif'}.get(ext, 'image/jpeg')
    return posixpath.relpath(image_path, opf_dir or '.'), media


def epub_metadata(epub_path: pathlib.Path):
    with zipfile.ZipFile(epub_path) as zf:
        container = ET.fromstring(zf.read('META-INF/container.xml'))
        rootfile = None
        for node in container.iter():
            if node.tag.split('}')[-1] == 'rootfile':
                rootfile = node.attrib.get('full-path')
                if rootfile:
                    break
        if not rootfile:
            raise RuntimeError('EPUB_CONTAINER_ROOTFILE_MISSING')

        opf = ET.fromstring(zf.read(rootfile))
        title = first_local(opf, 'title')
        creator = first_local(opf, 'creator')
        manifest = {}
        cover_id = ''
        cover_href = ''
        cover_media = ''

        for node in opf.iter():
            local = node.tag.split('}')[-1]
            if local == 'meta' and str(node.attrib.get('name', '')).lower() == 'cover':
                cover_id = str(node.attrib.get('content', '')).strip()
            elif local == 'item':
                item_id = str(node.attrib.get('id', '')).strip()
                href = str(node.attrib.get('href', '')).strip()
                media = str(node.attrib.get('media-type', '')).strip()
                props = str(node.attrib.get('properties', '')).split()
                if item_id:
                    manifest[item_id] = (href, media, props)
                if 'cover-image' in props and href:
                    cover_href, cover_media = href, media

        if not cover_href and cover_id and cover_id in manifest:
            cover_href, cover_media, _ = manifest[cover_id]

        if not cover_href:
            cover_href, cover_media = first_image_from_spine(zf, opf, rootfile, manifest)

        if not cover_href:
            ranked = []
            for item_id, (href, media, props) in manifest.items():
                if not href or not media.startswith('image/'):
                    continue
                score = 0
                hay = f'{item_id} {href}'.lower()
                if 'cover' in hay:
                    score += 10
                if media in ('image/jpeg', 'image/png', 'image/webp'):
                    score += 2
                try:
                    opf_dir = posixpath.dirname(rootfile)
                    image_path = posixpath.normpath(posixpath.join(opf_dir, urllib.parse.unquote(href)))
                    size = zf.getinfo(image_path).file_size
                except Exception:
                    size = 0
                ranked.append((score, size, href, media))
            if ranked:
                ranked.sort(reverse=True)
                cover_href, cover_media = ranked[0][2], ranked[0][3]

        cover_bytes = None
        if cover_href:
            opf_dir = posixpath.dirname(rootfile)
            cover_path = posixpath.normpath(posixpath.join(opf_dir, cover_href))
            try:
                cover_bytes = zf.read(cover_path)
            except KeyError:
                cover_path = urllib.parse.unquote(cover_path)
                cover_bytes = zf.read(cover_path)

        return {'title': title, 'creator': creator, 'cover_bytes': cover_bytes, 'cover_media': cover_media}


def extension_for(media, data):
    media = (media or '').lower()
    if media == 'image/png' or data.startswith(b'\x89PNG'):
        return '.png', 'image/png'
    if media == 'image/webp' or data.startswith(b'RIFF'):
        return '.webp', 'image/webp'
    if media == 'image/gif' or data.startswith(b'GIF8'):
        return '.gif', 'image/gif'
    return '.jpg', 'image/jpeg'


def main():
    objects = list_final_epubs()
    if not objects:
        raise SystemExit('NO_EPUB_OBJECTS')

    from datetime import datetime, timezone
    previous_catalog = read_existing_catalog()
    previous_books = previous_catalog.get('books') if isinstance(previous_catalog.get('books'), dict) else {}
    now = datetime.now(timezone.utc)
    backup_key = f"core/ebook/_system/catalog-v72/pre-enrich-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    if previous_books:
        put_object_bytes(backup_key, (json.dumps(previous_catalog, ensure_ascii=False, indent=2) + '\n').encode('utf-8'), 'application/json')
        print(f'R3_R2_CATALOG_BACKUP={backup_key}', flush=True)
    catalog = {'version': max(2, int(previous_catalog.get('version') or 1) + 1), 'generated_at': now.isoformat(), 'recovered_by': 'metadata-preserve-v72', 'books': {}}
    with tempfile.TemporaryDirectory(prefix='r3-epub-catalog-') as tmp:
        root = pathlib.Path(tmp)
        for i, obj in enumerate(objects, 1):
            key = obj['key']
            scope = obj['scope']
            print(f'[{i}/{len(objects)}] {scope}: {key}', flush=True)
            existing = previous_books.get(scope) if isinstance(previous_books.get(scope), dict) else {}
            existing_cover_key = str(existing.get('cover_key') or '').strip()
            cover_ok = bool(existing_cover_key and object_exists(existing_cover_key))
            no_cover_expected = str(existing.get('cover_missing_reason') or '') == 'epub-no-image'
            complete = bool(str(existing.get('title') or '').strip() and str(existing.get('creator') or '').strip() and (cover_ok or no_cover_expected))
            if complete:
                entry = dict(existing)
                entry['epub_key'] = key
                print(f'PRESERVE {scope}: metadata complete', flush=True)
            else:
                epub_path = root / f'{i:03d}.epub'
                epub_path.write_bytes(get_object_bytes(key))
                meta = epub_metadata(epub_path)
                entry = merge_entry(existing, meta, key)
                if cover_ok:
                    entry['cover_key'] = existing_cover_key
                    if existing.get('cover_type'):
                        entry['cover_type'] = existing.get('cover_type')
                    if existing.get('cover_bytes'):
                        entry['cover_bytes'] = existing.get('cover_bytes')
                    entry.pop('cover_missing_reason', None)
                else:
                    cover = meta.get('cover_bytes')
                    if cover:
                        ext, media = extension_for(meta.get('cover_media') or '', cover)
                        cover_key = f'core/ebook/{scope}/meta/cover{ext}'
                        put_object_bytes(cover_key, cover, media)
                        entry['cover_key'] = cover_key
                        entry['cover_type'] = media
                        entry['cover_bytes'] = len(cover)
                        entry.pop('cover_missing_reason', None)
                    else:
                        entry.pop('cover_key', None)
                        entry.pop('cover_type', None)
                        entry.pop('cover_bytes', None)
                        entry['cover_missing_reason'] = 'epub-no-image'
                        print(f'WARN no cover found: {scope}', flush=True)
            catalog['books'][scope] = entry
            sidecar = {
                'bookKey': key,
                'display_title': entry.get('title') or '',
                'author': entry.get('creator') or '',
                'cover_key': entry.get('cover_key') or '',
                'updated_at': catalog['generated_at'],
                'source': 'metadata-preserve-v72',
            }
            put_object_bytes(f'core/ebook/{scope}/meta/book.json', (json.dumps(sidecar, ensure_ascii=False, indent=2) + '\n').encode('utf-8'), 'application/json')

        index_bytes = (json.dumps(catalog, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        put_object_bytes(INDEX_KEY, index_bytes, 'application/json')
        put_object_bytes('core/ebook/_system/catalog-v72/latest.json', index_bytes, 'application/json')
        print('R3_R2_CATALOG_ENRICH=PASS books=%d covers=%d mode=preserve' % (len(catalog['books']), sum(1 for x in catalog['books'].values() if x.get('cover_key'))))


if __name__ == '__main__':
    main()
