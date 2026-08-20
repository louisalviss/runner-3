#!/usr/bin/env python3
import json, os, re, subprocess, tempfile
from pathlib import Path
from urllib.parse import quote, urlparse
import requests

ROOT=Path(__file__).resolve().parents[1]
BUCKET=os.environ.get('AUDIO_LIBRARY_BUCKET','runner3-wp-media')
STATUS=ROOT/'ops/audio-library/chat-intake-status.json'
ITEM_PREFIX='audio-library/items/'
QUEUE_PREFIX='audio-library/queue/'
UA='Runner3RedditMetadataResolver/1.0'


def wrangler_get(key):
    with tempfile.NamedTemporaryFile(suffix='.json',delete=False) as tmp: p=Path(tmp.name)
    try:
        r=subprocess.run(['npx','-y','wrangler@4.123.0','r2','object','get',f'{BUCKET}/{key}',f'--file={p}','--remote'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if r.returncode!=0 or not p.exists() or p.stat().st_size==0: return None
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return None
    finally: p.unlink(missing_ok=True)


def wrangler_put(key,val):
    with tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf-8') as tmp:
        json.dump(val,tmp,ensure_ascii=False,separators=(',',':')); p=Path(tmp.name)
    try:
        subprocess.check_call(['npx','-y','wrangler@4.123.0','r2','object','put',f'{BUCKET}/{key}',f'--file={p}','--content-type=application/json; charset=utf-8','--remote'],cwd=ROOT)
    finally: p.unlink(missing_ok=True)


def is_short(u):
    p=urlparse(u); return (p.hostname or '').lower().endswith('reddit.com') and '/s/' in p.path


def extract_candidate(text, original):
    s=str(text or '').replace('\\u002F','/').replace('\\/','/')
    m=re.search(r'https?://(?:www\.)?reddit\.com(?P<path>/r/[^\s"<>]+/comments/[a-z0-9]+(?:/[^\s"<>?]*)?)',s,re.I)
    if m: return 'https://www.reddit.com'+m.group('path').split('?')[0]
    m=re.search(r'/comments/([a-z0-9]+)',s,re.I)
    if m:
        sm=re.search(r'/r/([^/]+)/s/',urlparse(original).path,re.I)
        if sm: return f'https://www.reddit.com/r/{sm.group(1)}/comments/{m.group(1)}/'
    for pat in [r'"name"\s*:\s*"t3_([a-z0-9]+)"',r'"id"\s*:\s*"t3_([a-z0-9]+)"',r'"postId"\s*:\s*"([a-z0-9]+)"']:
        m=re.search(pat,s,re.I)
        if m:
            sm=re.search(r'/r/([^/]+)/s/',urlparse(original).path,re.I)
            if sm: return f'https://www.reddit.com/r/{sm.group(1)}/comments/{m.group(1)}/'
    return None


def resolve(url):
    endpoints=[
        ('oembed','https://www.reddit.com/oembed?url='+quote(url,safe='')),
        ('api-oembed','https://www.reddit.com/api/oembed?url='+quote(url,safe='')),
        ('api-info','https://www.reddit.com/api/info.json?url='+quote(url,safe='')),
    ]
    diags=[]
    for name,target in endpoints:
        try:
            r=requests.get(target,headers={'User-Agent':UA,'Accept':'application/json,text/plain,*/*'},timeout=45,allow_redirects=True)
            cand=extract_candidate(r.url,url) or extract_candidate(r.headers.get('location',''),url) or extract_candidate(r.text,url)
            if cand: return cand,f'{name}:{r.status_code}'
            diags.append(f'{name}:{r.status_code}:{len(r.text or "")}')
        except Exception as e:
            diags.append(f'{name}:{type(e).__name__}')
    return None,';'.join(diags)


def main():
    if not STATUS.exists(): print(json.dumps({'ok':True,'results':[]})); return
    try: ids=(json.loads(STATUS.read_text(encoding='utf-8')).get('itemIds') or [])[:10]
    except Exception: ids=[]
    out=[]
    for item_id in ids:
        item=wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
        if not item: out.append({'id':item_id,'status':'missing'}); continue
        src=str(item.get('sourceUrl') or '')
        if not is_short(src): out.append({'id':item_id,'status':'skip'}); continue
        canonical,mode=resolve(src)
        if not canonical: out.append({'id':item_id,'status':'unresolved','detail':mode}); continue
        item['sharedUrl']=item.get('sharedUrl') or src
        item['sourceUrl']=canonical; item['canonicalUrl']=canonical; item['error']=None
        wrangler_put(f'{ITEM_PREFIX}{item_id}.json',item)
        q=wrangler_get(f'{QUEUE_PREFIX}{item_id}.json') or {'id':item_id,'createdAt':item.get('createdAt')}
        q['sourceUrl']=canonical; q['sharedUrl']=src
        wrangler_put(f'{QUEUE_PREFIX}{item_id}.json',q)
        out.append({'id':item_id,'status':'resolved','mode':mode,'canonicalResolved':True})
    print(json.dumps({'ok':True,'results':out},ensure_ascii=False))

if __name__=='__main__': main()
