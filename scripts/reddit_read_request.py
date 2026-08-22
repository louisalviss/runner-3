#!/usr/bin/env python3
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / 'ops/audio-library/reddit-read-request.json'
RESULT = ROOT / 'ops/audio-library/reddit-read-result.json'
BRIDGE_STATUS = ROOT / 'ops/audio-library/chatgpt-bridge-status.json'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def write_result(payload):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': payload.get('status'), 'canonicalUrl': payload.get('canonicalUrl'), 'title': payload.get('title'), 'chars': len(payload.get('rawText') or ''), 'updatedAt': payload.get('updatedAt')}, ensure_ascii=False))


def is_canonical(url):
    return bool(re.search(r'/comments/[a-z0-9]+', str(url or ''), re.I))


def reddit_canonical(value):
    text = str(value or '')
    m = re.search(r'https?://(?:www\.)?reddit\.com(/r/[^\s"\'<>]+/comments/[a-z0-9]+(?:/[^\s"\'<>?]*)?)', text, re.I)
    if not m:
        m = re.search(r'https?://(?:www\.)?reddit\.com(/comments/[a-z0-9]+(?:/[^\s"\'<>?]*)?)', text, re.I)
    if not m:
        return None
    return ('https://www.reddit.com' + m.group(1)).split('?')[0].rstrip('/') + '/'


def resolve_rxddit(source):
    diagnostics = []
    try:
        u = urlparse(source)
        target = urlunparse(u._replace(scheme='https', netloc='rxddit.com'))
        r = requests.get(target, headers={'User-Agent': UA, 'Accept': 'text/html,*/*'}, timeout=40, allow_redirects=False)
        location = r.headers.get('location', '')
        diagnostics.append(f'rxddit:{r.status_code}:{"location" if location else "no-location"}:{len(r.text or "")}')
        for candidate in (location, r.url, r.text):
            c = reddit_canonical(candidate)
            if c:
                return c, diagnostics
        if location:
            lu = urlparse(location)
            if lu.hostname in {'rxddit.com', 'www.rxddit.com'} and '/comments/' in lu.path:
                return urlunparse(lu._replace(scheme='https', netloc='www.reddit.com', query='', fragment='')).rstrip('/') + '/', diagnostics
    except Exception as e:
        diagnostics.append(f'rxddit-error:{type(e).__name__}')
    return None, diagnostics


def bridge_url():
    data = json.loads(BRIDGE_STATUS.read_text(encoding='utf-8'))
    return str(data['url']).rstrip('/')


def queue_token():
    token = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not token:
        raise RuntimeError('CLOUDFLARE_API_TOKEN missing')
    return hashlib.sha256(b'runner3-chatgpt-queue-v2\0' + token.encode()).hexdigest()


def fetch_bridge(url):
    try:
        r = requests.post(
            bridge_url() + '/source/reddit',
            params={'token': queue_token()},
            json={'url': url},
            headers={'User-Agent': UA, 'Accept': 'application/json'},
            timeout=90,
        )
        try:
            data = r.json()
        except Exception:
            data = {'ok': False, 'diagnostics': [f'bridge-non-json:{r.status_code}:{len(r.content)}']}
        return r.status_code, data
    except Exception as e:
        return 0, {'ok': False, 'diagnostics': [f'bridge-error:{type(e).__name__}']}


def clean(value):
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+', ' ', str(value or '').replace('\r', ''))).strip()


def reddit_json_to_raw(data):
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError('reddit-json-shape')
    post = (((data[0] or {}).get('data') or {}).get('children') or [{}])[0].get('data') or {}
    title = clean(post.get('title') or 'Reddit')
    selftext = clean(post.get('selftext') or '')
    comments = []
    def walk(children, depth=0):
        if not isinstance(children, list) or depth > 3 or len(comments) >= 150:
            return
        for child in children:
            if len(comments) >= 150 or child.get('kind') != 't1':
                continue
            row = child.get('data') or {}
            body = clean(row.get('body') or '')
            if len(body) >= 20:
                score = row.get('score')
                comments.append(f'[Comment score {score}] {body}' if isinstance(score, int) else f'[Comment] {body}')
            replies = row.get('replies')
            if isinstance(replies, dict):
                walk(((replies.get('data') or {}).get('children') or []), depth + 1)
    walk(((data[1] or {}).get('data') or {}).get('children') or [])
    parts = ([f'[Post]\n{selftext}'] if selftext else []) + comments
    return title, clean('\n\n'.join(parts))


def fetch_direct(canonical):
    path = urlparse(canonical).path.rstrip('/')
    mid = re.search(r'/comments/([a-z0-9]+)', path, re.I)
    endpoints = [
        f'https://www.reddit.com{path}.json?raw_json=1&limit=100&sort=top',
        f'https://old.reddit.com{path}.json?raw_json=1&limit=100&sort=top',
    ]
    if mid:
        endpoints.append(f'https://www.reddit.com/comments/{mid.group(1)}.json?raw_json=1&limit=100&sort=top')
    diagnostics = []
    for endpoint in endpoints:
        try:
            r = requests.get(endpoint, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'}, timeout=50, allow_redirects=True)
            diagnostics.append(f'direct:{urlparse(endpoint).hostname}:{r.status_code}:{len(r.content)}')
            if r.status_code != 200 or len(r.content) < 200:
                continue
            data = r.json()
            title, raw = reddit_json_to_raw(data)
            if raw:
                return {'ok': True, 'title': title, 'rawText': raw, 'diagnostics': diagnostics}
        except Exception as e:
            diagnostics.append(f'direct-error:{type(e).__name__}')
    return {'ok': False, 'diagnostics': diagnostics}


def main():
    if not REQUEST.exists():
        write_result({'status': 'error', 'error': 'request-missing', 'updatedAt': now()})
        return 1
    req = json.loads(REQUEST.read_text(encoding='utf-8'))
    source = str(req.get('url') or '').strip()
    if 'reddit.com/' not in source.lower():
        write_result({'status': 'error', 'error': 'invalid-reddit-url', 'updatedAt': now()})
        return 1

    diagnostics = []
    canonical = source if is_canonical(source) else None
    if not canonical:
        canonical, d = resolve_rxddit(source)
        diagnostics.extend(d)
    target = canonical or source

    status_code, data = fetch_bridge(target)
    diagnostics.append(f'bridge-http:{status_code}')
    diagnostics.extend([str(x)[:200] for x in (data.get('diagnostics') or [])])
    resolved = str(data.get('canonicalUrl') or canonical or '')
    if resolved:
        canonical = resolved

    if data.get('ok') and str(data.get('rawText') or '').strip():
        write_result({
            'status': 'ok',
            'inputUrl': source,
            'canonicalUrl': canonical or target,
            'title': str(data.get('title') or 'Reddit'),
            'rawText': str(data.get('rawText') or ''),
            'transport': 'cloudflare-worker-egress',
            'diagnostics': diagnostics,
            'updatedAt': now(),
        })
        return 0

    if canonical:
        direct = fetch_direct(canonical)
        diagnostics.extend(direct.get('diagnostics') or [])
        if direct.get('ok'):
            write_result({
                'status': 'ok',
                'inputUrl': source,
                'canonicalUrl': canonical,
                'title': direct.get('title') or 'Reddit',
                'rawText': direct.get('rawText') or '',
                'transport': 'github-runner-reddit-json',
                'diagnostics': diagnostics,
                'updatedAt': now(),
            })
            return 0

    write_result({
        'status': 'failed',
        'inputUrl': source,
        'canonicalUrl': canonical,
        'title': str(data.get('title') or 'Reddit'),
        'rawText': '',
        'transport': None,
        'diagnostics': diagnostics,
        'updatedAt': now(),
    })
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
