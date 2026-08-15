#!/usr/bin/env python3
import sys, re, time
import urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_archive as b


def atom_rows_range(form, start_date, end_date):
    out=[]
    offset=0
    for page in range(12):
        base='https://www.sec.gov/cgi-bin/browse-edgar'
        params={
            'action':'getcompany','CIK':b.CIK,'type':form,
            'dateb':pd.Timestamp(end_date).strftime('%Y%m%d'),
            'owner':'exclude','count':'100','start':str(offset),'output':'atom'
        }
        url=base+'?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'User-Agent':'Louis research contact@example.com'})
        with urllib.request.urlopen(req,timeout=45) as resp:
            content=resp.read(); status=resp.status
        soup=BeautifulSoup(content,'xml')
        entries=soup.find_all('entry')
        print('ATOM',form,'page',page,'offset',offset,'status',status,'entries',len(entries))
        if not entries: break
        oldest=None
        for e in entries:
            fd=e.find('filing-date'); ft=e.find('filing-type'); href=e.find('filing-href')
            if not fd or not href: continue
            filed=pd.Timestamp(fd.get_text(strip=True))
            oldest=filed if oldest is None or filed<oldest else oldest
            if filed < pd.Timestamp(start_date) or filed > pd.Timestamp(end_date): continue
            filing_type=ft.get_text(strip=True) if ft else form
            h=href.get_text(strip=True)
            m=re.search(r'/([0-9]{10}-[0-9]{2}-[0-9]{6})-index\.html',h,re.I)
            if not m:
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
        if oldest is not None and oldest < pd.Timestamp(start_date): break
        if len(entries)<100: break
        offset += len(entries)
        time.sleep(0.12)
    return out


def master_rows_from_atom(year,q):
    start=pd.Timestamp(year=year,month=3*(q-1)+1,day=1)
    end=start+pd.offsets.QuarterEnd(startingMonth=3)
    rows=[]
    for form in ('NPORT-P','N-CSR','N-CSRS','N-Q'):
        rows += atom_rows_range(form,start,end)
    if not rows:
        print('ATOM QUARTER',year,q,'candidates 0')
        return []
    df=pd.DataFrame(rows).drop_duplicates(['form','filed','filename']).sort_values(['filed','form'])
    print('ATOM QUARTER',year,q,'candidates',len(df),'forms',df.groupby('form').size().to_dict())
    return df.to_dict('records')


b.master_rows = master_rows_from_atom
b.main()
