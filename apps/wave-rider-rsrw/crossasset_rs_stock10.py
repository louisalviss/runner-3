#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

HELPER=Path(os.getenv('WR_CROSSASSET_HELPER','/tmp/crossasset'))
sys.path.insert(0,str(HELPER))
import wr_dukascopy_expanded_matrix as exp

SRC=Path(os.getenv('WR_RS_SOURCE_ROOT','/tmp/source'))
OUT=Path(os.getenv('WR_RS_OUT','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)
TF=10; EMA_LEN=50
SHARD=int(os.getenv('WR_RS_SHARD','0')); SHARDS=int(os.getenv('WR_RS_SHARDS','8'))
COSTS=(0.0,0.25,0.5,1.0,2.0)


def read_trades(symbol):
    pats=list(SRC.rglob(f'trades-{symbol}-{TF}m.jsonl'))
    if not pats: return []
    out=[]
    for ln in pats[0].read_text().splitlines():
        if ln.strip():
            try: out.append(json.loads(ln))
            except Exception: pass
    return out


def side(t):
    s=str(t.get('side','')).upper()
    return 'SHORT' if s in ('S','SHORT') else 'LONG'


def cost_r(t,bps):
    d=abs(float(t['e'])-float(t['s']))
    return 0.0 if d<=0 else (float(t['e'])/d)*(bps/10000.0)


def met(trades,bps=0.0):
    a=[float(t['R'])-cost_r(t,bps) for t in trades]
    if not a:
        return {'n':0,'R':0.0,'avg_R':None,'PF':None,'win_rate':None,'max_DD_R':0.0}
    gp=sum(max(x,0.0) for x in a); gl=sum(max(-x,0.0) for x in a)
    eq=peak=0.0; mdd=0.0
    for x in a:
        eq+=x; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return {'n':len(a),'R':sum(a),'avg_R':sum(a)/len(a),'PF':gp/gl if gl else None,
            'win_rate':100.0*sum(x>0 for x in a)/len(a),'max_DD_R':mdd}


def pack(trades):
    return {f'{bps:g}bps':met(trades,bps) for bps in COSTS}


def by_year(trades):
    z={}
    for y in range(2022,2027):
        q=[t for t in trades if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y]
        z[str(y)]=met(q,0.0)
    return z


def load_close(symbol):
    df,manifest,instrument=exp.load_mid(symbol,TF)
    if df is None or df.empty: raise RuntimeError(f'no midpoint data {symbol}')
    return df['close'].copy()


def gate_from_ratio(ratio):
    ratio=ratio.replace([np.inf,-np.inf],np.nan).dropna().sort_index()
    ema=ratio.ewm(span=EMA_LEN,adjust=False).mean()
    return (ratio>ema)&(ema>ema.shift(1))


def signal_bar_ts(t):
    return pd.Timestamp(int(t['signal']),unit='ms',tz='UTC')-pd.Timedelta(minutes=TF)


def apply_gate(trades,gate):
    keep=[]; removed=[]; matched=missing=0
    for t in trades:
        if side(t)=='SHORT':
            keep.append(t); continue
        ts=signal_bar_ts(t)
        if ts not in gate.index or pd.isna(gate.loc[ts]):
            missing+=1; removed.append(t); continue
        matched+=1
        if bool(gate.loc[ts]): keep.append(t)
        else: removed.append(t)
    return keep,removed,matched,missing


def symbols():
    out=[]
    for p in SRC.rglob(f'trades-*-{TF}m.jsonl'):
        n=p.name
        s=n[len('trades-'):-len(f'-{TF}m.jsonl')]
        if s!='US500': out.append(s)
    return sorted(set(out))


def row_metrics(sym,base,rs,removed,matched,missing):
    bl=[t for t in base if side(t)=='LONG']; bs=[t for t in base if side(t)=='SHORT']
    rl=[t for t in rs if side(t)=='LONG']; rs_short=[t for t in rs if side(t)=='SHORT']
    return {
      'symbol':sym,'tf':'10m','benchmark':'US500','ema':50,'mode':'WR_PLUS_RS_LONG_ONLY',
      'base':pack(base),'filtered':pack(rs),'delta_gross_R':met(rs)['R']-met(base)['R'],
      'long':{'base':pack(bl),'filtered':pack(rl),'removed':pack(removed),
              'retention_pct':100*len(rl)/len(bl) if bl else None,'matched':matched,'missing':missing},
      'short':{'base':pack(bs),'filtered':pack(rs_short)},
      'years':{'base':by_year(base),'filtered':by_year(rs)}
    }


def run_shard():
    bench=load_close('US500')
    syms=[s for i,s in enumerate(symbols()) if i%SHARDS==SHARD]
    rows=[]; base_all=[]; rs_all=[]; removed_all=[]; unavailable=[]
    for sym in syms:
        base=read_trades(sym)
        if not base: continue
        try: c=load_close(sym)
        except Exception as e:
            unavailable.append({'symbol':sym,'error':repr(e)}); continue
        idx=c.index.intersection(bench.index)
        ratio=(c.loc[idx]/bench.loc[idx]).dropna()
        filt,removed,matched,missing=apply_gate(base,gate_from_ratio(ratio))
        rows.append(row_metrics(sym,base,filt,removed,matched,missing))
        base_all.extend(base); rs_all.extend(filt); removed_all.extend(removed)
        print(sym,'base',len(base),'rs',len(filt),'deltaR',round(met(filt)['R']-met(base)['R'],4))
    payload={'shard':SHARD,'rows':rows,'base_trades':base_all,'filtered_trades':rs_all,
             'removed_longs':removed_all,'unavailable':unavailable}
    (OUT/f'shard-{SHARD}.json').write_text(json.dumps(payload))
    print('SHARD',SHARD,'symbols',len(rows),'base',len(base_all),'filtered',len(rs_all),'unavailable',len(unavailable))


def aggregate_report(base,rs,removed,rows,unavailable):
    key=lambda t:(int(t.get('signal',0)),str(t.get('symbol','')),side(t))
    base=sorted(base,key=key); rs=sorted(rs,key=key); removed=sorted(removed,key=key)
    bl=[t for t in base if side(t)=='LONG']; bs=[t for t in base if side(t)=='SHORT']
    rl=[t for t in rs if side(t)=='LONG']; rss=[t for t in rs if side(t)=='SHORT']
    improved=sum(1 for r in rows if r['delta_gross_R']>0)
    worsened=sum(1 for r in rows if r['delta_gross_R']<0)
    unchanged=len(rows)-improved-worsened
    return {
      'status':'COMPLETE','strategy':'Frozen WR 2.5.13 10m trades + transferred Stock/US500 RS EMA50 long-only confirmation',
      'source_wr_run':32507430808,'source_universe':'Fusion/Nasdaq-100 available stock cases','tf':'10m','ema':50,
      'rule':'LONG WR signal requires Stock/US500 > EMA50(Stock/US500) and EMA50 slope up at causal signal bar; SHORT unchanged',
      'causal_timestamp_rule':'RS feature bar = signal close timestamp - 10m',
      'no_alpha_tuning':True,
      'aggregate':{
        'base':pack(base),'filtered':pack(rs),
        'delta':{f'{bps:g}bps_R':met(rs,bps)['R']-met(base,bps)['R'] for bps in COSTS},
        'long':{'base':pack(bl),'filtered':pack(rl),'removed':pack(removed),
                'retention_pct':100*len(rl)/len(bl) if bl else None},
        'short':{'base':pack(bs),'filtered':pack(rss)},
        'years':{'base':by_year(base),'filtered':by_year(rs)},
        'symbol_dispersion':{'symbols':len(rows),'improved':improved,'worsened':worsened,'unchanged':unchanged},
        'unavailable':unavailable
      },
      'symbols':rows
    }


def merge():
    root=Path(os.getenv('WR_RS_MERGE_ROOT','/tmp/all'))
    rows=[]; base=[]; rs=[]; removed=[]; unavailable=[]; shards=[]
    for p in sorted(root.rglob('shard-*.json')):
        x=json.loads(p.read_text()); shards.append(x['shard']); rows.extend(x['rows'])
        base.extend(x['base_trades']); rs.extend(x['filtered_trades']); removed.extend(x['removed_longs']); unavailable.extend(x['unavailable'])
    if sorted(shards)!=list(range(SHARDS)):
        raise RuntimeError(f'missing shards: got {sorted(shards)}')
    report=aggregate_report(base,rs,removed,rows,unavailable)
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    a=report['aggregate']
    print('FINAL base',a['base']['0bps'])
    print('FINAL filtered',a['filtered']['0bps'])
    print('FINAL removed_longs',a['long']['removed']['0bps'])
    print('FINAL dispersion',a['symbol_dispersion'])


def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'shard'
    if mode=='shard': run_shard()
    elif mode=='merge': merge()
    else: raise SystemExit('mode shard|merge')

if __name__=='__main__': main()
