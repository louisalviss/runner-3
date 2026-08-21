#!/usr/bin/env python3
# Retrigger clean WR Market State OOS run after repository ownership repair.
from __future__ import annotations
import json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import wr_dukascopy_expanded_matrix as exp

OUT=Path(os.getenv('WR_OUT','/tmp/wr-market-state'));OUT.mkdir(parents=True,exist_ok=True)
FEATURES=['atr_bps','atr_ratio_14_50','range_atr','body_atr','gap_atr','rv20_bps','trend20_atr','efficiency20','location20','session_frac','tf10']

def rma(s,n):
    return s.ewm(alpha=1.0/n,adjust=False,min_periods=n).mean()

def feature_frame(df,tf,tz='America/New_York'):
    x=df.copy()
    pc=x['close'].shift(1)
    tr=pd.concat([(x['high']-x['low']).abs(),(x['high']-pc).abs(),(x['low']-pc).abs()],axis=1).max(axis=1)
    atr14=rma(tr,14); atr50=rma(tr,50)
    ret=np.log(x['close']).diff()
    move=(x['close']-x['close'].shift(20)).abs()
    path=x['close'].diff().abs().rolling(20,min_periods=20).sum()
    hi20=x['high'].rolling(20,min_periods=20).max(); lo20=x['low'].rolling(20,min_periods=20).min(); span=(hi20-lo20)
    loc=(x['close']-lo20)/span.replace(0,np.nan)
    local=x.index.tz_convert(tz)
    minute=local.hour*60+local.minute
    session_frac=np.clip((minute-(9*60+30))/390.0,0,1)
    f=pd.DataFrame(index=x.index)
    f['atr_bps']=atr14/x['close']*10000.0
    f['atr_ratio_14_50']=atr14/atr50
    f['range_atr']=(x['high']-x['low'])/atr14
    f['body_atr']=(x['close']-x['open']).abs()/atr14
    f['gap_atr']=(x['open']-pc).abs()/atr14
    f['rv20_bps']=ret.rolling(20,min_periods=20).std()*10000.0
    f['trend20_atr']=move/atr14
    f['efficiency20']=move/path.replace(0,np.nan)
    f['location20']=loc
    f['session_frac']=session_frac
    f['tf10']=1.0 if tf==10 else 0.0
    return f

def cost_r(t,bps):
    d=abs(float(t['e'])-float(t['s']))
    return 0.0 if d<=0 else (float(t['e'])/d)*(bps/10000.0)

def run_tf(symbol,tf,raw_df,instrument,manifest):
    if raw_df is None or raw_df.empty:return 0
    df,reject=exp.aggregate(raw_df,5,tf)
    if df.empty:return 0
    base,ref=exp.load_modules(tf); group,tick,tz,session=exp.cfg(symbol); base.tv_tick=lambda _i,_v:tick
    bars=exp.to_bars(df,base.Bar,tf)
    trades,_raw=base.run_case(ref,bars,exp.provider_info(symbol),exp.STATE_START.to_pydatetime(),anchor='start',use_session=True)
    ff=feature_frame(df,tf,tz)
    n=0
    with (OUT/f'features-{symbol}-{tf}m.jsonl').open('w') as fh:
        for t in trades:
            sig=pd.Timestamp(int(t['signal']),unit='ms',tz='UTC')
            candidates=[sig, sig-pd.Timedelta(minutes=tf)]
            row=None;fts=None
            for ts in candidates:
                if ts in ff.index:
                    rr=ff.loc[ts]
                    if isinstance(rr,pd.DataFrame):rr=rr.iloc[-1]
                    if rr[FEATURES].notna().all(): row=ts;fts=rr;break
            if fts is None:continue
            rec={'symbol':symbol,'tf':tf,'signal':int(t['signal']),'exit':int(t['exit']),'R':float(t['R']),
                 'net_1bps':float(t['R'])-cost_r(t,1.0),'net_2bps':float(t['R'])-cost_r(t,2.0),
                 'year':sig.year,'feature_bar':row.isoformat()}
            for k in FEATURES:rec[k]=float(fts[k])
            fh.write(json.dumps(rec)+'\n');n+=1
    print('FEATURES',symbol,tf,n,flush=True);return n

def run_symbol(symbol):
    instrument=exp.resolve_symbol(symbol)
    if not instrument:
        print('UNAVAILABLE',symbol,flush=True);return
    df,m,_=exp.load_mid(symbol,5)
    for tf in (5,10):run_tf(symbol,tf,df,instrument,m)

if __name__=='__main__':
    run_symbol(os.environ.get('SYMBOL') or sys.argv[1])
