#!/usr/bin/env python3
import json,re,sys,hashlib
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

TARGETS={
 'robots':'https://www.mx-xz.com/robots.txt',
 'all1':'https://www.mx-xz.com/sf-jq/all/',
 'all2':'https://www.mx-xz.com/sf-jq/all/2/',
 'opening':'https://www.mx-xz.com/sf-jq/kaitou/',
 'article':'https://www.mx-xz.com/show_34620.html',
}
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36 runner-3/moxing-probe'

def clean(s): return re.sub(r'\s+',' ',s or '').strip()

def main():
 out=Path(sys.argv[1] if len(sys.argv)>1 else 'moxing_probe'); out.mkdir(parents=True,exist_ok=True)
 sess=requests.Session(); sess.headers.update({'User-Agent':UA,'Accept-Language':'zh-CN,zh;q=0.9'})
 recs=[]
 for name,url in TARGETS.items():
  try:
   r=sess.get(url,timeout=30,allow_redirects=True)
   html=r.text
   p=out/f'{name}.html'; p.write_text(html,encoding='utf-8',errors='replace')
   soup=BeautifulSoup(html,'lxml')
   anchors=[]
   for a in soup.find_all('a',href=True):
    href=urljoin(r.url,a['href']); txt=clean(a.get_text(' ',strip=True))
    if 'mx-xz.com' in urlparse(href).netloc:
     anchors.append({'text':txt[:120],'href':href})
   blocks=[]
   for tag in soup.find_all(['article','main','section','div']):
    txt=clean(tag.get_text(' ',strip=True))
    if len(txt)>=300:
     blocks.append({'tag':tag.name,'id':tag.get('id'),'class':tag.get('class') or [],'chars':len(txt),'text':txt[:1000]})
   blocks=sorted(blocks,key=lambda x:x['chars'],reverse=True)[:20]
   recs.append({'name':name,'requested_url':url,'final_url':r.url,'status':r.status_code,'bytes':len(r.content),'title':clean(soup.title.get_text(' ',strip=True)) if soup.title else '', 'anchors_count':len(anchors),'show_links':[x for x in anchors if re.search(r'/show_\d+\.html$',urlparse(x['href']).path)][:60], 'page_links':[x for x in anchors if '/sf-jq/all/' in x['href']][:40], 'large_blocks':blocks,'sha256':hashlib.sha256(r.content).hexdigest()})
  except Exception as e:
   recs.append({'name':name,'requested_url':url,'error':f'{type(e).__name__}: {e}'})
 (out/'probe.json').write_text(json.dumps(recs,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps([{k:r.get(k) for k in ('name','status','bytes','title','anchors_count','error')} for r in recs],ensure_ascii=False,indent=2))
if __name__=='__main__': main()
