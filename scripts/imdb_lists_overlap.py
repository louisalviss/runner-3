#!/usr/bin/env python3
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from cloakbrowser import launch
from playwright.sync_api import Error as PlaywrightError

WATCHLIST_URL = "https://www.imdb.com/user/ur83495069/watchlist?ref_=ext_shr_lnk"
WATCHED_URL = "https://www.imdb.com/list/ls569620232?ref_=ext_shr_lnk"
OUT = Path("imdb_lists_output")
OUT.mkdir(parents=True, exist_ok=True)
PAGE_SIZE = 250


def with_page(url, page_no):
    p = urlsplit(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q["sort"] = "list_order,asc"
    q["page"] = str(page_no)
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))


def safe_eval(page, script, retries=8):
    last = None
    for _ in range(retries):
        try:
            return page.evaluate(script)
        except PlaywrightError as exc:
            last = exc
            if "Execution context was destroyed" not in str(exc):
                raise
            page.wait_for_timeout(1200)
    raise last


def dedupe_title_links(page):
    return safe_eval(page, r"""() => {
      const out=[]; const seen=new Set();
      for (const a of document.querySelectorAll('a[href*="/title/tt"]')) {
        const href=a.getAttribute('href')||'';
        const m=href.match(/\/title\/(tt\d+)/);
        if(!m||seen.has(m[1])) continue;
        const card=a.closest('li.ipc-metadata-list-summary-item') || a.closest('[data-testid="list-item"]') || a.closest('li') || a.parentElement;
        if(!card) continue;
        const same=Array.from(card.querySelectorAll(`a[href*="/title/${m[1]}"]`));
        let title=same.map(x=>(x.textContent||'').trim()).find(Boolean)||'';
        if(!title){
          const lines=(card.innerText||'').split('\n').map(x=>x.trim()).filter(Boolean);
          const numbered=lines.find(x=>/^\d+\.\s+/.test(x));
          title=numbered?numbered.replace(/^\d+\.\s+/,''):(lines[0]||'');
        }
        title=title.replace(/^\d+\.\s+/, '').trim();
        const cardText=(card.innerText||'').trim();
        // IMDb sometimes concatenates metadata as "TV-MATV Series", so do not
        // require a word boundary before the second "TV" token.
        const isSeries=/TV Series|TV Mini Series|TV Short/i.test(cardText);
        seen.add(m[1]);
        out.push({id:m[1],title,href:a.href,card_text:cardText,is_series:isSeries});
      }
      return out;
    }""")


def reported_total(text):
    patterns = [
        r"\d+\s*-\s*\d+\s+(?:of\s+)(\d+)",
        r"\d+\s*-\s*\d+\s*\n\s*of\s+(\d+)",
        r"(\d+)\s+titles?",
        r"(\d+)\s+items?",
    ]
    normalized = re.sub(r"[ \t]+", " ", text)
    for pat in patterns:
        m = re.search(pat, normalized, flags=re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def load_view(page, max_rounds=12):
    history=[]; stable=0
    for _ in range(max_rounds):
        rows=dedupe_title_links(page); count=len(rows); history.append(count)
        safe_eval(page,r"""() => {
          const els=Array.from(document.querySelectorAll('button,a'));
          const target=els.find(el=>{
            const t=(el.innerText||el.textContent||'').trim();
            const a=(el.getAttribute('aria-label')||'').trim();
            return /^\d+\s+more$/i.test(t)||/^\d+\s+more$/i.test(a)||/^more$/i.test(t)||/load more/i.test(t)||/show more/i.test(t);
          });
          if(target){target.scrollIntoView({block:'center'});target.click();return true;}
          window.scrollTo(0,document.body.scrollHeight); return false;
        }""")
        page.wait_for_timeout(900)
        new_count=len(dedupe_title_links(page))
        stable=stable+1 if new_count<=count else 0
        if stable>=3: break
    return history


def scan_paged(page, base_url, stem):
    union={}; variants=[]; reported=None
    page_no=1
    page_count=None
    while True:
        url=with_page(base_url,page_no)
        resp=page.goto(url,wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(3500)
        history=load_view(page)
        rows=dedupe_title_links(page)
        text=page.locator("body").inner_text(timeout=12000)
        total=reported_total(text)
        if total is not None:
            reported=max(reported or 0,total)
            page_count=max(1,math.ceil(reported/PAGE_SIZE))
        before=len(union)
        for row in rows:
            union.setdefault(row["id"],row)
        variants.append({
            "page":page_no,
            "requested_url":url,
            "final_url":page.url,
            "http_status":resp.status if resp else None,
            "reported_total":total,
            "captured_in_page":len(rows),
            "union_before":before,
            "union_after":len(union),
            "count_history":history,
        })
        print(stem,'page',page_no,'view',len(rows),'union',len(union),'reported',reported,'pages',page_count,flush=True)
        if page_count is None:
            if page_no>=4:
                break
        elif page_no>=page_count:
            break
        page_no+=1

    rows=list(union.values())
    rows.sort(key=lambda x:(x.get("title") or "").lower())
    (OUT/f"{stem}.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/f"{stem}-variants.json").write_text(json.dumps(variants,ensure_ascii=False,indent=2),encoding="utf-8")
    return {
        "source_url":base_url,
        "reported_total":reported,
        "captured_unique":len(rows),
        "complete":reported is not None and len(rows)>=reported,
        "rows":rows,
    }


def main():
    browser=launch(browser_version="146.0.7680.177.5",headless=False,humanize=True)
    try:
        page=browser.new_page(viewport={"width":1365,"height":900})
        watchlist=scan_paged(page,WATCHLIST_URL,"watchlist")
        watched=scan_paged(page,WATCHED_URL,"watched")
        watchlist_map={x["id"]:x for x in watchlist["rows"]}
        watched_map={x["id"]:x for x in watched["rows"]}
        common=sorted(set(watchlist_map)&set(watched_map),key=lambda tt:(watchlist_map[tt].get("title") or watched_map[tt].get("title") or "").lower())
        overlap=[]
        for tt in common:
            w=watchlist_map[tt]; d=watched_map[tt]
            is_series=bool(w.get("is_series") or d.get("is_series"))
            overlap.append({
                "id":tt,
                "title":w.get("title") or d.get("title") or "",
                "is_series":is_series,
                "watchlist_card_text":w.get("card_text") or "",
                "watched_card_text":d.get("card_text") or "",
                "watchlist_href":w.get("href") or "",
                "watched_href":d.get("href") or "",
            })
        overlap_series=[x for x in overlap if x["is_series"]]
        overlap_movies=[x for x in overlap if not x["is_series"]]
        (OUT/"overlap.json").write_text(json.dumps(overlap,ensure_ascii=False,indent=2),encoding="utf-8")
        (OUT/"overlap-series.json").write_text(json.dumps(overlap_series,ensure_ascii=False,indent=2),encoding="utf-8")
        summary={
            "watchlist":{k:v for k,v in watchlist.items() if k!="rows"},
            "watched":{k:v for k,v in watched.items() if k!="rows"},
            "overlap_count":len(overlap),
            "overlap_ids":[x["id"] for x in overlap],
            "overlap_titles":[x["title"] for x in overlap],
            "waiting_next_season_count":len(overlap_series),
            "waiting_next_season_titles":[x["title"] for x in overlap_series],
            "overlap_movies_not_auto_tagged":[x["title"] for x in overlap_movies],
            "rule":"Overlap is evidence only. Only TV-series overlaps are tagged as watched + waiting for the next season; movie overlaps are not auto-tagged.",
        }
        (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        if not watchlist["complete"] or not watched["complete"]:
            raise SystemExit("Incomplete paged capture; refusing to treat overlap as final")
    finally:
        browser.close()


if __name__=="__main__":
    main()
