#!/usr/bin/env python3
import html
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
STATUS = ROOT / 'ops/audio-library/chat-intake-status.json'
ITEM_PREFIX = 'audio-library/items/'
QUEUE_PREFIX = 'audio-library/queue/'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'


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
        subprocess.check_call([
            'npx','-y','wrangler@4.123.0','r2','object','put',f'{BUCKET}/{key}',
            f'--file={path}','--content-type=application/json; charset=utf-8','--remote'
        ], cwd=ROOT)
    finally:
        path.unlink(missing_ok=True)


def is_reddit_short(url: str) -> bool:
    p = urlparse(url)
    return (p.hostname or '').lower().endswith('reddit.com') and '/s/' in p.path


def normalize_reddit_candidate(value: str):
    if not value:
        return None
    value = html.unescape(value).replace('\\u002F','/').replace('\\/','/')
    m = re.search(r'https?://(?:www\.)?reddit\.com(?P<path>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)', value, re.I)
    if m:
        return 'https://www.reddit.com' + m.group('path').rstrip('\\')
    m = re.search(r'https?://(?:www\.)?curl-x\.com(?P<path>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)', value, re.I)
    if m:
        return 'https://www.reddit.com' + m.group('path').rstrip('\\')
    m = re.search(r'(?P<path>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)', value, re.I)
    if m:
        return 'https://www.reddit.com' + m.group('path').rstrip('\\')
    return None


def resolve_via_curlx(url: str):
    p = urlparse(url)
    target = 'https://www.curl-x.com' + p.path
    if p.query:
        target += '?' + p.query
    try:
        r = requests.get(
            target,
            headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*', 'Accept-Language': 'en-US,en;q=0.9'},
            timeout=60,
            allow_redirects=True,
        )
    except Exception as e:
        return None, f'curlx-request-{type(e).__name__}'

    for candidate in [r.url, r.headers.get('location','')]:
        found = normalize_reddit_candidate(candidate)
        if found:
            return found.split('?')[0], f'curlx-url:{r.status_code}'

    body = html.unescape(r.text or '')
    body = body.replace('\\u002F','/').replace('\\/','/')
    patterns = [
        r'https?://(?:www\.)?reddit\.com/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?',
        r'https?://(?:www\.)?curl-x\.com/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?',
        r'/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?',
    ]
    for pat in patterns:
        m = re.search(pat, body, re.I)
        if m:
            found = normalize_reddit_candidate(m.group(0))
            if found:
                return found.split('?')[0], f'curlx-html:{r.status_code}'

    post_id = None
    for pat in [r'"postId"\s*:\s*"([a-z0-9]+)"', r'"redditPostId"\s*:\s*"([a-z0-9]+)"', r'/comments/([a-z0-9]+)']:
        m = re.search(pat, body, re.I)
        if m:
            post_id = m.group(1)
            break
    if post_id:
        subreddit = None
        sm = re.search(r'/r/([^/]+)/s/', p.path, re.I)
        if sm:
            subreddit = sm.group(1)
        if subreddit:
            return f'https://www.reddit.com/r/{subreddit}/comments/{post_id}/', f'curlx-id:{r.status_code}'

    return None, f'curlx-no-target:{r.status_code}/{len(body)}:{r.url}'


def main():
    if not STATUS.exists():
        print(json.dumps({'ok': True, 'results': [], 'reason': 'no-status'})); return
    try:
        ids = (json.loads(STATUS.read_text(encoding='utf-8')).get('itemIds') or [])[:10]
    except Exception:
        ids = []
    results = []
    for item_id in ids:
        item = wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
        if not item:
            results.append({'id': item_id, 'status': 'missing'}); continue
        src = str(item.get('sourceUrl') or '')
        if not is_reddit_short(src):
            results.append({'id': item_id, 'status': 'skip'}); continue
        canonical, mode = resolve_via_curlx(src)
        if not canonical:
            results.append({'id': item_id, 'status': 'unresolved', 'detail': mode}); continue
        item['sharedUrl'] = item.get('sharedUrl') or src
        item['sourceUrl'] = canonical
        item['canonicalUrl'] = canonical
        item['error'] = None
        wrangler_put(f'{ITEM_PREFIX}{item_id}.json', item)
        queue = wrangler_get(f'{QUEUE_PREFIX}{item_id}.json') or {'id': item_id, 'createdAt': item.get('createdAt')}
        queue['sourceUrl'] = canonical
        queue['sharedUrl'] = src
        wrangler_put(f'{QUEUE_PREFIX}{item_id}.json', queue)
        results.append({'id': item_id, 'status': 'resolved', 'mode': mode, 'canonicalUrl': canonical})
    print(json.dumps({'ok': True, 'results': results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
