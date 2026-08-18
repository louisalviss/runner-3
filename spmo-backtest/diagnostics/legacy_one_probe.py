#!/usr/bin/env python3
import requests
acc='0001193125-16-644489'
compact=acc.replace('-','')
url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{acc}.txt'
r=requests.get(url,timeout=180,headers={'User-Agent':'runner-3 spmo research'}); print('STATUS',r.status_code,'LEN',len(r.text)); r.raise_for_status(); t=r.text
low=t.lower(); needles=['s&p 500 momentum','spmo','momentum portfolio','momentum']
seen=[]
for n in needles:
 i=0
 while True:
  j=low.find(n,i)
  if j<0:break
  if all(abs(j-x)>100 for x in seen):seen.append(j)
  i=j+len(n)
print('HITS',seen[:20])
for j in sorted(seen)[:8]:
 print('\n---',j,'---\n')
 print(t[max(0,j-5000):min(len(t),j+25000)])
