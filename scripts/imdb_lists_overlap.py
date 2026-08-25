#!/usr/bin/env python3
import json
import re
from pathlib import Path

from cloakbrowser import launch
from playwright.sync_api import Error as PlaywrightError

WATCHLIST_URL = "https://www.imdb.com/user/ur83495069/watchlist?ref_=ext_shr_lnk"
WATCHED_URL = "https://www.imdb.com/list/ls569620232?ref_=ext_shr_lnk"
OUT = Path("imdb_lists_output")
OUT.mkdir(parents=True, exist_ok=True)


def safe_eval(page, script, retries=8):
    last = None
    for _ in range(retries):
        try:
            return page.evaluate(script)
        except PlaywrightError as exc:
            last = exc
            if "Execution context was destroyed" not in str(exc):
                raise
            page.wait_for_timeout(1500)
    raise last


def dedupe_title_links(page):
    return safe_eval(page, r"""() => {
      const out = [];
      const seen = new Set();
      for (const a of document.querySelectorAll('a[href*="/title/tt"]')) {
        const href = a.getAttribute('href') || '';
        const m = href.match(/\/title\/(tt\d+)/);
        if (!m || seen.has(m[1])) continue;
        const card = a.closest('li.ipc-metadata-list-summary-item') ||
                     a.closest('[data-testid="list-item"]') ||
                     a.closest('li') || a.parentElement;
        if (!card) continue;
        const same = Array.from(card.querySelectorAll(`a[href*="/title/${m[1]}"]`));
        let title = same.map(x => (x.textContent || '').trim()).find(Boolean) || '';
        if (!title) {
          const lines = (card.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
          const numbered = lines.find(x => /^\d+\.\s+/.test(x));
          title = numbered ? numbered.replace(/^\d+\.\s+/, '') : (lines[0] || '');
        }
        seen.add(m[1]);
        out.push({id:m[1], title, href:a.href, card_text:(card.innerText||'').trim()});
      }
      return out;
    }""")


def reported_total(text):
    patterns = [r"1-\d+\s*\nof\s+(\d+)", r"(\d+)\s+titles?", r"(\d+)\s+items?"]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def load_all(page, max_rounds=80):
    history=[]
    stable=0
    for _ in range(max_rounds):
        rows=dedupe_title_links(page)
        count=len(rows)
        history.append(count)
        body=page.locator("body").inner_text(timeout=15000)
        total=reported_total(body)
        if total is not None and count >= total:
            break
        safe_eval(page, r"""() => {
          const els = Array.from(document.querySelectorAll('button,a'));
          const target = els.find(el => {
            const t=(el.innerText||el.textContent||'').trim();
            const a=(el.getAttribute('aria-label')||'').trim();
            return /^\d+\s+more$/i.test(t) || /^\d+\s+more$/i.test(a) || /^more$/i.test(t) || /load more/i.test(t) || /show more/i.test(t);
          });
          if (target) { target.scrollIntoView({block:'center'}); target.click(); return true; }
          window.scrollTo(0, document.body.scrollHeight);
          return false;
        }""")
        page.wait_for_timeout(1800)
        new_count=len(dedupe_title_links(page))
        stable = stable + 1 if new_count <= count else 0
        if stable >= 6:
            break
    return history


def scan(page, url, stem):
    resp=page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(8000)
    history=load_all(page)
    rows=dedupe_title_links(page)
    text=page.locator("body").inner_text(timeout=15000)
    total=reported_total(text)
    (OUT/f"{stem}.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/f"{stem}.txt").write_text(text,encoding="utf-8")
    return {"source_url":url,"final_url":page.url,"http_status":resp.status if resp else None,"reported_total":total,"captured_unique":len(rows),"count_history":history,"rows":rows}


def main():
    browser=launch(browser_version="146.0.7680.177.5", headless=False, humanize=True)
    try:
        page=browser.new_page(viewport={"width":1365,"height":900})
        watchlist=scan(page, WATCHLIST_URL, "watchlist")
        watched=scan(page, WATCHED_URL, "watched")
        watchlist_map={x["id"]:x for x in watchlist["rows"]}
        watched_map={x["id"]:x for x in watched["rows"]}
        common=sorted(set(watchlist_map) & set(watched_map), key=lambda tt:(watchlist_map[tt].get("title") or watched_map[tt].get("title") or "").lower())
        overlap=[]
        for tt in common:
            w=watchlist_map[tt]; d=watched_map[tt]
            overlap.append({"id":tt,"title":w.get("title") or d.get("title") or "","watchlist_card_text":w.get("card_text") or "","watched_card_text":d.get("card_text") or "","watchlist_href":w.get("href") or "","watched_href":d.get("href") or ""})
        (OUT/"overlap.json").write_text(json.dumps(overlap,ensure_ascii=False,indent=2),encoding="utf-8")
        summary={"watchlist":{k:v for k,v in watchlist.items() if k!="rows"},"watched":{k:v for k,v in watched.items() if k!="rows"},"overlap_count":len(overlap),"overlap_ids":[x["id"] for x in overlap],"overlap_titles":[x["title"] for x in overlap],"rule":"Appears in both Watchlist and Đã xem => watched but intentionally retained to wait for a later season/part; verify title-level semantics before write if title is not episodic/franchise-capable."}
        (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False))
    finally:
        browser.close()


if __name__=="__main__":
    main()
