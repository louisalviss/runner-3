#!/usr/bin/env python3
from __future__ import annotations

import json, math, statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

DATA_URL='https://raw.githubusercontent.com/plotly/datasets/master/all_stocks_5yr.csv'
OUT=Path('results/felipe-breakout-public-pilot.json')


def ema(a,n):
    return pd.Series(a,dtype=float).ewm(span=n,adjust=False).mean().to_numpy()


def atr(rows,n):
    h=rows['high'].to_numpy(float); l=rows['low'].to_numpy(float); c=rows['close'].to_numpy(float)
    pc=np.r_[c[0],c[:-1]]
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
    return pd.Series(tr).ewm(alpha=1/n,adjust=False).mean().to_numpy()


def pctile(a,p):
    return float(np.quantile(np.asarray(a,float),p)) if a else None


def summarize(ts):
    if not ts:return {'trades':0}
    rets=[t['ret'] for t in ts]; rs=[t['R'] for t in ts]
    gp=sum(x for x in rets if x>0); gl=-sum(x for x in rets if x<0)
    return {
      'trades':len(ts),
      'win_rate_pct':100*sum(x>0 for x in rets)/len(ts),
      'avg_return_pct':100*statistics.fmean(rets),
      'median_return_pct':100*statistics.median(rets),
      'p25_return_pct':100*pctile(rets,.25),
      'p75_return_pct':100*pctile(rets,.75),
      'profit_factor_return':gp/gl if gl else None,
      'avg_R':statistics.fmean(rs),
      'median_R':statistics.median(rs),
      'stop_rate_pct':100*sum(bool(t['stopped']) for t in ts)/len(ts),
      'avg_hold_days':statistics.fmean(t['hold_days'] for t in ts),
    }


def signal_stage(g,i,e8,e20,e50,a5,a20):
    if i<80 or i+5>=len(g):return None
    o=g.open.to_numpy(float);h=g.high.to_numpy(float);l=g.low.to_numpy(float);c=g.close.to_numpy(float)
    if not (e8[i]>e20[i]>e50[i] and e8[i]>e8[i-3] and e20[i]>e20[i-5] and e50[i]>e50[i-10]):return None
    if not (c[i]>np.max(h[i-7:i]) and c[i]>o[i]):return None
    body=abs(c[i]-o[i]); prevbody=abs(c[i-1]-o[i-1]); rng=max(1e-12,h[i]-l[i])
    if not (body>prevbody and (c[i]-l[i])/rng>=.786):return None
    risk=c[i]-l[i]
    if risk<=0 or risk>2.5*a20[i]:return None
    stage='base'
    if np.all(c[i-7:i] >= e20[i-7:i]):
        first_low=np.min(l[i-7:i-3]); second_low=np.min(l[i-4:i])
        if second_low>first_low and a5[i-1] <= .95*a20[i-1]:stage='vcp'
    if stage!='vcp':return stage,l[i],risk
    launch=None
    for j in range(max(55,i-30),i-6):
        if c[j] > e50[j]+.5*a5[j] and c[j-1] <= e50[j-1]+.5*a5[j-1]:launch=j
    if launch is not None:
        base=e50[launch]+.5*a5[launch]
        if base>0 and np.max(h[launch:i])/base-1>=.05:stage='first_leg_vcp'
    return stage,l[i],risk


def run_symbol(sym,g):
    g=g.sort_values('date').reset_index(drop=True)
    if len(g)<120:return {'base':[],'vcp':[],'first_leg_vcp':[]}
    c=g.close.to_numpy(float); e8=ema(c,8);e20=ema(c,20);e50=ema(c,50);a5=atr(g,5);a20=atr(g,20)
    out={'base':[],'vcp':[],'first_leg_vcp':[]}; last={k:-999 for k in out}
    o=g.open.to_numpy(float);h=g.high.to_numpy(float);l=g.low.to_numpy(float)
    for i in range(len(g)):
        sig=signal_stage(g,i,e8,e20,e50,a5,a20)
        if not sig:continue
        stage,stop,risk=sig
        buckets=['base']
        if stage in ('vcp','first_leg_vcp'):buckets.append('vcp')
        if stage=='first_leg_vcp':buckets.append('first_leg_vcp')
        for b in buckets:
            if i-last[b]<5:continue
            entry=c[i]; exitp=c[i+5]; stopped=False; hd=5
            for k in range(i+1,i+6):
                if o[k]<=stop: exitp=o[k];stopped=True;hd=k-i;break
                if l[k]<=stop: exitp=stop;stopped=True;hd=k-i;break
            ret=exitp/entry-1
            out[b].append({'symbol':sym,'date':str(g.date.iloc[i].date()),'ret':float(ret),'R':float((exitp-entry)/risk),'stopped':stopped,'hold_days':hd,'risk_pct':float(100*risk/entry)})
            last[b]=i
    return out


def main():
    df=pd.read_csv(DATA_URL,parse_dates=['date'])
    df.columns=[str(x).lower() for x in df.columns]
    needed={'date','open','high','low','close','name'}
    if not needed.issubset(df.columns):raise SystemExit(f'missing columns: {sorted(needed-set(df.columns))}')
    df=df.dropna(subset=['date','open','high','low','close','name'])
    allb={'base':[],'vcp':[],'first_leg_vcp':[]}; coverage=[]
    for sym,g in df.groupby('name',sort=True):
        g=g[['date','open','high','low','close']].copy()
        good=(g[['open','high','low','close']]>0).all(axis=1)
        g=g.loc[good]
        if len(g)<120:continue
        b=run_symbol(str(sym),g)
        for k in allb:allb[k].extend(b[k])
        coverage.append({'symbol':str(sym),'rows':int(len(g))})
    yearly={}
    for t in allb['first_leg_vcp']:yearly.setdefault(t['date'][:4],[]).append(t)
    result={
      'schema':1,
      'strategy':'Felipe Guirao EOD breakout public-post approximation',
      'generated_at':datetime.now(timezone.utc).isoformat(),
      'data_source':DATA_URL,
      'period':{'start':str(df.date.min().date()),'end':str(df.date.max().date())},
      'universe_usable':len(coverage),
      'methodology':{
        'entry':'daily close proxy for 3:58pm ET','stop':'breakout-day low; gap-through exits next open','exit':'close after 5 trading sessions',
        'base':'EMA8>20>50 rising; close > prior 7-session high; bullish body > previous body; close-location >=78.6%; risk <=2.5 ATR20',
        'vcp_add':'prior 7 closes >= EMA20; higher low; ATR5 <=0.95 ATR20',
        'first_leg_add':'cross above EMA50+0.5 ATR5 cloud 7-30 sessions earlier; >=5% expansion',
        'omitted':['proprietary CML','breadth/timing model','visual VCP/triangle judgement','true 3:58pm execution'],
        'biases':['dataset universe/constituent survivorship effects','no commissions/slippage','signal-level statistics, not portfolio CAGR']},
      'results':{k:summarize(v) for k,v in allb.items()},
      'first_leg_yearly':{y:summarize(v) for y,v in sorted(yearly.items())},
      'best_first_leg':sorted(allb['first_leg_vcp'],key=lambda t:t['ret'],reverse=True)[:10],
      'worst_first_leg':sorted(allb['first_leg_vcp'],key=lambda t:t['ret'])[:10],
      'coverage_count':len(coverage)}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
