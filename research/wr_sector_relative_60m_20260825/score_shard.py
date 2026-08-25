#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

sys.path.insert(0, os.environ.get('WR_SECTOR_HELPER_DIR','/tmp/wrsector'))
import exp
_orig_resolve=exp.resolve_symbol
def _resolve(symbol):
    if symbol in {'XLC','XLRE'}: return f'{symbol}.US/USD'
    return _orig_resolve(symbol)
exp.resolve_symbol=_resolve
OUT=Path(os.environ.get('WR_SECTOR_OUT','/tmp/wr-sector')); OUT.mkdir(parents=True,exist_ok=True)
UNIVERSE='AAPL ADBE ADI ADP ADSK AEP ALNY AMAT AMD AMGN AMZN AVGO BKR CDNS CMCSA COST CPRT CSCO CSGP CSX CTSH DXCM EA EXC FANG FTNT GILD GOOG GOOGL HON IDXX INTC INTU ISRG KHC LRCX MAR MCHP MDLZ META MPWR MRVL MSFT MU NFLX NVDA ODFL ORLY PANW PAYX PCAR PEP PLTR PYPL QCOM REGN ROST SBUX SNPS TMUS TSLA TTWO TXN VRTX WDAY WDC WMT ZS'.split()
SECTOR={}
for sec,names in {
 'XLK':'AAPL ADBE ADI ADSK AMAT AMD AVGO CDNS CSCO CTSH FTNT INTC INTU LRCX MCHP MPWR MRVL MSFT MU NVDA PANW PLTR QCOM SNPS TXN WDAY WDC ZS'.split(),
 'XLC':'CMCSA EA GOOG GOOGL META NFLX TMUS TTWO'.split(),
 'XLY':'AMZN MAR ORLY ROST SBUX TSLA'.split(),
 'XLP':'COST KHC MDLZ PEP WMT'.split(),
 'XLE':'BKR FANG'.split(), 'XLF':'PYPL'.split(),
 'XLV':'ALNY AMGN DXCM GILD IDXX ISRG REGN VRTX'.split(),
 'XLI':'ADP CPRT CSX HON ODFL PAYX PCAR'.split(), 'XLU':'AEP EXC'.split(), 'XLRE':'CSGP'.split(),
}.items():
    for s in names: SECTOR[s]=sec
if set(SECTOR)!=set(UNIVERSE): raise RuntimeError('sector map mismatch')

def parent_trades():
    hits=list(Path('/tmp/parent').rglob('execution-trades.jsonl'))
    if len(hits)!=1: raise RuntimeError(f'parent artifact mismatch {hits}')
    out={s:[] for s in UNIVERSE}
    for line in hits[0].read_text().splitlines():
        if line.strip():
            x=json.loads(line); sym=x.get('_symbol') or x.get('symbol')
            if sym in out: out[sym].append(x)
    return out

def mid60(symbol,cache):
    if symbol in cache:return cache[symbol]
    raw,_,_=exp.load_mid(symbol,5)
    if raw is None or raw.empty: cache[symbol]=None; return None
    frame,_=exp.aggregate(raw,5,60)
    cache[symbol]=None if frame is None or frame.empty else frame[['open','high','low','close']].sort_index()
    return cache[symbol]

def context(stock,sec,spy):
    idx=stock.index.intersection(sec.index).intersection(spy.index); x=pd.DataFrame(index=idx)
    if not len(idx):return x
    x['ss']=stock.loc[idx,'close'].astype(float)/sec.loc[idx,'close'].astype(float)
    x['sm']=sec.loc[idx,'close'].astype(float)/spy.loc[idx,'close'].astype(float)
    x['ess']=x.ss.ewm(span=50,adjust=False,min_periods=50).mean(); x['esm']=x.sm.ewm(span=50,adjust=False,min_periods=50).mean()
    x['dss']=x.ess.diff(); x['dsm']=x.esm.diff(); return x

def score(row,sym,bench,ctx):
    o=dict(row); o.update(symbol=sym,sector_etf=bench,context_scoreable=False,sector_aligned=False)
    ts=pd.Timestamp(int(row['signal']),unit='ms',tz='UTC'); bo=ts-pd.Timedelta(minutes=60)
    o['signal_date_ny']=ts.tz_convert(ZoneInfo('America/New_York')).date().isoformat(); o['signal_bar_open']=bo.isoformat()
    if ctx is None or ctx.empty or bo not in ctx.index:return o
    z=ctx.loc[bo]
    if any(pd.isna(z[k]) for k in ('ss','sm','ess','esm','dss','dsm')):return o
    o['context_scoreable']=True
    side=str(row.get('side','')).upper()
    if side=='L': o['sector_aligned']=bool(z.ss>z.ess and z.dss>0 and z.sm>z.esm and z.dsm>0)
    elif side=='S': o['sector_aligned']=bool(z.ss<z.ess and z.dss<0 and z.sm<z.esm and z.dsm<0)
    else:o['context_scoreable']=False
    return o

def main():
    shard=int(os.environ.get('SHARD','0')); n=int(os.environ.get('SHARDS','8')); mine=[s for i,s in enumerate(UNIVERSE) if i%n==shard]
    parent=parent_trades(); cache={}; spy=mid60('SPY',cache); rows=[]; diag=[]
    for sym in mine:
        bench=SECTOR[sym]; st=mid60(sym,cache); sec=mid60(bench,cache); ctx=None if st is None or sec is None or spy is None else context(st,sec,spy)
        rr=[score(x,sym,bench,ctx) for x in parent[sym]]; rows.extend(rr)
        d={'symbol':sym,'benchmark':bench,'parent':len(parent[sym]),'scoreable':sum(x['context_scoreable'] for x in rr),'aligned':sum(x['sector_aligned'] for x in rr),'stock_data':st is not None,'bench_data':sec is not None,'spy_data':spy is not None};diag.append(d);print('SCORED',d,flush=True)
    with (OUT/f'scored-shard-{shard}.jsonl').open('w') as f:
        for x in rows:f.write(json.dumps(x,default=str)+'\n')
    (OUT/f'diagnostics-shard-{shard}.json').write_text(json.dumps(diag,indent=2))
if __name__=='__main__':main()
