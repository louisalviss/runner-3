#!/usr/bin/env python3
import requests
ACCS=['0001193125-16-644489','0001193125-17-002614','0001193125-17-221822','0001193125-18-002695','0001193125-18-214392','0001193125-18-321151','0001193125-19-138363']
for acc in ACCS:
    compact=acc.replace('-','')
    url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{acc}.txt'
    r=requests.get(url,timeout=180,headers={'User-Agent':'runner-3 spmo research'}); r.raise_for_status(); t=r.text
    hits=[]
    low=t.lower()
    for needle in ['s&p 500 momentum','spmo','momentum portfolio']:
        i=0
        while True:
            j=low.find(needle,i)
            if j<0: break
            hits.append(j); i=j+len(needle)
    hits=sorted(set(hits))
    print('\n\n===== ACCESSION',acc,'LEN',len(t),'HITS',hits[:10],'=====')
    for j in hits[:3]:
        print('\n--- CONTEXT',j,'---\n',t[max(0,j-3000):min(len(t),j+12000)])
