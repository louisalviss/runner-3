import json, os, re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

OUT = Path(os.environ.get('WORKSPACE', '.')) / 'evidence'
OUT.mkdir(parents=True, exist_ok=True)
res = {'notes': [], 'markets': {}}
network = []
hits = []


def text(frame, limit=2_000_000):
    try:
        return frame.locator('body').inner_text(timeout=5000)[:limit]
    except Exception:
        return ''


def frame_score(frame):
    host = (urlparse(frame.url).hostname or '').lower()
    if not host.startswith('i1x9gr.'):
        return -999, ''
    t = text(frame, 120000)
    score = 100
    if 'Saba Soccer' in t:
        score += 100
    if 'Prediction Market' in t:
        score += 50
    if '/promotion' in frame.url:
        score += 50
    if t.strip() == 'Loading':
        score -= 100
    return score, t


def provider(page, ready=False):
    items = []
    for f in page.frames:
        s, t = frame_score(f)
        if s > -999:
            items.append((s, len(t), f, t))
    if not items:
        return None
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if ready and items[0][0] < 200:
        return None
    return items[0]


def drawer_x(frame):
    try:
        return float(frame.locator('.side-nav').first.evaluate('e=>e.getBoundingClientRect().x'))
    except Exception:
        return None


def top_left_probe(frame):
    js = r'''() => {
      const out=[]; const seen=new Set();
      for (let y=4;y<=47;y+=4) for (let x=4;x<=64;x+=4) {
        for (const e of document.elementsFromPoint(x,y).slice(0,8)) {
          const r=e.getBoundingClientRect();
          const key=[e.tagName,String(e.className||''),e.id||'',Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)].join('|');
          if(seen.has(key)) continue; seen.add(key);
          const attrs={}; for(const a of e.attributes||[]) if(/^(aria-|data-|role$|href$|xlink:href$)/i.test(a.name)) attrs[a.name]=a.value;
          out.push({tag:e.tagName,cls:String(e.className||'').slice(0,400),id:e.id||'',text:(e.innerText||e.textContent||'').trim().replace(/\s+/g,' ').slice(0,120),rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},attrs,html:(e.outerHTML||'').slice(0,700)});
        }
      }
      return out;
    }'''
    try:
        return frame.evaluate(js)
    except Exception as e:
        return [{'error': type(e).__name__}]


def open_drawer(frame):
    res['drawer_x_before'] = drawer_x(frame)
    probe = top_left_probe(frame)
    res['top_left_probe'] = probe
    # We now know the real control is .header__menu, but keep discovery fallback for rotating builds.
    try:
        menu = frame.locator('.header__menu').first
        if menu.count():
            res['header_menu_box'] = menu.bounding_box()
            menu.click(timeout=4000)
            frame.page.wait_for_timeout(600)
            if drawer_x(frame) is not None and drawer_x(frame) > -80:
                res['drawer_open_point'] = {'selector':'.header__menu'}
                res['drawer_x_after'] = drawer_x(frame)
                return True
    except Exception as e:
        res['header_menu_error'] = type(e).__name__

    points=[]; seen=set()
    for d in probe:
        if 'rect' not in d: continue
        r=d['rect']; blob=' '.join([d.get('cls',''),d.get('id',''),d.get('html',''),json.dumps(d.get('attrs',{}))])
        score=0
        if re.search(r'hamb|burger',blob,re.I): score+=100
        if re.search(r'menu',blob,re.I): score+=70
        if re.search(r'(side|drawer).*nav|nav.*(side|drawer)',blob,re.I): score+=50
        if score and r['x']<90 and r['y']<48:
            x=max(2,min(85,r['x']+max(2,r['w']//2))); y=max(2,min(46,r['y']+max(2,r['h']//2)))
            if (x,y) not in seen: seen.add((x,y)); points.append((score,x,y))
    points.sort(reverse=True)
    for y in [12,18,24,30,36,42]:
        for x in [8,14,20,26,32,38,44,50,56,62]:
            if (x,y) not in seen: points.append((0,x,y)); seen.add((x,y))
    attempts=[]
    for score,x,y in points:
        try:
            frame.locator('body').click(position={'x':x,'y':y},timeout=2500); frame.page.wait_for_timeout(500)
            dx=drawer_x(frame); attempts.append({'x':x,'y':y,'score':score,'drawer_x':dx})
            if dx is not None and dx>-80:
                res['drawer_open_point']={'x':x,'y':y,'score':score}; break
        except Exception as e:
            attempts.append({'x':x,'y':y,'score':score,'error':type(e).__name__})
    res['drawer_attempts']=attempts; res['drawer_x_after']=drawer_x(frame)
    return res['drawer_x_after'] is not None and res['drawer_x_after']>-80


def drawer_switch_state(frame):
    try:
        return frame.evaluate(r'''() => Array.from(document.querySelectorAll('.side-nav .live-switch__btn')).map(e=>({text:(e.innerText||'').trim(),cls:String(e.className||''),aria:e.getAttribute('aria-selected'),data:Array.from(e.attributes).filter(a=>a.name.startsWith('data-')).reduce((o,a)=>(o[a.name]=a.value,o),{}),html:e.outerHTML.slice(0,700)}))''')
    except Exception:
        return []


def click_drawer_sports(frame):
    res['drawer_switch_before'] = drawer_switch_state(frame)
    try:
        btns = frame.locator('.side-nav .live-switch__btn')
        for i in range(min(btns.count(),10)):
            el=btns.nth(i)
            try:
                if re.search(r'^\s*Sports\s*$',el.inner_text(),re.I):
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.click(timeout=5000)
                    frame.page.wait_for_timeout(2200)
                    res['drawer_sports_clicked']=True
                    res['drawer_switch_after']=drawer_switch_state(frame)
                    res['drawer_after_sports_text']=frame.locator('.side-nav').inner_text(timeout=5000)[:700000]
                    return True
            except Exception as e:
                res.setdefault('drawer_sports_errors',[]).append(type(e).__name__)
    except Exception as e:
        res['drawer_sports_outer_error']=type(e).__name__
    res['drawer_sports_clicked']=False
    return False


def click_more(frame):
    try:
        more=frame.locator('.side-nav .side-menu__more').first
        res['more_box_before']=more.bounding_box()
        more.scroll_into_view_if_needed(timeout=4000)
        more.click(timeout=5000)
        frame.page.wait_for_timeout(1800)
        res['more_clicked']=True
        return True
    except Exception as e:
        res['more_error']=type(e).__name__; res['more_clicked']=False; return False


def collect_menu_items(frame):
    try:
        return frame.evaluate(r'''() => Array.from(document.querySelectorAll('.side-nav .side-menu__btn,.side-nav .side-sub-menu__btn,.side-nav .side-menu__more,.side-nav .side-features__item')).map(e=>{let r=e.getBoundingClientRect();return {text:(e.innerText||'').trim().replace(/\s+/g,' '),cls:String(e.className||''),x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}})''')
    except Exception:
        return []


def find_and_click_outright(frame):
    # Do not require it to already be in the viewport; scroll the drawer item into view.
    candidates=[]
    try:
        nodes=frame.locator('.side-nav *')
        for i in range(min(nodes.count(),4000)):
            el=nodes.nth(i)
            try:
                t=(el.inner_text(timeout=500) or '').strip()
                if re.fullmatch(r'Outright(?:\s+\d+)?',t,re.I):
                    bb=el.bounding_box(); candidates.append((i,t,bb,el))
            except Exception: pass
    except Exception: pass
    res['outright_candidates']=[{'text':t,'box':bb} for _,t,bb,_ in candidates[:20]]
    for _,t,bb,el in candidates:
        try:
            el.scroll_into_view_if_needed(timeout=4000); frame.page.wait_for_timeout(300)
            el.click(timeout=6000); frame.page.wait_for_timeout(1200)
            res['outright_label']=t; res['outright_clicked']=True; return True
        except Exception as e:
            res.setdefault('outright_click_errors',[]).append(type(e).__name__)
    res['outright_clicked']=False
    return False


with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    context=browser.new_context(viewport={'width':390,'height':844},screen={'width':390,'height':844},device_scale_factor=3,is_mobile=True,has_touch=True,locale='en-US',timezone_id='Asia/Bangkok',user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 26_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1')
    page=context.new_page()
    def on_request(r):
        if r.resource_type in ('document','xhr','fetch'): network.append({'kind':'request','type':r.resource_type,'method':r.method,'url':r.url,'post':(r.post_data or '')[:50000]})
    def on_response(r):
        if r.request.resource_type not in ('document','xhr','fetch'): return
        network.append({'kind':'response','type':r.request.resource_type,'status':r.status,'url':r.url})
        try:
            body=r.text()
            if len(body)<=12_000_000 and re.search(r'outright|premier league|2026.?2027|relegat|goal.?scorer|top.?4|gameid.{0,20}999',body,re.I|re.S): hits.append({'url':r.url,'status':r.status,'body':body[:8_000_000]})
        except Exception: pass
    page.on('request',on_request); page.on('response',on_response)
    resp=page.goto('https://www.m88.com/sports/Saba%20Sports?Language=en-US',wait_until='domcontentloaded',timeout=45000); res['m88_status']=resp.status if resp else None
    f=None
    for _ in range(45):
        q=provider(page,ready=True)
        if q: f=q[2]; res['provider']=f.url; res['ready_text']=q[3][:150000]; break
        page.wait_for_timeout(1000)
    if not f:
        res['notes'].append('SABA provider never hydrated')
    else:
        page.screenshot(path=str(OUT/'01-ready.png'),full_page=False)
        if not open_drawer(f):
            res['notes'].append('Could not open SABA drawer')
        else:
            res['drawer_text_initial']=f.locator('.side-nav').inner_text(timeout=5000)[:700000]
            res['menu_items_initial']=collect_menu_items(f)
            page.screenshot(path=str(OUT/'02-drawer-open.png'),full_page=False)
            click_drawer_sports(f)
            res['menu_items_sports']=collect_menu_items(f)
            page.screenshot(path=str(OUT/'03-sports.png'),full_page=False)
            # First try Outright directly; if collapsed under More, expand More and retry.
            if not find_and_click_outright(f):
                click_more(f)
                res['drawer_text_after_more']=f.locator('.side-nav').inner_text(timeout=5000)[:900000]
                res['menu_items_after_more']=collect_menu_items(f)
                page.screenshot(path=str(OUT/'04-after-more.png'),full_page=False)
                find_and_click_outright(f)
            if not res.get('outright_clicked'):
                res['notes'].append('Outright not found after scoped drawer Sports + More')
            else:
                page.wait_for_timeout(9000)
                q=provider(page,ready=False)
                if q: f=q[2]; res['provider_after_outright']=f.url
                page.screenshot(path=str(OUT/'05-outright.png'),full_page=False)
                corpus=''
                for _ in range(80):
                    now=text(f,2_000_000)
                    if now and now not in corpus: corpus+='\n'+now
                    try: f.evaluate('window.scrollBy(0,550)')
                    except Exception:
                        try: f.locator('.main-wrap__content').evaluate('(e)=>e.scrollBy(0,550)')
                        except Exception: pass
                    page.wait_for_timeout(220)
                res['outright_text']=corpus[:3_000_000]
                patterns={
                  'winner':[r'ENGLISH\s+PREMIER\s+LEAGUE.{0,12000}?WINNER',r'PREMIER\s+LEAGUE.{0,12000}?WINNER'],
                  'top4':[r'ENGLISH\s+PREMIER\s+LEAGUE.{0,12000}?TOP\s*4',r'PREMIER\s+LEAGUE.{0,12000}?TOP\s*4'],
                  'relegation':[r'ENGLISH\s+PREMIER\s+LEAGUE.{0,12000}?RELEGAT',r'PREMIER\s+LEAGUE.{0,12000}?RELEGAT'],
                  'goalscorer':[r'ENGLISH\s+PREMIER\s+LEAGUE.{0,15000}?(?:GOAL.?SCORER|TOP\s+GOAL)',r'PREMIER\s+LEAGUE.{0,15000}?(?:GOAL.?SCORER|TOP\s+GOAL)']}
                for key,pats in patterns.items():
                    rec={'found':False,'source':None,'window':''}
                    for pat in pats:
                        m=re.search(pat,corpus,re.I|re.S)
                        if m: rec.update(found=True,source='dom',window=corpus[max(0,m.start()-3000):min(len(corpus),m.start()+180000)]); break
                    if not rec['found']:
                        for h in hits:
                            for pat in pats:
                                m=re.search(pat,h['body'],re.I|re.S)
                                if m: rec.update(found=True,source='network',url=h['url'],window=h['body'][max(0,m.start()-6000):min(len(h['body']),m.start()+260000)]); break
                            if rec['found']: break
                    res['markets'][key]=rec
    context.close(); browser.close()

(OUT/'result.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
(OUT/'network.json').write_text(json.dumps(network,ensure_ascii=False,indent=2))
(OUT/'hits.json').write_text(json.dumps(hits,ensure_ascii=False,indent=2))
print(json.dumps(res,ensure_ascii=False,indent=2)[:400000])
