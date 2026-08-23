import io
import json
from urllib.parse import quote

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests

S = requests.Session()
S.headers.update({'User-Agent':'louis-research-deep-audit/1.0'})

HF_EPS = 'siddharthmb/stocks-earnings-eps_estimate'
AV_DEMO = 'https://www.alphavantage.co/query?function=EARNINGS_ESTIMATES&symbol=IBM&apikey=demo'


def get_json(url, timeout=120):
    r=S.get(url,timeout=timeout)
    print('HTTP',r.status_code,url,'bytes',len(r.content))
    r.raise_for_status()
    return r.json()


def alpha_vantage_probe():
    try:
        j=get_json(AV_DEMO)
    except Exception as e:
        print('AV_ERROR',repr(e)); return
    print('AV_TOP_KEYS',json.dumps(list(j.keys())))
    print('AV_JSON_SAMPLE',json.dumps(j,default=str)[:25000])
    # Recursively find likely revision/timestamp keys.
    keys=set()
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                keys.add(k); walk(v)
        elif isinstance(x,list):
            for v in x[:100]: walk(v)
    walk(j)
    print('AV_ALL_KEYS',json.dumps(sorted(keys)))
    revkeys=[k for k in keys if any(s in k.lower() for s in ('revision','estimate','analyst','date','period','eps','revenue'))]
    print('AV_RELEVANT_KEYS',json.dumps(sorted(revkeys)))
    text=json.dumps(j).lower()
    print('AV_HAS_REVISION_TOKEN', 'revision' in text)


def parquet_urls(did):
    j=get_json(f'https://datasets-server.huggingface.co/parquet?dataset={quote(did)}')
    return [x['url'] for x in j.get('parquet_files',[])]


def read_panel():
    urls=parquet_urls(HF_EPS)
    print('HF_URL_COUNT',len(urls))
    cols=['date','act_symbol','period','period_end_date','consensus','recent','count','high','low','year_ago']
    frames=[]
    total_bytes=0
    for i,u in enumerate(urls):
        r=S.get(u,timeout=300)
        print('HF_DOWNLOAD',i,r.status_code,len(r.content))
        r.raise_for_status(); total_bytes += len(r.content)
        pf=pq.ParquetFile(io.BytesIO(r.content))
        avail=[c for c in cols if c in pf.schema.names]
        frames.append(pf.read(columns=avail).to_pandas())
    df=pd.concat(frames,ignore_index=True)
    print('HF_TOTAL_BYTES',total_bytes)
    print('HF_SHAPE',df.shape)
    print('HF_COLUMNS',json.dumps(list(df.columns)))
    df['date']=pd.to_datetime(df['date'],errors='coerce')
    df['period_end_date']=pd.to_datetime(df['period_end_date'],errors='coerce')
    for c in ['consensus','recent','count','high','low','year_ago']:
        if c in df: df[c]=pd.to_numeric(df[c],errors='coerce')
    print('HF_DATE_RANGE',str(df.date.min()),str(df.date.max()))
    print('HF_PERIOD_END_RANGE',str(df.period_end_date.min()),str(df.period_end_date.max()))
    print('HF_SYMBOLS',int(df.act_symbol.nunique()))
    print('HF_PERIOD_TYPES',json.dumps(df.period.value_counts(dropna=False).head(20).to_dict(),default=int))
    # snapshot frequency
    dates=pd.Series(sorted(df.date.dropna().unique()))
    gaps=dates.diff().dt.days.dropna()
    print('HF_DISTINCT_DATES',len(dates))
    print('HF_DATE_GAP_DAYS',json.dumps({'median':float(gaps.median()),'p10':float(gaps.quantile(.1)),'p90':float(gaps.quantile(.9)),'min':float(gaps.min()),'max':float(gaps.max())}))
    print('HF_ROWS_PER_DATE',json.dumps({'median':float(df.groupby('date').size().median()),'p10':float(df.groupby('date').size().quantile(.1)),'p90':float(df.groupby('date').size().quantile(.9))}))

    # Key uniqueness and true revision behavior.
    key=['act_symbol','period','period_end_date']
    valid=df.dropna(subset=['date','act_symbol','period','period_end_date']).sort_values(key+['date']).copy()
    g=valid.groupby(key,sort=False)
    sizes=g.size()
    multi=sizes[sizes>=2]
    print('HF_GROUPS',len(sizes),'MULTI_GROUPS',len(multi),'PCT_MULTI',float((sizes>=2).mean()))
    # Sample only multi groups using merge rather than huge .loc index.
    mk=multi.reset_index()[key]
    m=valid.merge(mk,on=key,how='inner')
    gg=m.groupby(key,sort=False)
    nun=gg.consensus.nunique(dropna=True)
    first=gg.consensus.first(); last=gg.consensus.last()
    diff=(first-last).abs()
    revisions=gg.consensus.apply(lambda s:int((s.diff().abs()>1e-12).sum()))
    print('HF_REVISION_BEHAVIOR',json.dumps({
        'multi_groups':int(len(nun)),
        'groups_with_consensus_change':int((nun>1).sum()),
        'pct_groups_with_consensus_change':float((nun>1).mean()),
        'groups_first_last_diff':int((diff>1e-12).sum()),
        'pct_first_last_diff':float((diff>1e-12).mean()),
        'median_revision_events':float(revisions.median()),
        'p90_revision_events':float(revisions.quantile(.9)),
        'p99_revision_events':float(revisions.quantile(.99)),
    }))

    # Causality sanity: observation dates relative to period end.
    lead=(valid.period_end_date-valid.date).dt.days
    print('HF_LEAD_DAYS',json.dumps({
        'median':float(lead.median()),'p10':float(lead.quantile(.1)),'p90':float(lead.quantile(.9)),
        'pct_observed_after_period_end':float((lead<0).mean()),
        'pct_0_365_before':float(((lead>=0)&(lead<=365)).mean())
    }))

    # Check same-day duplicates with conflicting consensus.
    dkey=key+['date']
    ds=valid.groupby(dkey).agg(n=('consensus','size'),nu=('consensus','nunique')).reset_index()
    print('HF_DUPLICATE_KEYS',json.dumps({'groups_n_gt1':int((ds.n>1).sum()),'groups_conflicting_consensus':int((ds.nu>1).sum())}))

    # Cross-sectional coverage by year and periods.
    valid['year']=valid.date.dt.year
    cov=valid.groupby(['year','period']).agg(rows=('act_symbol','size'),symbols=('act_symbol','nunique'),dates=('date','nunique')).reset_index()
    print('HF_COVERAGE_BY_YEAR_PERIOD',cov.to_json(orient='records'))

    # Quantify 30d revision availability using asof within each key, no return outcomes.
    # Use 21-45 day prior observation to avoid exact-calendar dependence.
    samples=[]
    for name,grp in valid.groupby(key,sort=False):
        grp=grp.dropna(subset=['consensus']).sort_values('date')
        if len(grp)<2: continue
        arrd=grp.date.values.astype('datetime64[D]').astype('int64')
        arrv=grp.consensus.to_numpy(float)
        for i in range(1,len(grp)):
            diffs=arrd[i]-arrd[:i]
            idx=np.where((diffs>=21)&(diffs<=45))[0]
            if idx.size:
                j=idx[-1]
                old=arrv[j]; new=arrv[i]
                if np.isfinite(old) and np.isfinite(new):
                    samples.append((new-old, old, new))
    if samples:
        a=np.asarray(samples,float)
        print('HF_30D_REVISION_SAMPLES',json.dumps({
            'n':int(len(a)),
            'pct_up':float((a[:,0]>0).mean()),
            'pct_down':float((a[:,0]<0).mean()),
            'pct_flat':float((a[:,0]==0).mean()),
            'median_abs_change':float(np.median(np.abs(a[:,0]))),
        }))
    else:
        print('HF_30D_REVISION_SAMPLES',json.dumps({'n':0}))

    # Provenance remains the gating problem.
    print('HF_PROVENANCE_VERDICT','UNRESOLVED_NO_DATASET_CARD_SOURCE_OR_LICENSE')


def main():
    alpha_vantage_probe()
    read_panel()
    print('DEEP_SOURCE_AUDIT_DONE')

if __name__=='__main__': main()
