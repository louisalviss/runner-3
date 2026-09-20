#!/usr/bin/env python3
import argparse, concurrent.futures, csv, html, json, os, re, sqlite3, subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(os.environ.get('SEOTRENDS_PUBLIC_HOME', '/var/lib/seotrends-public'))
DATA, CHANGES, SCANS = BASE/'data', BASE/'changes', BASE/'scans'
SCANS.mkdir(parents=True, exist_ok=True)
UA='Mozilla/5.0 SeoTrendsPublicScanner/1.3'

class HeadMetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title=False
        self.title_parts=[]
        self.description=''
    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag=='title':
            self.in_title=True
        elif tag=='meta' and not self.description:
            d={str(k).lower(): (v or '') for k,v in attrs}
            if str(d.get('name','')).lower()=='description':
                self.description=str(d.get('content',''))
    def handle_endtag(self, tag):
        if tag.lower()=='title':
            self.in_title=False
    def handle_data(self, data):
        if self.in_title and len(self.title_parts)<16:
            self.title_parts.append(data)

GOOD={'ai':3,'saas':4,'software':3,'tool':3,'tools':3,'app':2,'api':2,'automation':3,'analytics':3,'seo':3,'generator':2,'editor':2,'converter':2,'calculator':2,'transcription':3,'image':2,'video':2,'data':2,'shop':1,'store':1,'travel':1,'affiliate':2,'viewer':2,'resize':2,'screen':1,'rss':2,'compare':2,'checker':2,'lookup':2,'tracker':2,'validator':2,'compress':2,'pdf':1,'qr':1,'monitor':1}
MONEY={'pricing':3,'subscription':3,'subscribe':2,'plans':2,'trial':2,'pro':1,'business':1,'enterprise':2,'buy':1,'checkout':1}
RISK={'crack':-8,'torrent':-8,'casino':-7,'gambling':-7,'betting':-7,'porn':-9,'xxx':-9,'free spins':-7,'downloader':-3,'youtube downloader':-5,'tiktok downloader':-5,'soundcloud downloader':-5,'mod apk':-8,'hack':-5}
PREFERRED_TLDS={'.com':2,'.ai':2,'.io':1,'.app':1,'.co':1,'.net':0}

p=argparse.ArgumentParser()
p.add_argument('--date')
p.add_argument('--max',type=int,default=300)
p.add_argument('--workers',type=int,default=16)
p.add_argument('--timeout',type=int,default=5)
a=p.parse_args()
day=a.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')

def load_domains():
    added=CHANGES/f'{day}-added.txt'
    vals=[x.strip() for x in added.read_text(encoding='utf-8').splitlines() if x.strip()] if added.exists() else []
    return vals[:a.max]

def fetch_site(domain):
    out={'domain':domain,'ok':False,'status':None,'final_url':'','title':'','description':'','error':''}
    for scheme in ('https://','http://'):
        url=scheme+domain
        try:
            cp=subprocess.run(['curl','-L','-sS','--compressed','--connect-timeout','2','--max-time',str(a.timeout),'--max-filesize','256000','--range','0-255999','-A',UA,'-o','-','-w','\n__META__%{http_code}\t%{url_effective}',url],capture_output=True,timeout=a.timeout+2)
            raw=cp.stdout.decode('utf-8','ignore')
            marker='\n__META__'; pos=raw.rfind(marker)
            meta=raw[pos+len(marker):].strip() if pos>=0 else ''
            body=raw[:pos] if pos>=0 else raw
            parts=meta.split('\t',1)
            code=int(parts[0]) if parts and parts[0].isdigit() else 0
            final=parts[1] if len(parts)>1 else url
            if code<200 or code>=400:
                out['error']=f'HTTP_{code or "ERR"}'
                continue
            out['status']=code; out['final_url']=final
            parser=HeadMetaParser()
            try: parser.feed(body[:131072])
            except Exception: pass
            title=' '.join(parser.title_parts)
            if title: out['title']=html.unescape(re.sub(r'\s+',' ',title).strip())[:300]
            if parser.description: out['description']=html.unescape(re.sub(r'\s+',' ',parser.description).strip())[:500]
            out['ok']=True
            break
        except subprocess.TimeoutExpired:
            out['error']='TIMEOUT'
        except Exception as e:
            out['error']=type(e).__name__
    return out

def present(k,text):
    return re.search(r'(?<![a-z0-9])'+re.escape(k)+r'(?![a-z0-9])',text) is not None

def score(row):
    text=' '.join([row['domain'].replace('.',' '),row.get('title',''),row.get('description','')]).lower()
    s=2 if row.get('ok') else -4
    signals=[]; risks=[]
    for k,v in GOOD.items():
        if present(k,text): s+=v; signals.append(k)
    for k,v in MONEY.items():
        if present(k,text): s+=v; signals.append(k)
    for k,v in RISK.items():
        if present(k,text): s+=v; risks.append(k)
    for t,v in PREFERRED_TLDS.items():
        if row['domain'].endswith(t): s+=v; break
    label=row['domain'].split('.')[0]
    if len(label)<=12: s+=1
    if '-' in label: s-=1
    if len(label)>24: s-=1
    row['score']=s; row['signals']=sorted(set(signals)); row['risk_flags']=sorted(set(risks))
    return row

domains=load_domains(); rows=[]
if domains:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(a.workers,32))) as ex:
        rows=[score(r) for r in ex.map(fetch_site,domains)]
rows.sort(key=lambda r:(r['score'],r['ok'],r['domain']),reverse=True)
jsonl=SCANS/f'{day}-candidates.jsonl'; csvp=SCANS/f'{day}-candidates.csv'; md=SCANS/f'{day}-shortlist.md'; semq=SCANS/f'{day}-semrush-queue.json'
with jsonl.open('w',encoding='utf-8') as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False)+'\n')
with csvp.open('w',encoding='utf-8',newline='') as f:
    cols=['domain','score','ok','status','final_url','title','description','signals','risk_flags','error']
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
    for r in rows:
        x=dict(r); x['signals']='|'.join(r['signals']); x['risk_flags']='|'.join(r['risk_flags'])
        w.writerow({k:x.get(k,'') for k in cols})
short=[r for r in rows if r['score']>=7 and r['signals'] and not r['risk_flags']][:25]
lines=[f'# SeoTrends daily shortlist — {day}','',f'- mode: added-only',f'- scanned: {len(rows)}',f'- shortlist: {len(short)}','- source: public sitemap diff + public target websites','- no paywalled SeoTrends data used','']
for i,r in enumerate(short,1):
    lines += [f'## {i}. {r["domain"]} — score {r["score"]}',f'- {r["title"] or "(no title)"}',f'- signals: {", ".join(r["signals"][:8]) or "-"}',f'- url: {r.get("final_url") or "-"}','']
md.write_text('\n'.join(lines)+'\n',encoding='utf-8')
queue={'date':day,'source':'seotrends-public-daily','count':len(short),'items':[{'domain':r['domain'],'discovery_score':r['score'],'title':r.get('title',''),'description':r.get('description',''),'signals':r.get('signals',[]),'url':r.get('final_url','')} for r in short]}
semq.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'ok':True,'date':day,'mode':'added-only','scanned':len(rows),'shortlist':len(short),'jsonl':str(jsonl),'csv':str(csvp),'md':str(md),'semrush_queue':str(semq)},ensure_ascii=False))
