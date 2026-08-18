import csv, json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (compatible; PetAftercareValidation/1.0; research validation)'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
BASE='https://findpetcremations.com'
STATES=['texas','california','florida','ohio','arizona']
EXCLUDE={'findpetcremations.com','facebook.com','instagram.com','youtube.com','youtu.be','google.com','maps.google.com','twitter.com','x.com','linkedin.com','tiktok.com','yelp.com','bbb.org','apple.com'}

def get(url, timeout=15):
    try:
        r=S.get(url,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and 'text/html' in r.headers.get('content-type',''): return r
    except Exception: pass

def text(html):
    s=BeautifulSoup(html,'lxml')
    for x in s(['script','style','noscript','svg']): x.decompose()
    return ' '.join(s.stripped_strings)

def external_site(html):
    soup=BeautifulSoup(html,'lxml'); out=[]
    for a in soup.select('a[href]'):
        h=a.get('href','').strip()
        if not h.startswith('http'): continue
        host=urlparse(h).netloc.lower().replace('www.','')
        if not host or any(host==d or host.endswith('.'+d) for d in EXCLUDE): continue
        out.append(h)
    return out[0] if out else None

def score_site(site):
    r=get(site)
    if not r: return {'site_ok':False}
    root=r.url; pages=[(root,r.text)]; soup=BeautifulSoup(r.text,'lxml')
    root_host=urlparse(root).netloc.lower().replace('www.',''); links=[]
    keys=('price','pricing','crem','aftercare','service','aquam','memorial','pet-loss','end-of-life')
    for a in soup.select('a[href]'):
        h=urljoin(root,a.get('href','')).split('#')[0]; p=urlparse(h)
        host=p.netloc.lower().replace('www.',''); label=(' '.join(a.stripped_strings)+' '+p.path).lower()
        if host==root_host and any(k in label for k in keys) and h!=root and h not in links: links.append(h)
    for h in links[:5]:
        rr=get(h)
        if rr: pages.append((rr.url,rr.text))
        time.sleep(.05)
    T=' '.join(text(h) for _,h in pages); low=T.lower()
    dollars=re.findall(r'\$\s?([0-9]{2,4}(?:\.\d{1,2})?)',T)
    petctx=any(k in low for k in ['pet crem','dog crem','cat crem','aquamation','pet aftercare','animal crem'])
    prices=petctx and len(dollars)>=2
    weights=re.findall(r'(?:\d{1,3}\s*(?:-|to)\s*\d{1,3}|under\s+\d{1,3}|over\s+\d{1,3}|\d{1,3}\+?)\s*(?:lb|lbs|pounds)',low)
    return {
      'site_ok':True,'final_url':root,'pages_crawled':len(pages),'price_values_found':len(dollars),
      'has_exact_price_signal':prices,'has_weight_tiers':prices and len(weights)>=2,
      'has_pickup':any(k in low for k in ['home pickup','at-home pickup','pick up your pet','pickup service','pet pickup']),
      'has_turnaround':bool(re.search(r'(?:return|ready|ashes|remains).{0,80}\b(?:\d+\s*(?:business\s*)?(?:day|days|hour|hours)|same[- ]day|next[- ]day)\b',low)),
      'has_private':('private cremation' in low or 'individual cremation' in low),
      'has_communal':('communal cremation' in low or 'group cremation' in low),
      'has_aquamation':any(k in low for k in ['aquamation','alkaline hydrolysis','water cremation']),
      'has_24_7':any(k in low for k in ['24/7','24-hour','24 hour','after hours','emergency pickup']),
      'has_inclusions':any(k in low for k in ['urn included','includes urn','paw print included','clay paw','ink paw','keepsake included']),
      'sample_prices':dollars[:8],'source_pages':[u for u,_ in pages[:6]]}

profiles=[]
for st in STATES:
    for page in range(1,7):
        u=f'{BASE}/directory/{st}' + ('' if page==1 else f'?page={page}')
        r=get(u)
        if not r: continue
        before=len(profiles); soup=BeautifulSoup(r.text,'lxml')
        for a in soup.select('a[href]'):
            h=a.get('href','')
            if '/directory/provider/' in h:
                full=urljoin(BASE,h).split('#')[0]
                if full not in profiles: profiles.append(full)
        if len(profiles)==before and page>=3: break
        time.sleep(.08)
profiles=profiles[:180]
rows=[]
for i,purl in enumerate(profiles,1):
    pr=get(purl)
    if not pr: rows.append({'profile_url':purl,'profile_ok':False}); continue
    T=text(pr.text); soup=BeautifulSoup(pr.text,'lxml'); h1=soup.find('h1')
    site=external_site(pr.text)
    rec={'profile_url':purl,'profile_ok':True,'name':h1.get_text(' ',strip=True) if h1 else '',
         'provider_site':site,'fpc_pricing_verified':('Pricing has not yet been verified' not in T and '$' in T)}
    if site: rec.update(score_site(site))
    else: rec['site_ok']=False
    rows.append(rec)
    if i%20==0: print('processed',i,'/',len(profiles),flush=True)
    time.sleep(.08)

def rate(key, pred=lambda r:True):
    vals=[r for r in rows if pred(r)]; c=sum(bool(r.get(key)) for r in vals)
    return {'n':len(vals),'count':c,'pct':round(100*c/len(vals),1) if vals else 0}
summary={
 'captured_at_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
 'seed_states':STATES,'profiles_sampled':len(rows),
 'provider_sites_found':sum(bool(r.get('provider_site')) for r in rows),
 'provider_sites_accessible':sum(bool(r.get('site_ok')) for r in rows),
 'rates_all_profiles':{'fpc_pricing_verified':rate('fpc_pricing_verified'),'provider_site_found':rate('provider_site')},
 'rates_accessible_sites':{k:rate(k,lambda r:r.get('site_ok')) for k in ['has_exact_price_signal','has_weight_tiers','has_pickup','has_turnaround','has_private','has_communal','has_aquamation','has_24_7','has_inclusions']},
 'notes':'Automated heuristic validation; exact pricing signals require manual spot-checking.'}
Path('pet-aftercare-validation').mkdir(exist_ok=True)
Path('pet-aftercare-validation/summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
Path('pet-aftercare-validation/sample.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
fields=sorted(set().union(*(r.keys() for r in rows))) if rows else []
with open('pet-aftercare-validation/sample.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
print(json.dumps(summary,indent=2))
