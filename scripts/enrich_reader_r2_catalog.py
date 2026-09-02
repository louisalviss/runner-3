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
                ranked.append((score, href, media))
            if ranked:
                ranked.sort(reverse=True)
                cover_href, cover_media = ranked[0][1], ranked[0][2]

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
    catalog = {'version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(), 'books': {}}
    with tempfile.TemporaryDirectory(prefix='r3-epub-catalog-') as tmp:
        root = pathlib.Path(tmp)
        for i, obj in enumerate(objects, 1):
            key = obj['key']
            scope = obj['scope']
            print(f'[{i}/{len(objects)}] {scope}: {key}', flush=True)
            epub_path = root / f'{i:03d}.epub'
            epub_path.write_bytes(get_object_bytes(key))
            meta = epub_metadata(epub_path)
            entry = {'title': meta.get('title') or '', 'creator': meta.get('creator') or '', 'epub_key': key}
            cover = meta.get('cover_bytes')
            if cover:
                ext, media = extension_for(meta.get('cover_media') or '', cover)
                cover_key = f'core/ebook/{scope}/meta/cover{ext}'
                put_object_bytes(cover_key, cover, media)
                entry['cover_key'] = cover_key
                entry['cover_type'] = media
                entry['cover_bytes'] = len(cover)
            else:
                print(f'WARN no cover found: {scope}', flush=True)
            catalog['books'][scope] = entry

        index_bytes = (json.dumps(catalog, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        put_object_bytes(INDEX_KEY, index_bytes, 'application/json')
        print('R3_R2_CATALOG_ENRICH=PASS books=%d covers=%d' % (len(catalog['books']), sum(1 for x in catalog['books'].values() if x.get('cover_key'))))


if __name__ == '__main__':
    main()
