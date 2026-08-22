#!/usr/bin/env python3
import json,re
from pathlib import Path
from urllib.parse import urlparse,urlunparse
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[2]
REQUEST=ROOT/'ops/audio-library/reddit-read-request.json'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'

def clean(s):
    s=str(s or '').replace('\r','')
    s=re.sub(r'[`*_>#|]',' ',s)
    s=re.sub(r'[ \t]+',' ',s)
    return re.sub(r'\n{3,}','\n\n',s).strip()

def target_url(fallback):
    try:
        d=json.loads(REQUEST.read_text(encoding='utf-8'))
        u=str(d.get('url') or '').strip()
        return u if 'reddit.com/' in u.lower() else fallback
    except Exception:
        return fallback

def canonical_from_text(text):
    m=re.search(r'https?://(?:www\.)?reddit\.com(/r/[^\s"\'<>]+/comments/[a-z0-9]+(?:/[^\s"\'<>?]*)?)',str(text or ''),re.I)
    if not m:
        m=re.search(r'https?://(?:www\.)?reddit\.com(/comments/[a-z0-9]+(?:/[^\s"\'<>?]*)?)',str(text or ''),re.I)
    return ('https://www.reddit.com'+m.group(1)).split('?')[0].rstrip('/')+'/' if m else None

def resolve(source):
    if '/comments/' in source:
        return source.split('?')[0].rstrip('/')+'/'
    u=urlparse(source)
    rx=urlunparse(u._replace(scheme='https',netloc='rxddit.com'))
    r=requests.get(rx,headers={'User-Agent':UA,'Accept':'text/html,*/*'},timeout=45,allow_redirects=False)
    loc=r.headers.get('location','')
    c=canonical_from_text(loc) or canonical_from_text(r.text)
    if c:return c
    if loc:
        lu=urlparse(loc)
        if lu.hostname in {'rxddit.com','www.rxddit.com'} and '/comments/' in lu.path:
            return urlunparse(lu._replace(scheme='https',netloc='www.reddit.com',query='',fragment='')).rstrip('/')+'/'
    raise RuntimeError(f'resolve failed rxddit={r.status_code}/{len(r.text or "")}')

def parse_json(data):
    post=data[0]['data']['children'][0]['data']
    title=clean(post.get('title') or 'Reddit')
    chunks=[]
    body=clean(post.get('selftext') or '')
    if body:chunks.append('[Post]\n'+body)
    comments=[]
    def walk(children,depth=0):
        if depth>3 or len(comments)>=150:return
        for child in children or []:
            if len(comments)>=150:return
            if child.get('kind')!='t1':continue
            d=child.get('data') or {}
            b=clean(d.get('body') or '')
            if len(b)>=20:
                score=d.get('score')
                comments.append((f'[Comment score {score}] ' if isinstance(score,int) else '[Comment] ')+b)
            rep=d.get('replies')
            if isinstance(rep,dict):walk(((rep.get('data') or {}).get('children') or []),depth+1)
    walk(((data[1].get('data') or {}).get('children') or []))
    chunks.extend(comments)
    return title,clean('\n\n'.join(chunks))

def fetch_json(canonical):
    p=urlparse(canonical).path.rstrip('/')
    pid=(re.search(r'/comments/([a-z0-9]+)',p,re.I) or [None,None])[1]
    urls=[f'https://www.reddit.com{p}.json?raw_json=1&limit=100&sort=top',f'https://old.reddit.com{p}.json?raw_json=1&limit=100&sort=top']
    if pid:urls.append(f'https://www.reddit.com/comments/{pid}.json?raw_json=1&limit=100&sort=top')
    errs=[]
    for u in urls:
        try:
            r=requests.get(u,headers={'User-Agent':UA,'Accept':'application/json,text/plain,*/*'},timeout=45)
            errs.append(f'{r.status_code}/{len(r.content)}')
            if r.status_code==200:
                title,text=parse_json(r.json())
                if len(text)>=300:return title,text
        except Exception as e:errs.append(type(e).__name__)
    raise RuntimeError('json '+','.join(errs))

def fetch_jina(canonical):
    errs=[]
    for u in ['https://r.jina.ai/'+canonical,'https://r.jina.ai/http://'+canonical.split('://',1)[-1]]:
        try:
            r=requests.get(u,headers={'User-Agent':UA,'Accept':'text/plain'},timeout=60)
            errs.append(f'{r.status_code}/{len(r.text)}')
            if r.status_code==200 and len(r.text)>=600:
                raw=r.text
                m=re.search(r'(?mi)^Title:\s*(.+)$',raw)
                title=clean(m.group(1)) if m else 'Reddit'
                text=re.sub(r'(?mi)^(Title|URL Source|Published Time|Markdown Content):\s*.*$','',raw)
                text=clean(text)
                if len(text)>=400:return title,text
        except Exception as e:errs.append(type(e).__name__)
    raise RuntimeError('jina '+','.join(errs))

def extract_reddit(_url):
    source=target_url(_url)
    canonical=resolve(source)
    try:
        title,text=fetch_json(canonical)
    except Exception as je:
        try:title,text=fetch_jina(canonical)
        except Exception as ji:raise RuntimeError(f'Reddit read failed: {je}; {ji}; canonical={canonical}')
    return title,text,'Reddit',canonical
