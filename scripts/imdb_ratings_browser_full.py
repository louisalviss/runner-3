#!/usr/bin/env python3
import json
import re
from pathlib import Path

from cloakbrowser import launch
from playwright.sync_api import Error as PlaywrightError

USER_ID = "ur83495069"
ASC_URL = f"https://www.imdb.com/user/{USER_ID}/ratings/?sort=date_added,asc"
OUT = Path("imdb_browser_output")
OUT.mkdir(parents=True, exist_ok=True)
PREV = Path("runner-output/imdb-ratings-browser-full")


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
        const m = a.getAttribute('href')?.match(/\/title\/(tt\d+)/);
        if (!m || seen.has(m[1])) continue;
        const card = a.closest('li.ipc-metadata-list-summary-item') || a.closest('[data-testid="list-item"]') || a.closest('li') || a.parentElement;
        if (!card) continue;
        const same = Array.from(card.querySelectorAll(`a[href*="/title/${m[1]}"]`));
        const title = same.map(x => (x.textContent || '').trim()).find(Boolean) || '';
        seen.add(m[1]);
        out.push({id:m[1], title, href:a.href, card_text:(card.innerText||'').trim()});
      }
      return out;
    }""")


def click_more_or_scroll(page):
    clicked = safe_eval(page, r"""() => {
      const els = Array.from(document.querySelectorAll('button,a'));
      const target = els.find(el => {
        const t=(el.innerText||el.textContent||'').trim();
        const a=(el.getAttribute('aria-label')||'').trim();
        return /^\d+\s+more$/i.test(t) || /^\d+\s+more$/i.test(a) || /^more$/i.test(t);
      });
      if (target) { target.scrollIntoView({block:'center'}); target.click(); return true; }
      window.scrollTo(0, document.body.scrollHeight);
      return false;
    }""")
    page.wait_for_timeout(1500)
    return clicked


def scroll_until_250(page):
    history=[]
    stable=0
    for _ in range(35):
        count=len(dedupe_title_links(page))
        history.append(count)
        if count >= 250:
            break
        click_more_or_scroll(page)
        new_count=len(dedupe_title_links(page))
        stable = stable + 1 if new_count <= count else 0
        if stable >= 5:
            break
    return history


def collect_graphql(page, bucket):
    def on_response(resp):
        if "graphql.imdb.com" not in resp.url:
            return
        try:
            bucket.append({"url":resp.url,"status":resp.status,"body":resp.text()})
        except Exception as exc:
            bucket.append({"url":resp.url,"status":resp.status,"error":f"{type(exc).__name__}: {exc}"})
    page.on("response", on_response)


def rating_map(records):
    out={}
    for rec in records:
        try:
            data=json.loads(rec.get("body") or "{}").get("data") or {}
        except Exception:
            continue
        for item in data.get("titles") or []:
            r=item.get("otherUserRating")
            if item.get("id") and r and r.get("value") is not None:
                out[item["id"]]={"value":r.get("value"),"date":r.get("date")}
    return out


def title_from_card(row):
    if row.get("title"):
        return row["title"]
    for line in (row.get("card_text") or "").splitlines():
        m=re.match(r"^\d+\.\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return ""


def main():
    old_graphql=[]
    old_cards=[]
    try:
        old_graphql=json.loads((PREV/"graphql-responses.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        old_cards=json.loads((PREV/"page1-full.json").read_text(encoding="utf-8"))
    except Exception:
        try:
            old_cards=json.loads((PREV/"all-visible-ratings-cards.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    fresh_graphql=[]
    browser=launch(browser_version="146.0.7680.177.5", headless=False, humanize=True)
    try:
        page=browser.new_page(viewport={"width":1365,"height":900})
        collect_graphql(page, fresh_graphql)
        resp=page.goto(ASC_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(8000)
        history=scroll_until_250(page)
        asc_cards=dedupe_title_links(page)
        asc_text=page.locator("body").inner_text(timeout=15000)
        (OUT/"asc-full.txt").write_text(asc_text,encoding="utf-8")
        (OUT/"asc-full.html").write_text(page.content(),encoding="utf-8")
        (OUT/"asc-full.json").write_text(json.dumps(asc_cards,ensure_ascii=False,indent=2),encoding="utf-8")

        total=None
        m=re.search(r"1-\d+\s*\nof\s+(\d+)",asc_text)
        if m:
            total=int(m.group(1))

        all_graphql=old_graphql+fresh_graphql
        ratings=rating_map(all_graphql)
        cards={}
        for row in old_cards+asc_cards:
            cards.setdefault(row["id"],row)

        clean=[]
        for tt,row in cards.items():
            rr=ratings.get(tt,{})
            clean.append({
                "id":tt,
                "title":title_from_card(row),
                "user_rating":rr.get("value"),
                "rated_at":rr.get("date"),
                "card_text":row.get("card_text") or "",
            })

        (OUT/"graphql-responses.json").write_text(json.dumps(all_graphql,ensure_ascii=False,indent=2),encoding="utf-8")
        (OUT/"ratings-clean.json").write_text(json.dumps(clean,ensure_ascii=False,indent=2),encoding="utf-8")
        summary={
            "user_id":USER_ID,
            "reported_total":total,
            "saved_newest_cards":len(old_cards),
            "oldest_asc_cards":len(asc_cards),
            "union_unique_titles":len(cards),
            "ratings_from_graphql":len(ratings),
            "ratings_joined_to_cards":sum(1 for x in clean if x["user_rating"] is not None),
            "asc_count_history":history,
            "asc_final_url":page.url,
            "fresh_graphql_response_count":len(fresh_graphql),
            "http_status":resp.status if resp else None,
        }
        (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False))
    finally:
        browser.close()


if __name__=="__main__":
    main()
