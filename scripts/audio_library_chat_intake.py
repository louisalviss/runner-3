#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
RETENTION_DAYS = int(os.environ.get('AUDIO_LIBRARY_RETENTION_DAYS', '30'))
ITEM_PREFIX = 'audio-library/items/'
QUEUE_PREFIX = 'audio-library/queue/'
MEDIA_PREFIX = 'audio-library/media/'


def normalize_url(raw: str) -> str:
    value = str(raw or '').strip()
    p = urlsplit(value)
    if p.scheme not in {'http', 'https'} or not p.netloc:
        raise ValueError('invalid http(s) URL')
    host = p.hostname.lower() if p.hostname else ''
    port = p.port
    netloc = host
    if port and not ((p.scheme == 'http' and port == 80) or (p.scheme == 'https' and port == 443)):
        netloc += f':{port}'
    return urlunsplit((p.scheme.lower(), netloc, p.path or '/', p.query, ''))


def source_label(url: str) -> str:
    host = (urlsplit(url).hostname or '').lower()
    if host == 'youtu.be' or host.endswith('youtube.com'):
        return 'YouTube'
    if host.endswith('reddit.com'):
        return 'Reddit'
    if host == 'x.com' or host.endswith('twitter.com'):
        return 'X'
    return host.removeprefix('www.') or 'Web'


def wrangler_get(key: str):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        cmd = ['npx', '-y', 'wrangler@4.123.0', 'r2', 'object', 'get', f'{BUCKET}/{key}', f'--file={tmp_path}', '--remote']
        run = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if run.returncode != 0:
            return None
        return json.loads(tmp_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def wrangler_put_json(key: str, payload: dict):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        json.dump(payload, tmp, ensure_ascii=False, separators=(',', ':'))
        tmp_path = Path(tmp.name)
    try:
        cmd = [
            'npx', '-y', 'wrangler@4.123.0', 'r2', 'object', 'put', f'{BUCKET}/{key}',
            f'--file={tmp_path}', '--content-type=application/json; charset=utf-8', '--remote',
        ]
        subprocess.check_call(cmd, cwd=ROOT)
    finally:
        tmp_path.unlink(missing_ok=True)


def enqueue(raw_url: str, origin='chat'):
    url = normalize_url(raw_url)
    item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url))
    item_key = f'{ITEM_PREFIX}{item_id}.json'
    queue_key = f'{QUEUE_PREFIX}{item_id}.json'
    existing = wrangler_get(item_key)
    if existing and existing.get('status') in {'pending', 'processing', 'ready'}:
        expires = existing.get('expiresAt')
        if existing.get('pinned') or not expires:
            return {'url': url, 'id': item_id, 'status': 'duplicate'}
        try:
            if datetime.fromisoformat(expires.replace('Z', '+00:00')) > datetime.now(timezone.utc):
                return {'url': url, 'id': item_id, 'status': 'duplicate'}
        except Exception:
            return {'url': url, 'id': item_id, 'status': 'duplicate'}

    now = datetime.now(timezone.utc)
    created = now.isoformat().replace('+00:00', 'Z')
    expires = (now + timedelta(days=RETENTION_DAYS)).isoformat().replace('+00:00', 'Z')
    label = source_label(url)
    item = {
        'id': item_id,
        'sourceUrl': url,
        'sourceLabel': label,
        'title': label,
        'status': 'pending',
        'createdAt': created,
        'updatedAt': created,
        'expiresAt': expires,
        'pinned': False,
        'durationSeconds': None,
        'progressSeconds': 0,
        'audioUrl': None,
        'transcriptUrl': None,
        'mediaPrefix': f'{MEDIA_PREFIX}{item_id}/',
        'error': None,
        'origin': origin,
    }
    queue = {'id': item_id, 'sourceUrl': url, 'createdAt': created, 'origin': origin}
    wrangler_put_json(item_key, item)
    wrangler_put_json(queue_key, queue)
    return {'url': url, 'id': item_id, 'status': 'queued'}


def urls_from_request(path: Path):
    data = json.loads(path.read_text(encoding='utf-8'))
    vals = []
    if isinstance(data.get('url'), str):
        vals.append(data['url'])
    if isinstance(data.get('urls'), list):
        vals.extend(x for x in data['urls'] if isinstance(x, str))
    if not vals:
        raise ValueError('request must contain url or urls')
    return vals


def main(argv):
    if len(argv) < 2:
        raise SystemExit('usage: audio_library_chat_intake.py <request.json> [...]')
    out = []
    for name in argv[1:]:
        path = Path(name)
        for url in urls_from_request(path):
            out.append(enqueue(url, origin='chat'))
    print(json.dumps({'ok': True, 'results': out}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv)
