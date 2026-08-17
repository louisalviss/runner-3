#!/usr/bin/env python3
import io, csv, requests
from datetime import datetime

FUNDS={
 'MTUM':('251614','ishares-msci-usa-momentum-factor-etf'),
 'IMTM':('271538','ishares-msci-intl-momentum-factor-etf'),
}
DATES=['20150529','20150601','20151130','20151201','20160531','20160601','20161130','20161201','20230531','20230601','20231130','20231201','20240531','20240603','20241129','20241202','20250530','20250602','20251128','20251201']
HEAD={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36','Accept':'text/csv,*/*'}
for fund,(pid,slug) in FUNDS.items():
    print('\n###',fund)
    for d in DATES:
        url=f'https://www.ishares.com/us/products/{pid}/{slug}/1467271812596.ajax'
        params={'fileType':'csv','fileName':f'{fund}_holdings','dataType':'fund','asOfDate':d}
        try:
            r=requests.get(url,params=params,headers=HEAD,timeout=30)
            txt=r.content.decode('utf-8-sig',errors='replace')
            ok=(r.status_code==200 and len(txt)>500 and ('Weight (%)' in txt or 'Market Value' in txt))
            print(d,'status',r.status_code,'len',len(txt),'ok',ok,'type',r.headers.get('content-type'))
            if ok:
                lines=txt.splitlines()
                # locate header containing Ticker/Weight
                hi=next((i for i,x in enumerate(lines) if 'Ticker' in x and 'Weight (%)' in x),None)
                if hi is not None:
                    rows=list(csv.DictReader(lines[hi:]))
                    eq=[]
                    for row in rows:
                        try:w=float((row.get('Weight (%)') or '').replace(',',''))
                        except:continue
                        ticker=(row.get('Ticker') or '').strip()
                        asset=(row.get('Asset Class') or '').strip()
                        if ticker and asset=='Equity':eq.append((w,ticker,row.get('Name','')))
                    eq.sort(reverse=True)
                    print(' TOP5',eq[:5])
        except Exception as e:
            print(d,'ERR',repr(e))
