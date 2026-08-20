#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
ITEM_PREFIX = 'audio-library/items/'
QUEUE_PREFIX = 'audio-library/queue/'
STATUS_FILES = [
    ROOT / 'ops/audio-library/chat-intake-status.json',
    ROOT / 'ops/audio-library/chatgpt-inbox-status.json',
]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/116.0',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.5',
}


def wrangler_get(key):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        path=Path(tmp.name)
    try:
        run=subprocess.run(['npx','-y','wrangler@4.123.0','r2','object','get',f'{BUCKET}/{key}',f'--file={path}','--remote'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if run.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    finally:
        path.unlink(missing_ok=True)


def wrangler_put(key,value):
    with tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf-8') as tmp:
        json.dump(value,tmp,ensure_ascii=False,separators=(',',':'))
        path=Path(tmp.name)
    try:
        subprocess.check_call(['npx','-y','wrangler@4.123.0','r2','object','put',f'{BUCKET}/{key}',f'--file={path}','--content-type=application/json; charset=utf-8','--remote'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    finally:
        path.unlink(missing_ok=True)


def collect_ids():
    out=[]
    def add(v):
        v=str(v or '')
        if v and v not in out: out.append(v)
    for p in STATUS_FILES:
        if not p.exists(): continue
        try: data=json.loads(p.read_text(encoding='utf-8'))
        except Exception: continue
        for i in data.get('itemIds') or []: add(i)
        for section in ('resolver','fxheaders','metadata','fallback','extractor'):
            obj=data.get(section) or {}
            for row in obj.get('results') or []:
                if isinstance(row,dict): add(row.get('id'))
    return out[:20]


def is_short(url):
    p=urlparse(url)
    return (p.hostname or '').lower().endswith('reddit.com') and '/s/' in p.path


def is_canonical(url):
    p=urlparse(url)
    return (p.hostname or '').lower().endswith('reddit.com') and '/comments/' in p.path


def canonical_from_location(location,base):
    if not location: return None
    try: u=urljoin(base,location)
    except Exception: return None
    p=urlparse(u)
    if not (p.hostname or '').lower().endswith('reddit.com'): return None
    if '/comments/' not in p.path: return None
    return f'https://www.reddit.com{p.path}'.rstrip('/') + '/'


def main():
    results=[]
    for item_id in collect_ids():
        item=wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
        if not item: continue
        src=str(item.get('sourceUrl') or '')
        shared=str(item.get('sharedUrl') or '')
        if is_canonical(src):
            results.append({'id':item_id,'status':'canonical','canonicalUrl':src})
            continue
        target=src if is_short(src) else (shared if is_short(shared) else '')
        if not target:
            results.append({'id':item_id,'status':'skip'})
            continue
        try:
            r=requests.get(target,headers=HEADERS,timeout=40,allow_redirects=False)
            location=r.headers.get('location') or r.headers.get('Location')
            canonical=canonical_from_location(location,target)
            if not canonical:
                results.append({'id':item_id,'status':'unresolved','httpStatus':r.status_code,'hasLocation':bool(location),'bytes':len(r.content)})
                continue
            item['sharedUrl']=item.get('sharedUrl') or target
            item['sourceUrl']=canonical
            item['canonicalUrl']=canonical
            item['error']=None
            wrangler_put(f'{ITEM_PREFIX}{item_id}.json',item)
            queue=wrangler_get(f'{QUEUE_PREFIX}{item_id}.json') or {'id':item_id,'createdAt':item.get('createdAt')}
            queue['sharedUrl']=item['sharedUrl']
            queue['sourceUrl']=canonical
            wrangler_put(f'{QUEUE_PREFIX}{item_id}.json',queue)
            results.append({'id':item_id,'status':'resolved','httpStatus':r.status_code,'mode':'fxreddit-header-fingerprint','canonicalResolved':True,'canonicalUrl':canonical})
        except Exception as e:
            results.append({'id':item_id,'status':'error','error':type(e).__name__})
    print(json.dumps({'ok':True,'results':results},ensure_ascii=False))


if __name__=='__main__':
    main()
