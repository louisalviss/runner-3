#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path

import audio_media_core as media

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
ITEM_PREFIX = 'audio-library/items/'
LEGACY_STATUS_FILES = [
    ROOT / 'ops/audio-library/chat-intake-status.json',
    ROOT / 'ops/audio-library/chatgpt-inbox-status.json',
]
ACTIVE_STATUSES = {'pending', 'waiting_chatgpt', 'processing'}


def load_core():
    path = SCRIPT_DIR / 'audio_library_extract_for_chatgpt.py'
    spec = importlib.util.spec_from_file_location('_runner3_audio_extract_core', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('unable to load audio extractor core')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, 'main', None)):
        raise RuntimeError(f'audio extractor main missing from {path}')
    return module


core = load_core()


def already_staged(item_id: str) -> bool:
    return (core.INBOX_DIR / f'{item_id}.json').exists() or (core.OUTBOX_DIR / f'{item_id}.json').exists()


def active_items_from_core():
    """Read active Audio Library items through scoped Runner3 Core access."""
    candidates = []
    for row in media.list_objects(ITEM_PREFIX, limit=1000):
        key = str(row.get('key') or '')
        if not key.endswith('.json'):
            continue
        try:
            item = media.get_json(key)
        except Exception:
            continue
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

    candidates.sort(key=lambda x: str(x.get('createdAt') or ''))
    return candidates[:core.MAX_ITEMS]


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
        for section in ('resolver', 'metadata', 'fallback', 'extractor'):
            obj = data.get(section) or {}
            for row in obj.get('results') or []:
                if isinstance(row, dict):
                    add(row.get('id'))
    return out[:20]


def legacy_pending_items():
    items = []
    for item_id in collect_legacy_ids():
        try:
            item = media.get_json(f'{ITEM_PREFIX}{item_id}.json')
        except Exception:
            item = None
        if not item or item.get('audioUrl') or already_staged(item_id):
            continue
        if str(item.get('status') or '') not in ACTIVE_STATUSES:
            continue
        items.append(item)
        if len(items) >= core.MAX_ITEMS:
            break
    return items


def pending_items_r2():
    try:
        return active_items_from_core()
    except Exception as error:
        items = legacy_pending_items()
        if items:
            return items
        raise RuntimeError(f'Library item discovery failed: {type(error).__name__}: {str(error)[:220]}')


core.pending_items = pending_items_r2
core.main()
