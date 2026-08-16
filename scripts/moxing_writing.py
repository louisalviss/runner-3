#!/usr/bin/env python3
import argparse,collections,concurrent.futures,hashlib,json,re,sqlite3,time
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://www.mx-xz.com'
LIST_BASE=BASE+'/sf-jq/all/'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36 runner-3/moxing-writing/1.0'

TOPICS={
 'hook_opening':['开头','开篇','黄金三章','第一章','切入'],
 'plot_structure':['情节','剧情','主线','故事线','结构','故事结构'],
 'outline':['大纲','细纲','纲要','框架'],
 'pacing_tension':['节奏','张力','拖沓','紧凑','高潮'],
 'character_design':['人物','主角','人设','性格','角色','配角'],
 'motivation_conflict':['目标','动机','欲望','矛盾','冲突'],
 'progression_power':['升级','修炼','境界','金手指','能力','实力'],
 'reward_payoff':['爽点','打脸','装逼','收获','机缘','奖励','期待感'],
 'worldbuilding':['世界观','世界背景','设定','背景设定','势力'],
 'foreshadow_mystery':['悬念','伏笔','铺垫','谜团','揭秘'],
 'dialogue_voice':['对话','对白','台词','说话'],
 'description_scene':['描写','场景','环境','动作描写','心理描写'],
 'romance_relationship':['感情','爱情','恋爱','女主','男主','关系'],
 'style_prose':['文笔','文风','文字','叙述','语言'],
 'market_retention':['追读','读者','留存','点击','订阅','签约','市场','卖点'],
 'title_blurb_packaging':['书名','简介','封面','包装','标题'],
 'pitfalls_editing':['避坑','错误','新人','常见问题','修改','自检'],
 'genre_pattern':['玄幻','仙侠','都市','悬疑','科幻','历史','言情','无限流','网文类型'],
 'serialization':['章节','更新','连载','断章','章末'],
 'craft_general':['写作技巧','写作方法','技巧','方法','创作技巧'],
}
QUERY_ALIASES={
 'mở đầu':'开头 开篇 黄金三章','hook':'开头 开篇','cốt truyện':'情节 剧情 主线','plot':'情节 剧情',
 'đại cương':'大纲 框架','outline':'大纲','nhịp':'节奏 张力','pacing':'节奏 张力','nhân vật':'人物 主角 人设 性格',
 'main':'主角 人设','động cơ':'目标 动机 欲望','xung đột':'矛盾 冲突','progression':'升级 修炼 境界 金手指',
 'tu luyện':'修炼 境界 升级','sảng':'爽点 打脸 装逼 期待感','payoff':'爽点 收获 奖励','worldbuilding':'世界观 背景设定',
 'thế giới':'世界观 背景设定','foreshadow':'伏笔 铺垫 悬念','thoại':'对话 台词','dialogue':'对话 台词',
 'miêu tả':'描写 场景','romance':'感情 爱情 恋爱','văn phong':'文笔 文风 叙述','độc giả':'读者 追读 留存',
 'retention':'追读 留存 订阅','tên truyện':'书名','giới thiệu':'简介','tránh lỗi':'避坑 错误 自检','thể loại':'玄幻 仙侠 都市 悬疑 科幻 历史',
}
DIRECT_NEG=['不要','不能','不该','不应','避免','切忌','忌讳','不宜','千万不要','尽量不要']
DIRECT_POS=['应该','应当','必须','需要','建议','最好','尽量','可以','要做到','关键是','核心是','注意','务必']
TECH=['方法','技巧','步骤','做法','方式','原则','套路','要点','秘诀']


def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def session():
 s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept-Language':'zh-CN,zh;q=0.9'}); return s

def get(s,url,tries=4):
 last=None
 for i in range(tries):
  try:
   r=s.get(url,timeout=30,allow_redirects=True)
   if r.status_code==200: return r
   last=RuntimeError(f'HTTP {r.status_code}')
  except Exception as e: last=e
  time.sleep(0.7*(i+1))
 raise last

def topic_scores(text):
 out=[]
 for topic,keys in TOPICS.items():
  hit=[k for k in keys if k in text]
  if hit: out.append((topic,len(hit),hit))
 return sorted(out,key=lambda x:(-x[1],x[0]))

def kind(text):
 if any(x in text for x in DIRECT_NEG): return 'dont',0.94
 if any(x in text for x in DIRECT_POS): return 'do',0.88
 if any(x in text for x in TECH): return 'technique',0.72
 return 'principle',0.56

def split_sentences(text):
 text=clean(text)
 parts=re.split(r'(?<=[。！？!?；;])\s*|\n+',text)
 return [clean(x) for x in parts if 12<=len(clean(x))<=420]

def parse_listing(html,page):
 s=BeautifulSoup(html,'lxml'); rows={}
 for a in s.find_all('a',href=True):
  href=urljoin(BASE,a['href']); p=urlparse(href).path
  if not re.fullmatch(r'/show_\d+\.html',p): continue
  txt=clean(a.get_text(' ',strip=True))
  if not txt: continue
  m=re.search(r'(\d+)人气',txt); pop=int(m.group(1)) if m else None
  rows[href]={'url':href,'listing_page':page,'listing_text':txt[:900],'listing_popularity':pop}
 return list(rows.values())

def crawl_inventory(max_pages=55):
 s=session(); rows={}; failures=[]
 for page in range(1,max_pages+1):
  url=LIST_BASE if page==1 else f'{LIST_BASE}{page}/'
  try:
   r=get(s,url); got=parse_listing(r.text,page)
   for x in got: rows[x['url']]=x
   print(f'listing {page}/{max_pages}: {len(got)} items; unique={len(rows)}',flush=True)
  except Exception as e:
   failures.append({'page':page,'url':url,'error':f'{type(e).__name__}:{e}'})
  time.sleep(0.12)
 return sorted(rows.values(),key=lambda x:int(re.search(r'(\d+)',x['url']).group(1))),failures

def article_parse(row):
 s=session(); r=get(s,row['url']); soup=BeautifulSoup(r.text,'lxml')
 art=soup.select_one('article.content_show'); body=soup.select_one('#sdcms_content')
 if not body: raise RuntimeError('missing #sdcms_content')
 h1=(art.select_one('h1') if art else soup.find('h1'))
 title=clean(h1.get_text(' ',strip=True)) if h1 else clean((soup.title.get_text(' ',strip=True) if soup.title else '').split(' - ')[0])
 full=clean(body.get_text('\n',strip=True)); full_sha=hashlib.sha256(full.encode()).hexdigest()
 useful=None
 if art:
  t=clean(art.get_text(' ',strip=True)); m=re.search(r'对\s*(\d+)\s*个作者有用',t); useful=int(m.group(1)) if m else None
 # Prefer paragraph/list-level actionable snippets; fall back to sentence-level principles.
 cand=[]; seen=set()
 for node in body.find_all(['h2','h3','p','li']):
  txt=clean(node.get_text(' ',strip=True))
  for sent in split_sentences(txt):
   if sent in seen: continue
   seen.add(sent); ts=topic_scores(sent+' '+title)
   if not ts: continue
   k,conf=kind(sent)
   actionable=k!='principle' or ts[0][1]>=2 or node.name in ('h2','h3')
   if not actionable: continue
   topic,score,matches=ts[0]
   cand.append({'topic':topic,'topic_score':score,'topic_matches':matches,'kind':k,'confidence':round(min(.98,conf+.04*min(score,3)),3),'text':sent[:420],'sentence_sha':hashlib.sha256(sent.encode()).hexdigest(),'node':node.name})
 # rank: directives, topic specificity, concise passages; cap to avoid mirroring articles.
 pri={'dont':4,'do':4,'technique':3,'principle':1}
 cand.sort(key=lambda x:(-pri[x['kind']],-x['topic_score'],-x['confidence'],len(x['text'])))
 per_topic=collections.Counter(); kept=[]
 for x in cand:
  if per_topic[x['topic']]>=8: continue
  per_topic[x['topic']]+=1; kept.append(x)
  if len(kept)>=36: break
 return {**row,'title':title,'useful_count':useful,'content_chars':len(full),'content_sha256':full_sha,'passages':kept}

def build(outdir,max_pages=55,workers=8):
 out=Path(outdir); out.mkdir(parents=True,exist_ok=True)
 inv,failures=crawl_inventory(max_pages)
 (out/'inventory.json').write_text(json.dumps({'schema':'moxing-writing-inventory-v1','pages':max_pages,'urls':len(inv),'failures':failures,'rows':inv},ensure_ascii=False,indent=2),encoding='utf-8')
 results=[]; failed=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  fut={ex.submit(article_parse,row):row for row in inv}
  for n,f in enumerate(concurrent.futures.as_completed(fut),1):
   row=fut[f]
   try: results.append(f.result())
   except Exception as e: failed.append({'url':row['url'],'error':f'{type(e).__name__}:{e}'})
   if n%50==0 or n==len(inv): print(f'articles {n}/{len(inv)} ok={len(results)} fail={len(failed)}',flush=True)
 # SQLite derived knowledge layer only, not full source prose.
 db=out/'moxing_writing.sqlite'; db.unlink(missing_ok=True); con=sqlite3.connect(db)
 con.executescript("""
 CREATE TABLE articles(id INTEGER PRIMARY KEY,url TEXT UNIQUE,title TEXT,listing_page INT,listing_popularity INT,useful_count INT,content_chars INT,content_sha256 TEXT);
 CREATE TABLE passages(id INTEGER PRIMARY KEY,article_id INT,topic TEXT,kind TEXT,confidence REAL,text TEXT,sentence_sha TEXT,node TEXT,UNIQUE(article_id,sentence_sha));
 CREATE VIRTUAL TABLE passage_fts USING fts5(title,topic,kind,text,content='',tokenize='unicode61');
 CREATE INDEX idx_pass_topic ON passages(topic,confidence DESC);
 """)
 for a in sorted(results,key=lambda x:x['url']):
  aid=con.execute('INSERT INTO articles(url,title,listing_page,listing_popularity,useful_count,content_chars,content_sha256) VALUES(?,?,?,?,?,?,?)',(a['url'],a['title'],a['listing_page'],a.get('listing_popularity'),a.get('useful_count'),a['content_chars'],a['content_sha256'])).lastrowid
  for p in a['passages']:
   pid=con.execute('INSERT OR IGNORE INTO passages(article_id,topic,kind,confidence,text,sentence_sha,node) VALUES(?,?,?,?,?,?,?)',(aid,p['topic'],p['kind'],p['confidence'],p['text'],p['sentence_sha'],p['node'])).lastrowid
   if pid: con.execute('INSERT INTO passage_fts(rowid,title,topic,kind,text) VALUES(?,?,?,?,?)',(pid,a['title'],p['topic'],p['kind'],p['text']))
 con.commit(); con.execute('PRAGMA optimize')
 counts={'listing_pages':max_pages,'inventory_urls':len(inv),'listing_failures':len(failures),'articles_ok':len(results),'articles_failed':len(failed),'passages':con.execute('select count(*) from passages').fetchone()[0],'directive_passages':con.execute("select count(*) from passages where kind in ('do','dont','technique')").fetchone()[0],'topics':con.execute('select count(distinct topic) from passages').fetchone()[0]}
 topic_counts=[{'topic':r[0],'passages':r[1]} for r in con.execute('select topic,count(*) from passages group by topic order by count(*) desc')]
 con.close()
 (out/'failed.json').write_text(json.dumps(failed,ensure_ascii=False,indent=2),encoding='utf-8')
 manifest={'schema':'moxing-writing-knowledge-v1','source':'https://www.mx-xz.com/sf-jq/','source_scope':'手法技巧 / writing craft','storage_policy':'derived metadata + capped actionable passages; full article prose is not mirrored','robots_checked':True,'counts':counts,'topic_counts':topic_counts,'query_aliases':'Vietnamese/English query aliases expanded to Chinese craft terms','limitations':['Moxing states materials may be member uploads or reposts from the internet; source attribution belongs to each page.','Passage labels are heuristic craft classifications, not authoritative facts.']}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(manifest,ensure_ascii=False,indent=2))

def expand_query(q):
 extra=[]; low=q.lower()
 for k,v in QUERY_ALIASES.items():
  if k in low: extra.append(v)
 return clean(q+' '+' '.join(extra))

def query(index,q,limit=12,topic=None):
 con=sqlite3.connect(Path(index)/'moxing_writing.sqlite'); con.row_factory=sqlite3.Row
 eq=expand_query(q); terms=[x for x in re.split(r'\s+',eq) if x][:24]; fts=' OR '.join('"'+x.replace('"','')+'"' for x in terms)
 params=[fts]; filt=''
 if topic: filt=' AND p.topic=?'; params.append(topic)
 rows=con.execute(f'''SELECT p.id,p.topic,p.kind,p.confidence,p.text,p.sentence_sha,a.title,a.url,a.useful_count,a.listing_popularity,-bm25(passage_fts,2.0,1.2,0.8,2.5) score FROM passage_fts JOIN passages p ON p.id=passage_fts.rowid JOIN articles a ON a.id=p.article_id WHERE passage_fts MATCH ? {filt} ORDER BY bm25(passage_fts,2.0,1.2,0.8,2.5),p.confidence DESC LIMIT ?''',params+[limit]).fetchall()
 out=[dict(r) for r in rows]; con.close(); return {'schema':'moxing-writing-query-v1','query':q,'expanded_query':eq,'topic_filter':topic,'hits':out}

def main():
 ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
 b=sp.add_parser('build'); b.add_argument('--out',required=True); b.add_argument('--pages',type=int,default=55); b.add_argument('--workers',type=int,default=8)
 q=sp.add_parser('query'); q.add_argument('--index',required=True); q.add_argument('--q',required=True); q.add_argument('--limit',type=int,default=12); q.add_argument('--topic',choices=sorted(TOPICS)); q.add_argument('--json-out')
 a=ap.parse_args()
 if a.cmd=='build': build(a.out,a.pages,a.workers)
 else:
  x=query(a.index,a.q,a.limit,a.topic); raw=json.dumps(x,ensure_ascii=False,indent=2); print(raw)
  if a.json_out: Path(a.json_out).write_text(raw,encoding='utf-8')
if __name__=='__main__': main()
