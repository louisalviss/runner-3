#!/usr/bin/env python3
import argparse, json, math, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE='https://api.binance.com/api/v3/klines'


def ms(s):
    return int(pd.Timestamp(s, tz='UTC').timestamp()*1000)


def fetch_klines(symbol, interval, start, end):
    out=[]; cur=ms(start); end_ms=ms(end)
    sess=requests.Session(); sess.headers.update({'User-Agent':'runner3-rsi-st-test/1.0'})
    while cur < end_ms:
        r=sess.get(BASE, params={'symbol':symbol,'interval':interval,'startTime':cur,'endTime':end_ms,'limit':1000}, timeout=30)
        r.raise_for_status(); rows=r.json()
        if not rows: break
        out.extend(rows)
        nxt=int(rows[-1][0])+1
        if nxt<=cur: break
        cur=nxt
        time.sleep(0.05)
    if not out: return pd.DataFrame()
    cols=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_base','taker_quote','ignore']
    df=pd.DataFrame(out,columns=cols).drop_duplicates('open_time').sort_values('open_time')
    for c in ['open','high','low','close','volume']: df[c]=pd.to_numeric(df[c],errors='coerce')
    df['dt']=pd.to_datetime(df.open_time,unit='ms',utc=True)
    return df.reset_index(drop=True)


def rma(values, n):
    a=np.asarray(values,dtype=float); out=np.full(len(a),np.nan)
    valid=[]
    for i,x in enumerate(a):
        if np.isfinite(x): valid.append(i)
        if len(valid)==n:
            seed_i=i; seed=np.nanmean(a[valid[-n:]])
            out[seed_i]=seed
            prev=seed
            for j in range(seed_i+1,len(a)):
                x=a[j]
                if np.isfinite(x): prev=(prev*(n-1)+x)/n
                out[j]=prev
            break
    return out


def indicators(df, rsi_len=10, sig_len=10, atr_len=10, factor=2.5):
    c=df.close.to_numpy(); h=df.high.to_numpy(); l=df.low.to_numpy()
    change=np.r_[np.nan,np.diff(c)]
    up=rma(np.where(np.isnan(change),np.nan,np.maximum(change,0)),rsi_len)
    down=rma(np.where(np.isnan(change),np.nan,np.maximum(-change,0)),rsi_len)
    rsi=np.where(down==0,100,np.where(up==0,0,100-(100/(1+up/down))))
    sig=pd.Series(rsi).rolling(sig_len,min_periods=sig_len).mean().to_numpy()
    bull=np.zeros(len(df),dtype=bool)
    bull[1:]=(rsi[1:]>sig[1:]) & (rsi[:-1]<=sig[:-1]) & np.isfinite(rsi[1:]) & np.isfinite(sig[1:]) & np.isfinite(rsi[:-1]) & np.isfinite(sig[:-1])
    special=np.zeros(len(df),dtype=bool); count=0
    for i in range(len(df)):
        if np.isfinite(rsi[i]) and rsi[i]>50: count=0
        if bull[i] and rsi[i]<50: count+=1
        if bull[i] and rsi[i]<50 and count==2:
            special[i]=True; count=0

    prev_c=np.r_[np.nan,c[:-1]]
    tr=np.nanmax(np.vstack([h-l, np.abs(h-prev_c), np.abs(l-prev_c)]),axis=0)
    tr[0]=h[0]-l[0]
    atr=rma(tr,atr_len)
    hl2=(h+l)/2
    upper=hl2+factor*atr; lower=hl2-factor*atr
    f_upper=np.full(len(df),np.nan); f_lower=np.full(len(df),np.nan); direction=np.full(len(df),np.nan); st=np.full(len(df),np.nan)
    for i in range(len(df)):
        if not np.isfinite(atr[i]): continue
        if i==0 or not np.isfinite(f_upper[i-1]):
            f_upper[i]=upper[i]; f_lower[i]=lower[i]; direction[i]=1; st[i]=f_upper[i]; continue
        pl=f_lower[i-1]; pu=f_upper[i-1]
        f_lower[i]=lower[i] if (lower[i]>pl or c[i-1]<pl) else pl
        f_upper[i]=upper[i] if (upper[i]<pu or c[i-1]>pu) else pu
        if not np.isfinite(atr[i-1]): direction[i]=1
        elif np.isclose(st[i-1],pu,rtol=1e-10,atol=1e-12): direction[i]=-1 if c[i]>f_upper[i] else 1
        else: direction[i]=1 if c[i]<f_lower[i] else -1
        st[i]=f_lower[i] if direction[i]==-1 else f_upper[i]
    sell=np.zeros(len(df),dtype=bool)
    sell[1:]=np.isfinite(direction[1:]) & np.isfinite(direction[:-1]) & ((direction[1:]-direction[:-1])>0)
    return rsi,sig,special,sell,direction


def run_bt(df,cost_bps_side=0,start_filter=None):
    if start_filter is not None: df=df[df.dt>=pd.Timestamp(start_filter,tz='UTC')].reset_index(drop=True)
    if len(df)<100: return None
    rsi,sig,buy,sell,direction=indicators(df)
    initial=10000.0; cash=initial; qty=0.0; entry_px=None; entry_equity=None; entry_i=None; trades=[]; curve=[]; inbars=0
    cost=cost_bps_side/10000.0
    pending_entry=False; pending_exit=False
    for i,row in df.iterrows():
        o=float(row.open); c=float(row.close)
        # Execute prior-bar close signals at this bar open. Exit first.
        if pending_exit and qty>0:
            px=o*(1-cost); proceeds=qty*px; pnl=proceeds-cash_at_entry
            ret=proceeds/entry_equity-1
            cash=proceeds; trades.append({'entry_i':entry_i,'exit_i':i,'entry':entry_px,'exit':px,'pnl':pnl,'ret':ret})
            qty=0; entry_px=None; entry_equity=None; entry_i=None
        if pending_entry and qty==0:
            entry_equity=cash; px=o*(1+cost); qty=cash/px; cash_at_entry=cash; entry_px=px; entry_i=i
        pending_entry=bool(buy[i]); pending_exit=bool(sell[i])
        equity=cash if qty==0 else qty*c
        if qty>0: inbars+=1
        curve.append(equity)
    if qty>0:
        px=float(df.iloc[-1].close)*(1-cost); proceeds=qty*px; pnl=proceeds-cash_at_entry; ret=proceeds/entry_equity-1
        trades.append({'entry_i':entry_i,'exit_i':len(df)-1,'entry':entry_px,'exit':px,'pnl':pnl,'ret':ret}); cash=proceeds; qty=0
        curve[-1]=cash
    arr=np.asarray(curve,float); peak=np.maximum.accumulate(arr); dd=(arr/peak)-1
    wins=[t for t in trades if t['pnl']>0]; losses=[t for t in trades if t['pnl']<0]
    gp=sum(t['pnl'] for t in wins); gl=-sum(t['pnl'] for t in losses)
    pf=(gp/gl) if gl>0 else (float('inf') if gp>0 else float('nan'))
    bh=float(df.iloc[-1].close/df.iloc[0].open-1)
    total=cash/initial-1
    return {
      'start':str(df.iloc[0].dt),'end':str(df.iloc[-1].dt),'bars':len(df),'trades':len(trades),
      'win_rate_pct':100*len(wins)/len(trades) if trades else 0,'profit_factor':pf,
      'total_return_pct':100*total,'max_dd_pct':100*float(dd.min()),'buy_hold_pct':100*bh,
      'delta_bhr_pp':100*(total-bh),'exposure_pct':100*inbars/len(df),
      'avg_trade_pct':100*np.mean([t['ret'] for t in trades]) if trades else 0,
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default='evidence/rsi-supertrend-external-test'); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    symbols=['SOLUSDT','ETHUSDT','XRPUSDT']; rows=[]; data_meta=[]
    end='2026-08-25'
    for interval,start in [('4h','2019-01-01'),('1h','2024-01-01')]:
      for sym in symbols:
        df=fetch_klines(sym,interval,start,end)
        if df.empty: continue
        data_meta.append({'symbol':sym,'interval':interval,'rows':len(df),'start':str(df.iloc[0].dt),'end':str(df.iloc[-1].dt)})
        for cost in [0,10,20]:
          scopes=[('full',None)] if interval=='1h' else [('full',None),('oos_2024','2024-01-01')]
          for scope,sf in scopes:
            r=run_bt(df,cost,sf)
            if r: rows.append({'symbol':sym,'interval':interval,'scope':scope,'cost_bps_side':cost,**r})
    res=pd.DataFrame(rows)
    res.to_csv(out/'results.csv',index=False)
    (out/'results.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'data_meta.json').write_text(json.dumps(data_meta,indent=2),encoding='utf-8')
    # Compact markdown: zero-cost and 10bps side only.
    show=res[(res.cost_bps_side.isin([0,10])) & (((res.interval=='4h')&(res.scope.isin(['full','oos_2024'])))|((res.interval=='1h')&(res.scope=='full')))].copy()
    cols=['symbol','interval','scope','cost_bps_side','trades','win_rate_pct','profit_factor','total_return_pct','max_dd_pct','buy_hold_pct','delta_bhr_pp','exposure_pct']
    md=['# RSI+SuperTrend external replication','', 'Exact Pine logic: RSI(10), RSI-SMA(10), second bullish cross below 50 triggers long; SuperTrend(10, 2.5) bearish flip exits. Orders filled at next bar open; long-only; 100% equity.', '', show[cols].round(2).to_markdown(index=False)]
    (out/'summary.md').write_text('\n'.join(md),encoding='utf-8')
    print(show[cols].round(3).to_string(index=False))

if __name__=='__main__': main()
