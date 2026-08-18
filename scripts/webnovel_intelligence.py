#!/usr/bin/env python3
from __future__ import annotations
import argparse, collections, concurrent.futures, datetime as dt, hashlib, json, random, re, sqlite3, threading, time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36 runner-3/webnovel-intelligence'
VOZ_ROOT='https://voz.vn/t/ban-luan-ve-cac-truyen-tien-hiep-kiem-hiep-ky-ao-ver-nextvoz.1421/'
MOXING='https://www.mx-xz.com'
QTRAN='https://www.qtran.app/wn/books'
ZHIHU_SEEDS=['https://www.zhihu.com/question/454846719/answer/109960694064']
MOXING_CATS=['shuming','kaitou','qingjie','rwsz','dagang','qianyue','jiqiao','bikeng','zatan','shoufa']
SIGNALS={
 'cautious_main':['thận trọng','cẩn thận','cẩu đạo','苟','谨慎','稳健'],
 'smart_main':['main thông minh','não','trí','IQ','khôn','聪明','智商在线'],
 'progression':['thăng cấp','cảnh giới','tu luyện','đột phá','progression','升级','境界','修炼'],
 'resource_loop':['tài nguyên','pháp bảo','công pháp','kỳ ngộ','loot','资源','法宝','功法','机缘'],
 'worldbuilding':['thế giới','bối cảnh','thế lực','tông môn','worldbuilding','世界观','势力'],
 'pacing':['nhịp','tiết tấu','kéo dài','câu giờ','水','节奏','拖沓'],
 'logic':['logic','hợp lý','vô lý','智障','降智','逻辑'],
 'character':['nhân vật','tính cách','main','nữ chính','角色','人物','主角'],
 'romance_harem':['hậu cung','nữ chính','tình cảm','harem','后宫','感情线'],
 'payoff':['sảng','đánh mặt','thỏa mãn','爽','打脸','高潮'],
 'ending':['kết','ending','kết thúc','烂尾','结局'],
 'originality':['mới lạ','sáng tạo','ý tưởng','não động','创意','脑洞'],
 'prose':['văn phong','câu chữ','dịch','文笔','文风'],
 'mystery':['bí ẩn','mystery','伏笔','悬疑','谜'],
}
POS=['hay','ổn','cuốn','đỉnh','tốt','thích','recommend','đáng đọc','不错','好看','推荐','神作','精品','精彩','喜欢']
NEG=['dở','tệ','chán','drop','bỏ','rác','không hay','烂','毒','弃书','垃圾','无聊','劝退','崩']
BOOK_RX=[re.compile(r'《([^》]{2,50})》'), re.compile(r'[“"]([^”"\n]{3,45})[”"]')]
_tls=threading.local()

def session():
 s=getattr(_tls,'s',None)
 if s is None:
  s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept-Language':'vi,zh-CN;q=0.9,zh;q=0.8,en;q=0.5'}); _tls.s=s
 return s

def fetch(url, attempts=4, delay=.5):
 err=None
 for i in range(attempts):
  try:
   r=session().get(url,timeout=30,allow_redirects=True)
   if r.status_code in (429,500,502,503,504): raise RuntimeError(f'HTTP {r.status_code}')
   return r
  except Exception as e:
   err=e; time.sleep(delay*(i+1)+random.random()*.2)
 raise err

def soup_bytes(content): return BeautifulSoup(content,'lxml')
def txt(x): return re.sub(r'\s+',' ',x or '').strip()
def sha(s): return hashlib.sha256((s or '').encode('utf-8')).hexdigest()
def excerpt(s,n=800): s=txt(s); return s if len(s)<=n else s[:n-1]+'…'
def sentiment(s):
 low=s.lower(); p=sum(low.count(x.lower()) for x in POS); n=sum(low.count(x.lower()) for x in NEG)
 return 'positive' if p>n and p else ('negative' if n>p and n else ('mixed' if p and n else 'neutral'))
def signal_hits(s):
 low=s.lower(); return {k:sum(low.count(x.lower()) for x in vs) for k,vs in SIGNALS.items() if any(x.lower() in low for x in vs)}
def book_titles(s):
 out=[]
 for rx in BOOK_RX: out += [txt(x) for x in rx.findall(s)]
 return list(dict.fromkeys(x for x in out if 2<=len(x)<=50))[:12]

def init_db(p):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.unlink(missing_ok=True)
 c=sqlite3.connect(p); c.executescript('''
 CREATE TABLE sources(source TEXT PRIMARY KEY,mode TEXT,status TEXT,notes TEXT,checked_at TEXT);
 CREATE TABLE items(id INTEGER PRIMARY KEY,source TEXT,item_type TEXT,url TEXT UNIQUE,title TEXT,author TEXT,published_at TEXT,category TEXT,excerpt TEXT,content_sha256 TEXT,popularity REAL,meta_json TEXT);
 CREATE TABLE signals(item_id INT,signal TEXT,score REAL,sentiment TEXT,PRIMARY KEY(item_id,signal));
 CREATE TABLE book_mentions(item_id INT,title TEXT,PRIMARY KEY(item_id,title));
 CREATE VIRTUAL TABLE items_fts USING fts5(title,excerpt,category,content='items',content_rowid='id',tokenize='unicode61 remove_diacritics 2');
 CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN INSERT INTO items_fts(rowid,title,excerpt,category) VALUES(new.id,new.title,new.excerpt,new.category); END;
 CREATE INDEX items_source ON items(source,item_type); CREATE INDEX sig_name ON signals(signal,score DESC); CREATE INDEX books_title ON book_mentions(title);
 '''); return c

def add_item(c, source, typ, url, title='', author='', date='', category='', body='', popularity=None, meta=None):
 body=txt(body); cur=c.execute('INSERT OR IGNORE INTO items(source,item_type,url,title,author,published_at,category,excerpt,content_sha256,popularity,meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(source,typ,url,txt(title),txt(author),date,category,excerpt(body),sha(body),popularity,json.dumps(meta or {},ensure_ascii=False)))
 if not cur.lastrowid: return None
 iid=cur.lastrowid; sent=sentiment(body)
 for k,v in signal_hits(body).items(): c.execute('INSERT OR REPLACE INTO signals VALUES(?,?,?,?)',(iid,k,float(v),sent))
 for b in book_titles(body): c.execute('INSERT OR IGNORE INTO book_mentions VALUES(?,?)',(iid,b))
 return iid

def moxing_collect(c,max_pages=12):
 seen=set(); count=0; failures=[]
 for cat in MOXING_CATS:
  for pg in range(1,max_pages+1):
   url=f'{MOXING}/sf-jq/{cat}/' if pg==1 else f'{MOXING}/sf-jq/{cat}/{pg}/'
   try:r=fetch(url)
   except Exception as e: failures.append([url,str(e)]); break
   if r.status_code!=200: break
   s=soup_bytes(r.content); found=[]
   roots={f'/sf-jq/{x}' for x in MOXING_CATS}
   for a in s.find_all('a',href=True):
    href=urljoin(r.url,a['href']); path=urlparse(href).path
    if not path.startswith('/sf-jq/') or path.rstrip('/') in roots: continue
    title=txt(a.get_text(' ',strip=True))
    if len(title)<5 or href in seen: continue
    par=a.find_parent(['article','li','div']); context=txt((par or a).get_text(' ',strip=True))
    if len(context)<len(title)+8: continue
    found.append((href,title,context))
   unique=[]; us=set()
   for row in found:
    if row[0] not in us: unique.append(row); us.add(row[0])
   if not unique and pg>1: break
   for href,title,context in unique:
    if href in seen: continue
    seen.add(href); m=re.search(r'(\d+(?:\.\d+)?)\s*人气',context); pop=float(m.group(1)) if m else None
    add_item(c,'moxing','writing_article',href,title=title,category=cat,body=context,popularity=pop,meta={'listing_page':url}); count+=1
   pages=[]
   for a in s.find_all('a',href=True):
    h=urljoin(r.url,a['href']); mm=re.search(rf'/sf-jq/{cat}/(\d+)/?$',urlparse(h).path)
    if mm: pages.append(int(mm.group(1)))
   if pg>=max(pages or [1]) and pg>1: break
   time.sleep(.35)
  c.commit()
 return {'items':count,'unique_urls':len(seen),'failures':failures[:20]}

def parse_voz_page(content,url):
 s=soup_bytes(content); rows=[]
 for art in s.select('article.message'):
  pid=(art.get('id') or '').replace('js-post-',''); author=art.get('data-author') or ''
  nm=art.select_one('.message-name'); author=author or (txt(nm.get_text(' ',strip=True)) if nm else '')
  tm=art.select_one('time'); date=tm.get('datetime','') if tm else ''
  body=art.select_one('.message-body .bbWrapper') or art.select_one('.message-body')
  if not body: continue
  for q in body.select('blockquote,.bbCodeBlock--quote,.bbCodeBlock-title'): q.decompose()
  text=txt(body.get_text(' ',strip=True))
  if not text: continue
  permalink=f'{VOZ_ROOT}post-{pid}' if pid else url
  rows.append((permalink,pid,author,date,text))
 return rows

def voz_last_page():
 r=fetch(VOZ_ROOT); s=soup_bytes(r.content); nums=[]
 for a in s.select('.pageNav-main a[href]'):
  t=txt(a.get_text())
  if t.isdigit(): nums.append(int(t))
  m=re.search(r'/page-(\d+)',a.get('href',''))
  if m: nums.append(int(m.group(1)))
 return max(nums or [1])

def voz_collect(c,workers=3,start_page=1,end_page=0):
 last=voz_last_page(); end=min(end_page or last,last); failed=[]; total=0; pages_done=0
 def one(pg):
  u=VOZ_ROOT if pg==1 else VOZ_ROOT+f'page-{pg}'
  try:
   r=fetch(u,attempts=5,delay=.8); time.sleep(.45); return pg,u,parse_voz_page(r.content,u),None
  except Exception as e:return pg,u,[],str(e)
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  futs={ex.submit(one,p):p for p in range(start_page,end+1)}
  for fut in concurrent.futures.as_completed(futs):
   pg,u,rows,err=fut.result()
   if err: failed.append([pg,err]); continue
   for link,pid,author,date,text in rows:
    add_item(c,'voz','forum_post',link,title=f'VOZ post {pid}',author=author,date=date,category='tien-hiep-kiem-hiep-ky-ao',body=text,meta={'page':pg,'post_id':pid}); total+=1
   pages_done+=1
   if pages_done%50==0: c.commit(); print(json.dumps({'phase':'voz','pages':pages_done,'items':total,'failed':len(failed)}),flush=True)
 c.commit(); return {'thread_last_page':last,'requested':[start_page,end],'pages_done':pages_done,'posts':total,'failed_pages':failed}

def zhihu_collect(c,seeds=ZHIHU_SEEDS):
 n=0; failures=[]
 for u in seeds:
  try:r=fetch(u)
  except Exception as e: failures.append([u,str(e)]); continue
  if r.status_code!=200: failures.append([u,f'HTTP {r.status_code}']); continue
  s=soup_bytes(r.content); title=txt(s.title.get_text(' ',strip=True) if s.title else ''); ans=s.select_one('.RichContent-inner')
  if ans:
   body=txt(ans.get_text(' ',strip=True)); add_item(c,'zhihu','writing_answer',r.url,title=title,category='webnovel_writing',body=body,meta={'full_chars':len(body)}); n+=1
  time.sleep(.5)
 c.commit(); return {'seeded_answers':n,'failures':failures}

def chivi_taxonomy(c):
 try:r=fetch(QTRAN)
 except Exception as e:return {'status':'failed','error':str(e)}
 if r.status_code!=200:return {'status':'failed','http':r.status_code}
 s=soup_bytes(r.content); genres=[]
 for a in s.find_all('a',href=True):
  h=urljoin(r.url,a['href']); q=parse_qs(urlparse(h).query)
  if 'gr' in q:
   g=txt(q['gr'][0])
   if g and g not in genres: genres.append(g)
 for g in genres: add_item(c,'chivi','genre_filter',urljoin(r.url,f'/wn/books?gr={requests.utils.quote(g)}&lm=24'),title=g,category='genre',body=g)
 c.commit(); return {'genres':genres,'genre_count':len(genres),'note':'library shell is public; individual book list is client-rendered, so v1 stores public taxonomy/filter routes only'}

def source_status(c):
 now=dt.datetime.now(dt.timezone.utc).isoformat(); rows=[
 ('moxing','automated','active','public static category listings; metadata/excerpts only'),
 ('voz','automated','active','public forum thread; excerpt/hash/signal only, not full-text mirror'),
 ('zhihu','seeded','active','specific public answers fetchable; discovery remains seed/on-demand'),
 ('chivi','partial','active','qtran library/filter shell public; book cards client-rendered'),
 ('youshu','on_demand','blocked_from_runner','Cloudflare 403 on www/mobile/backup from GitHub Actions; no bypass attempted'),
 ('lkong','seeded','login_gated_listing','forums index public; board enumeration requires login; public known thread URLs may be fetched on demand'),
 ('qidian','on_demand','challenge_from_runner','simple runner request returns 202/no useful page; use external search/on-demand metadata')]
 c.executemany('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)',[(a,b,d,n,now) for a,b,d,n in rows]); c.commit()

def build(out,voz_start=1,voz_end=0,workers=3,moxing_pages=12):
 out=Path(out); out.mkdir(parents=True,exist_ok=True); c=init_db(out/'webnovel_intelligence.sqlite'); source_status(c); res={}
 res['moxing']=moxing_collect(c,moxing_pages); res['zhihu']=zhihu_collect(c); res['chivi']=chivi_taxonomy(c); res['voz']=voz_collect(c,workers,voz_start,voz_end)
 counts={'items':c.execute('select count(*) from items').fetchone()[0],'moxing_items':c.execute("select count(*) from items where source='moxing'").fetchone()[0],'voz_posts':c.execute("select count(*) from items where source='voz'").fetchone()[0],'zhihu_items':c.execute("select count(*) from items where source='zhihu'").fetchone()[0],'chivi_taxonomy_items':c.execute("select count(*) from items where source='chivi'").fetchone()[0],'signal_edges':c.execute('select count(*) from signals').fetchone()[0],'book_mentions':c.execute('select count(*) from book_mentions').fetchone()[0],'fts_rows':c.execute('select count(*) from items_fts').fetchone()[0]}
 top_signals=[{'signal':r[0],'items':r[1],'score':r[2]} for r in c.execute('select signal,count(*),sum(score) from signals group by signal order by sum(score) desc')]
 source_rows=[dict(zip(['source','mode','status','notes','checked_at'],r)) for r in c.execute('select * from sources order by source')]
 c.execute('pragma optimize'); c.close(); manifest={'schema':'webnovel-intelligence-v1','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'policy':'metadata + compact excerpts + hashes + derived signals; no bulk full-text mirror','counts':counts,'collectors':res,'sources':source_rows,'top_signals':top_signals}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(manifest,ensure_ascii=False,indent=2))

def query(index,q,limit=20,source=''):
 c=sqlite3.connect(Path(index)/'webnovel_intelligence.sqlite'); c.row_factory=sqlite3.Row; terms=[x for x in re.findall(r'[0-9A-Za-zÀ-ỹĐđ\u4e00-\u9fff]+',q) if len(x)>1]; match=' OR '.join('"'+x.replace('"','')+'"' for x in terms[:20]); where=' AND i.source=?' if source else ''; params=[match]+([source] if source else [])
 rows=c.execute(f'''select i.*, -bm25(items_fts,3.0,1.0,1.3) score from items_fts join items i on i.id=items_fts.rowid where items_fts match ? {where} order by bm25(items_fts,3.0,1.0,1.3) limit ?''',params+[limit]).fetchall() if match else []; out=[]
 for r in rows:
  sig=[dict(x) for x in c.execute('select signal,score,sentiment from signals where item_id=? order by score desc',(r['id'],))]; bm=[x[0] for x in c.execute('select title from book_mentions where item_id=?',(r['id'],))]
  out.append({'score':r['score'],'source':r['source'],'type':r['item_type'],'title':r['title'],'author':r['author'],'date':r['published_at'],'category':r['category'],'excerpt':r['excerpt'],'url':r['url'],'signals':sig,'book_mentions':bm})
 print(json.dumps(out,ensure_ascii=False,indent=2)); c.close()

def stats(index): print((Path(index)/'manifest.json').read_text(encoding='utf-8'))
def main():
 ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True); b=sp.add_parser('build'); b.add_argument('--out',required=True); b.add_argument('--voz-start',type=int,default=1); b.add_argument('--voz-end',type=int,default=0); b.add_argument('--workers',type=int,default=3); b.add_argument('--moxing-pages',type=int,default=12); q=sp.add_parser('query'); q.add_argument('--index',required=True); q.add_argument('--q',required=True); q.add_argument('--limit',type=int,default=20); q.add_argument('--source',default=''); s=sp.add_parser('stats'); s.add_argument('--index',required=True); a=ap.parse_args()
 if a.cmd=='build':build(a.out,a.voz_start,a.voz_end,a.workers,a.moxing_pages)
 elif a.cmd=='query':query(a.index,a.q,a.limit,a.source)
 else:stats(a.index)
if __name__=='__main__':main()
