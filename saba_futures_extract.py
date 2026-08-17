#!/usr/bin/env python3
import json
import pathlib
import re
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

OUT = pathlib.Path("publish")
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "winner": {
        "label": "Winner",
        "pattern": r"ENGLISH PREMIER LEAGUE 2026/2027\s*-\s*WINNER",
        "min": 20,
    },
    "top4": {
        "label": "Top 4 Finish",
        "pattern": r"ENGLISH PREMIER LEAGUE 2026/2027\s*-\s*TOP 4 FINISH",
        "min": 20,
    },
    "relegation": {
        "label": "To Be Relegated",
        "pattern": r"ENGLISH PREMIER LEAGUE 2026/2027\s*-\s*TO BE RELEGATED",
        "min": 20,
    },
    "goalscorer": {
        "label": "Top Goalscorer",
        "pattern": r"ENGLISH PREMIER LEAGUE 2026/2027\s*-\s*TOP GOALSCORER",
        "min": 25,
    },
}


def parse_market_block(body: str, pattern: str):
    lines = [x.strip() for x in body.splitlines() if x.strip()]
    start = next((i for i, x in enumerate(lines) if re.search(pattern, x, re.I)), None)
    if start is None:
        return []

    block = []
    for x in lines[start + 1 :]:
        # Every SABA Outright market title in this board starts with an asterisk.
        if block and x.startswith("*") and re.search(r"20\d{2}|WINNER|FINISH|RELEGATED|GOALSCORER|BOTTOM|FORECAST", x, re.I):
            break
        block.append(x)
        if len(block) > 800:
            break

    selections = []
    i = 0
    while i + 2 < len(block):
        date_text, selection, odds_text = block[i], block[i + 1], block[i + 2]
        if (
            re.fullmatch(r"\d{2}/\d{2}/\d{4}", date_text)
            and re.search(r"[A-Za-z]", selection)
            and re.fullmatch(r"\d{1,3}(?:,\d{3})*(?:\.\d{1,3})?", odds_text)
        ):
            selections.append(
                {
                    "selection": selection,
                    "decimal": float(odds_text.replace(",", "")),
                    "market_date": date_text,
                }
            )
            i += 3
        else:
            i += 1
    return selections


def visible_target(frame, pattern):
    loc = frame.get_by_text(re.compile(pattern, re.I))
    for i in range(min(loc.count(), 120)):
        try:
            if loc.nth(i).is_visible():
                return loc.nth(i)
        except Exception:
            pass
    return None


result = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "source": "Dafabet OW / SABA public guest board",
    "source_url": "https://www.dafabet.com/en/sports",
    "sport": "Soccer",
    "league": "English Premier League",
    "season": "2026/2027",
    "odds_format": "Decimal",
    "markets": {},
}

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
    context = browser.new_context(locale="en-US", viewport={"width": 1500, "height": 1200})
    page = context.new_page()
    page.goto("https://www.dafabet.com/en/sports", wait_until="domcontentloaded", timeout=45000)

    sports_frame = None
    for _ in range(30):
        sports_frame = next(
            (f for f in page.frames if f.name == "sportsFrame" and "/Sports/1/" in f.url),
            None,
        )
        if sports_frame:
            break
        page.wait_for_timeout(1000)
    if not sports_frame:
        raise RuntimeError("SABA sportsFrame missing")

    base = sports_frame.url.split("/Sports/1/")[0]
    sports_frame.goto(
        base + "/Sports/1/OR?mode=m0&market=T",
        wait_until="domcontentloaded",
        timeout=40000,
    )

    # The lower EPL rows arrive after hydration. Waiting for the last target makes
    # all four target titles deterministic enough for the public board.
    try:
        sports_frame.get_by_text(re.compile(TARGETS["goalscorer"]["pattern"], re.I)).first.wait_for(
            state="visible", timeout=18000
        )
    except Exception:
        pass
    page.wait_for_timeout(1500)

    try:
        list_body = sports_frame.locator("body").inner_text(timeout=8000)
        m = re.search(r"\d{2}:\d{2}:\d{2}(?:AM|PM)\s+[A-Za-z]{3}\s+\d{1,2},\s+20\d{2}\s+GMT\s+[+-]\d+", list_body)
        if m:
            result["board_time"] = m.group(0)
    except Exception:
        pass

    for key, spec in TARGETS.items():
        chosen = visible_target(sports_frame, spec["pattern"])
        if not chosen:
            raise RuntimeError(f"Target market missing: {spec['label']}")

        try:
            chosen.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        chosen.click(timeout=8000)
        page.wait_for_timeout(2500)
        body = sports_frame.locator("body").inner_text(timeout=8000)
        selections = parse_market_block(body, spec["pattern"])
        if len(selections) < spec["min"]:
            raise RuntimeError(
                f"Incomplete {spec['label']}: {len(selections)} selections, expected >= {spec['min']}"
            )
        result["markets"][key] = {
            "label": spec["label"],
            "selection_count": len(selections),
            "selections": selections,
        }

        # Collapse before opening the next market; retain one hydrated guest board.
        try:
            chosen.click(timeout=5000)
            page.wait_for_timeout(600)
        except Exception:
            pass

    browser.close()

OUT.joinpath("data.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(
    json.dumps(
        {
            "generated_at": result["generated_at"],
            "board_time": result.get("board_time"),
            "markets": {k: v["selection_count"] for k, v in result["markets"].items()},
        },
        ensure_ascii=False,
    )
)
