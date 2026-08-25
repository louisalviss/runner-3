#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

sys.path.insert(0, os.environ.get('WR_SECTOR_HELPER_DIR','/tmp/wrsector'))
import exp
OUT=Path(os.environ.get('WR_SECTOR_OUT','/tmp/wr-sector')); OUT.mkdir(parents=True,exist_ok=True)
SECTORS={
 'TECH':'AAPL ADBE ADI ADSK AMAT AMD AVGO CDNS CSCO CTSH FTNT INTC INTU LRCX MCHP MPWR MRVL MSFT MU NVDA PANW PLTR QCOM SNPS TXN WDAY WDC ZS'.split(),
 'COMM':'CMCSA EA GOOG GOOGL META NFLX TMUS TTWO'.split(),
 'DISC':'AMZN MAR ORLY ROST SBUX TSLA'.split(),
 'STAPLES':'COST KHC MDLZ PEP WMT'.split(),
 'ENERGY':'BKR FANG'.split(),
 'HEALTH':'ALNY AMGN DXCM GILD IDXX ISRG REGN VRTX'.split(),
 'INDUSTRIALS':'ADP CPRT CSX HON ODFL PAYX PCAR'.split(),
 'UTILITIES':'AEP EXC'.split(),
}
ELIGIBLE={s for xs in SECTORS.values() for s in xs}

def parent_rows():
    hits=list(Path('/tmp/parent').rglob('execution-trades.jsonl'))
    if len(hits)!=1: raise RuntimeError(f'parent artifact mismatch {hits}')
    out={s:[] for s in ELIGIBLE}
    for line in hits[0].read_text().splitlines():
        if not line.strip():continue
        x=json.loads(line);sym=x.get('_symbol') or x.get('symbol')
        if sym in out:out[sym].append(x)
    return out

def mid60(symbol,cache):
    if symbol in cache:return cache[symbol]
    raw,_,_=exp.load_mid(symbol,5)
    if raw is None or raw.empty:cache[symbol]=None;return None
    frame,_=exp.aggregate(raw,5,60)
    cache[symbol]=None if frame is None or frame.empty else frame[['close']].sort_index()
    return cache[symbol]

def build_sector(members,cache):
    frames={s:mid60(s,cache) for s in members};spy=mid60('SPY',cache)
    if spy is None or any(v is None for v in frames.values()):return None,None
    idx=spy.index
    for v in frames.values():idx=idx.intersection(v.index)
    if len(idx)<60:return None,None
    closes=pd.DataFrame({s:frames[s].loc[idx,'close'].astype(float) for s in members},index=idx)
    spy_close=spy.loc[idx,'close'].astype(float)
    rets=closes.pct_change();full_ret=rets.mean(axis=1,skipna=False)
    full_idx=(1.0+full_ret.fillna(0.0)).cumprod();spy_idx=spy_close/float(spy_close.iloc[0])
    contexts={}
    for sym in members:
        peers=[s for s in members if s!=sym]
        loo_ret=rets[peers].mean(axis=1,skipna=False)
        loo_idx=(1.0+loo_ret.fillna(0.0)).cumprod();stock_idx=closes[sym]/float(closes[sym].iloc[0])
        x=pd.DataFrame(index=idx);x['ss']=stock_idx/loo_idx;x['sm']=full_idx/spy_idx
        x['ess']=x.ss.ewm(span=50,adjust=False,min_periods=50).mean();x['esm']=x.sm.ewm(span=50,adjust=False,min_periods=50).mean();x['dss']=x.ess.diff();x['dsm']=x.esm.diff();contexts[sym]=x
    return contexts,idx

def score(row,sym,sector,ctx):
    o=dict(row);o.update(symbol=sym,sector=sector,context_scoreable=False,sector_aligned=False)
    ts=pd.Timestamp(int(row['signal']),unit='ms',tz='UTC');bo=ts-pd.Timedelta(minutes=60);o['signal_date_ny']=ts.tz_convert(ZoneInfo('America/New_York')).date().isoformat();o['signal_bar_open']=bo.isoformat()
    if ctx is None or bo not in ctx.index:return o
    z=ctx.loc[bo]
    if any(pd.isna(z[k]) for k in ('ss','sm','ess','esm','dss','dsm')):return o
    o['context_scoreable']=True;side=str(row.get('side','')).upper()
    if side=='L':o['sector_aligned']=bool(z.ss>z.ess and z.dss>0 and z.sm>z.esm and z.dsm>0)
    elif side=='S':o['sector_aligned']=bool(z.ss<z.ess and z.dss<0 and z.sm<z.esm and z.dsm<0)
    else:o['context_scoreable']=False
    return o

def main():
    key=os.environ['SECTOR_KEY'];members=SECTORS[key];parent=parent_rows();cache={};contexts,idx=build_sector(members,cache);rows=[];diag=[]
    for sym in members:
        ctx=None if contexts is None else contexts[sym];rr=[score(x,sym,key,ctx) for x in parent[sym]];rows.extend(rr)
        d={'sector':key,'symbol':sym,'parent':len(parent[sym]),'scoreable':sum(x['context_scoreable'] for x in rr),'aligned':sum(x['sector_aligned'] for x in rr),'context_rows':0 if ctx is None else len(ctx)};diag.append(d);print('SCORED',d,flush=True)
    with (OUT/f'scored-{key}.jsonl').open('w') as f:
        for x in rows:f.write(json.dumps(x,default=str)+'\n')
    (OUT/f'diagnostics-{key}.json').write_text(json.dumps(diag,indent=2))
if __name__=='__main__':main()
