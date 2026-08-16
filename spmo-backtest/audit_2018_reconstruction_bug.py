#!/usr/bin/env python3
import json,re,requests
from bs4 import BeautifulSoup,NavigableString

BASE='https://www.sec.gov/Archives/edgar/data/1378872/000119312518214392'
H={'User-Agent':'SPMO research audit contact@example.com'}

def get(url):
    r=requests.get(url,headers=H,timeout=60)
    r.raise_for_status(); return r

idx=get(BASE+'/index.json').json()
items=idx['directory']['item']
htms=[x['name'] for x in items if x['name'].endswith(('.htm','.html'))]
print('FILES',htms)
# Prefer the largest HTML document; filing is an N-Q / portfolio schedule.
name=max(htms,key=lambda n: next((int(x.get('size',0)) for x in items if x['name']==n),0))
html=get(BASE+'/'+name).text
print('PRIMARY',name,len(html))

soup=BeautifulSoup(html,'lxml')
for tr in list(soup.find_all('tr')):
    cells=[' '.join(c.stripped_strings) for c in tr.find_all(['td','th'],recursive=False)]
    if cells: tr.replace_with(NavigableString('\n'+'\t'.join(cells)+'\n'))
t=soup.get_text('\n').replace('\xa0',' ')

# Locate exact SPMO schedule section.
pat=re.compile(r'(?:PowerShares|Invesco)\s+S&P\s*500(?:\s*®)?\s+Momentum\s+(?:Portfolio|ETF)\s*\(SPMO\)',re.I)
cs=list(pat.finditer(t))
print('SPMO_TITLE_HITS',len(cs))
for i,m in enumerate(cs[:10]):
    print('HIT',i,m.start(),repr(t[m.start():m.start()+180].replace('\n',' ')))

best=None
for m in cs:
    post=t[m.start():m.start()+80000]
    if 'Schedule of Investments' in t[max(0,m.start()-1500):m.start()+1000] and re.search(r'Net Assets\s*[—-]\s*100\.0%',post,re.I):
        # favor sections that contain both target names
        score=(100 if re.search('Microsoft',post,re.I) else 0)+(100 if re.search('Amazon',post,re.I) else 0)+post.count('\t')
        if best is None or score>best[0]: best=(score,m.start(),post)
if best is None:
    # fallback: first title with Net Assets termination
    for m in cs:
        post=t[m.start():m.start()+80000]
        if re.search(r'Net Assets\s*[—-]\s*100\.0%',post,re.I):
            best=(0,m.start(),post);break
if best is None: raise SystemExit('No exact SPMO schedule section found')
_,start,post=best
endm=re.search(r'Net Assets\s*[—-]\s*100\.0%[^\n]*',post,re.I)
z=post[:endm.end()]
print('SECTION_CHARS',len(z))

# Print exact flattened rows that mention target companies plus context.
lines=z.splitlines()
for target in ['Microsoft','Amazon']:
    hits=[i for i,l in enumerate(lines) if target.lower() in l.lower()]
    print('\nTARGET',target,'HITS',hits)
    for i in hits:
        for j in range(max(0,i-2),min(len(lines),i+3)):
            print(j,repr(lines[j]))

# Re-run the legacy row parser and show whether target rows survived.
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
    try:
        shares=int(re.sub(r'\D','',parts[i0])); value=int(re.sub(r'\D','',parts[i1]))
    except: continue
    names=[x for x in parts[i0+1:i1] if re.search(r'[A-Za-z]',x)]
    if not names or shares<=0 or value<=0: continue
    nm=max(names,key=len).strip('*_ ')
    out.append((shares,nm,value,line))
print('\nPARSED_ROWS',len(out))
for row in out:
    if 'Microsoft' in row[1] or 'Amazon' in row[1]: print('PARSED_TARGET',row[:3])

# Direct target diagnostics independent of generic parser.
for target in ['Microsoft','Amazon']:
    candidates=[]
    for i,l in enumerate(lines):
        if target.lower() in l.lower():
            block=' | '.join(lines[max(0,i-3):min(len(lines),i+4)])
            candidates.append(block)
    print('DIRECT_'+target.upper(),json.dumps(candidates,ensure_ascii=False))
