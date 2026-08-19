#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    data = json.loads(src.read_text(encoding='utf-8'))
    conversation = (data.get('raw') or {}).get('conversation') or {}
    posts = []
    seen = set()
    for node in walk(conversation):
        post_id = str(node.get('id') or '')
        text = node.get('text') or node.get('full_text')
        author = node.get('author')
        if not post_id.isdigit() or not isinstance(text, str) or not isinstance(author, dict):
            continue
        handle = author.get('screen_name') or author.get('username') or author.get('name') or ''
        key = post_id
        if key in seen:
            continue
        seen.add(key)
        posts.append({
            'id': post_id,
            'author': handle,
            'text': text.strip(),
            'replying_to': node.get('replying_to'),
            'url': node.get('url'),
            'likes': node.get('likes'),
            'created_at': node.get('created_at'),
        })
    out = {
        'tweet_id': data.get('tweet_id'),
        'post_count': len(posts),
        'posts': posts,
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'tweet_id': out['tweet_id'], 'post_count': len(posts)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
