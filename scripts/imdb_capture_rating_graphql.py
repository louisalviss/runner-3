#!/usr/bin/env python3
import json
from pathlib import Path
from cloakbrowser import launch
from playwright.sync_api import Error as PlaywrightError

URL='https://www.imdb.com/user/ur83495069/ratings/?sort=date_added,desc'
OUT=Path('imdb_graphql_capture'); OUT.mkdir(exist_ok=True)

def safe_eval(page, script, retries=8):
    last=None
    for _ in range(retries):
        try: return page.evaluate(script)
        except PlaywrightError as e:
            last=e
            if 'Execution context was destroyed' not in str(e): raise
            page.wait_for_timeout(1500)
    raise last

def count_titles(page):
    return safe_eval(page, r"""() => new Set(Array.from(document.querySelectorAll('a[href*="/title/tt"]')).map(a => (a.getAttribute('href')||'').match(/\/title\/(tt\d+)/)?.[1]).filter(Boolean)).size""")

def click_more(page):
    return safe_eval(page, r"""() => {
      const els=Array.from(document.querySelectorAll('button,a'));
      const el=els.find(x=>{const t=(x.innerText||x.textContent||'').trim();const a=(x.getAttribute('aria-label')||'').trim();return /^\d+\s+more$/i.test(t)||/^\d+\s+more$/i.test(a)||/^more$/i.test(t)});
      if(el){el.scrollIntoView({block:'center'});el.click();return true}
      window.scrollTo(0,document.body.scrollHeight);return false;
    }""")

def main():
    records=[]
    browser=launch(browser_version='146.0.7680.177.5',headless=False,humanize=True)
    try:
        page=browser.new_page(viewport={'width':1365,'height':900})
        def on_response(resp):
            if 'graphql.imdb.com' not in resp.url: return
            try:
                body=resp.text()
            except Exception as e:
                body=''
            req=resp.request
            records.append({
                'url':resp.url,'status':resp.status,'method':req.method,
                'post_data':req.post_data,'request_headers':req.headers,
                'response_body':body
            })
        page.on('response',on_response)
        page.goto(URL,wait_until='domcontentloaded',timeout=90000)
        page.wait_for_timeout(7000)
        hist=[]
        stable=0
        for _ in range(25):
            c=count_titles(page); hist.append(c)
            if c>=250: break
            click_more(page); page.wait_for_timeout(1600)
            nc=count_titles(page)
            stable=stable+1 if nc<=c else 0
            if stable>=5: break
        page.wait_for_timeout(4000)
        (OUT/'graphql.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        useful=[]
        for i,r in enumerate(records):
            try:
                obj=json.loads(r.get('response_body') or '{}')
                titles=(obj.get('data') or {}).get('titles')
                if isinstance(titles,list) and any(x.get('otherUserRating') for x in titles):
                    useful.append({'index':i,'count':len(titles),'post_data':r.get('post_data'),'url':r.get('url')})
            except Exception: pass
        summary={'title_count':count_titles(page),'history':hist,'graphql_responses':len(records),'useful':useful,'final_url':page.url}
        (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=False))
    finally:
        browser.close()

if __name__=='__main__': main()
