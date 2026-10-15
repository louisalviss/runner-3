#!/usr/bin/env python3
import argparse,csv,json,requests,datetime,time,concurrent.futures,collections,random
from pathlib import Path
from zoneinfo import ZoneInfo
P=Path(__file__).resolve().parent
a=argparse.ArgumentParser()
a.add_argument('--start',type=int,required=True);a.add_argument('--end',type=int,required=True)
opt=a.parse_args()
all_symbols=sorted({x['symbol'] for x in csv.DictReader(open(P/'PD_ALL_1139_GATE_EVIDENCE_MATRIX.csv'))}|{'SPY'})
targets=all_symbols[opt.start:opt.end]
from_ts=int(datetime.datetime(2026,9,10,tzinfo=datetime.timezone.utc).timestamp())
until_ts=int(datetime.datetime(2026,10,16,tzinfo=datetime.timezone.utc).timestamp())
hdr={'User-Agent':'Mozilla/5.0 (research; non-automated)' }
def fetch(ticker):
 url='https://query1.finance.yahoo.com/v8/finance/chart/'+ticker
 for attempt in range(2):
  try:
   r=requests.get(url,params={'interval':'1d','period1':from_ts,'period2':until_ts,'events':'div,splits'},
                  headers=hdr,timeout=20)
   if r.status_code!=200:
    if r.status_code in (429,500,502,503,504):
     time.sleep(1.5+attempt);continue
    return ticker,{'status':'HTTP_'+str(r.status_code),'bars':{}}
   j=r.json().get('chart',{})
   z=j.get('result')
   if not z:return ticker,{'status':'NO_CHART_RESULT','bars':{}}
   meta=z[0];q=meta['indicators']['quote'][0]
   adjustments=meta['indicators'].get('adjclose') or []
   if not adjustments:return ticker,{'status':'NO_ADJUSTED_PRICE','bars':{}}
   adj=adjustments[0]['adjclose'];out={}
   for i,ts in enumerate(meta.get('timestamp',[])):
    op=q['open'][i];cl=q['close'][i];ac=adj[i]
    if not op or not cl or not ac:continue
    d=datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).date().isoformat()
    if d>='2026-09-10' and d<='2026-10-15':
     factor=ac/cl
     out[d]=[round(op*factor,6),round(ac,6),round(q['low'][i]*factor,6) if q['low'][i] else None]
   return ticker,{'status':'OK','bars':out}
  except Exception as exc:
   if attempt==1:return ticker,{'status':type(exc).__name__,'bars':{}}
 return ticker,{'status':'RETRIES','bars':{}}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 result=dict(pool.map(fetch,targets))
(P/f'PD_OHLC_{opt.start}_{opt.end}.json').write_text(json.dumps(result,separators=(',',':')))
print('OHLC_BATCH',opt.start,opt.end,'N',len(result),'states',dict(collections.Counter(x['status'] for x in result.values())),flush=True)
