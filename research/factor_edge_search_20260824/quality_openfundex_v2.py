from pathlib import Path
import pandas as pd
import numpy as np
import requests

import quality_factor as q

CACHE=Path('/tmp/openfundex_cache'); CACHE.mkdir(parents=True,exist_ok=True)
BASE='https://huggingface.co/datasets/ttchopper/openfundex/resolve/main/'
FILES=['train_clean.parquet','validation_clean.parquet','test_clean.parquet','recent_clean.parquet']

def get_file(name):
    p=CACHE/name
    if p.exists() and p.stat().st_size>1_000_000: return p
    r=requests.get(BASE+name,timeout=180,stream=True,headers={'User-Agent':'Mozilla/5.0 quality-research'})
    r.raise_for_status()
    with open(p,'wb') as f:
        for ch in r.iter_content(1024*1024):
            if ch:f.write(ch)
    return p

def load_openfundex(w):
    use=['ticker','filing_date','period_end_date','revenue','total_assets','total_liabilities','free_cash_flow','net_margin','roa','gross_profit','f_score','composite_quality_score']
    d=pd.concat([pd.read_parquet(get_file(n),columns=use) for n in FILES],ignore_index=True)
    d['symbol']=d.ticker.map(q.px.norm_ticker)
    d['filed']=pd.to_datetime(d.filing_date,errors='coerce'); d['period_end']=pd.to_datetime(d.period_end_date,errors='coerce')
    symbols=set(w.loc[w.member & w.week.between(q.DISCOVERY[0],q.VALIDATION[1]),'symbol'].astype(str).unique())
    d=d[d.symbol.isin(symbols)].dropna(subset=['symbol','filed','period_end']).copy()
    d=d.sort_values(['symbol','period_end','filed']).drop_duplicates(['symbol','period_end'],keep='last').sort_values(['symbol','period_end'])
    g=d.groupby('symbol',observed=True,sort=False)
    d['fcf_assets']=d.free_cash_flow/d.total_assets.replace(0,np.nan)
    d['gross_profitability']=d.gross_profit/d.total_assets.replace(0,np.nan)
    d['leverage']=d.total_liabilities/d.total_assets.replace(0,np.nan)
    d['revenue_yoy']=d.revenue/g.revenue.shift(4)-1
    d['revenue_accel']=d.revenue_yoy-g.revenue_yoy.shift(4)
    cols=['symbol','filed','roa','fcf_assets','net_margin','revenue_yoy','revenue_accel','leverage','gross_profitability','f_score','composite_quality_score']
    meta={'source':'OpenFundex clean parquet','rows':len(d),'companies':int(d.symbol.nunique()),'filed_min':str(d.filed.min().date()),'filed_max':str(d.filed.max().date())}
    return d[cols].copy(),meta

def attach_ext(base,snaps):
    cols=['roa','fcf_assets','net_margin','revenue_yoy','revenue_accel','leverage','gross_profitability','f_score','composite_quality_score','fund_filed']
    for c in cols: base[c]=pd.NaT if c=='fund_filed' else np.nan
    for sym,idx in base.groupby('symbol',observed=True,sort=False).groups.items():
        s=snaps[snaps.symbol.eq(sym)].copy()
        if s.empty: continue
        s=s.rename(columns={'filed':'fund_filed'}).sort_values('fund_filed')
        left=base.loc[idx,['week']].sort_values('week')
        m=pd.merge_asof(left,s.drop(columns=['symbol']).sort_values('fund_filed'),left_on='week',right_on='fund_filed',direction='backward')
        m.index=left.index
        for c in cols: base.loc[m.index,c]=m[c].to_numpy()
    return base

def rank_ext(base):
    for c in ['roa','fcf_assets','net_margin','revenue_yoy','revenue_accel','gross_profitability','composite_quality_score']:
        base[f'{c}_pct']=base.groupby('week',observed=True)[c].rank(pct=True,method='average')
    base['quality_score']=base[['roa_pct','fcf_assets_pct','revenue_yoy_pct']].mean(axis=1,skipna=False)
    base['quality_pct']=base.groupby('week',observed=True).quality_score.rank(pct=True,method='average')
    return base

q.load_fundamentals=load_openfundex
q.attach=attach_ext
q.rank_features=rank_ext
q.SPECS={
    'ROA_TOP20':(lambda x:x.roa_pct>=.80,lambda x:x.roa_pct.between(.40,.60),'profitability / ROA'),
    'FCF_ASSETS_TOP20':(lambda x:x.fcf_assets_pct>=.80,lambda x:x.fcf_assets_pct.between(.40,.60),'free-cash-flow profitability'),
    'GROSS_PROFIT_TOP20':(lambda x:x.gross_profitability_pct>=.80,lambda x:x.gross_profitability_pct.between(.40,.60),'gross profitability / assets'),
    'F_SCORE_7PLUS':(lambda x:x.f_score>=7,lambda x:x.f_score.between(4,5),'Piotroski F-score quality'),
    'COMPOSITE_Q_TOP20':(lambda x:x.composite_quality_score_pct>=.80,lambda x:x.composite_quality_score_pct.between(.40,.60),'OpenFundex composite quality'),
    'REV_ACCEL_TOP20':(lambda x:x.revenue_accel_pct>=.80,lambda x:x.revenue_accel_pct.between(.40,.60),'revenue growth acceleration'),
    'QUALITY_TOP20':(lambda x:x.quality_pct>=.80,lambda x:x.quality_pct.between(.40,.60),'profitability + FCF + revenue growth'),
    'COMPOSITE_Q_LOWVOL':(lambda x:(x.composite_quality_score_pct>=.70)&(x.vol_pct<=.30),lambda x:(x.composite_quality_score_pct<=.50)&(x.vol_pct<=.30),'quality conditional on low volatility'),
}
q.main()
