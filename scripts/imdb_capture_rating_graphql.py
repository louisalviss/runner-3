#!/usr/bin/env python3
import json
from pathlib import Path
from cloakbrowser import launch
from playwright.sync_api import Error as PlaywrightError

URL='https://www.imdb.com/user/ur83495069/ratings/?sort=date_added,desc'
OUT=Path('imdb_graphql_capture'); OUT.mkdir(exist_ok=True)
BASE=Path('runner-output/imdb-ratings-browser-full/ratings-clean.json')

def safe_eval(page, script, arg=None, retries=8):
    last=None
    for _ in range(retries):
        try:
            return page.evaluate(script, arg) if arg is not None else page.evaluate(script)
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
    base=json.loads(BASE.read_text(encoding='utf-8'))
    missing_ids=[x['id'] for x in base if x.get('user_rating') is None]
    browser=launch(browser_version='146.0.7680.177.5',headless=False,humanize=True)
    try:
        page=browser.new_page(viewport={'width':1365,'height':900})
        def on_response(resp):
            if 'graphql.imdb.com' not in resp.url: return
            try: body=resp.text()
            except Exception: body=''
            req=resp.request
            records.append({'url':resp.url,'status':resp.status,'method':req.method,'post_data':req.post_data,'request_headers':req.headers,'response_body':body})
        page.on('response',on_response)
        page.goto(URL,wait_until='domcontentloaded',timeout=90000)
        page.wait_for_timeout(7000)
        hist=[]; stable=0
        for _ in range(25):
            c=count_titles(page); hist.append(c)
            if c>=250: break
            click_more(page); page.wait_for_timeout(1600)
            nc=count_titles(page); stable=stable+1 if nc<=c else 0
            if stable>=5: break
        page.wait_for_timeout(3500)

        useful=[]; template=None
        for i,r in enumerate(records):
            try:
                obj=json.loads(r.get('response_body') or '{}')
                titles=(obj.get('data') or {}).get('titles')
                if isinstance(titles,list) and any(x.get('otherUserRating') for x in titles):
                    useful.append({'index':i,'count':len(titles),'post_data':r.get('post_data'),'url':r.get('url')})
                    template=json.loads(r['post_data'])
            except Exception: pass
        if not template:
            raise RuntimeError('PersonalizedUserData template not captured')

        template['variables']['idArray']=missing_ids
        body=json.dumps(template,separators=(',',':'))
        result=safe_eval(page, r"""async (body) => {
          const r=await fetch('https://api.graphql.imdb.com/', {
            method:'POST',
            headers:{'content-type':'application/json','accept':'application/json'},
            body
          });
          return {status:r.status,text:await r.text()};
        }""", body)
        missing_obj=json.loads(result['text'])
        missing_titles=(missing_obj.get('data') or {}).get('titles') or []
        missing_map={x['id']:(x.get('otherUserRating') or {}) for x in missing_titles}

        complete=[]
        for row in base:
            x=dict(row)
            if x.get('user_rating') is None:
                rr=missing_map.get(x['id']) or {}
                x['user_rating']=rr.get('value')
                x['rated_at']=rr.get('date')
            complete.append(x)

        (OUT/'graphql.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'missing-query-response.json').write_text(json.dumps(missing_obj,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'ratings-complete.json').write_text(json.dumps(complete,ensure_ascii=False,indent=2),encoding='utf-8')
        summary={
          'title_count':count_titles(page),'history':hist,'graphql_responses':len(records),'useful':useful,
          'missing_requested':len(missing_ids),'missing_returned':len(missing_titles),
          'missing_with_rating':sum(1 for x in missing_titles if (x.get('otherUserRating') or {}).get('value') is not None),
          'complete_rows':len(complete),'complete_with_rating':sum(1 for x in complete if x.get('user_rating') is not None),
          'direct_query_status':result['status'],'final_url':page.url
        }
        (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=False))
    finally:
        browser.close()

if __name__=='__main__': main()
