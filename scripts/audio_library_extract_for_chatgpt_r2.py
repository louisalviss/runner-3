#!/usr/bin/env python3
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

# Reddit RSS is the reliable fallback from GitHub-hosted runners. Ensure the
# XML parser exists even if the surrounding workflow forgot to install it.
try:
    import lxml  # noqa: F401
except Exception:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'lxml'])

import audio_library_extract_for_chatgpt as core

ROOT = Path(__file__).resolve().parents[1]
BUCKET = 'runner3-wp-media'
ITEM_PREFIX = 'audio-library/items/'
STATUS_FILE = ROOT / 'ops/audio-library/status.json'
WRANGLER_CONFIG = ROOT / 'apps/audio-library/wrangler.jsonc'
LEGACY_STATUS_FILES = [
    ROOT / 'ops/audio-library/chat-intake-status.json',
    ROOT / 'ops/audio-library/chatgpt-inbox-status.json',
]
ACTIVE_STATUSES = {'pending', 'waiting_chatgpt', 'processing'}


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


def worker_url():
    data = json.loads(STATUS_FILE.read_text(encoding='utf-8'))
    return str(data['url']).rstrip('/')


def library_access_hash():
    text = WRANGLER_CONFIG.read_text(encoding='utf-8')
    m = re.search(r'"LIBRARY_ACCESS_SHA256"\s*:\s*"([0-9a-f]{64})"', text, re.I)
    if not m:
        raise RuntimeError('LIBRARY_ACCESS_SHA256 not found')
    return m.group(1).lower()


def library_session_token():
    raw = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not raw:
        raise RuntimeError('CLOUDFLARE_API_TOKEN missing')
    runner_shared = hashlib.sha256(raw.encode()).hexdigest()
    material = f'audio-library-session-v3\0{runner_shared}\0{library_access_hash()}'
    return hashlib.sha256(material.encode()).hexdigest()


def already_staged(item_id: str) -> bool:
    return (core.INBOX_DIR / f'{item_id}.json').exists() or (core.OUTBOX_DIR / f'{item_id}.json').exists()


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


def active_items_from_worker():
    """Read active Library items without claiming or mutating the queue.

    This is intentionally read-only. Extraction failures therefore remain
    eligible for the next 5-minute run instead of being stranded in
    `processing`. Existing inbox/outbox files are filtered before MAX_ITEMS so
    they cannot starve newer work.
    """
    headers = {
        'Authorization': 'Bearer ' + library_session_token(),
        'User-Agent': core.UA,
        'Accept': 'application/json',
    }
    r = requests.get(worker_url() + '/api/items', headers=headers, timeout=40)
    r.raise_for_status()
    data = r.json() if r.content else {}
    rows = data.get('items') if isinstance(data, dict) else []
    candidates = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get('id') or '')
        if not item_id or item.get('audioUrl'):
            continue
        if str(item.get('status') or '') not in ACTIVE_STATUSES:
            continue
        if already_staged(item_id):
            continue
        candidates.append(item)

    # Oldest first prevents a repeatedly failing new item from starving older
    # queued work, while MAX_ITEMS still bounds each run.
    candidates.sort(key=lambda x: str(x.get('createdAt') or ''))
    return [resolve_reddit_share(x) for x in candidates[:core.MAX_ITEMS]]


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
        if not item or item.get('audioUrl') or already_staged(item_id):
            continue
        if str(item.get('status') or '') not in ACTIVE_STATUSES:
            continue
        items.append(resolve_reddit_share(item))
        if len(items) >= core.MAX_ITEMS:
            break
    return items


def pending_items_r2():
    try:
        return active_items_from_worker()
    except Exception as e:
        items = legacy_pending_items()
        if items:
            return items
        raise RuntimeError(f'Library item discovery failed: {type(e).__name__}: {str(e)[:220]}')


core.pending_items = pending_items_r2
core.main()
