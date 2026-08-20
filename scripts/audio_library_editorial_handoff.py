#!/usr/bin/env python3
import json
import tempfile
from pathlib import Path

from audio_library_extract_for_chatgpt import extract_source, clean_text

ITEM_ID = '9fe80de0-6caa-5143-aaaa-f81b7a366f77'
CANONICAL = 'https://www.reddit.com/r/AskReddit/comments/1vsxt55/what_video_game_did_you_drop_laughably_quick/'


def main():
    with tempfile.TemporaryDirectory(prefix='editorial-handoff-') as td:
        title, raw, source_label, canonical = extract_source(CANONICAL, Path(td))
    raw = clean_text(raw)
    out = {
        'id': ITEM_ID,
        'title': title,
        'sourceLabel': source_label,
        'canonicalUrl': canonical,
        'rawText': raw,
        'editorPolicy': 'RAW_PUBLIC_SOURCE_ONLY_NO_TRANSLATION_NO_SUMMARY_NO_LLM',
    }
    Path('/tmp/audio-editorial-handoff.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'id': ITEM_ID, 'chars': len(raw), 'title': title}, ensure_ascii=False))


if __name__ == '__main__':
    main()
