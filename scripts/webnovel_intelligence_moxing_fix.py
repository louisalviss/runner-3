#!/usr/bin/env python3
"""Quality wrapper for Webnovel Intelligence v1.
- Moxing detail URLs are /show_<id>.html and each anchor wraps the full card.
- Preference signals use narrower terms to avoid substring inflation in Vietnamese forum text.
"""
import re,time
from urllib.parse import urljoin,urlparse
import webnovel_intelligence as w

REFINED_SIGNALS={
 'cautious_main':['thận trọng','cẩn thận','cẩu đạo','谨慎','稳健'],
 'smart_main':['thông minh','main khôn','main não','não to','iq cao','聪明','智商在线'],
 'progression':['thăng cấp','cảnh giới','tu luyện','đột phá','progression','升级','境界','修炼'],
 'resource_loop':['tài nguyên','pháp bảo','công pháp','kỳ ngộ','loot','资源','法宝','功法','机缘'],
 'worldbuilding':['thế giới','bối cảnh','thế lực','tông môn','worldbuilding','世界观','势力'],
 'pacing':['nhịp truyện','tiết tấu','kéo dài','câu giờ','拖沓','节奏'],
 'logic':['logic','hợp lý','vô lý','智障','降智','逻辑'],
 'character':['nhân vật','tính cách','main','nữ chính','角色','人物','主角'],
 'romance_harem':['hậu cung','nữ chính','tình cảm','harem','后宫','感情线'],
 'payoff':['sảng','đánh mặt','thỏa mãn','爽','打脸','高潮'],
 'ending':['kết thúc','kết truyện','kết cục','ending','烂尾','结局'],
 'originality':['mới lạ','sáng tạo','ý tưởng','não động','创意','脑洞'],
 'prose':['văn phong','câu chữ','dịch thuật','bản dịch','文笔','文风'],
 'mystery':['bí ẩn','mystery','伏笔','悬疑'],
}

def _has(text,term):
    t=text.lower(); q=term.lower()
    if re.search(r'[\u4e00-\u9fff]',q): return q in t
    return re.search(r'(?<![0-9A-Za-zÀ-ỹĐđ])'+re.escape(q)+r'(?![0-9A-Za-zÀ-ỹĐđ])',t,re.I) is not None

def signal_hits(text):
    out={}
    for k,terms in REFINED_SIGNALS.items():
        score=sum(len(re.findall(re.escape(term),text,re.I)) if re.search(r'[\u4e00-\u9fff]',term) else (1 if _has(text,term) else 0) for term in terms)
        if score: out[k]=score
    return out


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

w.signal_hits=signal_hits
w.moxing_collect=moxing_collect
if __name__=='__main__': w.main()
