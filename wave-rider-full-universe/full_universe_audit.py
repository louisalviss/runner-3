#!/usr/bin/env python3
from __future__ import annotations
import base64, csv, gzip, importlib.util, io, json, math, os, statistics, sys, tempfile, time, zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET
import requests

START = date(2025,1,1)
END = date(2026,8,14)
WARMUP_DAYS = 3
CHUNK_ID = int(os.getenv('CHUNK_ID','0'))
CHUNK_COUNT = int(os.getenv('CHUNK_COUNT','16'))
BASE_INTERVAL = os.getenv('BASE_INTERVAL','5m')  # 5m job also derives 10m
OUT = Path(os.getenv('OUT_DIR','audit_out'))
OUT.mkdir(parents=True, exist_ok=True)

REFERENCE_REPO='louisalviss/runner-3'
REFERENCE_BLOB_SHA='2ba5f66d33e2e483a4c669c95f3b97778c80fcd0'
REFERENCE_BLOB_URL=f'https://api.github.com/repos/{REFERENCE_REPO}/git/blobs/{REFERENCE_BLOB_SHA}'
S3='https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'
BASE='https://data.binance.vision/data/futures/um'
UA='wr-full-universe-audit/1.0'

# Explicit non-crypto USD-M products observed/anticipated in the archive/current venue.
TRADFI_BASES=set('''AAOI AAPL AMD AMZN ARM AVGO AXTI BILL BZ CL COIN COPPER CRCL CRWV DELL DRAM EWY GLW GOOGL HOOD IBM INTC KORU META MRVL MSFT MSTR MU NBIS NOK NVDA PLTR QQQ RKLB SAMSUNG SKHYNIX SKHY SNDK SNXX SOXL SOXS SPCX SPX SPY TSLA TSM WDC XAG XAU'''.split())

EXPECTED={
 'BNBUSDT':{3:0.066,5:0.363,10:-0.032}, 'TRXUSDT':{3:0.118,5:0.304,10:-0.071},
 'BTCUSDT':{3:0.104,5:0.174,10:-0.087}, 'AAVEUSDT':{3:0.131,5:0.121,10:-0.075},
 'DOTUSDT':{3:0.104,5:0.141,10:0.102}, 'BCHUSDT':{3:-0.027,5:0.129,10:-0.066},
 'LTCUSDT':{3:0.051,5:0.108,10:-0.048}, 'WIFUSDT':{3:0.108,5:-0.137,10:-0.139},
 'DOGEUSDT':{3:0.049,5:0.039,10:0.136}, 'SUIUSDT':{3:0.095,5:0.034,10:0.138},
 'LINKUSDT':{3:-0.004,5:-0.124,10:0.134}, 'AVAXUSDT':{3:0.017,5:0.044,10:0.008},
 'ADAUSDT':{3:-0.007,5:-0.004,10:0.018}, '1000PEPEUSDT':{3:-0.064,5:0.060,10:0.098},
 'NEARUSDT':{3:-0.153,5:-0.119,10:0.032},
}

def list_common_prefixes(prefix:str)->list[str]:
    sess=requests.Session(); marker=None; out=[]
    while True:
        url=f"{S3}?delimiter=/&prefix={quote(prefix,safe='/')}"
        if marker: url += f"&marker={quote(marker,safe='/')}"
        r=sess.get(url,headers={'User-Agent':UA},timeout=60); r.raise_for_status()
        root=ET.fromstring(r.content); ns={'s3':'http://s3.amazonaws.com/doc/2006-03-01/'}
        ps=[x.text or '' for x in root.findall('s3:CommonPrefixes/s3:Prefix',ns)]; out.extend(ps)
        trunc=(root.findtext('s3:IsTruncated',default='false',namespaces=ns) or 'false').lower()=='true'
        if not trunc: break
        nm=root.findtext('s3:NextMarker',default='',namespaces=ns) or (ps[-1] if ps else '')
        if not nm or nm==marker: raise RuntimeError('S3 pagination stalled')
        marker=nm
    return sorted(set(out))

def universe()->list[str]:
    prefix='data/futures/um/monthly/klines/'
    paths=list_common_prefixes(prefix)
    syms=[]
    for p in paths:
        s=p[len(prefix):].strip('/').upper() if p.startswith(prefix) else ''
        if not s.endswith('USDT') or '_' in s: continue
        base=s[:-4]
        if base in TRADFI_BASES: continue
        syms.append(s)
    return sorted(set(syms))

def load_reference():
    r=requests.get(REFERENCE_BLOB_URL,headers={'Accept':'application/vnd.github+json','User-Agent':UA},timeout=60); r.raise_for_status()
    p=r.json(); assert p.get('sha')==REFERENCE_BLOB_SHA
    raw=base64.b64decode(p['content'])
    f=tempfile.NamedTemporaryFile(suffix='.py',delete=False); f.write(raw); f.close()
    try:
        spec=importlib.util.spec_from_file_location('wr_ref',f.name); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
    finally:
        try: os.unlink(f.name)
        except: pass

def month_iter(a:date,b_incl:date):
    y,m=a.year,a.month
    while date(y,m,1)<=b_incl:
        yield y,m
        y,m=(y+1,1) if m==12 else (y,m+1)

def next_month(y,m): return date(y+1,1,1) if m==12 else date(y,m+1,1)

def get_zip(sess,url):
    for k in range(4):
        try:
            r=sess.get(url,headers={'User-Agent':UA},timeout=60)
            if r.status_code==404: return None
            if r.status_code in (429,500,502,503,504):
                time.sleep(1.5*(k+1)); continue
            r.raise_for_status(); return r.content
        except Exception:
            if k==3: raise
            time.sleep(1.5*(k+1))

def parse_zip(raw,wr):
    out=[]; prices=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if not n.endswith('/')]
        if not names: return out,prices
        text=z.read(names[0]).decode('utf-8-sig')
    for row in csv.reader(io.StringIO(text)):
        if not row: continue
        try: ot=int(float(row[0])); ct=int(float(row[6]))
        except: continue
        if ot>10**15: ot//=1000; ct//=1000
        vals=list(map(float,row[1:5])); out.append(wr.Bar(ot,ct,*vals)); prices.extend(row[1:5])
    return out,prices

def fetch_native(wr,symbol,interval):
    sess=requests.Session(); bars=[]; prices=[]; src=0
    warm=START-timedelta(days=WARMUP_DAYS)
    # Complete months through 2026-07. For August 2026, use daily through END.
    for y,m in month_iter(date(warm.year,warm.month,1), date(END.year,END.month,1)):
        ms=date(y,m,1); me=next_month(y,m)
        if me <= date(END.year,END.month,1):
            name=f'{symbol}-{interval}-{y:04d}-{m:02d}.zip'; url=f'{BASE}/monthly/klines/{symbol}/{interval}/{name}'
            raw=get_zip(sess,url)
            if raw:
                b,p=parse_zip(raw,wr); bars.extend(b); prices.extend(p); src+=1
        else:
            d=max(warm,ms)
            while d<=END:
                name=f'{symbol}-{interval}-{d.isoformat()}.zip'; url=f'{BASE}/daily/klines/{symbol}/{interval}/{name}'
                raw=get_zip(sess,url)
                if raw:
                    b,p=parse_zip(raw,wr); bars.extend(b); prices.extend(p); src+=1
                d+=timedelta(days=1)
    lo=int(datetime.combine(warm,datetime.min.time(),tzinfo=timezone.utc).timestamp()*1000)
    hi=int((datetime.combine(END+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc)-timedelta(milliseconds=1)).timestamp()*1000)
    ded={x.ot:x for x in bars if lo<=x.ot<=hi}; bars=[ded[k] for k in sorted(ded)]
    return bars,prices,src

def agg_10m_from_5m(wr,src):
    ms=10*60000; out=[]; key=None; g=[]
    def emit(g):
        if len(g)!=2 or g[1].ot-g[0].ot!=300000: return None
        return wr.Bar(g[0].ot,g[-1].ct,g[0].o,max(x.h for x in g),min(x.l for x in g),g[-1].c)
    for x in src:
        k=x.ot//ms
        if key is None: key=k
        if k!=key:
            y=emit(g)
            if y: out.append(y)
            g=[]; key=k
        g.append(x)
    y=emit(g)
    if y: out.append(y)
    return out

def qtile(vals,q):
    if not vals: return None
    s=sorted(vals); p=(len(s)-1)*q; a=int(math.floor(p)); b=int(math.ceil(p))
    return s[a] if a==b else s[a]+(s[b]-s[a])*(p-a)

def stats(symbol,tf,trades,base,coverage):
    rs=[float(t.canon_r) for t in trades]; n=len(rs)
    gp=sum(x for x in rs if x>0); gl=-sum(x for x in rs if x<0)
    stops=[]; req=[]
    for t in trades:
        if t.entry:
            sp=abs(t.entry-t.stop)/abs(t.entry)*100
            if sp>0: stops.append(sp); req.append(1.0/sp)
    blocks=[rs[i:i+50] for i in range(0,n,50) if len(rs[i:i+50])==50]
    block_means=[sum(b)/len(b) for b in blocks]
    def split_avg(a,b):
        x=rs[a:b]; return (sum(x)/len(x)) if x else None
    i60=int(n*.6); i80=int(n*.8)
    months=defaultdict(list)
    for t in trades: months[t.signal_time[:7]].append(float(t.canon_r))
    month_means={k:sum(v)/len(v) for k,v in sorted(months.items())}
    out={
      'symbol':symbol,'tf':tf,'status':'OK','n':n,'total_r':sum(rs),'avg_r':(sum(rs)/n if n else None),
      'pf_r':(gp/gl if gl else None),'win_rate_pct':(100*sum(x>0 for x in rs)/n if n else None),
      'max_dd_pct':base.get('max_dd_pct'),'max_losing_streak':base.get('max_losing_streak'),
      'stop_pct_p50':qtile(stops,.5),'stop_pct_p90':qtile(stops,.9),'req_x_p50':qtile(req,.5),'req_x_p90':qtile(req,.9),
      'positive_50_blocks':sum(x>0 for x in block_means),'full_50_blocks':len(block_means),'block50_means':block_means,
      'split60_avg_r':split_avg(0,i60),'split20_valid_avg_r':split_avg(i60,i80),'split20_final_avg_r':split_avg(i80,n),
      'positive_months':sum(x>0 for x in month_means.values()),'months_with_trades':len(month_means),'month_means':month_means,
      'first_signal':trades[0].signal_time if trades else None,'last_exit':trades[-1].exit_time if trades else None,
      'coverage':coverage,'reference_blob_sha':REFERENCE_BLOB_SHA,
    }
    for bps in (4,6,8):
        net=[]
        for r,sp in zip(rs,stops): net.append(r-(bps/100.0)/sp)
        out[f'net_{bps}bps_total_r']=sum(net) if len(net)==len(rs) else None
        out[f'net_{bps}bps_avg_r']=(sum(net)/len(net) if net and len(net)==len(rs) else None)
    exp=EXPECTED.get(symbol,{}).get(tf)
    if exp is not None and out['avg_r'] is not None:
        out['formal_expected_avg_r']=exp; out['formal_delta_avg_r']=out['avg_r']-exp; out['formal_parity_within_0_01']=abs(out['avg_r']-exp)<=.01
    return out

def main():
    wr=load_reference(); allsyms=universe(); selected=[s for i,s in enumerate(allsyms) if i%CHUNK_COUNT==CHUNK_ID]
    print(json.dumps({'universe':len(allsyms),'chunk':CHUNK_ID,'chunk_count':CHUNK_COUNT,'selected':len(selected),'base_interval':BASE_INTERVAL}))
    sm=int(datetime.combine(START,datetime.min.time(),tzinfo=timezone.utc).timestamp()*1000)
    en=int((datetime.combine(END+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc)-timedelta(milliseconds=1)).timestamp()*1000)
    metrics=[]; errors=[]
    trade_path=OUT/f'trades_{BASE_INTERVAL}_chunk_{CHUNK_ID}.csv.gz'
    with gzip.open(trade_path,'wt',newline='',encoding='utf-8') as tfh:
        fields=['symbol','tf','signal_time','entry_time','exit_time','canon_r','entry','stop','target','exit_reason','risk_cash','qty','ambiguous']
        tw=csv.DictWriter(tfh,fieldnames=fields); tw.writeheader()
        for idx,symbol in enumerate(selected,1):
            try:
                bars,prices,src=fetch_native(wr,symbol,BASE_INTERVAL)
                evalbars=sum(sm<=x.ct<=en for x in bars)
                if not bars or evalbars<100:
                    metrics.append({'symbol':symbol,'tf':int(BASE_INTERVAL[:-1]),'status':'EMPTY_OR_SHORT','coverage':{'bars_total':len(bars),'eval_bars':evalbars,'source_files':src}})
                    print(f'[{idx}/{len(selected)}] {symbol}: short {len(bars)}'); continue
                tick=wr.infer_tick(prices); wr.SYMBOL=symbol
                tfs=[int(BASE_INTERVAL[:-1])]
                datasets={tfs[0]:bars}
                if BASE_INTERVAL=='5m': datasets[10]=agg_10m_from_5m(wr,bars); tfs=[5,10]
                for tf in tfs:
                    tr,base=wr.run(tf,datasets[tf],tick,sm,en)
                    cov={'bars_total':len(datasets[tf]),'eval_bars':sum(sm<=x.ct<=en for x in datasets[tf]),'source_files':src,'tick':tick,'first_bar':wr.iso(datasets[tf][0].ot),'last_bar':wr.iso(datasets[tf][-1].ct)}
                    m=stats(symbol,tf,tr,base,cov); metrics.append(m)
                    for t in tr:
                        tw.writerow({'symbol':symbol,'tf':tf,'signal_time':t.signal_time,'entry_time':t.entry_time,'exit_time':t.exit_time,'canon_r':t.canon_r,'entry':t.entry,'stop':t.stop,'target':t.target,'exit_reason':t.exit_reason,'risk_cash':t.risk_cash,'qty':t.qty,'ambiguous':t.ambiguous})
                print(f'[{idx}/{len(selected)}] {symbol}: bars={len(bars)} tick={tick} ' + ' '.join(f"{m['tf']}m N={m.get('n',0)} avg={m.get('avg_r')}" for m in metrics[-len(tfs):]))
            except Exception as e:
                errors.append({'symbol':symbol,'error':repr(e)}); print(f'[{idx}/{len(selected)}] {symbol}: ERROR {e}',flush=True)
    with gzip.open(OUT/f'metrics_{BASE_INTERVAL}_chunk_{CHUNK_ID}.jsonl.gz','wt',encoding='utf-8') as f:
        for m in metrics: f.write(json.dumps(m,separators=(',',':'))+'\n')
    (OUT/f'manifest_{BASE_INTERVAL}_chunk_{CHUNK_ID}.json').write_text(json.dumps({'schema':1,'period':[START.isoformat(),END.isoformat()],'base_interval':BASE_INTERVAL,'universe_size':len(allsyms),'selected_count':len(selected),'metrics_count':len(metrics),'errors':errors,'excluded_tradfi_bases':sorted(TRADFI_BASES),'reference_blob_sha':REFERENCE_BLOB_SHA},indent=2))
    print(json.dumps({'done':True,'metrics':len(metrics),'errors':len(errors)}))
if __name__=='__main__': main()
