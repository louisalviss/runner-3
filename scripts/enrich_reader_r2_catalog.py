#!/usr/bin/env python3
import json
import mimetypes
import os
import pathlib
import posixpath
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

CORE = os.environ.get('R3_LIBRARY_ORIGIN', 'https://runner3-core.ducduy2411.workers.dev').rstrip('/')
BUCKET = os.environ.get('R3_ARTIFACT_BUCKET', 'runner3-artifacts')
INDEX_KEY = 'core/ebook/_index/library-books.json'


def run(*args):
    print('+', ' '.join(args), flush=True)
    subprocess.run(args, check=True)


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
                if 'cover' in hay: score += 10
                if media in ('image/jpeg', 'image/png', 'image/webp'): score += 2
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
                # Some EPUBs use percent-escaped paths in the manifest.
                from urllib.parse import unquote
                cover_path = unquote(cover_path)
                cover_bytes = zf.read(cover_path)

        return {
            'title': title,
            'creator': creator,
            'cover_bytes': cover_bytes,
            'cover_media': cover_media,
        }


def extension_for(media, data):
    media = (media or '').lower()
    if media == 'image/png' or data.startswith(b'\x89PNG'): return '.png', 'image/png'
    if media == 'image/webp' or data.startswith(b'RIFF'): return '.webp', 'image/webp'
    if media == 'image/gif' or data.startswith(b'GIF8'): return '.gif', 'image/gif'
    return '.jpg', 'image/jpeg'


def main():
    with urllib.request.urlopen(CORE + '/artifact-library/api/list', timeout=60) as response:
        payload = json.load(response)
    objects = payload.get('objects') or []
    if not objects:
        raise SystemExit('NO_EPUB_OBJECTS')

    catalog = {'version': 1, 'generated_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z', 'books': {}}
    with tempfile.TemporaryDirectory(prefix='r3-epub-catalog-') as tmp:
        root = pathlib.Path(tmp)
        for i, obj in enumerate(objects, 1):
            key = str(obj.get('key') or '')
            scope = str(obj.get('scope') or '')
            if not key or not scope:
                continue
            print(f'[{i}/{len(objects)}] {scope}: {key}', flush=True)
            epub_path = root / f'{i:03d}.epub'
            run('npx', '--yes', 'wrangler@4', 'r2', 'object', 'get', f'{BUCKET}/{key}', '--remote', '--file', str(epub_path))
            meta = epub_metadata(epub_path)
            entry = {
                'title': meta.get('title') or '',
                'creator': meta.get('creator') or '',
                'epub_key': key,
            }
            cover = meta.get('cover_bytes')
            if cover:
                ext, media = extension_for(meta.get('cover_media') or '', cover)
                cover_key = f'core/ebook/{scope}/meta/cover{ext}'
                cover_path = root / f'{i:03d}{ext}'
                cover_path.write_bytes(cover)
                run('npx', '--yes', 'wrangler@4', 'r2', 'object', 'put', f'{BUCKET}/{cover_key}', '--remote', '--file', str(cover_path), '--content-type', media)
                entry['cover_key'] = cover_key
                entry['cover_type'] = media
                entry['cover_bytes'] = len(cover)
            else:
                print(f'WARN no cover found: {scope}', flush=True)
            catalog['books'][scope] = entry

        index_path = root / 'library-books.json'
        index_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        run('npx', '--yes', 'wrangler@4', 'r2', 'object', 'put', f'{BUCKET}/{INDEX_KEY}', '--remote', '--file', str(index_path), '--content-type', 'application/json')
        print('R3_R2_CATALOG_ENRICH=PASS books=%d covers=%d' % (
            len(catalog['books']), sum(1 for x in catalog['books'].values() if x.get('cover_key'))
        ))


if __name__ == '__main__':
    main()
