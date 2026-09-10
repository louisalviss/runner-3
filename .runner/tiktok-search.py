import json, pathlib, re, urllib.parse
from playwright.sync_api import sync_playwright

queries=[]
for line in pathlib.Path('.runner/tiktok-url.txt').read_text(encoding='utf-8').splitlines():
    if line.startswith('SEARCH:'):
        q=line.split(':',1)[1].strip()
        if q: queries.append(q)

out={'mode':'tiktok_search','queries':queries,'results':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    ctx=browser.new_context(
        viewport={'width':1440,'height':1100},
        locale='vi-VN',
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/151 Safari/537.36'
    )
    for qi,q in enumerate(queries,1):
        page=ctx.new_page()
        url='https://www.tiktok.com/search?q='+urllib.parse.quote(q)
        rec={'query':q,'requested_url':url,'videos':[]}
        try:
            resp=page.goto(url,wait_until='domcontentloaded',timeout=45000)
            page.wait_for_timeout(8000)
            for _ in range(3):
                page.mouse.wheel(0,1200)
                page.wait_for_timeout(1800)
            rec['status']=resp.status if resp else None
            rec['final_url']=page.url
            rec['title']=page.title()
            try: rec['body_text']=page.locator('body').inner_text(timeout=7000)[:24000]
            except Exception as e: rec['body_error']=str(e)
            anchors=page.locator('a[href*="/video/"]')
            seen=set()
            for i in range(min(anchors.count(),40)):
                a=anchors.nth(i)
                try:
                    href=a.get_attribute('href') or ''
                    if href.startswith('/'): href='https://www.tiktok.com'+href
                    href=href.split('?')[0]
                    if '/video/' not in href or href in seen: continue
                    seen.add(href)
                    payload=a.evaluate("""el => {
                      let n=el, best='';
                      for(let i=0;i<7 && n;i++,n=n.parentElement){
                        const t=(n.innerText||'').trim();
                        if(t.length>best.length && t.length<2500) best=t;
                      }
                      const img=el.querySelector('img');
                      return {anchor_text:(el.innerText||'').trim(), context_text:best,
                              aria:el.getAttribute('aria-label')||'', img_alt:img?img.alt||'':''};
                    }""")
                    payload['url']=href
                    m=re.search(r'tiktok\.com/@([^/]+)/video/(\d+)',href)
                    if m:
                        payload['creator']='@'+m.group(1); payload['video_id']=m.group(2)
                    rec['videos'].append(payload)
                    if len(rec['videos'])>=16: break
                except Exception:
                    pass
            page.screenshot(path=f'evidence/search-{qi}.png',full_page=False)
        except Exception as e:
            rec['error']=f'{type(e).__name__}: {e}'
        out['results'].append(rec)
        page.close()
    ctx.close(); browser.close()
pathlib.Path('evidence/search-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'queries':queries,'counts':[len(x.get('videos',[])) for x in out['results']]},ensure_ascii=False))
