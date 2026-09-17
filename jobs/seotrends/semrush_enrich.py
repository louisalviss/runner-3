#!/usr/bin/env python3
import argparse, csv, io, json, math, os, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(os.environ.get('SEOTRENDS_PUBLIC_HOME', '/var/lib/seotrends-public'))
SCANS = BASE / 'scans'
CACHE = Path(os.environ.get('SEMRUSH_CACHE_HOME', '/var/lib/seotrends-semrush-cache'))
SCANS.mkdir(parents=True, exist_ok=True); CACHE.mkdir(parents=True, exist_ok=True)
UA = 'SeoTrendsSemrushEnricher/1.1'

p = argparse.ArgumentParser()
p.add_argument('--date')
p.add_argument('--database', default=os.environ.get('SEMRUSH_DATABASE', 'us'))
p.add_argument('--max', type=int, default=25)
a = p.parse_args()
day = a.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
queue_path = SCANS / f'{day}-semrush-queue.json'
status_path = SCANS / f'{day}-semrush-status.json'
out_jsonl = CACHE / f'{day}-semrush-enriched.jsonl'
out_md = CACHE / f'{day}-semrush-shortlist.md'
key = os.environ.get('SEMRUSH_API_KEY', '').strip()

# Semrush API usage restrictions state cached API information must not be kept >1 month
# without express written consent. Purge local API-derived files after 29 days.
cutoff = datetime.now(timezone.utc) - timedelta(days=29)
for q in CACHE.glob('*'):
    try:
        if datetime.fromtimestamp(q.stat().st_mtime, timezone.utc) < cutoff:
            q.unlink()
    except Exception:
        pass

if not queue_path.exists():
    status = {'ok': True, 'enabled': bool(key), 'date': day, 'database': a.database, 'queued': 0, 'enriched': 0, 'reason': 'queue_missing', 'cache_home': str(CACHE), 'retention_days': 29}
    status_path.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(status)); raise SystemExit(0)

queue = json.loads(queue_path.read_text(encoding='utf-8'))
items = list(queue.get('items') or [])[:max(0, a.max)]
if not key:
    status = {'ok': True, 'enabled': False, 'date': day, 'database': a.database, 'queued': len(items), 'enriched': 0, 'reason': 'SEMRUSH_API_KEY_missing', 'cache_home': str(CACHE), 'retention_days': 29}
    status_path.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(status)); raise SystemExit(0)

def domain_overview(domain):
    params = {'type':'domain_rank','key':key,'domain':domain,'database':a.database,'export_columns':'Dn,Rk,Or,Ot,Oc,Ad,At,Ac'}
    url = 'https://api.semrush.com/?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode('utf-8', 'replace').strip()
    if not text or text.startswith('ERROR '): return {'error': text or 'empty_response'}
    rows = list(csv.DictReader(io.StringIO(text), delimiter=';'))
    if not rows: return {'error': 'no_rows'}
    row = rows[0]
    def num(*names):
        for name in names:
            raw = row.get(name, '')
            try:
                if raw != '': return float(raw)
            except Exception: pass
        return 0.0
    return {'domain':row.get('Domain') or row.get('Dn') or domain,'rank':num('Rank','Rk'),'organic_keywords':num('Organic Keywords','Or'),'organic_traffic':num('Organic Traffic','Ot'),'organic_cost':num('Organic Cost','Oc'),'adwords_keywords':num('Adwords Keywords','Ad'),'adwords_traffic':num('Adwords Traffic','At'),'adwords_cost':num('Adwords Cost','Ac')}

def seo_score(m):
    if m.get('error'): return 0
    kw=max(0.0,m.get('organic_keywords',0.0)); tr=max(0.0,m.get('organic_traffic',0.0)); cost=max(0.0,m.get('organic_cost',0.0))
    return round(min(20.0,2.2*math.log10(1+kw)+2.8*math.log10(1+tr)+1.8*math.log10(1+cost)),2)

rows=[]
for item in items:
    d=item.get('domain','').strip()
    if not d: continue
    try: metrics=domain_overview(d)
    except Exception as e: metrics={'error':type(e).__name__}
    s=seo_score(metrics); row=dict(item)
    row['semrush_database']=a.database; row['semrush']=metrics; row['semrush_score']=s
    row['combined_score']=round(float(item.get('discovery_score',item.get('score',0)))+s,2)
    rows.append(row)
rows.sort(key=lambda x:(x.get('combined_score',0),x.get('semrush_score',0)),reverse=True)
with out_jsonl.open('w',encoding='utf-8') as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False)+'\n')
lines=[f'# SeoTrends + Semrush — {day}','',f'- database: {a.database}',f'- enriched: {len(rows)}','- Semrush source: official Domain Overview API','- local cache retention: 29 days; excluded from Telegram durable archive','']
for i,r in enumerate(rows[:15],1):
    m=r.get('semrush') or {}
    lines += [f'## {i}. {r.get("domain")} — combined {r.get("combined_score")}',f'- discovery score: {r.get("discovery_score",r.get("score",0))} | Semrush score: {r.get("semrush_score",0)}',f'- organic keywords: {int(m.get("organic_keywords",0) or 0):,} | traffic: {int(m.get("organic_traffic",0) or 0):,} | traffic cost: ${m.get("organic_cost",0) or 0:,.0f}',f'- title: {r.get("title") or "-"}','']
out_md.write_text('\n'.join(lines)+'\n',encoding='utf-8')
status={'ok':True,'enabled':True,'date':day,'database':a.database,'queued':len(items),'enriched':len(rows),'errors':sum(1 for r in rows if (r.get('semrush') or {}).get('error')),'cache_home':str(CACHE),'retention_days':29}
status_path.write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
print(json.dumps(status))
