#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv, io, importlib.util, json, math, statistics, sys, time, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'wave-rider-verify'/'reference_verify.py'
spec=importlib.util.spec_from_file_location('wrref', REF)
assert spec and spec.loader
wr=importlib.util.module_from_spec(spec); sys.modules[spec.name]=wr; spec.loader.exec_module(wr)

START=date(2025,1,1)
END=date(2026,8,14)
WARMUP_MONTH='2024-12'
TF=5
S3='https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'
PREFIX='data/futures/um/monthly/klines/'
UA='wr-full-universe-5m/1.0'

# Explicit non-crypto USD-M contracts observed in the 2026 archive/current exchange universe.
# We exclude these only from the crypto breadth summary; raw rows are not otherwise Stage1-filtered.
NONCRYPTO_BASES=set('AAOI AAPL AMD AMZN ARM AVGO AXTI BILL BZ CL COIN COPPER CRCL CRWV DELL DRAM EWY GLW GOOGL HOOD IBM INTC KORU META MRVL MSTR MU NBIS NOK NVDA PLTR QQQ RKLB SAMSUNG SKHYNIX SKHY SNDK SNXX SOXL SOXS SPCX SPX SPY TSLA TSM WDC XAG XAU'.split())


def list_symbols():
    sess=requests.Session(); marker=None; out=[]
    while True:
        url=f"{S3}?delimiter=/&prefix={quote(PREFIX,safe='/')}"
        if marker: url += f"&marker={quote(marker,safe='/')}"
        r=sess.get(url,headers={'User-Agent':UA},timeout=45); r.raise_for_status()
        root=ET.fromstring(r.content); ns={'s3':'http://s3.amazonaws.com/doc/2006-03-01/'}
        ps=[x.text or '' for x in root.findall('s3:CommonPrefixes/s3:Prefix',ns)]
        out.extend(ps)
        trunc=(root.findtext('s3:IsTruncated',default='false',namespaces=ns) or 'false').lower()=='true'
        if not trunc: break
        nm=root.findtext('s3:NextMarker',default='',namespaces=ns) or (ps[-1] if ps else '')
        if not nm or nm==marker: raise RuntimeError('S3 pagination stalled')
        marker=nm
    syms=[]
    for p in sorted(set(out)):
        tail=p[len(PREFIX):].strip('/') if p.startswith(PREFIX) else ''
        if tail.endswith('USDT'): syms.append(tail.upper())
    return sorted(set(syms))


def month_iter(a:date,b:date):
    y,m=a.year,a.month
    while (y,m) <= (b.year,b.month):
        yield y,m
        m+=1
        if m==13: y+=1; m=1


def parse_zip(content:bytes):
    rows=[]; prices=[]
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit(): continue
        try:
            ot=int(row[0]); ct=int(row[6]); o,h,l,c=map(float,row[1:5])
        except Exception:
            continue
        rows.append(wr.Bar(ot,ct,o,h,l,c)); prices.extend(row[1:5])
    return rows,prices


def fetch_symbol(symbol:str):
    sess=requests.Session(); sess.headers['User-Agent']=UA
    bars=[]; prices=[]; fetched=[]; missing=[]
    # One warmup month + evaluation full months through Jul-2026.
    months=[(2024,12)] + [(y,m) for y,m in month_iter(START,date(2026,7,31))]
    for y,m in months:
        ym=f'{y:04d}-{m:02d}'
        url=f'https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{TF}m/{symbol}-{TF}m-{ym}.zip'
        try:
            r=sess.get(url,timeout=40)
            if r.status_code==404:
                missing.append(ym); continue
            r.raise_for_status(); rr,pp=parse_zip(r.content); bars.extend(rr); prices.extend(pp); fetched.append(ym)
        except Exception:
            missing.append(ym)
    # Current partial month via daily archive.
    d=date(2026,8,1)
    while d<=END:
        ds=d.isoformat(); url=f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{TF}m/{symbol}-{TF}m-{ds}.zip'
        try:
            r=sess.get(url,timeout=40)
            if r.status_code==404:
                missing.append(ds); d+=timedelta(days=1); continue
            r.raise_for_status(); rr,pp=parse_zip(r.content); bars.extend(rr); prices.extend(pp); fetched.append(ds)
        except Exception:
            missing.append(ds)
        d+=timedelta(days=1)
    ded={b.ot:b for b in bars}; bars=[ded[k] for k in sorted(ded)]
    tick=wr.infer_tick(prices) if prices else None
    return bars,tick,fetched,missing


def q(xs,p):
    if not xs: return None
    s=sorted(xs); x=(len(s)-1)*p; lo=int(math.floor(x)); hi=int(math.ceil(x))
    if lo==hi:return s[lo]
    return s[lo]*(hi-x)+s[hi]*(x-lo)


def pf(rs):
    gp=sum(x for x in rs if x>0); gl=-sum(x for x in rs if x<0)
    return gp/gl if gl>0 else None


def segments(rs):
    n=len(rs)
    if not n:return {}
    c1=max(1,int(n*.60)); c2=min(n,max(c1+1,int(n*.80))) if n>=5 else n
    parts={'train60':rs[:c1],'valid20':rs[c1:c2],'final20':rs[c2:]}
    return {k:(sum(v)/len(v) if v else None) for k,v in parts.items()}


def blocks50(rs):
    vals=[]
    for i in range(0,len(rs),50):
        x=rs[i:i+50]
        if len(x)==50: vals.append(sum(x)/50)
    return {'n':len(vals),'positive':sum(x>0 for x in vals),'positive_share':(sum(x>0 for x in vals)/len(vals) if vals else None),'min_avg_r':min(vals) if vals else None,'median_avg_r':q(vals,.5) if vals else None}


def analyze_symbol(symbol):
    bars,tick,fetched,missing=fetch_symbol(symbol)
    if not bars or tick is None:
        return {'symbol':symbol,'base':symbol[:-4],'crypto':symbol[:-4] not in NONCRYPTO_BASES,'status':'NO_DATA','fetched_units':len(fetched),'missing_units':len(missing)}
    st=int(datetime(START.year,START.month,START.day,tzinfo=timezone.utc).timestamp()*1000)
    en=int((datetime(END.year,END.month,END.day,tzinfo=timezone.utc)+timedelta(days=1)).timestamp()*1000)-1
    # Skip symbols with no evaluation bars.
    evalbars=[b for b in bars if st<=b.ct<=en]
    if len(evalbars)<100:
        return {'symbol':symbol,'base':symbol[:-4],'crypto':symbol[:-4] not in NONCRYPTO_BASES,'status':'INSUFFICIENT_BARS','bars':len(evalbars),'tick':tick,'fetched_units':len(fetched),'missing_units':len(missing)}
    wr.SYMBOL=symbol
    trades,base=wr.run(TF,bars,tick,st,en)
    rs=[float(t.canon_r) for t in trades]
    stop_pct=[abs(float(t.entry)-float(t.stop))/abs(float(t.entry))*100 for t in trades if float(t.entry)!=0]
    req=[1.0/x for x in stop_pct if x>0]
    net={}
    for bps in (4,6,8,10):
        net[str(bps)]=sum(r-(bps/100.0)/sp for r,sp in zip(rs,stop_pct)) if len(stop_pct)==len(rs) else None
    seg=segments(rs); blk=blocks50(rs)
    strict=(len(rs)>=100 and (sum(rs)/len(rs) if rs else 0)>0 and net.get('6',-1)>0 and all(seg.get(k) is not None and seg.get(k)>0 for k in ('train60','valid20','final20')) and (blk['positive_share'] is not None and blk['positive_share']>=0.60))
    first=evalbars[0].ot if evalbars else None; last=evalbars[-1].ct if evalbars else None
    return {
        'symbol':symbol,'base':symbol[:-4],'crypto':symbol[:-4] not in NONCRYPTO_BASES,'status':'OK','bars':len(evalbars),'tick':tick,
        'first_bar_utc':wr.iso(first) if first else None,'last_bar_utc':wr.iso(last) if last else None,
        'n':len(rs),'avg_r':(sum(rs)/len(rs) if rs else None),'total_r':sum(rs),'pf_r':pf(rs),
        'win_rate':(100*sum(r>0 for r in rs)/len(rs) if rs else None),'max_dd_pct':base.get('max_dd_pct'),'max_losing_streak':base.get('max_losing_streak'),
        'stop_pct_p50':q(stop_pct,.5),'stop_pct_p90':q(stop_pct,.9),'req_x_p50':q(req,.5),'req_x_p90':q(req,.9),'req_x_max':max(req) if req else None,
        'net_r_4bps':net.get('4'),'net_r_6bps':net.get('6'),'net_r_8bps':net.get('8'),'net_r_10bps':net.get('10'),
        'segment_avg_r':seg,'blocks50':blk,'strict_breadth_candidate':strict,
        'fetched_units':len(fetched),'missing_units':len(missing)
    }


def run_chunk(chunk,chunks,out):
    syms=list_symbols(); part=syms[chunk::chunks]
    rows=[]
    for i,s in enumerate(part,1):
        try:r=analyze_symbol(s)
        except Exception as e:r={'symbol':s,'base':s[:-4],'crypto':s[:-4] not in NONCRYPTO_BASES,'status':'ERROR','error':repr(e)}
        rows.append(r)
        print(f'[{chunk}] {i}/{len(part)} {s} {r.get("status")} N={r.get("n")} AvgR={r.get("avg_r")}',flush=True)
    Path(out).write_text(json.dumps({'chunk':chunk,'chunks':chunks,'symbols_total':len(syms),'rows':rows},indent=2),encoding='utf-8')


def merge(indir,out):
    rows=[]
    for p in sorted(Path(indir).glob('chunk_*.json')):
        rows.extend(json.loads(p.read_text())['rows'])
    ok=[r for r in rows if r.get('status')=='OK' and r.get('crypto')]
    trad=[r for r in rows if r.get('status')=='OK' and not r.get('crypto')]
    eligible=[r for r in ok if (r.get('n') or 0)>=100]
    def cnt(pred): return sum(1 for r in eligible if pred(r))
    summary={
      'strategy':'Wave Rider v2.5.13 exact reference','timeframe':'5m','period':[START.isoformat(),END.isoformat()],
      'archive_usdt_symbols':len(rows),'crypto_ok_symbols':len(ok),'explicit_noncrypto_ok_symbols':len(trad),'crypto_n_ge_100':len(eligible),
      'breadth':{
        'avg_r_positive':cnt(lambda r:(r.get('avg_r') or -999)>0),
        'net_6bps_positive':cnt(lambda r:(r.get('net_r_6bps') or -999)>0),
        'all_60_20_20_segments_positive':cnt(lambda r:all((r.get('segment_avg_r') or {}).get(k) is not None and (r['segment_avg_r'][k]>0) for k in ('train60','valid20','final20'))),
        'positive_50block_share_ge_60pct':cnt(lambda r:(r.get('blocks50') or {}).get('positive_share') is not None and r['blocks50']['positive_share']>=.60),
        'strict_candidates':cnt(lambda r:r.get('strict_breadth_candidate') is True),
      },
      'notes':['No Stage1/Stage2/Day/Zone filters.','Universe is all archived Binance USD-M USDT contracts with explicit known TradFi/commodity bases excluded from crypto breadth summary.','5m monthly archive bars are fed directly to the same v2.5.13 reference run() engine; Aug 1-14 uses official daily 5m archive.','Strict candidate is diagnostic, not a production rule: N>=100, AvgR>0, net@6bps>0, all mechanical 60/20/20 segments positive, and >=60% complete 50-trade blocks positive.']
    }
    ranked=sorted(eligible,key=lambda r:(r.get('avg_r') if r.get('avg_r') is not None else -999),reverse=True)
    payload={'summary':summary,'ranked_crypto':ranked,'all_rows':rows}
    Path(out).write_text(json.dumps(payload,indent=2),encoding='utf-8')
    # compact CSV
    cols=['symbol','n','avg_r','total_r','pf_r','win_rate','max_dd_pct','stop_pct_p50','req_x_p50','req_x_p90','net_r_6bps','net_r_8bps','strict_breadth_candidate']
    with Path(out).with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for r in ranked:w.writerow({k:r.get(k) for k in cols})
    print(json.dumps(summary,indent=2))
    print('TOP 30')
    for r in ranked[:30]:
        print(r['symbol'],r['n'],round(r['avg_r'],4),round(r['net_r_6bps'],2),r['strict_breadth_candidate'])


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--chunk',type=int); ap.add_argument('--chunks',type=int,default=16); ap.add_argument('--out',default='chunk_0.json'); ap.add_argument('--merge'); ap.add_argument('--merged-out',default='full_universe_5m.json')
    a=ap.parse_args()
    if a.merge: merge(a.merge,a.merged_out)
    else:
        if a.chunk is None: raise SystemExit('--chunk required')
        run_chunk(a.chunk,a.chunks,a.out)

if __name__=='__main__': main()
