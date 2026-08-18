import csv,glob,json,os,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

TF=int(os.environ.get('TF_MIN','3'))
BASE=Path(os.environ.get('BASE_DIR','/tmp/base'))
IN=Path(os.environ.get('IN_DIR','/tmp/all'))
OUT=Path(os.environ.get('OUT_DIR','/tmp/final')); OUT.mkdir(parents=True,exist_ok=True)
S=[];E=[]
for p in glob.glob(str(IN/'summary-*.json')):S+=json.load(open(p))
for p in glob.glob(str(IN/'errors-*.json')):E+=json.load(open(p))
S.sort(key=lambda x:x['symbol'])
tv=json.load(open(BASE/'tv_tick_map.json'));b5=json.load(open(BASE/'summary.json'))
tradfi={'BZUSDT','CLUSDT','DRAMUSDT','EWYUSDT','INTCUSDT','KORUUSDT','MRVLUSDT','MSTRUSDT','MUUSDT','SAMSUNGUSDT','SKHYNIXUSDT','SKHYUSDT','SNDKUSDT','SNXXUSDT','SOXLUSDT','SOXSUSDT','SPCXUSDT','XAGUSDT'}
base_syms={x['symbol'] for x in b5};U=sorted((base_syms&set(tv))-tradfi)
assert len(U)==654
Uset=set(U);b5=[x for x in b5 if x['symbol'] in Uset]
T=[]
with open(OUT/'trades.jsonl','w') as dst:
    for p in glob.glob(str(IN/'trades-*.jsonl')):
        for line in open(p):
            if line.strip():
                a=json.loads(line);T.append(a);dst.write(json.dumps(a,separators=(',',':'))+'\n')

def costs(trades):
    z={'n':len(trades),'gross_r':sum(x['R'] for x in trades)}
    for bps in (4,6,8,10):z[f'net_r_{bps}bps']=sum(x['R']-(x['entry']/abs(x['entry']-x['stop']))*bps/10000 for x in trades)
    z['avg_gross_r']=z['gross_r']/z['n'] if z['n'] else None
    z['avg_net6_r']=z['net_r_6bps']/z['n'] if z['n'] else None
    loss=sum(max(-x['R'],0) for x in trades);z['pf_gross']=sum(max(x['R'],0) for x in trades)/loss if loss else None
    stops=sorted(x['stop_pct'] for x in trades if x.get('stop_pct') is not None)
    if stops:
        z['median_stop_pct']=statistics.median(stops);z['p10_stop_pct']=stops[max(0,int(.10*(len(stops)-1)))];z['p90_stop_pct']=stops[int(.90*(len(stops)-1))]
    return z

def summary5(rows):
    z={'n':sum(x['n'] for x in rows),'gross_r':sum(x['total_r'] for x in rows)}
    for bps in (4,6,8,10):z[f'net_r_{bps}bps']=sum(x[f'net_r_{bps}bps'] for x in rows)
    z['avg_gross_r']=z['gross_r']/z['n'] if z['n'] else None;z['avg_net6_r']=z['net_r_6bps']/z['n'] if z['n'] else None
    return z

def period_key(ms,kind):
    d=datetime.fromtimestamp(ms/1000,tz=timezone.utc)
    return str(d.year) if kind=='year' else f'{d.year}Q{(d.month-1)//3+1}'
def grouped(trades,kind):
    g=defaultdict(list)
    for x in trades:g[period_key(x['signal_time'],kind)].append(x)
    return {k:costs(v) for k,v in sorted(g.items())}

rt=costs(T);r5=summary5(b5)
rt['symbols_completed']=len(S);rt['symbols_with_trades']=sum(x['n']>0 for x in S);rt['symbols_n_ge_100']=sum(x['n']>=100 for x in S);rt['symbols_net6_positive_n_ge_100']=sum(x['n']>=100 and x['net_r_6bps']>0 for x in S)
r5['symbols']=len(b5);r5['symbols_n_ge_100']=sum(x['n']>=100 for x in b5);r5['symbols_net6_positive_n_ge_100']=sum(x['n']>=100 and x['net_r_6bps']>0 for x in b5)
report={'status':f'PHASE1_{TF}M_COMPLETE','engine':'WR v2.5.15 deterministic','scope':'same 654 current-TV crypto symbols; no Zone/Day changes','coverage_signal':'2025-01-01 through 2026-08-14 UTC',f'tf_{TF}m':rt,'canonical_5m_same_universe':r5,f'delta_{TF}m_minus_5m':{k:rt[k]-r5[k] for k in ('n','gross_r','net_r_4bps','net_r_6bps','net_r_8bps','net_r_10bps')},f'{TF}m_by_year':grouped(T,'year'),f'{TF}m_by_quarter':grouped(T,'quarter'),f'{TF}m_by_side':{k:costs([x for x in T if x['side']==k]) for k in ('LONG','SHORT')},'errors':E}
json.dump(report,open(OUT/'phase1_report.json','w'),indent=2)
json.dump(S,open(OUT/'summary.json','w'),indent=2);json.dump(E,open(OUT/'errors.json','w'),indent=2);json.dump(U,open(OUT/'universe.json','w'),indent=2)
fields=['symbol','tf','bars','tick','n','total_r','avg_r','win_rate','pf','net_r_4bps','net_r_6bps','net_r_8bps','net_r_10bps']
with open(OUT/'summary.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r.get(k) for k in fields} for r in S)
print(json.dumps(report,indent=2))
