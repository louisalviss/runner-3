from pathlib import Path
import pandas as pd
import numpy as np
import requests

import quality_factor as q

# diagnostic trigger: 2026-08-24
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
    use=['ticker','filing_date','period_end_date','revenue','total_assets','total_liabilities','free_cash_flow','net_margin','roa']
    parts=[]
    for name in FILES:
        p=get_file(name)
        parts.append(pd.read_parquet(p,columns=use))
    d=pd.concat(parts,ignore_index=True)
    d['symbol']=d.ticker.map(q.px.norm_ticker)
    d['filed']=pd.to_datetime(d.filing_date,errors='coerce')
    d['period_end']=pd.to_datetime(d.period_end_date,errors='coerce')
    symbols=set(w.loc[w.member & w.week.between(q.DISCOVERY[0],q.VALIDATION[1]),'symbol'].astype(str).unique())
    d=d[d.symbol.isin(symbols)].dropna(subset=['symbol','filed','period_end']).copy()
    d=d.sort_values(['symbol','period_end','filed']).drop_duplicates(['symbol','period_end'],keep='last')
    d=d.sort_values(['symbol','period_end'])
    g=d.groupby('symbol',observed=True,sort=False)
    d['fcf_assets']=d.free_cash_flow/d.total_assets.replace(0,np.nan)
    d['leverage']=d.total_liabilities/d.total_assets.replace(0,np.nan)
    d['revenue_yoy']=d.revenue/g.revenue.shift(4)-1
    d['revenue_accel']=d.revenue_yoy-g.revenue_yoy.shift(4)
    snaps=d[['symbol','filed','roa','fcf_assets','net_margin','revenue_yoy','revenue_accel','leverage']].copy()
    meta={'source':'OpenFundex clean parquet','rows':len(d),'companies':int(d.symbol.nunique()),'filed_min':str(d.filed.min().date()),'filed_max':str(d.filed.max().date())}
    return snaps,meta

q.load_fundamentals=load_openfundex
q.main()
