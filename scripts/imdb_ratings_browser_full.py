#!/usr/bin/env python3
import json
import re
from pathlib import Path

from cloakbrowser import launch

USER_ID = "ur83495069"
START_URL = f"https://www.imdb.com/user/{USER_ID}/ratings/?sort=date_added,desc"
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
        const attrs = [];
        for (const el of card.querySelectorAll('[aria-label],[title],[data-testid]')) {
          const rec = {};
          for (const k of ['aria-label','title','data-testid']) {
            const v = el.getAttribute(k);
            if (v) rec[k] = v;
          }
          if (Object.keys(rec).length) attrs.push(rec);
        }
        out.push({
          id: m[1],
          title,
          href: a.href,
          card_text: (card.innerText || '').trim(),
          attrs
        });
      }
      return out;
    }""")


def nav_controls(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('button,a'))
      .map((el, i) => ({i, text:(el.innerText||el.textContent||'').trim(), href:el.href||'', aria:el.getAttribute('aria-label')||''}))
      .filter(x => x.text || x.aria)
      .filter(x => /more|next|previous|^\d+$|of\s+\d+/i.test(`${x.text} ${x.aria}`))
    """)


def scroll_until_stable(page, expected=None, max_rounds=35):
    stable = 0
    history = []
    for _ in range(max_rounds):
        count = len(dedupe_title_links(page))
        history.append(count)
        if expected and count >= expected:
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
    (OUT / f"{label}.txt").write_text(page.locator("body").inner_text(timeout=15000), encoding="utf-8")
    (OUT / f"{label}.html").write_text(page.content(), encoding="utf-8")
    rows = dedupe_title_links(page)
    (OUT / f"{label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"{label}-nav.json").write_text(json.dumps(nav_controls(page), ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def click_next(page):
    info = page.evaluate("""() => {
      const els = Array.from(document.querySelectorAll('button,a'));
      const el = els.find(x => {
        const t=(x.innerText||x.textContent||'').trim();
        const a=(x.getAttribute('aria-label')||'').trim();
        return /^next$/i.test(t) || /^next$/i.test(a);
      });
      if (!el) return {clicked:false};
      const before=location.href;
      el.scrollIntoView({block:'center'});
      el.click();
      return {clicked:true, tag:el.tagName, href:el.href||'', before};
    }""")
    if info.get("clicked"):
        page.wait_for_timeout(6000)
        info["after"] = page.url
    return info


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


def main():
    graphql = []
    browser = launch(browser_version="146.0.7680.177.5", headless=False, humanize=True)
    try:
        page = browser.new_page(viewport={"width": 1365, "height": 900})
        collect_graphql(page, graphql)
        resp = page.goto(START_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)

        initial_text = page.locator("body").inner_text(timeout=15000)
        total = None
        m = re.search(r"1-\d+\s*\nof\s+(\d+)", initial_text)
        if m:
            total = int(m.group(1))

        hist1 = scroll_until_stable(page, expected=250)
        rows1 = save_snapshot(page, "page1-full")
        if total is None:
            full_text = (OUT / "page1-full.txt").read_text(encoding="utf-8")
            m = re.search(r"1-\d+\s*\nof\s+(\d+)", full_text)
            if m:
                total = int(m.group(1))

        next_info = click_next(page)
        rows2 = []
        hist2 = []
        if next_info.get("clicked"):
            expected2 = max((total or 261) - len(rows1), 1)
            hist2 = scroll_until_stable(page, expected=expected2, max_rounds=15)
            rows2 = save_snapshot(page, "page2-full")

        merged = []
        seen = set()
        for row in rows1 + rows2:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            merged.append(row)

        ratings = rating_map_from_graphql(graphql)
        clean = []
        for row in merged:
            rr = ratings.get(row["id"], {})
            clean.append({
                "id": row["id"],
                "title": row.get("title") or "",
                "user_rating": rr.get("value"),
                "rated_at": rr.get("date"),
                "card_text": row.get("card_text") or "",
            })

        (OUT / "graphql-responses.json").write_text(json.dumps(graphql, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "all-visible-ratings-cards.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "ratings-clean.json").write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

        summary = {
            "user_id": USER_ID,
            "start_url": START_URL,
            "http_status": resp.status if resp else None,
            "reported_total": total,
            "page1_unique_titles": len(rows1),
            "page2_unique_titles": len(rows2),
            "merged_unique_titles": len(merged),
            "ratings_from_graphql": len(ratings),
            "ratings_joined_to_cards": sum(1 for x in clean if x["user_rating"] is not None),
            "page1_count_history": hist1,
            "page2_count_history": hist2,
            "next": next_info,
            "graphql_response_count": len(graphql),
        }
        (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        browser.close()


if __name__ == "__main__":
    main()
