#!/usr/bin/env python3
import csv, hashlib, requests

FUNDS={
 'MTUM':('251614','ishares-msci-usa-momentum-factor-etf'),
 'IMTM':('271538','ishares-msci-intl-momentum-factor-etf'),
}
DATES=['20150601','20230601','20251231','20260630']
HEAD={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36','Accept':'text/csv,*/*'}
for fund,(pid,slug) in FUNDS.items():
    print('\n###',fund)
    for d in DATES:
        url=f'https://www.ishares.com/us/products/{pid}/{slug}/1467271812596.ajax'
        params={'fileType':'csv','fileName':f'{fund}_holdings','dataType':'fund','asOfDate':d}
        r=requests.get(url,params=params,headers=HEAD,timeout=30)
        txt=r.content.decode('utf-8-sig',errors='replace')
        lines=txt.splitlines()
        print('\nDATE',d,'status',r.status_code,'len',len(txt),'sha',hashlib.sha256(r.content).hexdigest()[:16],'type',r.headers.get('content-type'),'final',r.url)
        print('HEAD8:')
        for x in lines[:8]: print(repr(x[:240]))
        hi=next((i for i,x in enumerate(lines) if 'Ticker' in x and ('Weight' in x or 'Market Value' in x)),None)
        print('header_index',hi,'line',repr(lines[hi][:300]) if hi is not None else None)
        if hi is not None:
            rows=list(csv.DictReader(lines[hi:]))
            print('fieldnames',list(rows[0].keys()) if rows else [])
            eq=[]
            for row in rows:
                wtkey=next((k for k in row.keys() if k and 'Weight' in k),None)
                try:w=float((row.get(wtkey) or '').replace(',','').replace('%',''))
                except:continue
                ticker=(row.get('Ticker') or '').strip()
                asset=(row.get('Asset Class') or '').strip()
                if ticker and (asset=='Equity' or not asset):eq.append((w,ticker,row.get('Name','')))
            eq.sort(reverse=True)
            print('TOP5',eq[:5])
