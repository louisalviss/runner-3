#!/usr/bin/env python3
import requests
s=requests.Session();s.headers.update({'User-Agent':'Mozilla/5.0'})
qs=['US02079K3059','02079K305','US02079K1079','02079K107','US30231G1022','30231G102','US3696043013','369604301','US0079031078','007903107']
for q in qs:
    try:
        js=s.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q,'quotesCount':5,'newsCount':0},timeout=10).json()
        print(q,[(z.get('symbol'),z.get('shortname'),z.get('exchange'),z.get('quoteType')) for z in js.get('quotes',[])],flush=True)
    except Exception as e: print(q,'ERR',repr(e),flush=True)
