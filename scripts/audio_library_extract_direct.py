#!/usr/bin/env python3
import json
import subprocess
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
    x_urls = []
    for row in data.get('results') or []:
        item_id = str(row.get('id') or '').strip()
        url = str(row.get('url') or '').strip()
        if not item_id or not url:
            continue
        label = source_label(url)
        items.append({'id': item_id, 'sourceUrl': url, 'sourceLabel': label, 'title': label})
        if label == 'X':
            x_urls.append(url)
    if x_urls:
        helper = Path(__file__).with_name('inspect_x_video_for_chatgpt.py')
        cp = subprocess.run([sys.executable, str(helper), *x_urls], text=True, capture_output=True)
        print(json.dumps({'x_visual_inspect_rc': cp.returncode, 'stdout': cp.stdout[-2000:], 'stderr': cp.stderr[-2000:]}, ensure_ascii=False))
    if not items:
        print(json.dumps({'ok': True, 'results': []}, ensure_ascii=False))
        return
    extractor.pending_items = lambda: items[: extractor.MAX_ITEMS]
    extractor.main()


if __name__ == '__main__':
    main()
