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
UA = 'Runner3AudioResolver/3.1'
LYNX_UA = 'FreeBSD/11.0 Lynx/56'


def wrangler_get(key):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        path = Path(tmp.name)
    try:
        run = subprocess.run(['npx','-y','wrangler@4.123.0','r2','object','get',f'{BUCKET}/{key}',f'--file={path}','--remote'], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if run.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    finally:
        path.unlink(missing_ok=True)


def wrangler_put(key, value):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        json.dump(value, tmp, ensure_ascii=False, separators=(',', ':'))
        path = Path(tmp.name)
    try:
        run = subprocess.run(['npx','-y','wrangler@4.123.0','r2','object','put',f'{BUCKET}/{key}',f'--file={path}','--content-type=application/json; charset=utf-8','--remote'], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if run.returncode != 0:
            raise RuntimeError('wrangler put failed')
    finally:
        path.unlink(missing_ok=True)


def is_short(url):
    p = urlparse(url)
    return (p.hostname or '').lower().endswith('reddit.com') and '/s/' in p.path


def all_strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield str(k)
            yield from all_strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from all_strings(x)


def canonical_from(v, original):
    subreddit = None
    m = re.search(r'/r/([^/]+)/s/', urlparse(original).path, re.I)
    if m:
        subreddit = m.group(1)
    for s in all_strings(v):
        s = html.unescape(s).replace('\\u002F','/').replace('\\/','/')
        pats = [
            r'https?://(?:www\.|old\.)?reddit\.com(?P<p>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
            r'https?://(?:www\.|old\.)?reddit\.com(?P<p>/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
            r'(?P<p>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
            r'(?P<p>/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',
        ]
        for pat in pats:
            mm = re.search(pat, s, re.I)
            if mm:
                return ('https://www.reddit.com' + mm.group('p')).split('?')[0].rstrip('/') + '/'
        mm = re.search(r'https?://redd\.it/([a-z0-9]+)', s, re.I)
        if mm:
            return f'https://www.reddit.com/comments/{mm.group(1)}/'
        for pat in [r'"postId"\s*:\s*"([a-z0-9]+)"', r'"redditPostId"\s*:\s*"([a-z0-9]+)"', r'\bt3_([a-z0-9]+)\b']:
            mm = re.search(pat, s, re.I)
            if mm and subreddit:
                return f'https://www.reddit.com/r/{subreddit}/comments/{mm.group(1)}/'
    return None


def try_reddit_lynx(url):
    diagnostics=[]
    for follow in (False, True):
        try:
            r = requests.get(
                url,
                headers={'User-Agent':LYNX_UA,'Accept':'text/html,*/*','Accept-Language':'en-US,en;q=0.9'},
                timeout=45,
                allow_redirects=follow,
            )
        except Exception as e:
            diagnostics.append(f'{"follow" if follow else "manual"}:{type(e).__name__}')
            continue
        mode = 'follow' if follow else 'manual'
        loc = r.headers.get('location','')
        found = canonical_from([r.url, loc, r.text], url)
        if found:
            return found, f'lynx:{r.status_code}:{mode}:canonical'
        text = html.unescape(r.text or '').replace('\\u002F','/').replace('\\/','/')
        # s9e/TextFormatter's Reddit /s/ rule extracts this path directly.
        m = re.search(r'(?<![A-Za-z0-9_])([A-Za-z0-9_]+/comments/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+/[A-Za-z0-9_]+)?)', text)
        if m:
            path = m.group(1).strip('/')
            return f'https://www.reddit.com/r/{path}/', f'lynx:{r.status_code}:{mode}:s9e-path'
        diagnostics.append(f'{mode}:{r.status_code}:{len(r.text or "")}:{"loc" if loc else "noloc"}')
    return None, 'lynx:' + ','.join(diagnostics)


def try_microlink(url):
    try:
        r = requests.get('https://api.microlink.io', params={'url': url}, headers={'User-Agent':UA,'Accept':'application/json'}, timeout=75)
        data = r.json()
    except Exception as e:
        return None, f'microlink:{type(e).__name__}'
    found = canonical_from(data, url)
    status = data.get('status') if isinstance(data, dict) else None
    return found, f'microlink:{r.status_code}:{status or "no-status"}'


def try_domainee(url):
    try:
        r = requests.get('https://api.domainee.dev/v1/tools/redirect-checker', params={'url':url}, headers={'User-Agent':UA,'Accept':'application/json'}, timeout=60)
        try: data = r.json()
        except Exception: data = r.text
    except Exception as e:
        return None, f'domainee:{type(e).__name__}'
    return canonical_from(data, url), f'domainee:{r.status_code}'


def try_curlx(url):
    try:
        r = requests.post('https://www.curl-x.com/api/extract', json={'url':url}, headers={'User-Agent':'curl/8.5.0','Accept':'application/json','Content-Type':'application/json'}, timeout=75)
        try: data = r.json()
        except Exception: data = r.text
    except Exception as e:
        return None, f'curlx:{type(e).__name__}'
    code = data.get('code') if isinstance(data, dict) else None
    return canonical_from(data, url), f'curlx:{r.status_code}:{code or "ok"}'


def try_reddit_headers(url):
    out=[]
    for ua in ['Mozilla/5.0','Googlebot/2.1','Slackbot-LinkExpanding 1.0','Discordbot/2.0']:
        try:
            r = requests.get(url, headers={'User-Agent':ua,'Accept':'text/html,*/*'}, timeout=35, allow_redirects=False)
            loc = r.headers.get('location','')
            found = canonical_from([loc, r.text], url)
            if found: return found, f'reddit:{r.status_code}:{ua.split("/")[0]}'
            out.append(str(r.status_code))
        except Exception:
            out.append('err')
    return None, 'reddit:' + ','.join(out)


def update(item_id, src, canonical):
    item = wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
    queue = wrangler_get(f'{QUEUE_PREFIX}{item_id}.json')
    if item:
        item['sharedUrl'] = item.get('sharedUrl') or src
        item['sourceUrl'] = canonical
        item['canonicalUrl'] = canonical
        item['error'] = None
        wrangler_put(f'{ITEM_PREFIX}{item_id}.json', item)
    if queue:
        queue['sharedUrl'] = queue.get('sharedUrl') or src
        queue['sourceUrl'] = canonical
        wrangler_put(f'{QUEUE_PREFIX}{item_id}.json', queue)
    return bool(item or queue)


def main():
    if not STATUS.exists():
        print(json.dumps({'ok':True,'results':[],'reason':'no-status'})); return
    try:
        ids = (json.loads(STATUS.read_text(encoding='utf-8')).get('itemIds') or [])[:10]
    except Exception:
        ids=[]
    results=[]
    for item_id in ids:
        item = wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
        if not item:
            results.append({'id':item_id,'status':'missing'}); continue
        src = str(item.get('sourceUrl') or '')
        if not is_short(src):
            results.append({'id':item_id,'status':'skip'}); continue
        diagnostics=[]
        canonical=None
        mode=None
        for fn in (try_reddit_lynx, try_microlink, try_domainee, try_curlx, try_reddit_headers):
            canonical, mode = fn(src)
            diagnostics.append(mode)
            if canonical: break
        if canonical:
            updated = update(item_id, src, canonical)
            results.append({'id':item_id,'status':'resolved','mode':mode,'r2Updated':updated,'canonicalResolved':True})
        else:
            results.append({'id':item_id,'status':'unresolved','detail':';'.join(diagnostics)[:1000]})
    print(json.dumps({'ok':True,'results':results}, ensure_ascii=False))

if __name__ == '__main__':
    main()
