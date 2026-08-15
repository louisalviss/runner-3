#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).with_name('backtest.py')
s=p.read_text()
start=s.index('# Add name-search fallback candidates only when N-PORT ticker is absent.')
end_marker="Path(OUT/'name_ticker_fallback.json').write_text(json.dumps(name_cache,indent=2))"
end=s.index(end_marker,start)+len(end_marker)
replacement=r'''# Add name-search fallback candidates only when N-PORT ticker is absent.
# Resolve unique issuer titles concurrently; title preserves share class better than issuer name.
from concurrent.futures import ThreadPoolExecutor, as_completed
sess_headers={'User-Agent':'Mozilla/5.0'}
missing=[]
for h in frames.values():
    for _,r in h[h.ticker.isna()].iterrows():
        key=(str(r.get('ISSUER_TITLE') or r['name']).strip(),str(r['name']).strip())
        missing.append(key)
missing=sorted(set(missing))

def lookup(pair):
    title,name=pair
    import requests as _rq
    ss=_rq.Session();ss.headers.update(sess_headers)
    for q in (title,name):
        try:
            js=ss.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q,'quotesCount':8,'newsCount':0},timeout=8).json()
            qs=[z for z in js.get('quotes',[]) if z.get('quoteType')=='EQUITY' and z.get('exchange') in ('NMS','NYQ','NGM','NCM','ASE','PCX')]
            if qs:return pair,norm_ticker(qs[0].get('symbol'))
        except Exception:pass
    return pair,None

pair_map={}
with ThreadPoolExecutor(max_workers=16) as ex:
    futs=[ex.submit(lookup,x) for x in missing]
    for k,f in enumerate(as_completed(futs),1):
        pair,t=f.result();pair_map[pair]=t
        if k%50==0:print('TICKER_RESOLVE',k,'/',len(futs),flush=True)
name_cache={}
for h in frames.values():
    for idx,r in h[h.ticker.isna()].iterrows():
        pair=(str(r.get('ISSUER_TITLE') or r['name']).strip(),str(r['name']).strip())
        t=pair_map.get(pair);h.at[idx,'ticker']=t
        name_cache[pair[0]]=t
Path(OUT/'name_ticker_fallback.json').write_text(json.dumps(name_cache,indent=2))'''
patched=s[:start]+replacement+s[end:]
exec(compile(patched,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
