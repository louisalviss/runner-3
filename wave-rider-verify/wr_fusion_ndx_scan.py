#!/usr/bin/env python3
from __future__ import annotations
import json, os, statistics, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import wr_dukascopy_expanded_matrix as exp

# Fusion officially states it offers all Nasdaq-100 equities. This list is a
# conservative guaranteed-core universe, not the full 110-symbol Fusion list.
# It intentionally includes both GOOG/GOOGL share classes. SNDK added in 2026.
NDX=[
'AAPL','ABNB','ADBE','ADI','ADP','ADSK','AEP','ALNY','AMAT','AMD','AMGN','AMZN','APP','ARM','ASML','AVGO','AXON','BKNG','BKR','CCEP','CDNS','CEG','CHTR','CMCSA','COST','CPRT','CRWD','CSCO','CSGP','CSX','CTAS','CTSH','DASH','DDOG','DXCM','EA','EXC','FANG','FAST','FER','FTNT','GEHC','GILD','GOOG','GOOGL','HON','IDXX','INSM','INTC','INTU','ISRG','KDP','KHC','KLAC','LIN','LRCX','MAR','MCHP','MDLZ','MELI','META','MNST','MPWR','MRVL','MSFT','MSTR','MU','NFLX','NVDA','NXPI','ODFL','ORLY','PANW','PAYX','PCAR','PDD','PEP','PLTR','PYPL','QCOM','REGN','ROP','ROST','SBUX','SHOP','SNDK','SNPS','STX','TMUS','TRI','TSLA','TTWO','TXN','VRSK','VRTX','WBD','WDAY','WDC','WMT','XEL','ZS']

OUT=Path(os.getenv('WR_OUT','/tmp/wr-fusion-ndx'));OUT.mkdir(parents=True,exist_ok=True)


def break_even_bps(trades):
    gross=sum(float(t['R']) for t in trades)
    slope=sum((float(t['e'])/abs(float(t['e'])-float(t['s'])))/10000.0 for t in trades if abs(float(t['e'])-float(t['s']))>0)
    return None if gross<=0 or slope<=0 else gross/slope


def pepperstone_commission_floor(trades):
    # Official US share CFD commission = $0.02/share/side, hence $0.04 round trip.
    vals=[]
    for t in trades:
        d=abs(float(t['e'])-float(t['s']))
        vals.append(float(t['R'])-(0.04/d if d>0 else 0.0))
    return {'n':len(vals),'net_R':sum(vals),'avg_R':statistics.mean(vals) if vals else None}


def enrich(symbol,tf):
    sp=OUT/f'summary-{symbol}-{tf}m.json'; tp=OUT/f'trades-{symbol}-{tf}m.jsonl'
    if not sp.exists(): return
    s=json.loads(sp.read_text())
    if s.get('status') not in ('OK','SHORT_HISTORY') or not tp.exists():
        s['fusion_core_universe']=True;s['pepperstone_commission_floor']=None;s['break_even_bps']=None
        sp.write_text(json.dumps(s,indent=2,default=str));return
    trades=[json.loads(x) for x in tp.read_text().splitlines() if x.strip()]
    s['fusion_core_universe']=True
    s['break_even_bps']=break_even_bps(trades)
    s['pepperstone_commission_floor']=pepperstone_commission_floor(trades)
    sp.write_text(json.dumps(s,indent=2,default=str))


def run_symbol(symbol):
    if symbol not in NDX: raise RuntimeError(f'not in NDX core: {symbol}')
    instrument=exp.resolve_symbol(symbol)
    if not instrument:
        for tf in (5,10): exp.save_unavailable(symbol,tf,'instrument not found')
        return
    df,manifest,_=exp.load_mid(symbol,5)
    for tf in (5,10):
        exp.run_one(symbol,tf,df,5,instrument,manifest)
        enrich(symbol,tf)

if __name__=='__main__':
    run_symbol(os.environ.get('SYMBOL') or sys.argv[1])
