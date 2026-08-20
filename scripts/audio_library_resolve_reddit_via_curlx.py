#!/usr/bin/env python3
import html
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
STATUS = ROOT / 'ops/audio-library/chat-intake-status.json'
ITEM_PREFIX = 'audio-library/items/'
QUEUE_PREFIX = 'audio-library/queue/'
UA = 'Runner3AudioResolver/2.2 (+https://github.com/louisalviss/runner-3)'
CURLX_API = 'https://www.curl-x.com/api/extract'
DOMAINEE_API = 'https://api.domainee.dev/v1/tools/redirect-checker'
REDIRECTCHECK_API = 'https://www.redirectcheck.org/api/check'


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
    value = html.unescape(str(value)).replace('\\u002F','/').replace('\\/','/')
    patterns = [
        r'https?://(?:www\.)?reddit\.com(?P<path>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
        r'https?://(?:www\.)?reddit\.com(?P<path>/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
        r'https?://(?:www\.)?curl-x\.com(?P<path>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
        r'(?P<path>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
        r'(?P<path>/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
    ]
    for pat in patterns:
        m = re.search(pat, value, re.I)
        if m:
            return ('https://www.reddit.com' + m.group('path').rstrip('\\')).split('?')[0]
    return None


def subreddit_from_share(url: str):
    m = re.search(r'/r/([^/]+)/s/', urlparse(url).path, re.I)
    return m.group(1) if m else None


def post_id_from_text(value: str):
    text = html.unescape(str(value or '')).replace('\\u002F','/').replace('\\/','/')
    for pat in [
        r'/comments/([a-z0-9]+)',
        r'"postId"\s*:\s*"([a-z0-9]+)"',
        r'"redditPostId"\s*:\s*"([a-z0-9]+)"',
        r'"id"\s*:\s*"t3_([a-z0-9]+)"',
        r'"name"\s*:\s*"t3_([a-z0-9]+)"',
    ]:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


def canonical_from_payload(payload, original_url: str):
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload or '')
    found = normalize_reddit_candidate(text)
    if found:
        return found
    post_id = post_id_from_text(text)
    subreddit = subreddit_from_share(original_url)
    if post_id and subreddit:
        return f'https://www.reddit.com/r/{subreddit}/comments/{post_id}/'
    return None


def resolve_via_reddit_manual(url: str):
    diagnostics=[]
    uas=[
        UA,
        'PullMD/1.0 (URL-to-Markdown service)',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    ]
    for ua in uas:
        try:
            r=requests.get(
                url,
                headers={'User-Agent':ua,'Accept':'text/html,application/xhtml+xml,*/*','Accept-Language':'en-US,en;q=0.9'},
                timeout=35,
                allow_redirects=False,
            )
        except Exception as e:
            diagnostics.append(type(e).__name__)
            continue
        location=r.headers.get('location','')
        if location:
            absolute=urljoin(url,location)
            found=normalize_reddit_candidate(absolute)
            if found:
                return found, f'reddit-manual:{r.status_code}:location'
        # Some edge responses contain the destination in a tiny HTML/JSON wrapper.
        found=normalize_reddit_candidate(r.text or '')
        if found:
            return found, f'reddit-manual:{r.status_code}:body'
        diagnostics.append(f'{r.status_code}:{"loc" if location else "noloc"}:{len(r.text or "")}')
    return None, 'reddit-manual-no-target:' + ','.join(diagnostics)


def resolve_via_curlx_api(url: str):
    try:
        r = requests.post(
            CURLX_API,
            json={'url': url},
            headers={'User-Agent': UA,'Accept':'application/json','Content-Type':'application/json','Accept-Language':'en-US,en;q=0.9'},
            timeout=75,
            allow_redirects=True,
        )
    except Exception as e:
        return None, f'curlx-api-request-{type(e).__name__}'
    try:
        data = r.json()
    except Exception:
        data = None
    for candidate in [r.url, r.headers.get('location','')]:
        found = normalize_reddit_candidate(candidate)
        if found:
            return found, f'curlx-api-url:{r.status_code}'
    if data is not None:
        found = canonical_from_payload(data, url)
        if found:
            code = data.get('code') if isinstance(data, dict) else None
            return found, f'curlx-api-json:{r.status_code}:{code or "ok"}'
    found = normalize_reddit_candidate(r.text or '')
    if found:
        return found, f'curlx-api-text:{r.status_code}'
    post_id = post_id_from_text(r.text or '')
    subreddit = subreddit_from_share(url)
    if post_id and subreddit:
        return f'https://www.reddit.com/r/{subreddit}/comments/{post_id}/', f'curlx-api-id:{r.status_code}'
    code = data.get('code') if isinstance(data, dict) else None
    return None, f'curlx-api-no-target:{r.status_code}:{code or "no-code"}:{len(r.text or "")}'


def resolve_via_domainee(url: str):
    try:
        r = requests.get(DOMAINEE_API, params={'url': url}, headers={'User-Agent': UA, 'Accept': 'application/json'}, timeout=60)
    except Exception as e:
        return None, f'domainee-request-{type(e).__name__}'
    try:
        data = r.json()
    except Exception:
        data = None
    for source in [data, r.text, r.headers.get('location','')]:
        found = canonical_from_payload(source, url) if source is not None else None
        if found:
            return found, f'domainee:{r.status_code}'
    return None, f'domainee-no-target:{r.status_code}:{len(r.text or "")}'


def resolve_via_redirectcheck(url: str):
    attempts = [('post', {'url':url,'method':'GET','followMetaRefresh':True}),('get',None)]
    errors=[]
    for mode, body in attempts:
        try:
            if mode == 'post':
                r=requests.post(REDIRECTCHECK_API,json=body,headers={'User-Agent':UA,'Accept':'application/json','Content-Type':'application/json'},timeout=60)
            else:
                r=requests.get(REDIRECTCHECK_API,params={'url':url,'ua':'Googlebot'},headers={'User-Agent':UA,'Accept':'application/json'},timeout=60)
        except Exception as e:
            errors.append(f'{mode}:{type(e).__name__}')
            continue
        try:
            data=r.json()
        except Exception:
            data=None
        for source in [data,r.text,r.headers.get('location','')]:
            found=canonical_from_payload(source,url) if source is not None else None
            if found:
                return found, f'redirectcheck-{mode}:{r.status_code}'
        errors.append(f'{mode}:{r.status_code}/{len(r.text or "")}')
    return None, 'redirectcheck-no-target:' + ','.join(errors)


def resolve_via_curlx_legacy(url: str):
    p = urlparse(url)
    target = 'https://www.curl-x.com' + p.path
    if p.query:
        target += '?' + p.query
    try:
        r = requests.get(target, headers={'User-Agent':'curl/8.10.1','Accept':'*/*'}, timeout=60, allow_redirects=True)
    except Exception as e:
        return None, f'curlx-legacy-request-{type(e).__name__}'
    for candidate in [r.url, r.headers.get('location',''), r.text or '']:
        found = normalize_reddit_candidate(candidate)
        if found:
            return found, f'curlx-legacy:{r.status_code}'
    post_id = post_id_from_text(r.text or '')
    subreddit = subreddit_from_share(url)
    if post_id and subreddit:
        return f'https://www.reddit.com/r/{subreddit}/comments/{post_id}/', f'curlx-legacy-id:{r.status_code}'
    return None, f'curlx-legacy-no-target:{r.status_code}:{len(r.text or "")}'


def resolve_via_curlx(url: str):
    diagnostics=[]
    for fn in [resolve_via_reddit_manual, resolve_via_curlx_api, resolve_via_domainee, resolve_via_redirectcheck, resolve_via_curlx_legacy]:
        canonical, mode = fn(url)
        if canonical:
            return canonical, mode
        diagnostics.append(mode)
    return None, ';'.join(diagnostics)


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
            results.append({'id': item_id, 'status': 'unresolved', 'detail': mode[:1000]}); continue
        item['sharedUrl'] = item.get('sharedUrl') or src
        item['sourceUrl'] = canonical
        item['canonicalUrl'] = canonical
        item['error'] = None
        wrangler_put(f'{ITEM_PREFIX}{item_id}.json', item)
        queue = wrangler_get(f'{QUEUE_PREFIX}{item_id}.json') or {'id':item_id,'createdAt':item.get('createdAt')}
        queue['sourceUrl'] = canonical
        queue['sharedUrl'] = src
        wrangler_put(f'{QUEUE_PREFIX}{item_id}.json', queue)
        results.append({'id': item_id, 'status': 'resolved', 'mode': mode, 'canonicalResolved': True})
    print(json.dumps({'ok': True, 'results': results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
