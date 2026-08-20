#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests

import audio_library_extract_for_chatgpt as core

ROOT = Path(__file__).resolve().parents[1]
BUCKET = 'runner3-wp-media'
ITEM_PREFIX = 'audio-library/items/'
STATUS_FILE = ROOT / 'ops/audio-library/status.json'
LEGACY_STATUS_FILES = [
    ROOT / 'ops/audio-library/chat-intake-status.json',
    ROOT / 'ops/audio-library/chatgpt-inbox-status.json',
]


def wrangler_get(key: str):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        path = Path(tmp.name)
    try:
        run = subprocess.run(
            ['npx','-y','wrangler@4.123.0','r2','object','get',f'{BUCKET}/{key}',f'--file={path}','--remote'],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if run.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    finally:
        path.unlink(missing_ok=True)


def runner_token():
    raw = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not raw:
        raise RuntimeError('CLOUDFLARE_API_TOKEN missing')
    return hashlib.sha256(raw.encode()).hexdigest()


def worker_url():
    data = json.loads(STATUS_FILE.read_text(encoding='utf-8'))
    return str(data['url']).rstrip('/')


def resolve_reddit_share(item: dict):
    src = str(item.get('sourceUrl') or '')
    if 'reddit.com' not in src.lower() or '/s/' not in src:
        return item
    try:
        import audio_library_resolve_reddit_via_rxddit as rx
        import audio_library_resolve_reddit_via_curlx_next as base
        canonical, mode = rx.try_rxddit(src)
        if not canonical:
            for fn in (base.try_reddit_lynx, base.try_microlink, base.try_domainee, base.try_curlx, base.try_reddit_headers):
                canonical, mode = fn(src)
                if canonical:
                    break
        if canonical:
            try:
                base.update(str(item.get('id') or ''), src, canonical)
            except Exception:
                pass
            item = dict(item)
            item['sharedUrl'] = src
            item['sourceUrl'] = canonical
            item['canonicalUrl'] = canonical
            item['resolveMode'] = mode
    except Exception:
        pass
    return item


def claim_pending_from_worker():
    """Claim the real R2 queue through the runner API.

    UI-added links are created directly in R2 and therefore may never appear in
    chat-intake status files. The runner queue is the authoritative source.
    """
    items = []
    headers = {'X-Runner-Token': runner_token(), 'User-Agent': core.UA}
    base_url = worker_url()
    for _ in range(core.MAX_ITEMS):
        r = requests.get(base_url + '/api/runner/next', headers=headers, timeout=40)
        if r.status_code == 204:
            break
        r.raise_for_status()
        data = r.json() if r.content else {}
        item = data.get('item') if isinstance(data, dict) else None
        if not isinstance(item, dict) or not item.get('id'):
            break
        items.append(resolve_reddit_share(item))
    return items


def collect_legacy_ids():
    out = []
    def add(value):
        value = str(value or '')
        if value and value not in out:
            out.append(value)
    for status_path in LEGACY_STATUS_FILES:
        if not status_path.exists():
            continue
        try:
            data = json.loads(status_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        for item_id in data.get('itemIds') or []:
            add(item_id)
        for section in ('resolver','metadata','fallback','extractor'):
            obj = data.get(section) or {}
            for row in obj.get('results') or []:
                if isinstance(row, dict):
                    add(row.get('id'))
    return out[:20]


def legacy_pending_items():
    items = []
    for item_id in collect_legacy_ids():
        item = wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
        if not item or item.get('audioUrl'):
            continue
        if str(item.get('status') or '') not in {'pending','waiting_chatgpt','processing'}:
            continue
        items.append(resolve_reddit_share(item))
        if len(items) >= core.MAX_ITEMS:
            break
    return items


def pending_items_r2():
    try:
        return claim_pending_from_worker()
    except Exception as e:
        # Keep the old status-file path only as a resilience fallback.
        items = legacy_pending_items()
        if items:
            return items
        raise RuntimeError(f'R2 queue claim failed: {type(e).__name__}: {str(e)[:220]}')


core.pending_items = pending_items_r2
core.main()
