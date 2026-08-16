#!/usr/bin/env python3
import json,re,requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin,urlparse
u='https://www.mx-xz.com/sf-jq/kaitou/'
r=requests.get(u,headers={'User-Agent':'Mozilla/5.0 Chrome/139 runner-3/debug'},timeout=30)
s=BeautifulSoup(r.content,'lxml')
rows=[]
for a in s.find_all('a',href=True):
 h=urljoin(r.url,a['href']); p=urlparse(h).path
 if 'show_' in p or '/sf-jq/' in p:
  par=a.find_parent(['article','li','div'])
  rows.append({'href':h,'path':p,'text':' '.join(a.get_text(' ',strip=True).split())[:200],'parent':' '.join((par or a).get_text(' ',strip=True).split())[:700],'class':a.get('class') or [],'parent_class':(par.get('class') if par else []) or []})
print(json.dumps({'status':r.status_code,'bytes':len(r.content),'final':r.url,'title':s.title.get_text(' ',strip=True) if s.title else '', 'show_count':sum('/show_' in x['path'] for x in rows),'rows':rows[:100]},ensure_ascii=False,indent=2))
open('moxing_kaitou_debug.html','wb').write(r.content)
