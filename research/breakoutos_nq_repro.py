#!/usr/bin/env python3
from __future__ import annotations
import csv, json, math, os, statistics
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

CT=ZoneInfo('America/Chicago')
UTC=ZoneInfo('UTC')
OUT=Path(os.getenv('OUT','evidence/breakoutos-nq-repro')); OUT.mkdir(parents=True,exist_ok=True)
DUKA=Path(os.getenv('DUKA_CSV','/tmp/usatech_h1.csv'))
CCI_N=27; CCI_LB=18; CCI_T=-100.0; ATR_N=40; ATR_K=0.8

@dataclass
class Bar:
    ts:int; o:float; h:float; l:float; c:float
    @property
    def dt(self): return datetime.fromtimestamp(self.ts,UTC)
    @property
    def ct(self): return self.dt.astimezone(CT)

def yahoo_nq():
    url='https://query1.finance.yahoo.com/v8/finance/chart/NQ%3DF'
    p={'interval':'60m','range':'729d','includePrePost':'true','events':'div,splits'}
    r=requests.get(url,params=p,headers={'User-Agent':'Mozilla/5.0'},timeout=30); r.raise_for_status(); j=r.json()['chart']['result'][0]
    q=j['indicators']['quote'][0]; bars=[]
    for i,ts in enumerate(j['timestamp']):
        vals=(q['open'][i],q['high'][i],q['low'][i],q['close'][i])
        if any(v is None for v in vals): continue
        bars.append(Bar(int(ts),*(float(v) for v in vals)))
    return bars,{'source':'Yahoo Finance chart API NQ=F','instrument':'front continuous NQ=F','rows':len(bars),'first':bars[0].dt.isoformat(),'last':bars[-1].dt.isoformat()}

def parse_ts(x):
    x=str(x).strip()
    try:
        v=float(x)
        if v>1e12: v/=1000
        return int(v)
    except: pass
    d=datetime.fromisoformat(x.replace('Z','+00:00'))
    if d.tzinfo is None: d=d.replace(tzinfo=UTC)
    return int(d.timestamp())

def duka_proxy():
    bars=[]
    with DUKA.open(newline='') as f:
        for row in csv.DictReader(f):
            keys={k.lower():k for k in row}
            try:
                ts=parse_ts(row[keys['timestamp']]); o=float(row[keys['open']]); h=float(row[keys['high']]); l=float(row[keys['low']]); c=float(row[keys['close']])
            except Exception: continue
            bars.append(Bar(ts,o,h,l,c))
    bars.sort(key=lambda b:b.ts)
    return bars,{'source':'Dukascopy USATECH.IDX/USD','instrument':'NASDAQ-100 CFD proxy, not NQ futures','rows':len(bars),'first':bars[0].dt.isoformat(),'last':bars[-1].dt.isoformat()}

def rma(vals,n):
    out=[None]*len(vals); seed=[]; p=None
    for i,x in enumerate(vals):
        if p is None:
            seed.append(x)
            if len(seed)==n: p=sum(seed)/n; out[i]=p
        else:
            p=(p*(n-1)+x)/n; out[i]=p
    return out

def indicators(bars):
    tr=[]
    for i,b in enumerate(bars): tr.append(b.h-b.l if i==0 else max(b.h-b.l,abs(b.h-bars[i-1].c),abs(b.l-bars[i-1].c)))
    atr=rma(tr,ATR_N)
    tp=[(b.h+b.l+b.c)/3 for b in bars]; cci=[None]*len(bars)
    for i in range(CCI_N-1,len(bars)):
        w=tp[i-CCI_N+1:i+1]; ma=sum(w)/CCI_N; md=sum(abs(x-ma) for x in w)/CCI_N
        cci[i]=0.0 if md==0 else (tp[i]-ma)/(0.015*md)
    return atr,cci

def session_maps(bars):
    by={}
    for i,b in enumerate(bars):
        d=b.ct.date()
        if b.ct.weekday()>=5: continue
        by.setdefault(d,[]).append(i)
    days=sorted(by)
    prev={}
    for k in range(1,len(days)):
        pd=days[k-1]; d=days[k]
        prev[d]=min(bars[i].l for i in by[pd])
    return by,days,prev

def cci_ok(cci,signal_i):
    a=signal_i-CCI_LB+1
    if a<0: return False
    w=cci[a:signal_i+1]
    return len(w)==CCI_LB and all(x is not None for x in w) and min(w)<CCI_T

def run_dynamic(bars, filtered=False):
    atr,cci=indicators(bars); by,days,pdl=session_maps(bars); trades=[]
    for d in days:
        if d not in pdl: continue
        inds=by[d]; entry=None; entry_i=None; level_used=None
        for pos,i in enumerate(inds):
            if pos==0:
                sig_i=i-1
            else:
                sig_i=inds[pos-1]
            if sig_i<0 or atr[sig_i] is None: continue
            if filtered and not cci_ok(cci,sig_i): continue
            level=pdl[d]+ATR_K*atr[sig_i]
            b=bars[i]
            if b.h>=level:
                px=b.o if b.o>level else level
                entry=px; entry_i=i; level_used=level; break
        if entry is not None:
            exit_i=inds[-1]; exit_px=bars[exit_i].c
            trades.append({'date':str(d),'entry_ts':bars[entry_i].ts,'exit_ts':bars[exit_i].ts,'entry':entry,'exit':exit_px,'points':exit_px-entry,'level':level_used})
    return trades

def run_dayfixed(bars, filtered=False):
    atr,cci=indicators(bars); by,days,pdl=session_maps(bars); trades=[]
    for d in days:
        if d not in pdl: continue
        inds=by[d]; first=inds[0]; sig_i=first-1
        if sig_i<0 or atr[sig_i] is None: continue
        if filtered and not cci_ok(cci,sig_i): continue
        level=pdl[d]+ATR_K*atr[sig_i]
        entry=None; entry_i=None
        for i in inds:
            b=bars[i]
            if b.h>=level:
                entry=b.o if b.o>level else level; entry_i=i; break
        if entry is not None:
            exit_i=inds[-1]; exit_px=bars[exit_i].c
            trades.append({'date':str(d),'entry_ts':bars[entry_i].ts,'exit_ts':bars[exit_i].ts,'entry':entry,'exit':exit_px,'points':exit_px-entry,'level':level})
    return trades

def metric(ts,cost_points=0.0,mult=1.0):
    vals=[t['points']-cost_points for t in ts]; gp=sum(max(x,0) for x in vals); gl=sum(max(-x,0) for x in vals)
    eq=peak=0.; mdd=0.
    for x in vals:
        eq+=x; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    net=sum(vals); dd=abs(mdd)
    return {'n':len(vals),'net_points':net,'avg_points':net/len(vals) if vals else None,'PF':gp/gl if gl else None,'maxDD_points':mdd,'profit_dd':net/dd if dd>0 else None,'win_rate':100*sum(x>0 for x in vals)/len(vals) if vals else None,'net_dollars':net*mult,'avg_trade_dollars':(net/len(vals)*mult) if vals else None,'maxDD_dollars':mdd*mult}

def subset(ts,start=None,end=None):
    out=[]
    for t in ts:
        d=date.fromisoformat(t['date'])
        if start and d<start: continue
        if end and d>end: continue
        out.append(t)
    return out

def summarize(base,filt,mult,direct):
    costs=[0.0,0.5,1.0] if not direct else [0.0,0.5,1.0] # points RT; NQ 1 point=$20
    periods={'all':(None,None),'2024':(date(2024,1,1),date(2024,12,31)),'2025':(date(2025,1,1),date(2025,12,31)),'2026':(date(2026,1,1),date(2026,12,31)),'post_publication':(date(2026,5,15),None),'last5y':(date(2021,1,1),None)}
    out={}
    for name,(a,z) in periods.items():
        B=subset(base,a,z); F=subset(filt,a,z)
        out[name]={}
        for c in costs:
            bm=metric(B,c,mult); fm=metric(F,c,mult)
            out[name][str(c)]={'base':bm,'cci':fm,'delta':{'trade_retention':fm['n']/bm['n'] if bm['n'] else None,'delta_avg_points':(fm['avg_points']-bm['avg_points']) if bm['avg_points'] is not None and fm['avg_points'] is not None else None,'delta_profit_dd':(fm['profit_dd']-bm['profit_dd']) if bm['profit_dd'] is not None and fm['profit_dd'] is not None else None,'delta_net_points':fm['net_points']-bm['net_points']}}
    return out

def evaluate(name,bars,meta,mult,direct):
    bars=sorted({b.ts:b for b in bars}.values(),key=lambda b:b.ts)
    result={'dataset':name,'meta':meta,'rules':{'base':'long stop; previous trading-day low + 0.8*ATR(40); 60m; CT calendar sessions; EOD exit','cci':'Lowest(CCI(27),18)<-100 evaluated on completed signal bar'},'conventions':{}}
    for conv,runner in [('dynamic_next_bar',run_dynamic),('day_fixed',run_dayfixed)]:
        b=runner(bars,False); f=runner(bars,True)
        result['conventions'][conv]={'summary':summarize(b,f,mult,direct),'base_trades':b,'cci_trades':f}
    return result

def compact(r):
    c={}
    for conv,v in r['conventions'].items():
        c[conv]={}
        for p in ('all','2024','2025','2026','post_publication','last5y'):
            x=v['summary'][p]['0.0']; c[conv][p]=x
    return c

def main():
    datasets=[]
    try:
        y,ym=yahoo_nq(); datasets.append(('NQ_YAHOO_60M',y,ym,20.0,True))
    except Exception as e:
        (OUT/'yahoo_error.txt').write_text(repr(e))
    if DUKA.exists():
        d,dm=duka_proxy(); datasets.append(('USATECH_DUKA_H1_PROXY',d,dm,1.0,False))
    final={'article_claims':{'base_profit_dd':7.53,'cci_profit_dd':8.6,'base_avg_trade_dollars':116,'cci_avg_trade_dollars':149},'datasets':{}}
    for name,bars,meta,mult,direct in datasets:
        r=evaluate(name,bars,meta,mult,direct); final['datasets'][name]=r
        print('RESULT',name,json.dumps(compact(r),separators=(',',':')))
    (OUT/'summary.json').write_text(json.dumps(final,indent=2,default=str))
    # light compact file
    (OUT/'compact.json').write_text(json.dumps({k:compact(v) for k,v in final['datasets'].items()},indent=2))
if __name__=='__main__': main()
