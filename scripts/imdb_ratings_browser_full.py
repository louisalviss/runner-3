#!/usr/bin/env python3
import json
import re
from pathlib import Path

from cloakbrowser import launch

USER_ID = "ur83495069"
DESC_URL = f"https://www.imdb.com/user/{USER_ID}/ratings/?sort=date_added,desc"
ASC_URL = f"https://www.imdb.com/user/{USER_ID}/ratings/?sort=date_added,asc"
OUT = Path("imdb_browser_output")
OUT.mkdir(parents=True, exist_ok=True)


def dedupe_title_links(page):
    return page.evaluate("""() => {
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
        out.push({
          id: m[1],
          title,
          href: a.href,
          card_text: (card.innerText || '').trim()
        });
      }
      return out;
    }""")


def scroll_until_stable(page, expected=250, max_rounds=35):
    stable = 0
    history = []
    for _ in range(max_rounds):
        count = len(dedupe_title_links(page))
        history.append(count)
        if count >= expected:
            break
        clicked = page.evaluate("""() => {
          const els = Array.from(document.querySelectorAll('button,a'));
          const target = els.find(el => {
            const t=(el.innerText||el.textContent||'').trim();
            const a=(el.getAttribute('aria-label')||'').trim();
            return /^\d+\s+more$/i.test(t) || /^\d+\s+more$/i.test(a) || /^more$/i.test(t);
          });
          if (target) { target.scrollIntoView({block:'center'}); target.click(); return true; }
          return false;
        }""")
        if not clicked:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1400)
        new_count = len(dedupe_title_links(page))
        if new_count <= count:
            stable += 1
        else:
            stable = 0
        if stable >= 4:
            break
    return history


def save_snapshot(page, label):
    text = page.locator("body").inner_text(timeout=15000)
    (OUT / f"{label}.txt").write_text(text, encoding="utf-8")
    (OUT / f"{label}.html").write_text(page.content(), encoding="utf-8")
    rows = dedupe_title_links(page)
    (OUT / f"{label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows, text


def collect_graphql(page, bucket):
    def on_response(resp):
        if "graphql.imdb.com" not in resp.url:
            return
        try:
            bucket.append({"url": resp.url, "status": resp.status, "body": resp.text()})
        except Exception as exc:
            bucket.append({"url": resp.url, "status": resp.status, "error": f"{type(exc).__name__}: {exc}"})
    page.on("response", on_response)


def rating_map_from_graphql(graphql):
    out = {}
    for rec in graphql:
        try:
            data = json.loads(rec.get("body") or "{}").get("data") or {}
        except Exception:
            continue
        for item in data.get("titles") or []:
            r = item.get("otherUserRating")
            if item.get("id") and r and r.get("value") is not None:
                out[item["id"]] = {"value": r.get("value"), "date": r.get("date")}
    return out


def capture_sort(page, url, label):
    resp = page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(5000)
    history = scroll_until_stable(page, expected=250)
    rows, text = save_snapshot(page, label)
    return {
        "status": resp.status if resp else None,
        "rows": rows,
        "text": text,
        "history": history,
        "final_url": page.url,
    }


def main():
    graphql = []
    browser = launch(browser_version="146.0.7680.177.5", headless=False, humanize=True)
    try:
        page = browser.new_page(viewport={"width": 1365, "height": 900})
        collect_graphql(page, graphql)

        desc = capture_sort(page, DESC_URL, "desc-full")
        asc = capture_sort(page, ASC_URL, "asc-full")

        total = None
        for text in (desc["text"], asc["text"]):
            m = re.search(r"1-\d+\s*\nof\s+(\d+)", text)
            if m:
                total = int(m.group(1))
                break

        merged_cards = {}
        for row in desc["rows"] + asc["rows"]:
            merged_cards.setdefault(row["id"], row)

        ratings = rating_map_from_graphql(graphql)
        all_ids = list(merged_cards)
        clean = []
        for tt in all_ids:
            row = merged_cards[tt]
            rr = ratings.get(tt, {})
            clean.append({
                "id": tt,
                "title": row.get("title") or "",
                "user_rating": rr.get("value"),
                "rated_at": rr.get("date"),
                "card_text": row.get("card_text") or "",
            })

        (OUT / "graphql-responses.json").write_text(json.dumps(graphql, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "ratings-clean.json").write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

        summary = {
            "user_id": USER_ID,
            "reported_total": total,
            "desc_unique_titles": len(desc["rows"]),
            "asc_unique_titles": len(asc["rows"]),
            "union_unique_titles": len(merged_cards),
            "ratings_from_graphql": len(ratings),
            "ratings_joined_to_cards": sum(1 for x in clean if x["user_rating"] is not None),
            "desc_count_history": desc["history"],
            "asc_count_history": asc["history"],
            "desc_final_url": desc["final_url"],
            "asc_final_url": asc["final_url"],
            "graphql_response_count": len(graphql),
        }
        (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        browser.close()


if __name__ == "__main__":
    main()
