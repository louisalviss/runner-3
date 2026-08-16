#!/usr/bin/env python3
import json,re,time,sys
from urllib.parse import urljoin,urlparse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

TARGETS={
 'youshu_books':'https://www.youshu.me/book_reviewsnum_1_0_0_0_0_0_1.html',
 'youshu_booklists':'https://www.youshu.me/booklists',
 'youshu_mobile':'https://m.youshu.me/',
 'youshu_backup':'https://xiaoshuo.me/',
 'lkong_forums':'https://www.lkong.com/forums',
 'lkong_review':'https://www.lkong.com/forum/8',
 'lkong_recommend':'https://www.lkong.com/forum/60',
 'lkong_industry':'https://www.lkong.com/forum/15',
}
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36 runner-3/webnovel-probe'

def fetch(url):
 s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept-Language':'zh-CN,zh;q=0.9,en;q=0.4'})
 r=s.get(url,timeout=30,allow_redirects=True); return r

def summarize(name,url,out):
 try:
  r=fetch(url); html=r.text
  soup=BeautifulSoup(html,'lxml')
  title=soup.title.get_text(' ',strip=True) if soup.title else ''
  anchors=[]
  for a in soup.find_all('a',href=True):
   text=' '.join(a.get_text(' ',strip=True).split())
   href=urljoin(r.url,a['href'])
   if text or re.search(r'(book|thread|forum|review|list)',href,re.I):
    anchors.append({'text':text[:180],'href':href})
  tables=[]
  for t in soup.find_all('table')[:5]:
   rows=[]
   for tr in t.find_all('tr')[:20]:
    cells=[' '.join(x.get_text(' ',strip=True).split()) for x in tr.find_all(['th','td'])]
    if cells: rows.append(cells)
   tables.append(rows)
  likely=[]
  key='youshu' if ('youshu' in name or 'backup' in name) else 'lkong'
  pat=r'(book|review|booklist|sort)' if key=='youshu' else r'(thread|forum)'
  for a in soup.find_all('a',href=True):
   href=urljoin(r.url,a['href'])
   if re.search(pat,urlparse(href).path,re.I):
    par=a.find_parent(['li','tr','article','div'])
    txt=' '.join((par or a).get_text(' ',strip=True).split())
    if txt and len(txt)>8:
     likely.append({'href':href,'anchor':' '.join(a.get_text(' ',strip=True).split())[:100],'parent':txt[:700], 'tag':(par.name if par else a.name), 'class':((par.get('class') if par else a.get('class')) or [])})
    if len(likely)>=120: break
  rec={'name':name,'requested_url':url,'final_url':r.url,'status':r.status_code,'bytes':len(r.content),'title':title,'anchors_count':len(anchors),'anchors':anchors[:600],'tables':tables,'likely':likely,'html_sha256':__import__('hashlib').sha256(r.content).hexdigest()}
  (out/f'{name}.html').write_text(html,encoding='utf-8',errors='replace')
  return rec
 except Exception as e:
  return {'name':name,'requested_url':url,'error':f'{type(e).__name__}: {e}'}

def main():
 out=Path(sys.argv[1] if len(sys.argv)>1 else 'probe_out'); out.mkdir(parents=True,exist_ok=True)
 rows=[]
 for n,u in TARGETS.items():
  rows.append(summarize(n,u,out)); time.sleep(1.2)
 (out/'probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps([{k:r.get(k) for k in ('name','status','bytes','title','anchors_count','final_url','error')} for r in rows],ensure_ascii=False,indent=2))
if __name__=='__main__': main()
