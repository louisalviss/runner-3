#!/usr/bin/env python3
import argparse, csv, io, json, math, os, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(os.environ.get('SEOTRENDS_PUBLIC_HOME', '/var/lib/seotrends-public'))
SCANS = BASE / 'scans'
SCANS.mkdir(parents=True, exist_ok=True)
UA = 'SeoTrendsSemrushEnricher/1.0'

p = argparse.ArgumentParser()
p.add_argument('--date')
p.add_argument('--database', default=os.environ.get('SEMRUSH_DATABASE', 'us'))
p.add_argument('--max', type=int, default=25)
a = p.parse_args()
day = a.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
queue_path = SCANS / f'{day}-semrush-queue.json'
status_path = SCANS / f'{day}-semrush-status.json'
out_jsonl = SCANS / f'{day}-semrush-enriched.jsonl'
out_md = SCANS / f'{day}-semrush-shortlist.md'
key = os.environ.get('SEMRUSH_API_KEY', '').strip()

if not queue_path.exists():
    status = {'ok': True, 'enabled': bool(key), 'date': day, 'database': a.database, 'queued': 0, 'enriched': 0, 'reason': 'queue_missing'}
    status_path.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(status)); raise SystemExit(0)

queue = json.loads(queue_path.read_text(encoding='utf-8'))
items = list(queue.get('items') or [])[:max(0, a.max)]
if not key:
    status = {'ok': True, 'enabled': False, 'date': day, 'database': a.database, 'queued': len(items), 'enriched': 0, 'reason': 'SEMRUSH_API_KEY_missing'}
    status_path.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(status)); raise SystemExit(0)

def domain_overview(domain):
    params = {
        'type': 'domain_rank', 'key': key, 'domain': domain, 'database': a.database,
        'export_columns': 'Dn,Rk,Or,Ot,Oc,Ad,At,Ac'
    }
    url = 'https://api.semrush.com/?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode('utf-8', 'replace').strip()
    if not text or text.startswith('ERROR '):
        return {'error': text or 'empty_response'}
    rows = list(csv.DictReader(io.StringIO(text), delimiter=';'))
    if not rows:
        return {'error': 'no_rows'}
    row = rows[0]
    def num(name):
        raw = row.get(name, '')
        try: return float(raw)
        except Exception: return 0.0
    return {
        'domain': row.get('Domain') or row.get('Dn') or domain,
        'rank': num('Rank') or num('Rk'),
        'organic_keywords': num('Organic Keywords') or num('Or'),
        'organic_traffic': num('Organic Traffic') or num('Ot'),
        'organic_cost': num('Organic Cost') or num('Oc'),
        'adwords_keywords': num('Adwords Keywords') or num('Ad'),
        'adwords_traffic': num('Adwords Traffic') or num('At'),
        'adwords_cost': num('Adwords Cost') or num('Ac'),
    }

def seo_score(m):
    if m.get('error'): return 0
    kw = max(0.0, m.get('organic_keywords', 0.0)); tr = max(0.0, m.get('organic_traffic', 0.0)); cost = max(0.0, m.get('organic_cost', 0.0))
    return round(min(20.0, 2.2*math.log10(1+kw) + 2.8*math.log10(1+tr) + 1.8*math.log10(1+cost)), 2)

rows = []
for item in items:
    d = item.get('domain', '').strip()
    if not d: continue
    try: metrics = domain_overview(d)
    except Exception as e: metrics = {'error': type(e).__name__}
    s = seo_score(metrics)
    row = dict(item)
    row['semrush_database'] = a.database
    row['semrush'] = metrics
    row['semrush_score'] = s
    row['combined_score'] = round(float(item.get('discovery_score', item.get('score', 0))) + s, 2)
    rows.append(row)

rows.sort(key=lambda x: (x.get('combined_score', 0), x.get('semrush_score', 0)), reverse=True)
with out_jsonl.open('w', encoding='utf-8') as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + '\n')
lines = [f'# SeoTrends + Semrush — {day}', '', f'- database: {a.database}', f'- enriched: {len(rows)}', '- Semrush source: official Domain Overview API', '']
for i, r in enumerate(rows[:15], 1):
    m = r.get('semrush') or {}
    lines += [
        f'## {i}. {r.get("domain")} — combined {r.get("combined_score")}',
        f'- discovery score: {r.get("discovery_score", r.get("score", 0))} | Semrush score: {r.get("semrush_score", 0)}',
        f'- organic keywords: {int(m.get("organic_keywords",0) or 0):,} | traffic: {int(m.get("organic_traffic",0) or 0):,} | traffic cost: ${m.get("organic_cost",0) or 0:,.0f}',
        f'- title: {r.get("title") or "-"}', ''
    ]
out_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')
status = {'ok': True, 'enabled': True, 'date': day, 'database': a.database, 'queued': len(items), 'enriched': len(rows), 'errors': sum(1 for r in rows if (r.get('semrush') or {}).get('error'))}
status_path.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
print(json.dumps(status))
