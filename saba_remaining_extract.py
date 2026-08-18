import json,re,pathlib
from playwright.sync_api import sync_playwright

OUT=pathlib.Path('evidence')
targets={
 'relegation':r'ENGLISH PREMIER LEAGUE 2026/2027\s*-\s*TO BE RELEGATED',
 'goalscorer':r'ENGLISH PREMIER LEAGUE 2026/2027\s*-\s*TOP GOALSCORER',
}
result={'markets':{}}
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
 c=b.new_context(locale='en-US',viewport={'width':1500,'height':1200})
 pg=c.new_page(); pg.goto('https://www.dafabet.com/en/sports',wait_until='domcontentloaded',timeout=45000)
 sf=None
 for _ in range(30):
  sf=next((f for f in pg.frames if f.name=='sportsFrame' and '/Sports/1/' in f.url),None)
  if sf: break
  pg.wait_for_timeout(1000)
 if not sf: raise RuntimeError('sportsFrame missing')
 base=sf.url.split('/Sports/1/')[0]
 sf.goto(base+'/Sports/1/OR?mode=m0&market=T',wait_until='domcontentloaded',timeout=40000)
 # Hydration can lag; use the lower EPL market as readiness signal.
 try: sf.get_by_text(re.compile(targets['goalscorer'],re.I)).first.wait_for(state='visible',timeout=18000)
 except: pass
 pg.wait_for_timeout(1500)
 for name,pat in targets.items():
  rec={}; loc=sf.get_by_text(re.compile(pat,re.I)); chosen=None
  for i in range(min(loc.count(),100)):
   try:
    if loc.nth(i).is_visible(): chosen=loc.nth(i); break
   except: pass
  rec['found']=bool(chosen)
  if not chosen:
   try: rec['list_body']=sf.locator('body').inner_text(timeout=8000)[:60000]
   except: rec['list_body']=''
   result['markets'][name]=rec; continue
  try: chosen.scroll_into_view_if_needed(timeout=5000)
  except: pass
  chosen.click(timeout=8000); pg.wait_for_timeout(3500)
  try: body=sf.locator('body').inner_text(timeout=8000)
  except: body=''
  rec['body']=body[:90000]
  lines=[x.strip() for x in body.splitlines() if x.strip()]
  start=next((i for i,x in enumerate(lines) if re.search(pat,x,re.I)),None)
  block=[]
  if start is not None:
   for x in lines[start+1:]:
    if block and (x.startswith('*ENGLISH PREMIER LEAGUE') or x.startswith('*UEFA ') or x.startswith('*GERMANY') or x.startswith('*SPAIN') or x.startswith('*ITALY')): break
    block.append(x)
    if len(block)>600: break
  rec['block']=block
  selections=[]; i=0
  while i+2<len(block):
   a,bv,cv=block[i],block[i+1],block[i+2]
   if re.fullmatch(r'\d{2}/\d{2}/\d{4}',a) and re.search(r'[A-Za-z]',bv) and re.fullmatch(r'\d{1,3}(?:,\d{3})*(?:\.\d{1,3})?',cv):
    selections.append({'selection':bv,'odds':cv}); i+=3
   else: i+=1
  rec['selections']=selections
  result['markets'][name]=rec
  try: chosen.click(timeout=5000); pg.wait_for_timeout(800)
  except: pass
 b.close()
OUT.mkdir(exist_ok=True)
OUT.joinpath('remaining.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:{'found':v.get('found'),'selections':v.get('selections',[])} for k,v in result['markets'].items()},ensure_ascii=False,indent=2))
