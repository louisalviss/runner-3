#!/usr/bin/env python3
import re
from pathlib import Path
import pandas as pd
import yfinance as yf
import audit_legacy_exact_section as base

RB=pd.Timestamp('2017-09-15')
SNAP=pd.Timestamp('2017-10-31')
EXIT=pd.Timestamp('2018-03-16')
ACC='0001193125-18-002695'
URL='https://www.sec.gov/Archives/edgar/data/1378872/000119312518002695/d473179dncsr.htm'

t=base.flatten(base.fetch(URL))
pat=re.compile(r'PowerShares\s+S&P\s*500(?:\s*®)?\s+Momentum\s+Portfolio\s*\(SPMO\)\s*\(continued\)',re.I)
matches=list(pat.finditer(t))
if not matches: raise RuntimeError('No SPMO continued schedule heading')
# Choose the continuation that explicitly carries the target report date and schedule totals.
cand=[]
for m in matches:
    post=t[m.start():m.start()+5000]
    score=(100 if 'October 31, 2017' in post[:1500] else 0)+(100 if 'Net Assets—100.0%' in post else 0)+(100 if 'Number of Shares' in post[:1500] else 0)
    cand.append((score,m.start()))
score,cont_start=max(cand)
if score<300: raise RuntimeError(f'No exact target continuation; score={score}')

# The SPMO schedule may span several pages. The last Net Assets—100% boundary before
# the target continuation is the prior fund's schedule end. Start immediately after it.
lookback=max(0,cont_start-150000)
prior=t[lookback:cont_start]
prev=list(re.finditer(r'Net Assets\s*[—-]\s*100\.0%[^\n]*',prior,re.I))
if not prev: raise RuntimeError('Prior fund Net Assets boundary not found')
start=lookback+prev[-1].end()
cur=re.search(r'Net Assets\s*[—-]\s*100\.0%[^\n]*',t[cont_start:cont_start+10000],re.I)
if not cur: raise RuntimeError('SPMO Net Assets boundary not found')
end=cont_start+cur.end()
z=t[start:end]
print('MULTIPAGE_SECTION',start,cont_start,end,'chars',len(z),flush=True)

holdings=base.parse_holdings(z)
print('PARSED_HOLDINGS',len(holdings),flush=True)
h=holdings.head(60).copy()
h['ticker']=h['name'].map(base.resolve)
h=h.dropna(subset=['ticker']).drop_duplicates('ticker')
tickers=h.ticker.tolist()
if len(tickers)<30: raise RuntimeError(f'Too few resolved candidates: {len(tickers)}')

d=yf.download(tickers,start=(RB-pd.Timedelta(days=7)).strftime('%Y-%m-%d'),end=(EXIT+pd.Timedelta(days=7)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=False,progress=False)
close,adj,op=base.fld(d,'Close',tickers),base.fld(d,'Adj Close',tickers),base.fld(d,'Open',tickers)
rr=[]
for _,r in h.iterrows():
    tt=r.ticker
    if tt not in close.columns or close[tt].dropna().empty: continue
    try:
        rv=r.snapshot_value*base.at(close,RB,tt)/base.at(close,SNAP,tt)
        cr=base.at(adj,EXIT,tt)/base.at(adj,RB,tt)-1
    except Exception as e:
        print('PRICE_FAIL',tt,repr(e),flush=True); continue
    en=base.after(op,RB+pd.Timedelta(days=1),tt); xo=base.after(op,EXIT+pd.Timedelta(days=1),tt)
    nr=float('nan')
    if en and xo:
        ed,eo=en; xd,xv=xo
        nr=(xv*base.at(adj,xd,tt)/base.at(close,xd,tt))/(eo*base.at(adj,ed,tt)/base.at(close,ed,tt))-1
    rr.append((tt,r['name'],int(r.snapshot_value),rv,cr,nr))
ranked=pd.DataFrame(rr,columns=['ticker','name','snapshot_value','reconstructed_value','close_return','next_open_return']).sort_values('reconstructed_value',ascending=False)
print('RANKED\n'+ranked.head(20).to_string(index=False),flush=True)
if len(ranked)<2: raise RuntimeError('Too few priced candidates')
top=ranked.iloc[0]
margin=float(top.reconstructed_value/ranked.iloc[1].reconstructed_value-1)
result=pd.DataFrame([{
 'rebalance_date':RB.strftime('%Y-%m-%d'),'snapshot_date':SNAP.strftime('%Y-%m-%d'),'exit_date':EXIT.strftime('%Y-%m-%d'),
 'top1':top.ticker,'reconstructed_top1_value':float(top.reconstructed_value),'close_to_close_return':float(top.close_return),
 'next_open_return':float(top.next_open_return),'candidate_scope':'exact multipage SPMO schedule direct SEC; top60 snapshot holdings',
 'source_accession':ACC,'top1_margin_vs_2':margin,'parsed_holdings':len(holdings)
}])
out=Path('spmo-backtest/output'); out.mkdir(parents=True,exist_ok=True)
result.to_csv(out/'legacy_exact_2017-09-15_final.csv',index=False)
print('FINAL_2017SEP\n'+result.to_string(index=False),flush=True)
