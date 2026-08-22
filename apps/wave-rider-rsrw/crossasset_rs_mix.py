#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

HELPER = Path(os.getenv('WR_CROSSASSET_HELPER','/tmp/crossasset'))
sys.path.insert(0, str(HELPER))
import wr_dukascopy_expanded_matrix as exp

OUT = Path(os.getenv('WR_RS_GROUP_OUT','/tmp/wr-rs-groups')); OUT.mkdir(parents=True, exist_ok=True)
SRC = Path(os.getenv('WR_RS_SOURCE_ROOT','/tmp/source'))
EMA_LEN = int(os.getenv('WR_RS_EMA','50'))
SHARD = int(os.getenv('WR_RS_SHARD','0')); SHARDS = int(os.getenv('WR_RS_SHARDS','1'))
FX = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','USDCHF','NZDUSD','EURJPY','GBPJPY','EURGBP']
METALS = ['XAUUSD','XAGUSD']
INDICES = ['US500','NAS100']


def read_trades(symbol: str, tf: int = 5):
    pats = list(SRC.rglob(f'trades-{symbol}-{tf}m.jsonl'))
    if not pats:
        return []
    out=[]
    for ln in pats[0].read_text().splitlines():
        if ln.strip():
            try: out.append(json.loads(ln))
            except Exception: pass
    return out


def cost_r(t, bps):
    d=abs(float(t['e'])-float(t['s']))
    return 0.0 if d<=0 else (float(t['e'])/d)*(bps/10000.0)


def met(trades, bps=0.0):
    a=[float(t['R'])-cost_r(t,bps) for t in trades]
    if not a: return {'n':0,'R':0.0,'avg_R':None,'PF':None,'win_rate':None,'max_DD_R':0.0}
    gp=sum(max(x,0) for x in a); gl=sum(max(-x,0) for x in a)
    eq=peak=0.0; mdd=0.0
    for x in a:
        eq+=x; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return {'n':len(a),'R':sum(a),'avg_R':sum(a)/len(a),'PF':gp/gl if gl else None,
            'win_rate':100*sum(x>0 for x in a)/len(a),'max_DD_R':mdd}


def year_metrics(trades, bps=0.0):
    z={}
    for y in range(2022,2027):
        q=[t for t in trades if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y]
        z[str(y)]=met(q,bps)
    return z


def load_mid(symbol):
    df,manifest,instrument=exp.load_mid(symbol,5)
    if df is None or df.empty: raise RuntimeError(f'no midpoint data {symbol}')
    return df[['close']].copy(), manifest, instrument


def gate_from_ratio(ratio: pd.Series):
    ratio=ratio.replace([np.inf,-np.inf],np.nan).dropna().sort_index()
    ema=ratio.ewm(span=EMA_LEN,adjust=False).mean()
    return (ratio>ema)&(ema>ema.shift(1))


def signal_bar_ts(t):
    return pd.Timestamp(int(t['signal']),unit='ms',tz='UTC')-pd.Timedelta(minutes=5)


def apply_long_gate(trades, gate: pd.Series):
    keep=[]; long_base=[]; long_keep=[]; missing_long=0; matched_long=0
    for t in trades:
        side=str(t.get('side','')).upper()
        if side in ('S','SHORT'):
            keep.append(t); continue
        long_base.append(t)
        ts=signal_bar_ts(t)
        if ts not in gate.index or pd.isna(gate.loc[ts]):
            missing_long+=1; continue
        matched_long+=1
        if bool(gate.loc[ts]):
            keep.append(t); long_keep.append(t)
    return keep, {'long_base_n':len(long_base),'long_retained_n':len(long_keep),
                  'long_match_n':matched_long,'long_missing_n':missing_long,
                  'long_retention_pct':100*len(long_keep)/len(long_base) if long_base else None}


def summarize_symbol(group,symbol,trades,filtered,diag,benchmark):
    base0=met(trades,0); rs0=met(filtered,0)
    return {'group':group,'symbol':symbol,'tf':'5m','ema':EMA_LEN,'mode':'WR_PLUS_RS_LONG_ONLY',
            'benchmark':benchmark,'rule':'LONG WR signal requires RS > EMA(RS) and EMA slope up; SHORT WR unchanged',
            'base':{'gross':base0,'net_0.5bps':met(trades,.5),'net_1bps':met(trades,1.0),'years_gross':year_metrics(trades,0)},
            'rs':{'gross':rs0,'net_0.5bps':met(filtered,.5),'net_1bps':met(filtered,1.0),'years_gross':year_metrics(filtered,0)},
            'delta':{'n':rs0['n']-base0['n'],'R':rs0['R']-base0['R'],
                     'avg_R':None if base0['avg_R'] is None or rs0['avg_R'] is None else rs0['avg_R']-base0['avg_R'],
                     'net_0.5bps_R':met(filtered,.5)['R']-met(trades,.5)['R'],
                     'net_1bps_R':met(filtered,1.0)['R']-met(trades,1.0)['R']},
            'diagnostics':diag}


def aggregate(rows):
    def flatten(which):
        ts=[]
        for r in rows:
            sym=r['symbol']; trades=read_trades(sym,5)
            if which=='base': ts.extend(trades)
            else:
                ids={(int(x[0]),str(x[1])) for x in r['_retained_signals']}
                ts.extend([t for t in trades if (int(t['signal']),str(t.get('side'))) in ids])
        return ts
    b=flatten('base'); q=flatten('rs')
    return {'symbols':len(rows),'base':{'gross':met(b,0),'net_0.5bps':met(b,.5),'net_1bps':met(b,1),'years_gross':year_metrics(b,0)},
            'rs':{'gross':met(q,0),'net_0.5bps':met(q,.5),'net_1bps':met(q,1),'years_gross':year_metrics(q,0)},
            'delta':{'n':len(q)-len(b),'R':met(q,0)['R']-met(b,0)['R'],
                     'net_0.5bps_R':met(q,.5)['R']-met(b,.5)['R'],'net_1bps_R':met(q,1)['R']-met(b,1)['R']}}


def save_group(group, rows, extra=None):
    clean=[]
    for r in rows:
        z=dict(r); z.pop('_retained_signals',None); clean.append(z)
    report={'status':'COMPLETE','group':group,'strategy':'Frozen WR 2.5.13 trade artifact + transferred RS EMA50 confirmation',
            'tf':'5m','ema':EMA_LEN,'mode':'WR_PLUS_RS_LONG_ONLY','no_alpha_tuning':True,
            'aggregate':aggregate(rows),'symbols':clean}
    if extra: report.update(extra)
    (OUT/f'{group.lower()}-rs-mix.json').write_text(json.dumps(report,indent=2,default=str))
    print(group, json.dumps(report['aggregate']))


def run_fx():
    closes={s:load_mid(s)[0]['close'] for s in FX}
    rets={s:np.log(c).diff() for s,c in closes.items()}
    currencies=sorted(set(x[:3] for x in FX)|set(x[3:] for x in FX))
    strength={}
    for ccy in currencies:
        parts=[]
        for s,r in rets.items():
            if s[:3]==ccy: parts.append(r.rename(s))
            elif s[3:]==ccy: parts.append((-r).rename(s))
        strength[ccy]=pd.concat(parts,axis=1).mean(axis=1,skipna=True).fillna(0).cumsum()
    rows=[]
    for s in FX:
        tr=read_trades(s,5)
        if not tr: continue
        logrs=(strength[s[:3]]-strength[s[3:]]).dropna()
        ratio=np.exp(logrs-logrs.iloc[0])
        gate=gate_from_ratio(ratio)
        f,d=apply_long_gate(tr,gate)
        row=summarize_symbol('FX',s,tr,f,d,'10-pair currency-strength basket')
        row['_retained_signals']=[(int(t['signal']),str(t.get('side'))) for t in f]; rows.append(row)
    save_group('FX',rows,{'benchmark_method':'Base-vs-quote currency strength derived from signed 5m log returns across the frozen 10-pair FX universe.'})


def run_pair_group(group, syms):
    closes={s:load_mid(s)[0]['close'] for s in syms}
    rows=[]
    for s in syms:
        other=next(x for x in syms if x!=s)
        idx=closes[s].index.intersection(closes[other].index)
        ratio=(closes[s].loc[idx]/closes[other].loc[idx]).dropna()
        gate=gate_from_ratio(ratio)
        tr=read_trades(s,5)
        if not tr: continue
        f,d=apply_long_gate(tr,gate)
        row=summarize_symbol(group,s,tr,f,d,other)
        row['_retained_signals']=[(int(t['signal']),str(t.get('side'))) for t in f]; rows.append(row)
    save_group(group,rows)


def stock_symbols():
    out=[]
    for p in SRC.rglob('trades-*-5m.jsonl'):
        name=p.name
        if not name.startswith('trades-') or not name.endswith('-5m.jsonl'): continue
        s=name[len('trades-'):-len('-5m.jsonl')]
        if s not in FX+METALS+INDICES: out.append(s)
    return sorted(set(out))


def run_stock_shard():
    bench=load_mid('US500')[0]['close']
    rows=[]
    syms=[s for i,s in enumerate(stock_symbols()) if i%SHARDS==SHARD]
    for s in syms:
        tr=read_trades(s,5)
        if not tr: continue
        try: c=load_mid(s)[0]['close']
        except Exception as e:
            rows.append({'group':'STOCK','symbol':s,'status':'UNAVAILABLE','error':repr(e)}); continue
        idx=c.index.intersection(bench.index); ratio=(c.loc[idx]/bench.loc[idx]).dropna(); gate=gate_from_ratio(ratio)
        f,d=apply_long_gate(tr,gate)
        row=summarize_symbol('STOCK',s,tr,f,d,'US500')
        row['_retained_signals']=[(int(t['signal']),str(t.get('side'))) for t in f]; rows.append(row)
    (OUT/f'stock-shard-{SHARD}.json').write_text(json.dumps({'shard':SHARD,'rows':rows},indent=2,default=str))
    print('STOCK_SHARD',SHARD,'symbols',len(rows))


def merge_stock():
    root=Path(os.getenv('WR_RS_MERGE_ROOT','/tmp/all')); rows=[]
    for p in root.rglob('stock-shard-*.json'):
        x=json.loads(p.read_text()); rows.extend([r for r in x.get('rows',[]) if r.get('status')!='UNAVAILABLE'])
    save_group('STOCK',rows,{'benchmark_method':'Each stock / US500 midpoint ratio; frozen EMA50 transferred from crypto RS-only candidate.'})


def main():
    mode=(sys.argv[1] if len(sys.argv)>1 else '').lower()
    if mode=='fx': run_fx()
    elif mode=='metal': run_pair_group('METAL',METALS)
    elif mode=='index': run_pair_group('INDEX',INDICES)
    elif mode=='stock-shard': run_stock_shard()
    elif mode=='stock-merge': merge_stock()
    else: raise SystemExit('mode: fx|metal|index|stock-shard|stock-merge')

if __name__=='__main__': main()
