#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).with_name('backtest.py')
s=p.read_text()

# 1) Extend Yahoo price/actions download through the current research date so
# validation sees splits that happened after the Mar-2026 backtest exit.
s=s.replace("end=(NEXT_RB[TARGETS[-1][0]]+pd.Timedelta(days=10)).strftime('%Y-%m-%d')","end='2026-08-16'")

# 2) Resolve each security by stable identifiers before fuzzy issuer-name search.
start=s.index('# Add name-search fallback candidates only when N-PORT ticker is absent.')
end_marker="Path(OUT/'name_ticker_fallback.json').write_text(json.dumps(name_cache,indent=2))"
end=s.index(end_marker,start)+len(end_marker)
resolver=r'''# Resolve missing N-PORT tickers with stable identifiers first.
from concurrent.futures import ThreadPoolExecutor, as_completed
US_EX={'NMS','NYQ','NGM','NCM','ASE','PCX'}
CUSIP_FORCE={
 '02079K305':'GOOGL','02079K107':'GOOG',
 '084670702':'BRK-B','084670108':'BRK-A',
 '30231G102':'XOM','369604301':'GE',
}
missing=[]
for h in frames.values():
    for _,r in h[h.ticker.isna()].iterrows():
        key=(str(r.get('isin') or '').strip(),str(r.get('ISSUER_CUSIP') or '').strip(),
             str(r.get('ISSUER_TITLE') or '').strip(),str(r['name']).strip())
        missing.append(key)
missing=sorted(set(missing))

def lookup(key):
    isin,cusip,title,name=key
    if cusip in CUSIP_FORCE:return key,CUSIP_FORCE[cusip],'force'
    import requests as _rq
    ss=_rq.Session();ss.headers.update({'User-Agent':'Mozilla/5.0'})
    for kind,q in [('isin',isin),('cusip',cusip),('title',title),('name',name)]:
        if not q or q.lower()=='nan':continue
        try:
            js=ss.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q,'quotesCount':10,'newsCount':0},timeout=8).json()
            qs=[z for z in js.get('quotes',[]) if z.get('quoteType')=='EQUITY' and z.get('exchange') in US_EX]
            if qs:return key,norm_ticker(qs[0].get('symbol')),kind
        except Exception:pass
    return key,None,None

id_map={};method_map={}
with ThreadPoolExecutor(max_workers=16) as ex:
    futs=[ex.submit(lookup,x) for x in missing]
    for k,f in enumerate(as_completed(futs),1):
        key,t,m=f.result();id_map[key]=t;method_map[key]=m
        if k%50==0:print('TICKER_RESOLVE',k,'/',len(futs),flush=True)
name_cache={}
for h in frames.values():
    for idx,r in h[h.ticker.isna()].iterrows():
        key=(str(r.get('isin') or '').strip(),str(r.get('ISSUER_CUSIP') or '').strip(),
             str(r.get('ISSUER_TITLE') or '').strip(),str(r['name']).strip())
        t=id_map.get(key);h.at[idx,'ticker']=t
        name_cache[key[1] or key[0] or key[2]]=t
Path(OUT/'name_ticker_fallback.json').write_text(json.dumps(name_cache,indent=2))
Path(OUT/'ticker_resolution_methods.json').write_text(json.dumps({('|'.join(k)):method_map.get(k) for k in id_map},indent=2))'''
s=s[:start]+resolver+s[end:]

# 3) Validate ticker identity accounting for Yahoo's retroactive split adjustment.
start=s.index('# Validate ticker identity against N-PORT implied per-share price at report date.')
end_marker="print('INVALID_TICKER_ROWS',len(miss),'max_reported_pct',miss.reported_pct.max() if len(miss) else 0,flush=True)"
end=s.index(end_marker,start)+len(end_marker)
validation=r'''# Validate ticker identity against N-PORT implied per-share price.
# Yahoo historical Close is retro-adjusted for stock splits. Therefore the expected
# Yahoo/implied ratio is 1 / cumulative splits AFTER the report date, not 1.0.
validation=[]
for rb,h in frames.items():
    for idx,r in h.iterrows():
        t=r.ticker; implied=np.nan
        if str(r.UNIT).upper()=='NS' and pd.notna(r.shares) and r.shares>0: implied=r.value/r.shares
        px=before(rawc,r.report_date,t) if t else np.nan
        future_factor=1.0
        if t in splits.columns:
            ss=splits[t].fillna(0)
            ss=ss[(ss.index>r.report_date)&(ss!=0)]
            for z in ss: future_factor*=float(z)
        expected_ratio=(1.0/future_factor) if future_factor and np.isfinite(future_factor) else 1.0
        ratio=px/implied if np.isfinite(px) and np.isfinite(implied) and implied>0 else np.nan
        relerr=abs(ratio/expected_ratio-1) if np.isfinite(ratio) and expected_ratio else np.nan
        ok=bool(np.isfinite(px) and (not np.isfinite(implied) or (np.isfinite(relerr) and relerr<=0.12)))
        h.at[idx,'ticker_valid']=ok
        h.at[idx,'snapshot_px_ratio']=ratio
        h.at[idx,'expected_split_ratio']=expected_ratio
        h.at[idx,'validation_relerr']=relerr
        validation.append({'rb':rb.date(),'report_date':r.report_date.date(),'name':r['name'],'title':r.get('ISSUER_TITLE'),
                           'cusip':r.get('ISSUER_CUSIP'),'isin':r.get('isin'),'ticker':t,
                           'reported_pct':r.reported_pct,'implied_px':implied,'yahoo_px':px,'ratio':ratio,
                           'expected_ratio':expected_ratio,'relerr':relerr,'valid':ok})
val=pd.DataFrame(validation);val.to_csv(OUT/'ticker_validation.csv',index=False)
miss=val[~val.valid].sort_values(['rb','reported_pct'],ascending=[True,False])
miss.to_csv(OUT/'ticker_invalid.csv',index=False)
print('INVALID_TICKER_ROWS',len(miss),'max_reported_pct',miss.reported_pct.max() if len(miss) else 0,
      'invalid_weight_sum',miss.reported_pct.sum(),flush=True)'''
s=s[:start]+validation+s[end:]

# 4) Rewind disclosed values using the ratio of Yahoo split-adjusted closes.
# Do NOT divide by a split factor again: that would double-count splits.
start=s.index('# Rewind each disclosed post-rebalance snapshot to rebalance close.')
end=s.index('\ntop1=[]',start)
rewind=r'''# Rewind each disclosed post-rebalance snapshot to rebalance close.
# Yahoo Close is consistently split-adjusted across both dates, so its price ratio
# already converts post-split share counts into the correct pre/post-rebalance value.
ranked={};detail=[]
for rb,h in frames.items():
    z=h[h.ticker_valid.fillna(False)].copy(); vals=[]
    for _,r in z.iterrows():
        t=r.ticker; ps=before(rawc,r.report_date,t); pr=before(rawc,rb,t)
        if not np.isfinite(ps) or not np.isfinite(pr) or ps<=0: vals.append(np.nan); continue
        vals.append(r.value*(pr/ps))
    z['rb_value']=vals; z=z[z.rb_value.notna() & (z.rb_value>0)].sort_values('rb_value',ascending=False).reset_index(drop=True)
    z['rank']=np.arange(1,len(z)+1); z['weight']=z.rb_value/z.rb_value.sum()
    ranked[rb]=z
    zz=z.copy();zz.insert(0,'rebalance',rb.date());detail.append(zz)
    print('TOP5',rb.date(),[(x.ticker,round(x.weight*100,2)) for _,x in z.head(5).iterrows()],flush=True)
pd.concat(detail,ignore_index=True).to_csv(OUT/'ranked_holdings.csv',index=False)'''
s=s[:start]+rewind+s[end:]

exec(compile(s,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
