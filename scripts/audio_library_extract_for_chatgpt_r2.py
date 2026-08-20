#!/usr/bin/env python3
import json
import subprocess
import tempfile
from pathlib import Path

import audio_library_extract_for_chatgpt as core

ROOT = Path(__file__).resolve().parents[1]
BUCKET = 'runner3-wp-media'
ITEM_PREFIX = 'audio-library/items/'
STATUS_FILES = [
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


def collect_ids():
    out=[]
    def add(value):
        value=str(value or '')
        if value and value not in out:
            out.append(value)
    for status_path in STATUS_FILES:
        if not status_path.exists():
            continue
        try:
            data=json.loads(status_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        for item_id in data.get('itemIds') or []:
            add(item_id)
        for section in ('resolver','metadata','fallback','extractor'):
            obj=data.get(section) or {}
            for row in obj.get('results') or []:
                if isinstance(row,dict):
                    add(row.get('id'))
    return out[:20]


def pending_items_r2():
    items=[]
    for item_id in collect_ids():
        item=wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
        if not item:
            continue
        if item.get('audioUrl'):
            continue
        if str(item.get('status') or '') not in {'pending','waiting_chatgpt'}:
            continue
        items.append(item)
        if len(items) >= core.MAX_ITEMS:
            break
    return items


core.pending_items = pending_items_r2
core.main()
