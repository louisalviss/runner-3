#!/usr/bin/env python3
import json
from urllib.parse import urlparse, urlunparse

import requests

import audio_library_resolve_reddit_via_curlx_next as base
import audio_library_resolve_reddit_via_unfurl as unfurl

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/116.0'


def try_rxddit(source_url: str):
    try:
        src = urlparse(source_url)
        rx = src._replace(scheme='https', netloc='rxddit.com')
        target = urlunparse(rx)
        r = requests.get(
            target,
            headers={
                'User-Agent': UA,
                'Accept': 'text/html,application/xhtml+xml,*/*',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            timeout=45,
            allow_redirects=False,
        )
    except Exception as e:
        return None, f'rxddit:{type(e).__name__}'

    location = r.headers.get('location', '')
    candidates = [location, r.url, r.text or '']
    canonical = base.canonical_from(candidates, source_url)

    # FxReddit rewrites Reddit's canonical Location host back to its own host.
    # Convert such redirects back to www.reddit.com before handing them to the extractor.
    if not canonical and location:
        try:
            u = urlparse(location)
            if u.hostname in {'rxddit.com', 'www.rxddit.com'} and '/comments/' in u.path:
                canonical = urlunparse(u._replace(scheme='https', netloc='www.reddit.com', query='', fragment=''))
                canonical = canonical.rstrip('/') + '/'
        except Exception:
            pass

    return canonical, f'rxddit:{r.status_code}:{"location" if location else "no-location"}:{len(r.text or "")}'


def main():
    if not base.STATUS.exists():
        print(json.dumps({'ok': True, 'results': [], 'reason': 'no-status'})); return
    try:
        ids = (json.loads(base.STATUS.read_text(encoding='utf-8')).get('itemIds') or [])[:10]
    except Exception:
        ids = []

    results = []
    for item_id in ids:
        item = base.wrangler_get(f'{base.ITEM_PREFIX}{item_id}.json')
        if not item:
            results.append({'id': item_id, 'status': 'missing'}); continue
        src = str(item.get('sourceUrl') or '')
        if not base.is_short(src):
            results.append({'id': item_id, 'status': 'skip'}); continue

        diagnostics = []
        canonical, mode = try_rxddit(src)
        diagnostics.append(mode)

        if not canonical:
            for fn in (
                base.try_reddit_lynx,
                unfurl.try_reddit_oembed,
                unfurl.try_tinyutils,
                base.try_microlink,
                base.try_domainee,
                unfurl.try_redirectcheck,
                base.try_curlx,
                base.try_reddit_headers,
            ):
                canonical, mode = fn(src)
                diagnostics.append(mode)
                if canonical:
                    break

        if canonical:
            updated = base.update(item_id, src, canonical)
            results.append({
                'id': item_id,
                'status': 'resolved',
                'mode': mode,
                'r2Updated': updated,
                'canonicalResolved': True,
            })
        else:
            results.append({
                'id': item_id,
                'status': 'unresolved',
                'detail': ';'.join(diagnostics)[:1600],
            })

    print(json.dumps({'ok': True, 'results': results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
