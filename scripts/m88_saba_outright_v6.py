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


def visible_text(frame, pattern, exact=False):
    try:
        rx = re.compile(pattern, re.I)
        loc = frame.get_by_text(rx, exact=exact)
    except Exception:
        return None
    for i in range(min(loc.count(), 300)):
        try:
            el = loc.nth(i)
            if el.is_visible():
                bb = el.bounding_box()
                if bb and bb['x'] + bb['width'] > 0 and bb['x'] < 390 and bb['y'] + bb['height'] > 0 and bb['y'] < 844:
                    return el
        except Exception:
            pass
    return None


def top_left_probe(frame):
    js = r'''() => {
      const out=[];
      const seen=new Set();
      for (let y=4;y<=47;y+=4) for (let x=4;x<=64;x+=4) {
        const stack=document.elementsFromPoint(x,y);
        for (const e of stack.slice(0,8)) {
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
    before = drawer_x(frame)
    res['drawer_x_before'] = before
    probe = top_left_probe(frame)
    res['top_left_probe'] = probe

    # First try DOM candidates whose own/parent metadata names menu/nav/hamburger.
    candidates = []
    for d in probe:
        if 'rect' not in d:
            continue
        r = d['rect']
        if r['w'] <= 0 or r['h'] <= 0 or r['x'] >= 90 or r['y'] >= 48 or r['x'] + r['w'] <= 0 or r['y'] + r['h'] <= 0:
            continue
        blob = ' '.join([d.get('cls',''), d.get('id',''), d.get('html',''), json.dumps(d.get('attrs',{}))])
        score = 0
        if re.search(r'hamb|burger', blob, re.I): score += 100
        if re.search(r'menu', blob, re.I): score += 70
        if re.search(r'(side|drawer).*nav|nav.*(side|drawer)', blob, re.I): score += 50
        if re.search(r'header', blob, re.I): score += 10
        # center point clipped to top-left header region
        cx = max(2, min(85, r['x'] + max(2, r['w']//2)))
        cy = max(2, min(46, r['y'] + max(2, r['h']//2)))
        candidates.append((score, cx, cy, d))
    candidates.sort(key=lambda z: z[0], reverse=True)

    points = []
    seen = set()
    for score, x, y, d in candidates:
        if score <= 0:
            continue
        if (x,y) not in seen:
            seen.add((x,y)); points.append((x,y,'scored',score))
    # Fallback grid restricted above top-nav (top-nav starts at y=48).
    for y in [12,18,24,30,36,42]:
        for x in [8,14,20,26,32,38,44,50,56,62]:
            if (x,y) not in seen:
                seen.add((x,y)); points.append((x,y,'grid',0))

    attempts=[]
    for x,y,kind,score in points:
        if drawer_x(frame) is not None and drawer_x(frame) > -80:
            break
        try:
            desc = frame.evaluate(r'''([x,y])=>{const e=document.elementFromPoint(x,y);if(!e)return null;let r=e.getBoundingClientRect();return {tag:e.tagName,cls:String(e.className||'').slice(0,300),id:e.id||'',text:(e.innerText||e.textContent||'').trim().replace(/\s+/g,' ').slice(0,120),html:(e.outerHTML||'').slice(0,500),r:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]}}''',[x,y])
            frame.locator('body').click(position={'x':x,'y':y}, timeout=2500)
            frame.page.wait_for_timeout(500)
            after = drawer_x(frame)
            attempts.append({'x':x,'y':y,'kind':kind,'score':score,'target':desc,'drawer_x':after})
            if after is not None and after > -80:
                res['drawer_open_point']={'x':x,'y':y,'kind':kind,'score':score}
                break
        except Exception as e:
            attempts.append({'x':x,'y':y,'kind':kind,'score':score,'error':type(e).__name__,'drawer_x':drawer_x(frame)})
    res['drawer_attempts']=attempts
    res['drawer_x_after']=drawer_x(frame)
    return res['drawer_x_after'] is not None and res['drawer_x_after'] > -80


def click_drawer_sports(frame):
    # Ensure pre-match Sports mode inside the drawer, not Live.
    try:
        btns = frame.locator('.live-switch__btn')
        for i in range(min(btns.count(), 10)):
            el = btns.nth(i)
            try:
                if re.search(r'^\s*Sports\s*$', el.inner_text(), re.I):
                    el.click(timeout=4000)
                    frame.page.wait_for_timeout(1200)
                    res['drawer_sports_clicked']=True
                    return True
            except Exception:
                pass
    except Exception:
        pass
    res['drawer_sports_clicked']=False
    return False


def click_more(frame):
    try:
        more = frame.locator('.side-menu__more').first
        bb = more.bounding_box()
        res['more_box_before'] = bb
        if bb:
            more.scroll_into_view_if_needed(timeout=3000)
            more.click(timeout=5000)
            frame.page.wait_for_timeout(1200)
            res['more_clicked']=True
            return True
    except Exception as e:
        res['more_error']=type(e).__name__
    # fallback text but only if on-screen
    e = visible_text(frame, r'^\s*More\s*$')
    if e:
        try:
            e.click(timeout=4000); frame.page.wait_for_timeout(1200); res['more_clicked']=True; return True
        except Exception as ex:
            res['more_text_error']=type(ex).__name__
    res['more_clicked']=False
    return False


def collect_menu_items(frame):
    try:
        return frame.evaluate(r'''() => Array.from(document.querySelectorAll('.side-menu__btn,.side-sub-menu__btn,.side-menu__more,.side-features__item')).map(e=>{let r=e.getBoundingClientRect();return {text:(e.innerText||'').trim().replace(/\s+/g,' '),cls:String(e.className||''),x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}})''')
    except Exception:
        return []


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
    context = browser.new_context(viewport={'width':390,'height':844}, screen={'width':390,'height':844}, device_scale_factor=3, is_mobile=True, has_touch=True, locale='en-US', timezone_id='Asia/Bangkok', user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 26_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1')
    page = context.new_page()

    def on_request(r):
        if r.resource_type in ('document','xhr','fetch'):
            network.append({'kind':'request','type':r.resource_type,'method':r.method,'url':r.url,'post':(r.post_data or '')[:50000]})

    def on_response(r):
        if r.request.resource_type not in ('document','xhr','fetch'):
            return
        network.append({'kind':'response','type':r.request.resource_type,'status':r.status,'url':r.url})
        try:
            body = r.text()
            if len(body) <= 12_000_000 and re.search(r'outright|premier league|2026.?2027|relegat|goal.?scorer|top.?4|gameid.{0,20}999', body, re.I|re.S):
                hits.append({'url':r.url,'status':r.status,'body':body[:8_000_000]})
        except Exception:
            pass

    page.on('request', on_request)
    page.on('response', on_response)
    resp = page.goto('https://www.m88.com/sports/Saba%20Sports?Language=en-US', wait_until='domcontentloaded', timeout=45000)
    res['m88_status'] = resp.status if resp else None

    f = None
    for _ in range(45):
        q = provider(page, ready=True)
        if q:
            f = q[2]
            res['provider'] = f.url
            res['ready_text'] = q[3][:150000]
            break
        page.wait_for_timeout(1000)

    if not f:
        res['notes'].append('SABA provider never hydrated')
    else:
        page.screenshot(path=str(OUT/'01-ready.png'), full_page=False)
        if not open_drawer(f):
            res['notes'].append('Could not open SABA drawer')
        else:
            page.wait_for_timeout(800)
            res['drawer_text_initial'] = text(f, 500000)
            res['menu_items_initial'] = collect_menu_items(f)
            page.screenshot(path=str(OUT/'02-drawer-open.png'), full_page=False)

            click_drawer_sports(f)
            res['drawer_text_sports'] = text(f, 500000)
            res['menu_items_sports'] = collect_menu_items(f)
            click_more(f)
            res['drawer_text_after_more'] = text(f, 700000)
            res['menu_items_after_more'] = collect_menu_items(f)
            page.screenshot(path=str(OUT/'03-after-more.png'), full_page=False)

            outright = visible_text(f, r'^\s*Outright\s*$') or visible_text(f, r'\bOutright\b')
            if not outright:
                res['notes'].append('Outright not visible after drawer Sports + More')
                res['outright_clicked'] = False
            else:
                try:
                    res['outright_label'] = outright.inner_text()[:300]
                except Exception:
                    res['outright_label'] = 'Outright'
                try:
                    outright.click(timeout=7000)
                    res['outright_clicked'] = True
                except Exception as e:
                    res['outright_clicked'] = False
                    res['outright_error'] = type(e).__name__

            if res.get('outright_clicked'):
                page.wait_for_timeout(9000)
                q = provider(page, ready=False)
                if q:
                    f = q[2]
                    res['provider_after_outright'] = f.url
                page.screenshot(path=str(OUT/'04-outright.png'), full_page=False)
                corpus = ''
                # capture current DOM and progressively scroll the main content
                for _ in range(80):
                    now = text(f, 2_000_000)
                    if now and now not in corpus:
                        corpus += '\n' + now
                    try:
                        f.evaluate('window.scrollBy(0,550)')
                    except Exception:
                        try:
                            f.locator('.main-wrap__content').evaluate('(e)=>e.scrollBy(0,550)')
                        except Exception:
                            pass
                    page.wait_for_timeout(220)
                res['outright_text'] = corpus[:3_000_000]

                patterns = {
                    'winner': [r'ENGLISH\s+PREMIER\s+LEAGUE.{0,5000}?WINNER', r'PREMIER\s+LEAGUE.{0,5000}?WINNER'],
                    'top4': [r'ENGLISH\s+PREMIER\s+LEAGUE.{0,5000}?TOP\s*4', r'PREMIER\s+LEAGUE.{0,5000}?TOP\s*4'],
                    'relegation': [r'ENGLISH\s+PREMIER\s+LEAGUE.{0,5000}?RELEGAT', r'PREMIER\s+LEAGUE.{0,5000}?RELEGAT'],
                    'goalscorer': [r'ENGLISH\s+PREMIER\s+LEAGUE.{0,7000}?(?:GOAL.?SCORER|TOP\s+GOAL)', r'PREMIER\s+LEAGUE.{0,7000}?(?:GOAL.?SCORER|TOP\s+GOAL)']
                }
                for key, pats in patterns.items():
                    rec = {'found':False,'source':None,'window':''}
                    for pat in pats:
                        m = re.search(pat, corpus, re.I|re.S)
                        if m:
                            rec.update(found=True, source='dom', window=corpus[max(0,m.start()-2500):min(len(corpus),m.start()+150000)])
                            break
                    if not rec['found']:
                        for h in hits:
                            for pat in pats:
                                m = re.search(pat, h['body'], re.I|re.S)
                                if m:
                                    rec.update(found=True, source='network', url=h['url'], window=h['body'][max(0,m.start()-5000):min(len(h['body']),m.start()+220000)])
                                    break
                            if rec['found']:
                                break
                    res['markets'][key] = rec

    context.close()
    browser.close()

(OUT/'result.json').write_text(json.dumps(res, ensure_ascii=False, indent=2))
(OUT/'network.json').write_text(json.dumps(network, ensure_ascii=False, indent=2))
(OUT/'hits.json').write_text(json.dumps(hits, ensure_ascii=False, indent=2))
print(json.dumps(res, ensure_ascii=False, indent=2)[:350000])
