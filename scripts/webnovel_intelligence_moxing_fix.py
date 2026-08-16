#!/usr/bin/env python3
"""Build wrapper that corrects Moxing detail-link discovery.
Moxing category listings live under /sf-jq/<category>/ but article detail URLs are /show_<id>.html.
The detail anchor wraps the full card, so title must come from its title/H4 while card text becomes the excerpt.
"""
import re,time
from urllib.parse import urljoin,urlparse
import webnovel_intelligence as w


def moxing_collect(c,max_pages=12):
    seen=set(); count=0; failures=[]
    for cat in w.MOXING_CATS:
        for pg in range(1,max_pages+1):
            url=f'{w.MOXING}/sf-jq/{cat}/' if pg==1 else f'{w.MOXING}/sf-jq/{cat}/{pg}/'
            try: r=w.fetch(url)
            except Exception as e:
                failures.append([url,str(e)]); break
            if r.status_code!=200: break
            s=w.soup_bytes(r.content); unique=[]; page_seen=set()
            for a in s.find_all('a',href=True):
                href=urljoin(r.url,a['href']); path=urlparse(href).path
                if not re.fullmatch(r'/show_\d+\.html',path): continue
                h=a.find(['h1','h2','h3','h4'])
                title=w.txt(a.get('title') or (h.get_text(' ',strip=True) if h else ''))
                context=w.txt(a.get_text(' ',strip=True))
                if len(title)<5 or len(context)<len(title)+8 or href in seen or href in page_seen: continue
                unique.append((href,title,context)); page_seen.add(href)
            if not unique and pg>1: break
            for href,title,context in unique:
                seen.add(href)
                m=re.search(r'(\d+(?:\.\d+)?)\s*人气',context); pop=float(m.group(1)) if m else None
                w.add_item(c,'moxing','writing_article',href,title=title,category=cat,body=context,popularity=pop,meta={'listing_page':url})
                count+=1
            pages=[]
            for a in s.find_all('a',href=True):
                h=urljoin(r.url,a['href']); mm=re.search(rf'/sf-jq/{cat}/(\d+)/?$',urlparse(h).path)
                if mm: pages.append(int(mm.group(1)))
            if pg>=max(pages or [1]) and pg>1: break
            time.sleep(.35)
        c.commit()
    return {'items':count,'unique_urls':len(seen),'failures':failures[:20]}

w.moxing_collect=moxing_collect
if __name__=='__main__': w.main()
