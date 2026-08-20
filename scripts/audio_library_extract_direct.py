#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import audio_library_extract_for_chatgpt as extractor


def source_label(url: str) -> str:
    host = (urlparse(url).hostname or '').lower()
    if host == 'youtu.be' or host.endswith('youtube.com'):
        return 'YouTube'
    if host.endswith('reddit.com'):
        return 'Reddit'
    if host == 'x.com' or host.endswith('twitter.com'):
        return 'X'
    return host.removeprefix('www.') or 'Web'


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: audio_library_extract_direct.py <enqueue-result.json>')
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    items = []
    for row in data.get('results') or []:
        item_id = str(row.get('id') or '').strip()
        url = str(row.get('url') or '').strip()
        if not item_id or not url:
            continue
        label = source_label(url)
        items.append({'id': item_id, 'sourceUrl': url, 'sourceLabel': label, 'title': label})
    if not items:
        print(json.dumps({'ok': True, 'results': []}, ensure_ascii=False))
        return
    extractor.pending_items = lambda: items[: extractor.MAX_ITEMS]
    extractor.main()


if __name__ == '__main__':
    main()
