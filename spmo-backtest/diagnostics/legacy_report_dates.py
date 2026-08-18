#!/usr/bin/env python3
import requests,re
ACCS=['0001193125-16-523551','0001193125-16-644489','0001193125-16-722841','0001193125-17-002614','0001193125-17-103370','0001193125-17-221822','0001193125-17-297460','0001193125-18-002695','0001193125-18-100897','0001193125-18-214392','0001193125-18-287407','0001193125-18-321151','0001193125-19-020397','0001193125-19-138363','0001193125-19-287045']
for acc in ACCS:
 compact=acc.replace('-','')
 url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{acc}-index.htm'
 r=requests.get(url,timeout=90,headers={'User-Agent':'runner-3 spmo research'})
 text=r.text
 dates=re.findall(r'(?:Period of Report|CONFORMED PERIOD OF REPORT)[:\s|]*([0-9]{4}-?[0-9]{2}-?[0-9]{2})',text,re.I)
 print(acc,'status',r.status_code,'len',len(text),'periods',dates[:3])
 for line in text.splitlines():
  if 'Period of Report' in line or 'Filing Date' in line:
   print(' ',line[:500])
