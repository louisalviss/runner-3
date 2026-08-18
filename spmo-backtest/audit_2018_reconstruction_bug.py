#!/usr/bin/env python3
import json,re,requests
from bs4 import BeautifulSoup,NavigableString

BASE='https://www.sec.gov/Archives/edgar/data/1378872/000119312518214392'
H={'User-Agent':'SPMO research audit contact@example.com'}

def get(url):
    r=requests.get(url,headers=H,timeout=60); r.raise_for_status(); return r

idx=get(BASE+'/index.json').json(); items=idx['directory']['item']
htms=[x['name'] for x in items if x['name'].endswith(('.htm','.html'))]
main=[n for n in htms if re.search(r'ncsr|nq|nport',n,re.I) and 'index' not in n.lower()]
if not main: main=[n for n in htms if 'index' not in n.lower() and 'cert' not in n.lower()]
name=main[0]; html=get(BASE+'/'+name).text
print('PRIMARY',name,len(html))

soup=BeautifulSoup(html,'lxml')
for tr in list(soup.find_all('tr')):
    cells=[' '.join(c.stripped_strings) for c in tr.find_all(['td','th'],recursive=False)]
    if cells: tr.replace_with(NavigableString('\n'+'\t'.join(cells)+'\n'))
t=soup.get_text('\n').replace('\xa0',' ')

pat=re.compile(r'Invesco\s+S&P\s*500(?:\s*®)?\s+Momentum\s+ETF\s*\(SPMO\)',re.I)
cs=list(pat.finditer(t)); print('SPMO_TITLE_HITS',len(cs))
for i,m in enumerate(cs):
    print('HIT',i,m.start(),repr(t[m.start():m.start()+220].replace('\n',' ')))

# Exact portfolio schedule begins at the SPMO title that immediately carries the report date.
startm=None
for m in cs:
    head=t[m.start():m.start()+700]
    if re.search(r'April\s+30,\s*2018',head,re.I) and re.search(r'(Unaudited|Portfolio Composition|Number of Shares)',head,re.I):
        startm=m; break
if startm is None: raise SystemExit('No dated SPMO schedule start')
start=startm.start()

# The next fund's dated portfolio-composition title is a hard boundary. This is safer than
# scanning for the first generic Net Assets text in the giant multi-fund N-CSR.
next_start=None
for m in cs:
    if m.start()<=start: continue
    # Skip the SPMO continuation page; next actual different fund is located by generic title below.
# Find any next Invesco ETF title followed by April 30, 2018, excluding SPMO continuation.
generic=re.compile(r'Invesco\s+[^\n\t]{3,120}?ETF\s*\([^\)]+\)',re.I)
for m in generic.finditer(t,start+1000):
    head=t[m.start():m.start()+500]
    if re.search(r'April\s+30,\s*2018',head,re.I) and 'SPMO' not in m.group(0):
        next_start=m.start(); print('NEXT_FUND_BOUNDARY',repr(m.group(0)),next_start); break
if next_start is None: next_start=start+60000
z=t[start:next_start]
print('SECTION_CHARS',len(z),'TABS',z.count('\t'))

# If boundary is generous, clip at the last SPMO Net Assets line within it.
net=list(re.finditer(r'Net Assets\s*[—-]\s*100\.0%[^\n]*',z,re.I))
if net:
    z=z[:net[-1].end()]
print('CLIPPED_CHARS',len(z),'TABS',z.count('\t'))

lines=z.splitlines()
for target in ['Microsoft','Amazon']:
    hits=[i for i,l in enumerate(lines) if target.lower() in l.lower()]
    print('\nTARGET',target,'HITS',hits)
    for i in hits:
        for j in range(max(0,i-3),min(len(lines),i+4)): print(j,repr(lines[j]))

out=[]
for line in lines:
    parts=[' '.join(x.strip().split()) for x in line.split('\t')]
    parts=[x for x in parts if x not in ('','$','—','-')]
    if len(parts)<3: continue
    nums=[]
    for i,x in enumerate(parts):
        y=x.replace('$','').replace(',','').replace('(','').replace(')','').strip()
        if y.isdigit(): nums.append(i)
    if len(nums)<2: continue
    i0,i1=nums[0],nums[-1]
    if i1<=i0: continue
    try: shares=int(re.sub(r'\D','',parts[i0])); value=int(re.sub(r'\D','',parts[i1]))
    except: continue
    names=[x for x in parts[i0+1:i1] if re.search(r'[A-Za-z]',x)]
    if not names or shares<=0 or value<=0: continue
    nm=max(names,key=len).strip('*_ ')
    low=nm.lower()
    if any(q in low for q in ['common stocks','total investments','net assets','other assets','number of shares','sector breakdown']): continue
    out.append((shares,nm,value,line))
print('\nPARSED_ROWS',len(out))
for row in out:
    if 'Microsoft' in row[1] or 'Amazon' in row[1]: print('PARSED_TARGET',row[:3])
print('TOP_BY_SNAPSHOT_VALUE')
for row in sorted(out,key=lambda x:x[2],reverse=True)[:15]: print(row[:3])

for target in ['Microsoft','Amazon']:
    candidates=[]
    for i,l in enumerate(lines):
        if target.lower() in l.lower(): candidates.append(' | '.join(lines[max(0,i-3):min(len(lines),i+4)]))
    print('DIRECT_'+target.upper(),json.dumps(candidates,ensure_ascii=False))
