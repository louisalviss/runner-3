#!/usr/bin/env python3
import sys, re, time
import urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_archive as b

SEC_UA='Louis research contact@example.com'
_series_nport_cache=None

class UResp:
    def __init__(self, content, status=200):
        self.content=content
        self.status_code=status
        self.text=content.decode('utf-8','replace')
    def raise_for_status(self):
        if self.status_code>=400: raise RuntimeError(f'HTTP {self.status_code}')
    def close(self): pass


def urllib_get(url, *, stream=False, headers=None, tries=5, timeout=60):
    h={'User-Agent':SEC_UA}
    if headers: h.update(headers)
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers=h)
            with urllib.request.urlopen(req,timeout=timeout) as resp:
                data=resp.read(); status=resp.status
            return UResp(data,status)
        except Exception as e:
            last=e; print('URLLIB GETERR',repr(e),url)
            time.sleep(0.7*(i+1))
    raise last


def complete_url_folder(fn):
    acc=Path(fn).stem
    folder=acc.replace('-','')
    return f'https://www.sec.gov/Archives/edgar/data/{b.CIK}/{folder}/{acc}.txt'


def parse_atom_entries(content, form, start_date=None, end_date=None):
    soup=BeautifulSoup(content,'xml')
    entries=soup.find_all('entry')
    out=[]
    for e in entries:
        fd=e.find('filing-date'); ft=e.find('filing-type'); href=e.find('filing-href')
        accnode=e.find('accession-number')
        if not fd: continue
        filed=pd.Timestamp(fd.get_text(strip=True))
        if start_date is not None and filed < pd.Timestamp(start_date): continue
        if end_date is not None and filed > pd.Timestamp(end_date): continue
        filing_type=ft.get_text(strip=True) if ft else form
        acc=accnode.get_text(strip=True) if accnode else None
        if not acc and href:
            h=href.get_text(strip=True)
            m=re.search(r'/([0-9]{10}-[0-9]{2}-[0-9]{6})-index\.html',h,re.I)
            if m: acc=m.group(1)
            else:
                m2=re.search(r'/([0-9]{18})/',h)
                if m2:
                    s=m2.group(1); acc=f'{s[:10]}-{s[10:12]}-{s[12:]}'
        if not acc: continue
        out.append({
            'cik':b.CIK,'company':'Invesco Exchange-Traded Fund Trust II',
            'form':filing_type,'filed':filed,
            'filename':f'edgar/data/{b.CIK}/{acc}.txt'
        })
    return out, entries


def series_nport_rows():
    global _series_nport_cache
    if _series_nport_cache is not None: return _series_nport_cache
    params={
        'action':'getcompany','CIK':b.SERIES,'type':'NPORT-P',
        'owner':'exclude','count':'100','output':'atom'
    }
    url='https://www.sec.gov/cgi-bin/browse-edgar?'+urllib.parse.urlencode(params)
    content=urllib_get(url,timeout=45).content
    rows,entries=parse_atom_entries(content,'NPORT-P')
    df=pd.DataFrame(rows).drop_duplicates(['form','filed','filename']).sort_values('filed')
    print('SERIES NPORT inventory',len(df),'filings; range',df.filed.min().date(),df.filed.max().date())
    _series_nport_cache=df
    return df


def atom_rows_range(form, start_date, end_date):
    out=[]
    offset=0
    for page in range(12):
        params={
            'action':'getcompany','CIK':b.CIK,'type':form,
            'dateb':pd.Timestamp(end_date).strftime('%Y%m%d'),
            'owner':'exclude','count':'100','start':str(offset),'output':'atom'
        }
        url='https://www.sec.gov/cgi-bin/browse-edgar?'+urllib.parse.urlencode(params)
        content=urllib_get(url,timeout=45).content
        rows,entries=parse_atom_entries(content,form,start_date,end_date)
        print('ATOM',form,'page',page,'offset',offset,'entries',len(entries),'matched',len(rows))
        out += rows
        if not entries: break
        dates=[]
        soup=BeautifulSoup(content,'xml')
        for e in soup.find_all('entry'):
            fd=e.find('filing-date')
            if fd:
                try: dates.append(pd.Timestamp(fd.get_text(strip=True)))
                except: pass
        oldest=min(dates) if dates else None
        if oldest is not None and oldest < pd.Timestamp(start_date): break
        if len(entries)<100: break
        offset += len(entries)
        time.sleep(0.12)
    return out


def master_rows_from_atom(year,q):
    start=pd.Timestamp(year=year,month=3*(q-1)+1,day=1)
    end=start+pd.offsets.QuarterEnd(startingMonth=3)
    ndf=series_nport_rows()
    rows=ndf[(ndf.filed>=start)&(ndf.filed<=end)].to_dict('records')
    for form in ('N-CSR','N-CSRS','N-Q'):
        rows += atom_rows_range(form,start,end)
    if not rows:
        print('ATOM QUARTER',year,q,'candidates 0')
        return []
    df=pd.DataFrame(rows).drop_duplicates(['form','filed','filename']).sort_values(['filed','form'])
    print('ATOM QUARTER',year,q,'candidates',len(df),'forms',df.groupby('form').size().to_dict())
    return df.to_dict('records')


b.get = urllib_get
b.complete_url = complete_url_folder
b.master_rows = master_rows_from_atom
b.main()
