import io
import json
from urllib.parse import quote

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests

S=requests.Session(); S.headers.update({'User-Agent':'louis-research-deep-audit/1.1'})
HF_EPS='siddharthmb/stocks-earnings-eps_estimate'
AV_DEMO='https://www.alphavantage.co/query?function=EARNINGS_ESTIMATES&symbol=IBM&apikey=demo'

def get_json(url,timeout=120):
    r=S.get(url,timeout=timeout); print('HTTP',r.status_code,url,'bytes',len(r.content)); r.raise_for_status(); return r.json()

def alpha_vantage_probe():
    try: j=get_json(AV_DEMO)
    except Exception as e: print('AV_ERROR',repr(e)); return
    print('AV_TOP_KEYS',json.dumps(list(j.keys())))
    print('AV_JSON_SAMPLE',json.dumps(j,default=str)[:30000])
    keys=set()
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items(): keys.add(k); walk(v)
        elif isinstance(x,list):
            for v in x[:200]: walk(v)
    walk(j)
    rel=[k for k in keys if any(s in k.lower() for s in ('revision','estimate','analyst','date','period','eps','revenue'))]
    print('AV_RELEVANT_KEYS',json.dumps(sorted(rel)))
    print('AV_HAS_REVISION_TOKEN','revision' in json.dumps(j).lower())

def parquet_urls(did):
    j=get_json(f'https://datasets-server.huggingface.co/parquet?dataset={quote(did)}'); return [x['url'] for x in j.get('parquet_files',[])]

def read_panel():
    urls=parquet_urls(HF_EPS); cols=['date','act_symbol','period','period_end_date','consensus','recent','count','high','low','year_ago']
    frames=[]; total=0
    for i,u in enumerate(urls):
        r=S.get(u,timeout=300); print('HF_DOWNLOAD',i,r.status_code,len(r.content)); r.raise_for_status(); total+=len(r.content)
        pf=pq.ParquetFile(io.BytesIO(r.content)); frames.append(pf.read(columns=[c for c in cols if c in pf.schema.names]).to_pandas())
    df=pd.concat(frames,ignore_index=True); print('HF_TOTAL_BYTES',total); print('HF_SHAPE',df.shape)
    df['date']=pd.to_datetime(df.date,errors='coerce'); df['period_end_date']=pd.to_datetime(df.period_end_date,errors='coerce')
    for c in ['consensus','recent','count','high','low','year_ago']: df[c]=pd.to_numeric(df[c],errors='coerce')
    print('HF_DATE_RANGE',str(df.date.min()),str(df.date.max())); print('HF_SYMBOLS',int(df.act_symbol.nunique()))
    dates=pd.Series(sorted(df.date.dropna().unique())); gaps=dates.diff().dt.days.dropna()
    print('HF_DISTINCT_DATES',len(dates)); print('HF_DATE_GAP_DAYS',json.dumps({'median':float(gaps.median()),'p90':float(gaps.quantile(.9)),'max':float(gaps.max())}))

    key=['act_symbol','period','period_end_date']; valid=df.dropna(subset=key+['date']).sort_values(key+['date']).copy(); g=valid.groupby(key,sort=False)
    sizes=g.size(); nun=g.consensus.nunique(dropna=True); first=g.consensus.first(); last=g.consensus.last()
    prev=valid.groupby(key,sort=False).consensus.shift(1); changed=(valid.consensus.notna() & prev.notna() & ((valid.consensus-prev).abs()>1e-12)).astype('int8')
    valid['_changed']=changed; revcounts=valid.groupby(key,sort=False)._changed.sum()
    multi=sizes>=2
    print('HF_REVISION_BEHAVIOR',json.dumps({
      'groups':int(len(sizes)),'multi_groups':int(multi.sum()),'pct_multi':float(multi.mean()),
      'groups_with_consensus_change':int((nun>1).sum()),'pct_groups_with_consensus_change':float((nun>1).mean()),
      'groups_first_last_diff':int(((first-last).abs()>1e-12).sum()),
      'median_revision_events':float(revcounts[multi].median()),'p90_revision_events':float(revcounts[multi].quantile(.9)),'p99_revision_events':float(revcounts[multi].quantile(.99))}))

    lead=(valid.period_end_date-valid.date).dt.days
    print('HF_LEAD_DAYS',json.dumps({'median':float(lead.median()),'p10':float(lead.quantile(.1)),'p90':float(lead.quantile(.9)),'pct_after_period_end':float((lead<0).mean())}))
    dkey=key+['date']; ds=valid.groupby(dkey).consensus.agg(['size','nunique'])
    print('HF_DUPLICATE_KEYS',json.dumps({'groups_n_gt1':int((ds['size']>1).sum()),'groups_conflicting_consensus':int((ds['nunique']>1).sum())}))
    valid['year']=valid.date.dt.year; cov=valid.groupby(['year','period']).agg(rows=('act_symbol','size'),symbols=('act_symbol','nunique'),dates=('date','nunique')).reset_index()
    print('HF_COVERAGE_BY_YEAR_PERIOD',cov.to_json(orient='records'))

    weekly=valid[valid.date.dt.dayofweek==4].copy()
    old=weekly[key+['date','consensus']].rename(columns={'date':'old_date','consensus':'old_consensus'}).sort_values('old_date')
    cur=weekly[key+['date','consensus']].sort_values('date')
    try:
        m=pd.merge_asof(cur.sort_values('date'),old.sort_values('old_date'),left_on='date',right_on='old_date',by=key,direction='backward',tolerance=pd.Timedelta(days=45),allow_exact_matches=False)
        age=(m.date-m.old_date).dt.days; m=m[(age>=21)&m.consensus.notna()&m.old_consensus.notna()]
        d=m.consensus-m.old_consensus
        print('HF_30D_REVISION_SAMPLES',json.dumps({'n':int(len(d)),'pct_up':float((d>0).mean()),'pct_down':float((d<0).mean()),'pct_flat':float((d==0).mean()),'median_abs_change':float(d.abs().median())}))
    except Exception as e: print('HF_30D_AUDIT_ERROR',repr(e))
    print('HF_PROVENANCE_STATUS','MIRROR_REQUIRES_DIRECT_DOLTHUB_GATE')

def main():
    alpha_vantage_probe(); read_panel(); print('DEEP_SOURCE_AUDIT_DONE')
if __name__=='__main__': main()
