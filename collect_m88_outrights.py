#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright


def parse_post(value: str):
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        pass
    try:
        return {k: v[-1] for k, v in parse_qs(value).items()}
    except Exception:
        return {}


def provider_frame(page):
    frames = [f for f in page.frames if urlparse(f.url).netloc.startswith("i1x9gr.")]
    return frames[-1] if frames else None


def scroll_all(frame, pct: int):
    try:
        frame.evaluate(
            """pct => {
              const frac=Math.max(0,Math.min(1,pct/100));
              const root=document.scrollingElement||document.documentElement;
              if(root) root.scrollTop=(root.scrollHeight-root.clientHeight)*frac;
              for(const e of document.querySelectorAll('*')){
                const cs=getComputedStyle(e);
                if((cs.overflowY==='auto'||cs.overflowY==='scroll') && e.scrollHeight>e.clientHeight+180){
                  e.scrollTop=(e.scrollHeight-e.clientHeight)*frac;
                }
              }
            }""",
            pct,
        )
    except Exception:
        pass


def visible_title(frame, title: str):
    loc = frame.get_by_text(title, exact=True)
    for i in range(min(loc.count(), 30)):
        try:
            if loc.nth(i).is_visible():
                return loc.nth(i)
        except Exception:
            pass
    return None


def title_meta(title: str):
    clean = title.strip().lstrip("*").strip()
    season = None
    match = re.search(r"\b(20\d{2}/20\d{2})\b", clean)
    if match:
        season = match.group(1)
    competition = market_name = None
    if " - " in clean:
        left, right = clean.rsplit(" - ", 1)
        market_name = right.strip()
        competition = re.sub(r"\s*20\d{2}/20\d{2}\s*", " ", left).strip()
    return {
        "competition_guess": competition,
        "season_guess": season,
        "market_name_guess": market_name,
    }


def click_sports(frame, page):
    """Best-effort navigation to the normal Sports board before selecting Outright."""
    deadline = time.time() + 15
    while time.time() < deadline:
        current = provider_frame(page) or frame
        if "/sports/" in current.url:
            return current
        sports = current.get_by_text("Sports", exact=True)
        for i in range(min(sports.count(), 20)):
            try:
                node = sports.nth(i)
                if node.is_visible():
                    node.click(timeout=2500)
                    page.wait_for_timeout(900)
                    current = provider_frame(page) or current
                    if "/sports/" in current.url:
                        return current
            except Exception:
                pass
        page.wait_for_timeout(500)
    return provider_frame(page) or frame


def click_outright(frame, page, showall):
    """Open SABA Outright using its native feature-bar metadata, with text fallback."""
    start_showall = len(showall)
    deadline = time.time() + 28
    last_debug = {}

    while time.time() < deadline:
        frame = provider_frame(page) or frame
        if "/outright" in frame.url.lower():
            return frame

        clicked = False
        try:
            info = frame.evaluate(
                """() => {
                  const dm=document.querySelector('[data-market="outright"]');
                  const dk=document.querySelector('[data-key="outright"]');
                  const e=dm||dk;
                  const allDM=document.querySelectorAll('[data-market="outright"]').length;
                  const allDK=document.querySelectorAll('[data-key="outright"]').length;
                  if(!e) return {clicked:false,allDM,allDK};
                  e.scrollIntoView({block:'nearest',inline:'center'});
                  const btn=e.closest('.feature-bar__market-button') ||
                            e.closest('[data-market="outright"]') ||
                            e.closest('[data-key="outright"]') ||
                            e.parentElement || e;
                  btn.click();
                  return {clicked:true,allDM,allDK,tag:e.tagName,cls:e.className||'',text:(e.innerText||e.textContent||'').trim()};
                }"""
            )
            last_debug = info or last_debug
            clicked = bool((info or {}).get("clicked"))
        except Exception as exc:
            last_debug = {"metadata_selector_error": str(exc)}

        if not clicked:
            try:
                loc = frame.get_by_text(re.compile(r"^\s*Outright(?:\s+\d+)?\s*$", re.I))
                for i in range(min(loc.count(), 10)):
                    node = loc.nth(i)
                    try:
                        node.scroll_into_view_if_needed(timeout=1200)
                        node.evaluate(
                            """e => {
                              const btn=e.closest('.feature-bar__market-button') ||
                                        e.closest('[data-market="outright"]') ||
                                        e.closest('[data-key="outright"]') ||
                                        e.parentElement || e;
                              btn.click();
                            }"""
                        )
                        clicked = True
                        last_debug = {"text_fallback": True, "count": loc.count()}
                        break
                    except Exception:
                        pass
            except Exception as exc:
                last_debug = {**last_debug, "text_fallback_error": str(exc)}

        page.wait_for_timeout(1000 if clicked else 500)
        fresh = provider_frame(page) or frame
        if "/outright" in fresh.url.lower():
            print("OUTRIGHT_NAV_OK", fresh.url, json.dumps(last_debug, ensure_ascii=False))
            return fresh

        # A newly emitted ShowAllOdds after clicking is useful evidence that the board
        # changed; give the router a little more time to settle before another click.
        if clicked and len(showall) > start_showall:
            page.wait_for_timeout(1000)
            fresh = provider_frame(page) or fresh
            if "/outright" in fresh.url.lower():
                print("OUTRIGHT_NAV_OK", fresh.url, json.dumps(last_debug, ensure_ascii=False))
                return fresh
        frame = fresh

    try:
        diagnostic = frame.evaluate(
            """() => ({
              url:location.href,
              dataMarket:document.querySelectorAll('[data-market="outright"]').length,
              dataKey:document.querySelectorAll('[data-key="outright"]').length,
              featureButtons:document.querySelectorAll('.feature-bar__market-button').length,
              bodyText:(document.body?.innerText||'').slice(0,1200)
            })"""
        )
    except Exception as exc:
        diagnostic = {"url": getattr(frame, "url", ""), "diagnostic_error": str(exc)}
    raise RuntimeError("Could not navigate to SABA Outright: " + json.dumps({"last": last_debug, "page": diagnostic}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--health")
    ap.add_argument("--screenshot")
    ap.add_argument("--min-publish-ratio", type=float, default=0.75)
    args = ap.parse_args()

    showall = []
    getmarkets = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            screen={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            locale="en-US",
            timezone_id="Asia/Bangkok",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 26_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1",
        )
        page = context.new_page()

        def on_response(response):
            try:
                if "BFOdds/ShowAllOdds" in response.url:
                    showall.append(json.loads(response.text()))
                elif "BFOdds/GetMarket" in response.url:
                    getmarkets.append({
                        "post": response.request.post_data or "",
                        "body": response.text(),
                        "url": response.url,
                    })
            except Exception:
                pass

        page.on("response", on_response)
        page.goto("https://www.m88.com/sports/Saba%20Sports?Language=en-US", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(22000)
        frame = provider_frame(page)
        if not frame:
            raise RuntimeError("No SABA frame")

        frame = click_sports(frame, page)
        page.wait_for_timeout(3500)
        frame = provider_frame(page) or frame
        frame = click_outright(frame, page, showall)
        page.wait_for_timeout(7000)
        frame = provider_frame(page) or frame
        route = frame.url
        if "/outright" not in route.lower():
            raise RuntimeError("Outright route validation failed: " + route)

        for pct in range(0, 101, 10):
            scroll_all(frame, pct)
            page.wait_for_timeout(350)
        scroll_all(frame, 0)
        page.wait_for_timeout(800)

        league_names = {}
        team_names = {}
        for obj in showall:
            data = (obj or {}).get("Data") or {}
            for key, value in (data.get("LeagueN") or {}).items():
                league_names[str(key)] = value
            for key, value in (data.get("TeamN") or {}).items():
                team_names[str(key)] = value

        targets = []
        for key, title in league_names.items():
            if key.isdigit() and isinstance(title, str) and title.strip():
                targets.append((int(key), title.strip()))
        targets.sort(key=lambda item: item[0])
        if len(targets) < 40:
            raise RuntimeError(f"Unsafe Outright discovery count={len(targets)} showall={len(showall)}")

        markets = []
        failures = []
        unresolved = 0

        for index, (market_id, title) in enumerate(targets, 1):
            element = visible_title(frame, title)
            if element is None:
                for pct in range(0, 101, 10):
                    scroll_all(frame, pct)
                    page.wait_for_timeout(120)
                    element = visible_title(frame, title)
                    if element is not None:
                        break
            if element is None:
                failures.append({"market_id": market_id, "title": title, "reason": "title_not_in_dom"})
                continue

            try:
                element.scroll_into_view_if_needed(timeout=3500)
                page.wait_for_timeout(100)
            except Exception:
                pass

            captured = None
            for _ in range(2):
                before = len(getmarkets)
                try:
                    element.click(timeout=4500)
                except Exception:
                    try:
                        element.evaluate("e=>e.click()")
                    except Exception:
                        pass
                deadline = time.time() + 4.5
                while time.time() < deadline and captured is None:
                    for response in getmarkets[before:]:
                        post = parse_post(response["post"])
                        try:
                            got = int(post.get("Matchid", -1))
                        except Exception:
                            got = -1
                        if got == market_id:
                            captured = response
                            break
                    if captured is None:
                        page.wait_for_timeout(120)
                if captured is not None:
                    break

            if captured is None:
                failures.append({"market_id": market_id, "title": title, "reason": "no_native_getmarket"})
                continue
            try:
                obj = json.loads(captured["body"])
            except Exception:
                failures.append({"market_id": market_id, "title": title, "reason": "non_json_getmarket"})
                continue

            data = (obj or {}).get("Data") or {}
            for key, value in (data.get("TeamN") or {}).items():
                team_names[str(key)] = value
            selections = []
            for odd in data.get("NewOdds") or []:
                team_id = odd.get("TeamId")
                price = odd.get("Price")
                if price is None:
                    continue
                name = team_names.get(str(team_id))
                if not name:
                    name = f"ID:{team_id}"
                    unresolved += 1
                selections.append({
                    "name": name,
                    "odds": price,
                    "team_id": team_id,
                    "market_id": odd.get("MarketId"),
                })
            if not selections:
                failures.append({"market_id": market_id, "title": title, "reason": "empty_selections"})
                continue

            markets.append({
                "market_id": market_id,
                "title": title,
                "normalized_title": re.sub(r"\s+", " ", title).strip().casefold(),
                **title_meta(title),
                "selections": selections,
            })
            if index % 10 == 0:
                print(f"CAPTURE_PROGRESS {index}/{len(targets)} ok={len(markets)} fail={len(failures)}")
            try:
                element.click(timeout=1200)
                page.wait_for_timeout(60)
            except Exception:
                pass

        now = datetime.now(timezone.utc)
        vn = timezone(timedelta(hours=7))
        ratio = len(markets) / len(targets) if targets else 0
        result = {
            "schema_version": 2,
            "operator": "M88",
            "provider": "SABA Sports",
            "exact_operator_odds": True,
            "sport": "soccer",
            "dataset": "all_outrights",
            "source_kind": "public_guest_board_native_capture",
            "source_url": "https://www.m88.com/sports/Saba%20Sports?Language=en-US",
            "provider_route": route,
            "captured_at_utc": now.isoformat().replace("+00:00", "Z"),
            "captured_at_vn": now.astimezone(vn).isoformat(),
            "refresh_target_minutes": 15,
            "status": "fresh" if ratio >= 0.90 else "partial",
            "coverage": {
                "showall_responses": len(showall),
                "discovered_markets": len(targets),
                "captured_markets": len(markets),
                "failed_markets": len(failures),
                "capture_ratio": round(ratio, 4),
                "unresolved_selection_names": unresolved,
            },
            "usage": {
                "instruction": "Search title/normalized_title/competition_guess. Use only these M88 odds. A market may be declared not listed only when this snapshot is fresh and coverage is high. Never substitute another bookmaker.",
                "not_listed_requires_capture_ratio": 0.90,
                "stale_after_minutes": 45,
            },
            "markets": markets,
            "failures": failures,
        }

        if ratio < args.min_publish_ratio:
            raise RuntimeError(f"Unsafe capture coverage {ratio:.1%}: {len(markets)}/{len(targets)}")

        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if args.health:
            health = {key: result[key] for key in ("captured_at_utc", "captured_at_vn", "status", "coverage")}
            Path(args.health).write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.screenshot:
            page.screenshot(path=args.screenshot, full_page=False)
        print(json.dumps(result["coverage"], ensure_ascii=False))
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
