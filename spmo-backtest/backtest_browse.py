#!/usr/bin/env python3
import sys, re, time
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_archive as b

_inventory = None


def atom_rows(form, stop_before):
    out=[]
    start=0
    for page in range(80):
        url='https://www.sec.gov/cgi-bin/browse-edgar'
        params={
            'action':'getcompany','CIK':b.CIK,'type':form,'dateb':'',
            'owner':'exclude','count':'100','start':str(start),'output':'atom'
        }
        r=b.S.get(url,params=params,timeout=45)
        print('ATOM',form,'page',page,'start',start,'status',r.status_code,'bytes',len(r.content))
        r.raise_for_status()
        soup=BeautifulSoup(r.content,'xml')
        entries=soup.find_all('entry')
        if not entries: break
        oldest=None
        added=0
        for e in entries:
            fd=e.find('filing-date')
            ft=e.find('filing-type')
            href=e.find('filing-href')
            if not fd or not href: continue
            filed=pd.Timestamp(fd.get_text(strip=True))
            oldest=filed if oldest is None or filed<oldest else oldest
            filing_type=ft.get_text(strip=True) if ft else form
            h=href.get_text(strip=True)
            m=re.search(r'/([0-9]{10}-[0-9]{2}-[0-9]{6})-index\.html',h,re.I)
            if not m:
                # Fallback to accession directory segment.
                m2=re.search(r'/([0-9]{18})/',h)
                if not m2: continue
                s=m2.group(1); acc=f'{s[:10]}-{s[10:12]}-{s[12:]}'
            else:
                acc=m.group(1)
            out.append({
                'cik':b.CIK,'company':'Invesco Exchange-Traded Fund Trust',
                'form':filing_type,'filed':filed,
                'filename':f'edgar/data/{b.CIK}/{acc}.txt'
            })
            added+=1
        print('  entries',len(entries),'added',added,'oldest',oldest.date() if oldest is not None else None)
        if oldest is not None and oldest < pd.Timestamp(stop_before): break
        if len(entries)<100: break
        start += len(entries)
        time.sleep(0.15)
    return out


def ensure_inventory():
    global _inventory
    if _inventory is not None: return _inventory
    rows=[]
    # N-PORT started in 2019; retrieve far enough back to cover the first structured snapshots.
    rows += atom_rows('NPORT-P','2018-12-01')
    # Legacy portfolio schedules for 2016-2019.
    rows += atom_rows('N-CSR','2015-01-01')
    rows += atom_rows('N-CSRS','2015-01-01')
    rows += atom_rows('N-Q','2015-01-01')
    df=pd.DataFrame(rows)
    if df.empty: raise RuntimeError('browse-edgar returned no filing inventory')
    df=df.drop_duplicates(['form','filed','filename']).sort_values('filed')
    df.to_csv(b.OUT/'browse_inventory.csv',index=False)
    print('INVENTORY total',len(df),'by form',df.groupby('form').size().to_dict())
    _inventory=df
    return df


def master_rows_from_atom(year,q):
    df=ensure_inventory()
    start=pd.Timestamp(year=year,month=3*(q-1)+1,day=1)
    end=start+pd.offsets.QuarterEnd(startingMonth=3)
    c=df[(df.filed>=start)&(df.filed<=end)].copy()
    rows=c.to_dict('records')
    print('ATOM QUARTER',year,q,'candidates',len(rows),'forms',c.groupby('form').size().to_dict() if len(c) else {})
    return rows


b.master_rows = master_rows_from_atom
b.main()
