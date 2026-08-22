#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import wr_dukascopy_expanded_matrix as exp

OUT=Path(os.getenv('WR_OUT','/tmp/wr-market-exec')); OUT.mkdir(parents=True,exist_ok=True)
FEATURES=['atr_bps','atr_ratio_14_50','range_atr','body_atr','gap_atr','rv20_bps','trend20_atr','efficiency20','location20','session_frac','tf10']

def rma(s,n): return s.ewm(alpha=1.0/n,adjust=False,min_periods=n).mean()

def feature_frame(df,tf,tz='America/New_York'):
    x=df.copy();pc=x['close'].shift(1)
    tr=pd.concat([(x['high']-x['low']).abs(),(x['high']-pc).abs(),(x['low']-pc).abs()],axis=1).max(axis=1)
    atr14=rma(tr,14);atr50=rma(tr,50);ret=np.log(x['close']).diff();move=(x['close']-x['close'].shift(20)).abs();path=x['close'].diff().abs().rolling(20,min_periods=20).sum()
    hi=x['high'].rolling(20,min_periods=20).max();lo=x['low'].rolling(20,min_periods=20).min();span=hi-lo;local=x.index.tz_convert(tz);minute=local.hour*60+local.minute
    f=pd.DataFrame(index=x.index);f['atr_bps']=atr14/x.close*10000;f['atr_ratio_14_50']=atr14/atr50;f['range_atr']=(x.high-x.low)/atr14;f['body_atr']=(x.close-x.open).abs()/atr14;f['gap_atr']=(x.open-pc).abs()/atr14;f['rv20_bps']=ret.rolling(20,min_periods=20).std()*10000;f['trend20_atr']=move/atr14;f['efficiency20']=move/path.replace(0,np.nan);f['location20']=(x.close-lo)/span.replace(0,np.nan);f['session_frac']=np.clip((minute-570)/390.0,0,1);f['tf10']=1.0 if tf==10 else 0.0
    return f

def load_bid_ask(symbol):
    instrument=exp.resolve_symbol(symbol)
    if not instrument:return None,None,None,[]
    bid=exp.pick_const(('OFFER_SIDE_BID','PRICE_TYPE_BID','BID'));ask=exp.pick_const(('OFFER_SIDE_ASK','PRICE_TYPE_ASK','ASK'))
    bids=[];asks=[];manifest=[]
    for a,b in exp.month_chunks(exp.STATE_START,exp.END):
        try:
            db=exp.fetch_side(instrument,bid,a,b,5);da=exp.fetch_side(instrument,ask,a,b,5);idx=db.index.intersection(da.index)
            if len(idx):bids.append(db.loc[idx]);asks.append(da.loc[idx])
            manifest.append({'month':a.strftime('%Y-%m'),'rows':int(len(idx))})
        except Exception as e:manifest.append({'month':a.strftime('%Y-%m'),'error':repr(e)})
    if not bids:return None,None,instrument,manifest
    bd=pd.concat(bids).sort_index();ad=pd.concat(asks).sort_index();idx=bd.index.intersection(ad.index);bd=bd.loc[idx];ad=ad.loc[idx]
    bd=bd[~bd.index.duplicated(keep='last')];ad=ad[~ad.index.duplicated(keep='last')];idx=bd.index.intersection(ad.index);return bd.loc[idx],ad.loc[idx],instrument,manifest

def spread_bps(bid,ask,ts,field='open'):
    if ts not in bid.index or ts not in ask.index:return None
    bv=float(bid.at[ts,field]);av=float(ask.at[ts,field]);mid=(av+bv)/2
    return None if mid<=0 else (av-bv)/mid*10000

def cost_ratio(t):
    d=abs(float(t['e'])-float(t['s']));return None if d<=0 else float(t['e'])/d

def canonical_mid(bid5,ask5,tf):
    idx=bid5.index.intersection(ask5.index)
    mid5=(bid5.loc[idx,['open','high','low','close']]+ask5.loc[idx,['open','high','low','close']])/2.0
    if tf==5:return mid5
    mid,reject=exp.aggregate(mid5,5,tf)
    print('STRICT_AGG',tf,'rejected',reject,flush=True)
    return mid

def run_tf(symbol,tf,bid5,ask5,instrument,manifest):
    # Exact OOS parity requires midpoint at 5m first, then strict complete-bucket aggregation.
    mid=canonical_mid(bid5,ask5,tf)
    base,ref=exp.load_modules(tf);group,tick,tz,session=exp.cfg(symbol);base.tv_tick=lambda _i,_v:tick
    bars=exp.to_bars(mid,base.Bar,tf);trades,_=base.run_case(ref,bars,exp.provider_info(symbol),exp.STATE_START.to_pydatetime(),anchor='start',use_session=True);ff=feature_frame(mid,tf,tz)
    n=0;missing=0;path=OUT/f'exec-{symbol}-{tf}m.jsonl'
    with path.open('w') as fh:
        for t in trades:
            sig=pd.Timestamp(int(t['signal']),unit='ms',tz='UTC')
            # Signal timestamp is the signal candle close; mid/ff index is candle open.
            # Only the just-closed signal candle is causally valid for state features.
            fbar=sig-pd.Timedelta(minutes=tf)
            if not fbar < sig:
                raise AssertionError(f'non-causal feature timestamp {symbol} {tf}m row={fbar} signal={sig}')
            if fbar not in ff.index:
                missing+=1;continue
            fts=ff.loc[fbar];fts=fts.iloc[-1] if isinstance(fts,pd.DataFrame) else fts
            if not fts[FEATURES].notna().all():
                missing+=1;continue
            # Stop-entry begins on the next target-TF bar, at timestamp == signal close.
            ent_ts=sig
            exit_close=pd.Timestamp(int(t['exit']),unit='ms',tz='UTC')
            # Target-TF close is the close of its final 5m constituent bar.
            exit_quote_ts=exit_close-pd.Timedelta(minutes=5)
            ent_sp=spread_bps(bid5,ask5,ent_ts,'open');ex_sp=spread_bps(bid5,ask5,exit_quote_ts,'close')
            ratio=cost_ratio(t)
            rec={'symbol':symbol,'tf':tf,'signal':int(t['signal']),'exit':int(t['exit']),'side':t.get('side'),'R':float(t['R']),'reason':t.get('reason'),'e':float(t['e']),'s':float(t['s']),'ratio':ratio,'entry_spread_bps':ent_sp,'exit_spread_bps':ex_sp,'year':sig.year,'feature_bar':fbar.isoformat(),'feature_lag_minutes':tf}
            rec['observed_roundtrip_spread_bps']=None if ent_sp is None or ex_sp is None else (ent_sp+ex_sp)/2.0
            rec['net_1bps']=float(t['R'])-(ratio or 0)*1/10000;rec['net_2bps']=float(t['R'])-(ratio or 0)*2/10000
            for k in FEATURES:rec[k]=float(fts[k])
            fh.write(json.dumps(rec)+'\n');n+=1
    print('EXEC_ROWS',symbol,tf,n,'MISSING_SIGNAL_BAR_FEATURES',missing,flush=True)

def main():
    symbol=os.environ.get('SYMBOL') or sys.argv[1];bid,ask,instrument,manifest=load_bid_ask(symbol)
    if bid is None:
        (OUT/f'unavailable-{symbol}.json').write_text(json.dumps({'symbol':symbol,'status':'UNAVAILABLE','manifest':manifest},indent=2));return
    for tf in (5,10):run_tf(symbol,tf,bid,ask,instrument,manifest)
if __name__=='__main__':main()
