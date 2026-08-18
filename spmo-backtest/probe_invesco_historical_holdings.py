#!/usr/bin/env python3
import requests, re, json
from urllib.parse import urlencode
BASE='https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0'
H={'User-Agent':'Mozilla/5.0','Accept':'*/*'}
variants=[
 {},
 {'action':'download','audienceType':'Institutional','ticker':'SPMO'},
 {'action':'download','audienceType':'Institutional','ticker':'SPMO','asOfDate':'2018-03-19'},
 {'action':'download','audienceType':'Institutional','ticker':'SPMO','asOfDate':'03/19/2018'},
 {'action':'download','audienceType':'Institutional','ticker':'SPMO','date':'2018-03-19'},
 {'action':'download','audienceType':'Institutional','ticker':'SPMO','holdingsDate':'2018-03-19'},
 {'action':'download','audienceType':'Institutional','ticker':'SPMO','asof':'2018-03-19'},
 {'action':'download','audienceType':'Institutional','ticker':'SPMO','asOfDate':'2021-03-22'},
]
for q in variants:
    try:
        r=requests.get(BASE,params=q,headers=H,timeout=60,allow_redirects=True)
        text=r.text[:3000]
        print('\nQUERY',json.dumps(q),'STATUS',r.status_code,'TYPE',r.headers.get('content-type'),'CD',r.headers.get('content-disposition'),'LEN',len(r.content),'FINAL',r.url)
        print('HEAD',repr(text[:1000]))
        for pat in ['2018','2021','As of','as of','SPMO','Microsoft','NVIDIA','Micron']:
            if pat.lower() in text.lower(): print('HAS',pat)
    except Exception as e: print('ERR',q,repr(e))
