#!/usr/bin/env python3
import json, os
from urllib.parse import quote, urljoin
import requests

ACCOUNT=os.environ['CLOUDFLARE_ACCOUNT_ID'].strip()
TOKEN=os.environ['CLOUDFLARE_API_TOKEN'].strip()
BUCKET='runner3-wp-media'
BASE='https://runner3-core.ducduy2411.workers.dev'
ID='ebook-5c3258ea79a8ffb76bff5fd299ac4619'
BOOK='core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub'
KEY=f'audio-library/media/{ID}/episode.mp3'

def api_url(key):
    return f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets/{quote(BUCKET,safe='')}/objects/{quote(key,safe='/')}"

def main():
    h={'Authorization':f'Bearer {TOKEN}'}
    rr=requests.get(api_url(KEY),headers={**h,'Range':'bytes=0-31'},timeout=60)
    print(json.dumps({'r2RestStatus':rr.status_code,'r2Bytes':len(rr.content),'r2Prefix':rr.content[:8].hex()},ensure_ascii=False))
    s=requests.get(BASE+'/artifact-library/audio',params={'id':ID,'bookKey':BOOK},headers={'Cache-Control':'no-cache'},timeout=60)
    print(json.dumps({'statusHttp':s.status_code,'statusBody':s.text[:1000]},ensure_ascii=False))
    if s.status_code!=200: return 1
    d=s.json(); media=d.get('mediaUrl'); timing=d.get('timingUrl')
    if not media:
        print(json.dumps({'error':'mediaUrl missing'})); return 2
    m=requests.get(urljoin(BASE+'/',media),headers={'Range':'bytes=0-31','Cache-Control':'no-cache'},timeout=60)
    print(json.dumps({'mediaHttp':m.status_code,'mediaBody':m.text[:500] if 'json' in m.headers.get('content-type','') else None,'mediaBytes':len(m.content)},ensure_ascii=False))
    if timing:
        t=requests.get(urljoin(BASE+'/',timing),headers={'Cache-Control':'no-cache'},timeout=60)
        body=t.text[:500]
        print(json.dumps({'timingHttp':t.status_code,'timingBody':body},ensure_ascii=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
