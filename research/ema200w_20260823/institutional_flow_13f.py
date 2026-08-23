from __future__ import annotations

import json
import time
import numpy as np
import pandas as pd
from datasets import load_dataset
from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker

HORIZONS=(13,26,52)
DISC_START=pd.Timestamp('2017-01-01'); DISC_END=pd.Timestamp('2020-12-31')
VAL_START=pd.Timestamp('2021-01-01'); VAL_END=pd.Timestamp('2024-12-31')


def prices():
    w=load_prices(); _,periods=load_memberships(); w=add_membership_flag(w,periods)
    w['week']=pd.to_datetime(w['week']).astype('datetime64[ns]')
    g=w.groupby('series_id',sort=False,observed=True)
    w['ret52_pre']=g['close'].shift(1)/g['close'].shift(53)-1
    w['next_open']=g['open'].shift(-1)
    for h in HORIZONS: w[f'ret{h}']=g['close'].shift(-h)/w['next_open']-1
    return w


def source(symbols):
    cols=['ticker','date','net_flows_sum','growth_shrholders']
    ds=load_dataset('sovai/institutional_trading',split='train')
    df=ds.select_columns(cols).to_pandas()
    df['symbol']=df['ticker'].fillna('').astype(str).map(norm_ticker)
    df=df[df['symbol'].isin(symbols)].copy()
    df['source_date']=pd.to_datetime(df['date'],errors='coerce').astype('datetime64[ns]')
    for c in ['net_flows_sum','growth_shrholders']: df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=['source_date','net_flows_sum','growth_shrholders'])
    df=df.sort_values(['symbol','source_date']).drop_duplicates(['symbol','source_date'],keep='last')
    n=df.groupby('source_date')['symbol'].transform('size')
    df['flow_rank']=df.groupby('source_date')['net_flows_sum'].rank(pct=True,method='average')
    df['holder_rank']=df.groupby('source_date')['growth_shrholders'].rank(pct=True,method='average')
    df['cohort_n']=n
    df=df[n>=50].copy()
    # Conservative 13F availability: reports can be filed up to 45 days after quarter end.
    df['available_date']=df['source_date']+pd.Timedelta(days=46)
    meta={'raw_rows':len(ds),'usable_rows':len(df),'symbols':int(df.symbol.nunique()),
          'source_min':str(df.source_date.min().date()),'source_max':str(df.source_date.max().date()),
          'source_dates':int(df.source_date.nunique()),
          'net_flow_q':{str(k):float(v) for k,v in df.net_flows_sum.quantile([0,.1,.25,.5,.75,.9,1]).items()},
          'holder_q':{str(k):float(v) for k,v in df.growth_shrholders.quantile([0,.1,.25,.5,.75,.9,1]).items()}}
    return df,meta


def map_prices(df,w):
    rows=[]; pcols=['week','series_id','is_member','ret52_pre','next_open']+[f'ret{h}' for h in HORIZONS]
    for sym,r in df.groupby('symbol',sort=False,observed=True):
        p=w[w.symbol.eq(sym)][pcols].sort_values('week')
        if p.empty: continue
        m=pd.merge_asof(r.sort_values('available_date'),p,left_on='available_date',right_on='week',direction='forward',allow_exact_matches=False)
        lag=(m.week-m.available_date).dt.days
        m=m[lag.between(1,10,inclusive='both') & m.is_member.fillna(False) & m.next_open.notna()].copy()
        if len(m): rows.append(m)
    return pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()


def events(a):
    specs=[('TopQNetFlow',a.flow_rank>=.75,'flow'),('TopQHolderGrowth',a.holder_rank>=.75,'holder'),('BothTopQ',(a.flow_rank>=.75)&(a.holder_rank>=.75),'both')]
    rows=[]; base=['symbol','source_date','available_date','week','ret52_pre','flow_rank','holder_rank']
    for name,mask,code in specs:
        z=a.loc[mask & a.week.between(DISC_START,VAL_END),base].copy(); z['strategy']=name; z['code']=code
        for h in HORIZONS: z[f'ret{h}']=a.loc[z.index,f'ret{h}'].to_numpy()
        rows.append(z)
    return pd.concat(rows,ignore_index=True)


def controls(ev,a):
    for h in HORIZONS: ev[f'excess{h}']=np.nan; ev[f'control_n{h}']=0
    bydate={d:g for d,g in a.groupby('source_date',sort=False)}
    for j,r in enumerate(ev.itertuples(index=False)):
        p=bydate.get(r.source_date)
        if p is None or not np.isfinite(r.ret52_pre): continue
        if r.code=='flow': neutral=p.flow_rank.between(.40,.60)
        elif r.code=='holder': neutral=p.holder_rank.between(.40,.60)
        else: neutral=p.flow_rank.between(.40,.60)&p.holder_rank.between(.40,.60)
        rr=p.ret52_pre.to_numpy(float)
        base=neutral.to_numpy(bool)&np.isfinite(rr)&(p.symbol.to_numpy()!=r.symbol)
        m=base&(np.abs(rr-r.ret52_pre)<=.15)
        if m.sum()<5: m=base&(np.abs(rr-r.ret52_pre)<=.25)
        for h in HORIZONS:
            vals=p.loc[m,f'ret{h}'].to_numpy(float); vals=vals[np.isfinite(vals)]
            if len(vals)>=3 and np.isfinite(getattr(r,f'ret{h}')):
                ev.at[j,f'excess{h}']=getattr(r,f'ret{h}')-float(np.median(vals)); ev.at[j,f'control_n{h}']=len(vals)
    return ev


def summarize(ev,label,a,b):
    out=[]; rng=np.random.default_rng(20260823); z=ev[ev.week.between(a,b)]
    for st,x0 in z.groupby('strategy',sort=False):
        for h in HORIZONS:
            x=x0.dropna(subset=[f'ret{h}']); c=x.dropna(subset=[f'excess{h}']); wm=c.groupby('week')[f'excess{h}'].mean().to_numpy(float)
            if len(wm)>=8:
                bs=np.array([rng.choice(wm,len(wm),replace=True).mean() for _ in range(2000)]); lo,hi=np.quantile(bs,[.025,.975])
            else: lo=hi=np.nan
            out.append({'slice':label,'strategy':st,'horizon':h,'n':len(x),'matched_n':len(c),'signal_weeks':x.week.nunique(),
                        'median_return':x[f'ret{h}'].median(),'win_rate':(x[f'ret{h}']>0).mean(),'median_excess':c[f'excess{h}'].median(),
                        'mean_excess':c[f'excess{h}'].mean(),'beat_matched':(c[f'excess{h}']>0).mean(),'ci_lo':lo,'ci_hi':hi})
    return out


def main():
    t=time.time(); print('loading prices...',flush=True); w=prices()
    syms=set(w.loc[w.is_member & w.week.between(DISC_START,VAL_END),'symbol'].dropna().astype(str).unique())
    print('loading institutional source...',flush=True); d,meta=source(syms); a=map_prices(d,w)
    if a.empty: raise RuntimeError('no mapped institutional observations')
    meta.update({'mapped_rows':len(a),'mapped_symbols':int(a.symbol.nunique()),'mapped_week_min':str(a.week.min().date()),'mapped_week_max':str(a.week.max().date())})
    ev=controls(events(a),a); print('EVENTS',json.dumps(ev.groupby('strategy').size().to_dict()),flush=True)
    s=pd.DataFrame(summarize(ev,'discovery_2017_2020',DISC_START,DISC_END)+summarize(ev,'validation_2021_2024',VAL_START,VAL_END))
    meta['elapsed_sec']=round(time.time()-t,2); print('META',json.dumps(meta),flush=True); print(s.to_string(index=False),flush=True)
    v=s[(s.slice=='validation_2021_2024')&(s.horizon==26)].copy()
    v['pass']=(v.n>=300)&(v.median_excess>.01)&(v.beat_matched>=.525)&(v.ci_lo>0)
    print('GATE26',v[['strategy','n','matched_n','win_rate','median_return','median_excess','beat_matched','mean_excess','ci_lo','ci_hi','pass']].to_json(orient='records'),flush=True)
    print('DONE',flush=True)

if __name__=='__main__': main()
