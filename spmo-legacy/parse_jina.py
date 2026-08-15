#!/usr/bin/env python3
import re,time,json
from pathlib import Path
import pandas as pd
import requests

OUT=Path('spmo-legacy/output'); OUT.mkdir(parents=True,exist_ok=True)
DOCS=[
 ('2016-10-31','https://www.sec.gov/Archives/edgar/data/1378872/000119312517002614/d269293dncsr.htm'),
 ('2017-10-31','https://www.sec.gov/Archives/edgar/data/1378872/000119312518002695/d473179dncsr.htm'),
 ('2018-10-31','https://www.sec.gov/Archives/edgar/data/1378872/000119312519002456/d525171dncsr.htm'),
 ('2019-04-30','https://www.sec.gov/Archives/edgar/data/1378872/000119312519190405/d740133dncsrs.htm'),
]
HEADERS={'User-Agent':'Mozilla/5.0'}

def fetch(u):
    ju='https://r.jina.ai/'+u
    for i in range(4):
        try:
            r=requests.get(ju,headers=HEADERS,timeout=180)
            if r.status_code==200 and len(r.text)>100000:return r.text,ju
            print('HTTP',r.status_code,'bytes',len(r.content),ju,flush=True)
        except Exception as e:print('FETCH_ERR',type(e).__name__,str(e)[:200],flush=True)
        time.sleep(2+i*3)
    raise RuntimeError('Jina fetch failed '+u)

def locate_schedule(t):
    # Rebranding changed PowerShares -> Invesco and Portfolio -> ETF.
    patterns=[
      r'Schedule of Investments(?:\([^\n]*\))?\s*\n+\s*(?:PowerShares|Invesco) S&P 500(?:®)? Momentum (?:Portfolio|ETF) \(SPMO\)',
      r'Schedule of Investments(?:\([^\n]*\))?\s*\n+\s*(?:PowerShares|Invesco) S&P 500(?:®)? Momentum[^\n]*\(SPMO\)',
    ]
    starts=[]
    for pat in patterns:
        starts.extend(m.start() for m in re.finditer(pat,t,re.I))
    starts=sorted(set(starts))
    if not starts:
        # Last-resort: score every SPMO occurrence for schedule-like rows following it.
        for m in re.finditer(r'[^\n]{0,100}\(SPMO\)',t,re.I):
            seg=t[m.start():m.start()+30000]
            if 'Number\nof' in seg or 'Number\r\nof' in seg or 'Total Investments' in seg:
                starts.append(m.start())
    if not starts:raise RuntimeError('No SPMO schedule heading')
    scored=[]
    for s in starts:
        # End at next fund Schedule of Investments, or 80k chars max.
        tail=t[s+100:]
        m=re.search(r'\nSchedule of Investments(?:\([^\n]*\))?\s*\n',tail,re.I)
        e=(s+100+m.start()) if m else min(len(t),s+100000)
        seg=t[s:e]
        stock_lines=sum(1 for line in seg.splitlines() if re.match(r'^\s*\t?[\d,]+\t',line.replace('\xa0',' ')))
        score=stock_lines + 30*('Total Investments' in seg) + 20*('Net Assets' in seg)
        scored.append((score,s,e,seg))
    scored.sort(reverse=True,key=lambda x:x[0])
    score,s,e,seg=scored[0]
    print('SCHEDULE_CANDIDATES',[(a,b,c) for a,b,c,_ in scored],'chosen',s,e,'score',score,flush=True)
    return seg,s,e

def parse_rows(seg):
    rows=[]
    for line in seg.splitlines():
        # Normalize NBSP but preserve tabs; issuer names never contain tabs in Jina output.
        x=line.replace('\xa0',' ')
        parts=[p.strip() for p in x.split('\t')]
        parts=[p for p in parts if p not in ('','$')]
        if len(parts)<3:continue
        # First token must be an integer share count. Last token must be an integer USD value.
        if not re.fullmatch(r'[\d,]+',parts[0]):continue
        if not re.fullmatch(r'[\d,]+',parts[-1]):continue
        shares=int(parts[0].replace(',','')); value=int(parts[-1].replace(',',''))
        middle=parts[1:-1]
        # Reject subtotal/category rows; a real issuer token contains alphabetic chars.
        names=[p for p in middle if re.search(r'[A-Za-z]',p)]
        if not names:continue
        name=max(names,key=len)
        # Drop footnote tags appended to issuer, e.g. Amazon.com, Inc.(b)
        name=re.sub(r'\s*\([a-z](?:,[a-z])*\)\s*$','',name,flags=re.I).strip()
        if any(k in name.lower() for k in ['common stocks','total investments','net assets','money market fund','other assets less']):continue
        if shares<=0 or value<=0:continue
        rows.append({'shares':shares,'name':name,'value':value})
    # Remove exact duplicates caused by page-header continuation; keep legitimate issuer classes separate.
    df=pd.DataFrame(rows).drop_duplicates(['shares','name','value']).reset_index(drop=True)
    return df

def stated_total(seg):
    # Prefer Total Common Stocks..., else Total Investments (money-market may make latter slightly larger).
    for pat in [
      r'Total Common Stocks(?: and Other Equity Interests)?[\s\S]{0,350}?\t\s*\$?\s*([\d,]+)\s*\t',
      r'Total Investments[\s\S]{0,350}?\t\s*\$?\s*([\d,]+)\s*\t',
    ]:
        ms=list(re.finditer(pat,seg,re.I))
        if ms:return int(ms[-1].group(1).replace(',',''))
    return None

all_frames=[];meta=[]
for d,u in DOCS:
    print('\nFETCH',d,u,flush=True)
    text,relay=fetch(u)
    (OUT/f'raw-{d}.txt').write_text(text)
    seg,s,e=locate_schedule(text)
    (OUT/f'spmo-segment-{d}.txt').write_text(seg)
    df=parse_rows(seg)
    total=stated_total(seg); sm=int(df.value.sum()) if len(df) else 0
    ratio=sm/total if total else None
    print('PARSED',d,'rows',len(df),'sum',sm,'stated_total',total,'ratio',ratio,flush=True)
    print(df.sort_values('value',ascending=False).head(10).to_string(index=False),flush=True)
    df.insert(0,'report_date',d);df['source_url']=u;df['relay_url']=relay
    df.to_csv(OUT/f'holdings-{d}.csv',index=False); all_frames.append(df)
    meta.append({'report_date':d,'rows':len(df),'parsed_sum':sm,'stated_total':total,'coverage_ratio':ratio,'source_url':u})

allh=pd.concat(all_frames,ignore_index=True);allh.to_csv(OUT/'legacy_holdings.csv',index=False)
pd.DataFrame(meta).to_csv(OUT/'legacy_parse_meta.csv',index=False)
Path(OUT/'legacy_parse_meta.json').write_text(json.dumps(meta,indent=2))
# Hard gate: index normally has ~100 stocks; parser must capture nearly all disclosed equity value.
bad=[m for m in meta if m['rows']<90 or m['coverage_ratio'] is None or not (0.985<=m['coverage_ratio']<=1.015)]
if bad:raise RuntimeError('Legacy parser gate failed: '+json.dumps(bad))
print('\nLEGACY_PARSE_GATE PASS',flush=True)
