#!/usr/bin/env python3
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

from cloakbrowser import launch

USER_ID = "ur83495069"
START_URL = f"https://www.imdb.com/user/{USER_ID}/ratings/?sort=date_added,desc"
OUT = Path("imdb_browser_output")
OUT.mkdir(parents=True, exist_ok=True)


def dedupe_title_links(page):
    rows = page.evaluate("""() => {
      const out = [];
      const seen = new Set();
      for (const a of document.querySelectorAll('a[href*="/title/tt"]')) {
        const m = a.getAttribute('href')?.match(/\/title\/(tt\d+)/);
        if (!m || seen.has(m[1])) continue;
        const card = a.closest('li.ipc-metadata-list-summary-item') || a.closest('[data-testid="list-item"]') || a.closest('li') || a.parentElement;
        seen.add(m[1]);
        const attrs = [];
        if (card) {
          for (const el of card.querySelectorAll('[aria-label],[title],[data-testid]')) {
            const rec = {};
            for (const k of ['aria-label','title','data-testid']) {
              const v = el.getAttribute(k);
              if (v) rec[k] = v;
            }
            if (Object.keys(rec).length) attrs.push(rec);
          }
        }
        out.push({
          id: m[1],
          title: (a.textContent || '').trim(),
          href: a.href,
          card_text: (card?.innerText || '').trim(),
          attrs
        });
      }
      return out;
    }""")
    return rows


def visible_more_buttons(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('button,a'))
      .map((el, i) => ({i, text:(el.innerText||el.textContent||'').trim(), href:el.href||'', aria:el.getAttribute('aria-label')||''}))
      .filter(x => x.text || x.aria)
      .filter(x => /more|next|previous|^\d+$|of\s+\d+/i.test(`${x.text} ${x.aria}`))
    """)


def scroll_until_stable(page, expected=None, max_rounds=35):
    best = 0
    stable = 0
    history = []
    for r in range(max_rounds):
        rows = dedupe_title_links(page)
        count = len(rows)
        history.append(count)
        best = max(best, count)
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
    (OUT / f"{label}-nav.json").write_text(json.dumps(visible_more_buttons(page), ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def find_next_href(page):
    return page.evaluate("""() => {
      const els = Array.from(document.querySelectorAll('a'));
      const a = els.find(el => /^(next)$/i.test((el.innerText||el.textContent||'').trim()) || /next/i.test(el.getAttribute('aria-label')||''));
      return a ? a.href : null;
    }""")


def collect_graphql(page, bucket):
    def on_response(resp):
        url = resp.url
        if "graphql.imdb.com" not in url:
            return
        try:
            text = resp.text()
            bucket.append({"url": url, "status": resp.status, "body": text})
        except Exception as exc:
            bucket.append({"url": url, "status": resp.status, "error": f"{type(exc).__name__}: {exc}"})
    page.on("response", on_response)


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

        # IMDb currently lazy-loads page 1 even when the pager says 1-250.
        hist1 = scroll_until_stable(page, expected=250)
        rows1 = save_snapshot(page, "page1-full")
        next_href = find_next_href(page)

        rows2 = []
        hist2 = []
        if next_href:
            page.goto(next_href, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(4000)
            hist2 = scroll_until_stable(page, expected=(max(total - len(rows1), 1) if total else None), max_rounds=20)
            rows2 = save_snapshot(page, "page2-full")

        # Merge by tt id, preserving page order.
        merged = []
        seen = set()
        for row in rows1 + rows2:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            merged.append(row)

        (OUT / "graphql-responses.json").write_text(json.dumps(graphql, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {
            "user_id": USER_ID,
            "start_url": START_URL,
            "http_status": resp.status if resp else None,
            "reported_total": total,
            "page1_unique_titles": len(rows1),
            "page2_unique_titles": len(rows2),
            "merged_unique_titles": len(merged),
            "page1_count_history": hist1,
            "page2_count_history": hist2,
            "next_href": next_href,
            "graphql_response_count": len(graphql),
        }
        (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "all-visible-ratings-cards.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        browser.close()


if __name__ == "__main__":
    main()
