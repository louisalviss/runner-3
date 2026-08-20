#!/usr/bin/env python3
import json
from urllib.parse import quote

import requests

import audio_library_resolve_reddit_via_curlx_next as base

UA = 'Runner3AudioUnfurl/1.0'


def try_reddit_oembed(url):
    try:
        r = requests.get(
            'https://www.reddit.com/oembed',
            params={'url': url, 'format': 'json', 'omitscript': 'true'},
            headers={'User-Agent': 'FreeBSD/11.0 Lynx/56', 'Accept': 'application/json,text/plain,*/*'},
            timeout=45,
            allow_redirects=True,
        )
        try:
            data = r.json()
        except Exception:
            data = r.text
    except Exception as e:
        return None, f'oembed:{type(e).__name__}'
    found = base.canonical_from(data, url)
    if not found:
        found = base.canonical_from([r.url, r.headers.get('location','')], url)
    return found, f'oembed:{r.status_code}:{len(r.text or "")}'


def try_tinyutils(url):
    try:
        r = requests.get(
            'https://tinyutils.dev/api/url-resolve',
            params={'url': url},
            headers={'User-Agent': UA, 'Accept': 'application/json'},
            timeout=45,
        )
        try:
            data = r.json()
        except Exception:
            data = r.text
    except Exception as e:
        return None, f'tinyutils:{type(e).__name__}'
    return base.canonical_from(data, url), f'tinyutils:{r.status_code}'


def try_redirectcheck(url):
    try:
        r = requests.get(
            'https://www.redirectcheck.org/api/check',
            params={'url': url, 'ua': 'Googlebot'},
            headers={'User-Agent': UA, 'Accept': 'application/json'},
            timeout=60,
        )
        try:
            data = r.json()
        except Exception:
            data = r.text
    except Exception as e:
        return None, f'redirectcheck:{type(e).__name__}'
    return base.canonical_from(data, url), f'redirectcheck:{r.status_code}'


def main():
    if not base.STATUS.exists():
        print(json.dumps({'ok': True, 'results': [], 'reason': 'no-status'})); return
    try:
        ids = (json.loads(base.STATUS.read_text(encoding='utf-8')).get('itemIds') or [])[:10]
    except Exception:
        ids = []
    results=[]
    for item_id in ids:
        item=base.wrangler_get(f'{base.ITEM_PREFIX}{item_id}.json')
        if not item:
            results.append({'id':item_id,'status':'missing'}); continue
        src=str(item.get('sourceUrl') or '')
        if not base.is_short(src):
            results.append({'id':item_id,'status':'skip'}); continue
        diagnostics=[]
        canonical=None
        mode=None
        for fn in (
            base.try_reddit_lynx,
            try_reddit_oembed,
            try_tinyutils,
            base.try_microlink,
            base.try_domainee,
            try_redirectcheck,
            base.try_curlx,
            base.try_reddit_headers,
        ):
            canonical, mode = fn(src)
            diagnostics.append(mode)
            if canonical:
                break
        if canonical:
            updated=base.update(item_id,src,canonical)
            results.append({'id':item_id,'status':'resolved','mode':mode,'r2Updated':updated,'canonicalResolved':True})
        else:
            results.append({'id':item_id,'status':'unresolved','detail':';'.join(diagnostics)[:1400]})
    print(json.dumps({'ok':True,'results':results},ensure_ascii=False))

if __name__ == '__main__':
    main()
