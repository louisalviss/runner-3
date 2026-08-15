#!/usr/bin/env python3
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URLS = [
    ("golden_ch1", "https://www.hetushu.com/book/1265/841543.html"),
    ("dinosaur_ch22", "https://www.hetushu.com/book/1265/841623.html"),
    ("terminal", "https://www.hetushu.com/book/1265/842619.html"),
]


def visible_text(page):
    return page.eval_on_selector_all(
        "#content > *",
        """els => els.filter(e => {
          const s=getComputedStyle(e);
          const r=e.getBoundingClientRect();
          return s.display!=='none' && s.visibility!=='hidden' && Number(s.opacity)!==0 && r.width>0 && r.height>0;
        }).map(e => e.innerText.trim()).filter(Boolean)""",
    )


def main():
    out=Path('hetushu_visible'); out.mkdir(exist_ok=True)
    manifest=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        ctx=browser.new_context(user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36')
        for name,url in URLS:
            page=ctx.new_page()
            resp=page.goto(url,wait_until='domcontentloaded',timeout=90000)
            page.wait_for_timeout(5000)
            lines=visible_text(page)
            text='\n\n'.join(lines).strip()
            (out/f'{name}.txt').write_text(text,encoding='utf-8')
            manifest.append({'name':name,'url':url,'status':resp.status if resp else None,'lines':len(lines),'chars':len(text),'title':page.title()})
            page.close()
        browser.close()
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__': main()
