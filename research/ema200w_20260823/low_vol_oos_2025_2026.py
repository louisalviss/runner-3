from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from backtest import load_memberships, add_membership_flag, norm_ticker

HF_BASE='https://huggingface.co/datasets/paperswithbacktest/Stocks-Daily-Price/resolve/main/data/train-{i:05d}-of-00004.parquet?download=true'
START_WARM=pd.Timestamp('2023-01-01')
OOS_START=pd.Timestamp('2025-01-01')
OOS_END=pd.Timestamp('2026-08-05')
BOTTOM_FRAC=.20
COST_BPS=25.0
CACHE=Path('/tmp/low_vol_oos_pwb'); CACHE.mkdir(parents=True,exist_ok=True)


def download(url,path):
    if path.exists() and path.stat().st_size>50_000_000: return
    h={'User-Agent':'Mozilla/5.0 low-vol-oos/1.0'}
    with requests.get(url,stream=True,timeout=180,headers=h,allow_redirects=True) as r:
        print('DOWNLOAD_STATUS',url.split('/')[-1].split('?')[0],r.status_code,flush=True)
        r.raise_for_status()
        with open(str(path)+'.part','wb') as f:
            for ch in r.iter_content(1024*1024):
                if ch: f.write(ch)
    os.replace(str(path)+'.part',path)


def ann_return(x):
    x=pd.Series(x).dropna().astype(float)
    return float(np.prod(1+x)**(12/len(x))-1) if len(x) else np.nan

def sharpe0(x):
    x=pd.Series(x).dropna().astype(float)
    return float(x.mean()/x.std(ddof=1)*math.sqrt(12)) if len(x)>1 and x.std(ddof=1)>0 else np.nan

def ann_vol(x):
    x=pd.Series(x).dropna().astype(float)
    return float(x.std(ddof=1)*math.sqrt(12)) if len(x)>1 else np.nan

def maxdd(x):
    x=pd.Series(x).dropna().astype(float)
    if not len(x): return np.nan
    eq=(1+x).cumprod(); return float((eq/eq.cummax()-1).min())

def turnover(prev,cur):
    if not prev:return 1.0
    return 0.5*sum(abs(cur.get(s,0)-prev.get(s,0)) for s in set(prev)|set(cur))


def load_independent_weekly():
    _, periods=load_memberships()
    relevant=set()
    for sym,ps in periods.items():
        if any(end>=START_WARM and start<=OOS_END for start,end in ps): relevant.add(sym)
    chunks=[]; total_rows=0
    for i in range(4):
        path=CACHE/f'shard{i}.parquet'; download(HF_BASE.format(i=i),path)
        d=pd.read_parquet(path,columns=['symbol','date','open','close','adj_close'])
        total_rows+=len(d)
        d['symbol']=d['symbol'].astype(str).map(norm_ticker)
        d['date']=pd.to_datetime(d['date'],errors='coerce')
        d=d[d['symbol'].isin(relevant)&d['date'].between(START_WARM,OOS_END)].copy()
        if len(d): chunks.append(d)
        print('SHARD_FILTERED',i,len(d),flush=True)
    if not chunks: raise RuntimeError('no independent PWB price rows after filtering')
    d=pd.concat(chunks,ignore_index=True).dropna(subset=['date','symbol','open','close','adj_close'])
    d=d[(d.open>0)&(d.close>0)&(d.adj_close>0)].copy()
    factor=d.adj_close/d.close
    d['adj_open']=d.open*factor
    d['week']=d.date.dt.to_period('W-FRI').dt.end_time.dt.normalize()
    max_date=d.date.max()
    # Exclude a partial final W-FRI bucket if dataset stops before that Friday.
    d=d[d.week<=max_date.normalize()].copy()
    d=d.sort_values(['symbol','date'])
    w=d.groupby(['symbol','week'],sort=False,observed=True).agg(open=('adj_open','first'),close=('adj_close','last'),last_trade_date=('date','max')).reset_index().sort_values(['symbol','week']).reset_index(drop=True)
    gap=w.groupby('symbol',observed=True).week.diff().dt.days.fillna(0)
    w['segment_no']=(gap>84).groupby(w.symbol,observed=True).cumsum().astype(int)
    w['series_id']=w.symbol.astype(str)+'#'+w.segment_no.astype(str)
    w=add_membership_flag(w,periods)
    print('PRICE_META',json.dumps({'raw_rows_scanned':total_rows,'filtered_daily_rows':len(d),'weekly_rows':len(w),'symbols':int(w.symbol.nunique()),'date_min':str(d.date.min().date()),'date_max':str(d.date.max().date())}),flush=True)
    return w


def main():
    w=load_independent_weekly()
    g=w.groupby('series_id',sort=False,observed=True)
    w['weekly_ret']=g.close.pct_change(fill_method=None)
    w['vol52']=w.weekly_ret.groupby(w.series_id,observed=True).transform(lambda s:s.rolling(52,min_periods=40).std(ddof=1)*math.sqrt(52))
    w['next_open']=g.open.shift(-1)
    meta=w.groupby('series_id',observed=True).agg(last_week=('week','max'),last_close=('close','last'))
    cal=w[['week']].drop_duplicates(); cal['month']=cal.week.dt.to_period('M')
    forms=cal.groupby('month',as_index=False).week.max().sort_values('week').reset_index(drop=True); forms['next_form']=forms.week.shift(-1)
    forms=forms[forms.week.between(OOS_START,OOS_END)&forms.next_form.notna()].copy()
    rows=[]; prev_low={};prev_b={};c=COST_BPS/10000
    for r in forms.itertuples(index=False):
        fw=pd.Timestamp(r.week); nfw=pd.Timestamp(r.next_form)
        f=w[w.week.eq(fw)&w.is_member.fillna(False)&w.vol52.notna()&w.next_open.notna()][['symbol','series_id','vol52','next_open']].copy()
        if len(f)<100:continue
        ex=w[w.week.eq(nfw)][['series_id','next_open']].rename(columns={'next_open':'exit_open'})
        f=f.merge(ex,on='series_id',how='left').merge(meta,on='series_id',how='left')
        ended=f.last_week<(nfw+pd.Timedelta(days=10)); m=f.exit_open.isna()&ended
        f.loc[m,'exit_open']=f.loc[m,'last_close'];f['ret']=f.exit_open/f.next_open-1
        f=f.replace([np.inf,-np.inf],np.nan).dropna(subset=['ret'])
        if len(f)<100:continue
        f=f.sort_values(['vol52','symbol'],ascending=[True,True]).reset_index(drop=True);k=max(1,int(math.floor(len(f)*BOTTOM_FRAC)));low=f.iloc[:k]
        lw={s:1/len(low) for s in low.symbol.astype(str)};bw={s:1/len(f) for s in f.symbol.astype(str)}
        lto=turnover(prev_low,lw);bto=turnover(prev_b,bw);prev_low=lw;prev_b=bw
        lg=float(low.ret.mean());bg=float(f.ret.mean());ln=(1+lg)*(1-c*lto)-1;bn=(1+bg)*(1-c*bto)-1
        rows.append({'formation':fw,'n':len(f),'low_n':len(low),'low_gross':lg,'bench_gross':bg,'low_net25':ln,'bench_net25':bn,'low_turnover':lto,'bench_turnover':bto})
    p=pd.DataFrame(rows).sort_values('formation').reset_index(drop=True)
    if p.empty:raise RuntimeError('no OOS periods')
    out={'months':len(p),'formation_min':str(p.formation.min().date()),'formation_max':str(p.formation.max().date()),'low_cagr_gross':ann_return(p.low_gross),'bench_cagr_gross':ann_return(p.bench_gross),'cagr_diff_gross':ann_return(p.low_gross)-ann_return(p.bench_gross),'low_vol_gross':ann_vol(p.low_gross),'bench_vol_gross':ann_vol(p.bench_gross),'vol_ratio':ann_vol(p.low_gross)/ann_vol(p.bench_gross),'low_sharpe_gross':sharpe0(p.low_gross),'bench_sharpe_gross':sharpe0(p.bench_gross),'low_maxdd_gross':maxdd(p.low_gross),'bench_maxdd_gross':maxdd(p.bench_gross),'maxdd_improvement':maxdd(p.low_gross)-maxdd(p.bench_gross),'low_cagr_net25':ann_return(p.low_net25),'bench_cagr_net25':ann_return(p.bench_net25),'cagr_diff_net25':ann_return(p.low_net25)-ann_return(p.bench_net25),'low_sharpe_net25':sharpe0(p.low_net25),'bench_sharpe_net25':sharpe0(p.bench_net25),'sharpe_improvement_net25':sharpe0(p.low_net25)-sharpe0(p.bench_net25),'mean_low_turnover':float(p.low_turnover.mean())}
    print('OOS',json.dumps(out),flush=True)
    gate={'months_ge_16':out['months']>=16,'vol_ratio_le_0_85':out['vol_ratio']<=.85,'net25_sharpe_improvement_gt_0_10':out['sharpe_improvement_net25']>.10,'maxdd_improvement_ge_3pp':out['maxdd_improvement']>=.03,'net25_cagr_diff_ge_minus_2pp':out['cagr_diff_net25']>=-.02};gate['pass']=bool(all(gate.values()))
    print('OOS_GATE',json.dumps(gate),flush=True);print('DONE',flush=True)

if __name__=='__main__':main()
