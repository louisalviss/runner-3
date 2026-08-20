#!/usr/bin/env python3
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
STATUS_PATH = ROOT / 'ops/audio-library/chatgpt-bridge-status.json'
ITEM_PREFIX = 'audio-library/items/'
QUEUE_PREFIX = 'audio-library/queue/'
API = 'https://www.curl-x.com/api/extract'
UA = 'curl/8.5.0 Runner3AudioResolver/1.0'


def bridge_status():
    return json.loads(STATUS_PATH.read_text(encoding='utf-8'))


def queue_token():
    token = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not token:
        raise RuntimeError('CLOUDFLARE_API_TOKEN missing')
    return hashlib.sha256(b'runner3-chatgpt-queue-v2\0' + token.encode()).hexdigest()


def pending_items():
    url = str(bridge_status()['url']).rstrip('/') + '/pending'
    r = requests.get(url, params={'token': queue_token()}, headers={'User-Agent': UA}, timeout=40)
    r.raise_for_status()
    return r.json().get('items') or []


def wrangler_get(key: str):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        path = Path(tmp.name)
    try:
        run = subprocess.run(
            ['npx','-y','wrangler@4.123.0','r2','object','get',f'{BUCKET}/{key}',f'--file={path}','--remote'],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if run.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    finally:
        path.unlink(missing_ok=True)


def wrangler_put(key: str, value: dict):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        json.dump(value, tmp, ensure_ascii=False, separators=(',', ':'))
        path = Path(tmp.name)
    try:
        run = subprocess.run([
            'npx','-y','wrangler@4.123.0','r2','object','put',f'{BUCKET}/{key}',
            f'--file={path}','--content-type=application/json; charset=utf-8','--remote'
        ], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if run.returncode != 0:
            raise RuntimeError('wrangler put failed')
    finally:
        path.unlink(missing_ok=True)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def canonical_from_payload(payload):
    patterns = [
        re.compile(r'https?://(?:www\.|old\.)?reddit\.com(/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)', re.I),
        re.compile(r'https?://(?:www\.|old\.)?reddit\.com(/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)', re.I),
        re.compile(r'https?://redd\.it/([a-z0-9]+)', re.I),
    ]
    for text in strings(payload):
        for idx, pat in enumerate(patterns):
            m = pat.search(text)
            if not m:
                continue
            if idx < 2:
                return 'https://www.reddit.com' + m.group(1).rstrip('/')
            return 'https://www.reddit.com/comments/' + m.group(1)
    if isinstance(payload, dict) and str(payload.get('platform') or '').lower() == 'reddit':
        for key in ('postId','post_id','redditId','reddit_id'):
            value = str(payload.get(key) or '')
            if re.fullmatch(r'[a-z0-9]{5,12}', value, re.I):
                return 'https://www.reddit.com/comments/' + value
    return None


def update_item(item_id, original, canonical):
    now = datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    item_key = f'{ITEM_PREFIX}{item_id}.json'
    queue_key = f'{QUEUE_PREFIX}{item_id}.json'
    item = wrangler_get(item_key)
    queue = wrangler_get(queue_key)
    if item:
        item['sharedUrl'] = item.get('sharedUrl') or original
        item['sourceUrl'] = canonical
        item['canonicalUrl'] = canonical
        item['error'] = None
        item['updatedAt'] = now
        wrangler_put(item_key, item)
    if queue:
        queue['sharedUrl'] = queue.get('sharedUrl') or original
        queue['sourceUrl'] = canonical
        wrangler_put(queue_key, queue)
    return bool(item or queue)


def safe_shape(payload):
    if not isinstance(payload, dict):
        return {'type': type(payload).__name__}
    keys = sorted(str(k) for k in payload.keys())[:30]
    out = {'keys': keys}
    for key in ('platform','code','error'):
        if key in payload:
            value = str(payload.get(key) or '')
            if 'http://' not in value and 'https://' not in value:
                out[key] = value[:160]
    media = payload.get('media')
    if isinstance(media, list):
        out['mediaCount'] = len(media)
    return out


def main():
    results = []
    for item in pending_items()[:5]:
        item_id = str(item.get('id') or '')
        source = str(item.get('sourceUrl') or '')
        host = (urlparse(source).hostname or '').lower()
        if not item_id or 'reddit.com' not in host or '/s/' not in urlparse(source).path:
            continue
        try:
            r = requests.post(API, json={'url': source}, headers={
                'User-Agent': UA,
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }, timeout=75)
            try:
                payload = r.json()
            except Exception:
                payload = {'nonJson': True, 'bytes': len(r.content)}
            canonical = canonical_from_payload(payload)
            updated = update_item(item_id, source, canonical) if canonical else False
            results.append({
                'id': item_id,
                'status': 'resolved' if canonical else 'no_canonical',
                'httpStatus': r.status_code,
                'canonicalResolved': bool(canonical),
                'r2Updated': updated,
                'shape': safe_shape(payload),
            })
        except Exception as e:
            results.append({'id': item_id, 'status': 'error', 'error': type(e).__name__})
    print(json.dumps({'ok': True, 'results': results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
