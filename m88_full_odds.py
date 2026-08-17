#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# suffix: (market name, family, selections, odds-key suffix)
SIMPLE_MARKETS = {
    "a": ("ft_asian_handicap", "asian_handicap", ("home", "away"), "a"),
    "b": ("ft_over_under", "over_under", ("over", "under"), "b"),
    "c": ("ft_odd_even", "odd_even", ("odd", "even"), "c"),
    "d": ("ft_1x2", "1x2", ("home", "draw", "away"), "d"),
    "e": ("fh_asian_handicap", "asian_handicap", ("home", "away"), "e"),
    "f": ("fh_over_under", "over_under", ("over", "under"), "f"),
    "g": ("fh_1x2", "1x2", ("home", "draw", "away"), "g"),
    "h": ("fh_odd_even", "odd_even", ("odd", "even"), "h"),
    "i": ("double_chance", "double_chance", ("1X", "12", "X2"), "i"),
    "j": ("first_last_goal", "first_last_goal", (
        "first_goal_home", "first_goal_away", "last_goal_home", "last_goal_away", "no_goal"
    ), "j"),
    # The MSports response really uses an uppercase K for odds keys.
    "k": ("ht_ft", "ht_ft", (
        "home_home", "home_draw", "home_away",
        "draw_home", "draw_draw", "draw_away",
        "away_home", "away_draw", "away_away"
    ), "K"),
    "n": ("ft_total_goals", "total_goals", ("0-1", "2-3", "4-6", "7+"), "n"),
    "o": ("fh_total_goals", "total_goals", ("0-1", "2-3", "4+"), "o"),
}

SCOPE_FILES = ("live", "today", "early")
EXTRA_GROUPS = (4, 5, 6, 7, 8)
SCORE_RE = re.compile(r"^\d+-\d+$")


def text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def number(v: Any):
    s = text(v)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return s


def parse_price(raw: Any) -> dict[str, Any] | None:
    s = text(raw)
    if not s:
        return None
    parts = s.split("|")
    primary = text(parts[0]) if parts else ""
    # M88 uses a literal | for unavailable selections.
    if not primary:
        return None
    secondary = text(parts[1]) if len(parts) > 1 else ""
    choice_id = text(parts[2]) if len(parts) > 2 else ""
    return {
        "value": number(primary),
        "secondary": number(secondary),
        "choice_id": choice_id or None,
        "raw": s,
    }


def league_from_row(row: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    raw = text(row.get("event_name"))
    if not raw:
        return previous
    return {
        "id": text(row.get("no_event")) or previous.get("id"),
        "name": text(raw.split("|")[0]),
        "raw": raw,
    }


def simple_market_line(row: dict[str, Any], suffix: str) -> dict[str, Any] | None:
    market, family, selections, odds_suffix = SIMPLE_MARKETS[suffix]
    game_type = text(row.get(f"game_type_{suffix}"))
    if not game_type:
        return None
    prices = []
    for idx, selection in enumerate(selections, start=1):
        p = parse_price(row.get(f"odds_{idx}_{odds_suffix}"))
        if p is not None:
            prices.append({"selection": selection, **p})
    if not prices:
        return None
    item: dict[str, Any] = {
        "market": market,
        "family": family,
        "game_type": game_type,
        "sub_partai": text(row.get(f"sub_partai_{suffix}")) or None,
        "status_raw": text(row.get(f"status_{suffix}")) or None,
        "cash_out_raw": text(row.get(f"cash_out_{suffix}")) or None,
        "prices": prices,
    }
    if family in {"asian_handicap", "over_under"}:
        item["line"] = number(row.get(f"hdc_ori_{suffix}"))
        item["line_display_raw"] = text(row.get(f"hdc_display_{suffix}")) or None
    return item


def correct_score_line(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = text(row.get("odds_1_l")) or text(row.get("game_type_l"))
    if not raw or "_" not in raw:
        return None
    prices = []
    for chunk in raw.split("_"):
        parts = chunk.split("|")
        if not parts or not SCORE_RE.match(text(parts[0])):
            continue
        score = text(parts[0])
        primary = text(parts[1]) if len(parts) > 1 else ""
        if not primary:
            continue
        secondary = text(parts[2]) if len(parts) > 2 else ""
        choice = text(parts[3]) if len(parts) > 3 else ""
        prices.append({
            "selection": score,
            "value": number(primary),
            "secondary": number(secondary),
            "choice_id": choice or None,
            "raw": "|".join(parts),
        })
    if not prices:
        return None
    # The packed prefix is normally e.g. 1001_29 before score entries.
    prefix = raw.split("_")[0]
    return {
        "market": "correct_score",
        "family": "correct_score",
        "game_type": prefix,
        "sub_partai": None,
        "status_raw": None,
        "cash_out_raw": None,
        "prices": prices,
    }


def line_key(line: dict[str, Any]) -> str:
    return json.dumps({
        "market": line.get("market"),
        "game_type": line.get("game_type"),
        "sub_partai": line.get("sub_partai"),
        "line": line.get("line"),
        "prices": [(p.get("selection"), p.get("value"), p.get("choice_id")) for p in line.get("prices", [])],
    }, sort_keys=True, ensure_ascii=False)


def add_row_markets(match: dict[str, Any], row: dict[str, Any]) -> None:
    seen = match.setdefault("_market_keys", set())
    for suffix in SIMPLE_MARKETS:
        line = simple_market_line(row, suffix)
        if line is None:
            continue
        key = line_key(line)
        if key not in seen:
            seen.add(key)
            match["markets"].setdefault(line["market"], []).append(line)
    cs = correct_score_line(row)
    if cs is not None:
        key = line_key(cs)
        if key not in seen:
            seen.add(key)
            match["markets"].setdefault("correct_score", []).append(cs)


def new_match(row: dict[str, Any], scope: str, sport_id: str | None, league: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": scope,
        "sport_id": sport_id,
        "league": dict(league),
        "match_id": text(row.get("no_partai")) or None,
        "match_date": text(row.get("match_date")) or None,
        "home": text(row.get("club_home")),
        "away": text(row.get("club_away")),
        "home_score": text(row.get("home_score")) or None,
        "away_score": text(row.get("away_score")) or None,
        "live_timer": text(row.get("live_timer")) or None,
        "event_round": text(row.get("event_round")) or None,
        "is_live": text(row.get("is_live")) or None,
        "is_neutral": text(row.get("is_neutral")) or None,
        "markets": {},
        "_market_keys": set(),
    }


def parse_payload(payload: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    if payload.get("status") != 1:
        return []
    matches: list[dict[str, Any]] = []
    league: dict[str, Any] = {"id": None, "name": "", "raw": ""}
    current: dict[str, Any] | None = None
    for block in payload.get("data") or []:
        if not isinstance(block, dict):
            continue
        sport_id = text(block.get("spid")) or None
        for row in block.get("data") or []:
            if not isinstance(row, dict):
                continue
            league = league_from_row(row, league)
            home, away = text(row.get("club_home")), text(row.get("club_away"))
            if home or away:
                current = new_match(row, scope, sport_id, league)
                matches.append(current)
            elif current is None:
                continue
            elif league.get("name") and current.get("league", {}).get("name") != league.get("name"):
                continue
            add_row_markets(current, row)
    return matches


def match_key(m: dict[str, Any]) -> tuple:
    if m.get("match_id"):
        return ("id", str(m["match_id"]))
    return ("names", m.get("scope"), m.get("home"), m.get("away"), (m.get("league") or {}).get("name"))


def merge_match(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for field in ("match_date", "home_score", "away_score", "live_timer", "event_round", "is_live", "is_neutral"):
        if src.get(field) not in (None, ""):
            dst[field] = src[field]
    if src.get("league", {}).get("name"):
        dst["league"] = src["league"]
    seen = dst.setdefault("_market_keys", set())
    for name, lines in (src.get("markets") or {}).items():
        for line in lines:
            key = line_key(line)
            if key in seen:
                continue
            seen.add(key)
            dst["markets"].setdefault(name, []).append(line)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_scope(input_dir: Path, scope: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files = [(1, input_dir / f"{scope}.json")] + [(g, input_dir / f"{scope}_g{g}.json") for g in EXTRA_GROUPS]
    merged: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
    sources = []
    for group, path in files:
        payload = load_json(path)
        if payload is None:
            sources.append({"scope": scope, "group": group, "file": str(path), "present": False})
            continue
        parsed = parse_payload(payload, scope)
        sources.append({
            "scope": scope, "group": group, "file": str(path), "present": True,
            "api_status": payload.get("status"), "matches": len(parsed), "bytes": path.stat().st_size,
        })
        for m in parsed:
            key = match_key(m)
            if key not in merged:
                merged[key] = m
            else:
                merge_match(merged[key], m)
    out = list(merged.values())
    for m in out:
        m.pop("_market_keys", None)
    return out, sources


def write_csv(path: Path, matches: list[dict[str, Any]], odds_format: str) -> None:
    fields = [
        "scope", "league", "match_id", "match_date", "live_timer", "event_round", "home", "away",
        "home_score", "away_score", "market", "family", "game_type", "sub_partai", "line",
        "selection", "price", "secondary", "choice_id", "raw_price", "odds_format",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for m in matches:
            for market, lines in (m.get("markets") or {}).items():
                for line in lines:
                    for p in line.get("prices") or []:
                        w.writerow({
                            "scope": m.get("scope"), "league": (m.get("league") or {}).get("name"),
                            "match_id": m.get("match_id"), "match_date": m.get("match_date"),
                            "live_timer": m.get("live_timer"), "event_round": m.get("event_round"),
                            "home": m.get("home"), "away": m.get("away"),
                            "home_score": m.get("home_score"), "away_score": m.get("away_score"),
                            "market": market, "family": line.get("family"), "game_type": line.get("game_type"),
                            "sub_partai": line.get("sub_partai"), "line": line.get("line"),
                            "selection": p.get("selection"), "price": p.get("value"),
                            "secondary": p.get("secondary"), "choice_id": p.get("choice_id"),
                            "raw_price": p.get("raw"), "odds_format": odds_format,
                        })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default="evidence")
    ap.add_argument("--output-json", default="evidence/m88_full_odds.json")
    ap.add_argument("--output-csv", default="evidence/m88_full_odds.csv")
    ap.add_argument("--odds-format", default="decimal")
    args = ap.parse_args()
    input_dir = Path(args.input_dir)
    all_matches: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for scope in SCOPE_FILES:
        ms, ss = load_scope(input_dir, scope)
        all_matches.extend(ms)
        sources.extend(ss)
    by_scope = {s: sum(1 for m in all_matches if m.get("scope") == s) for s in SCOPE_FILES}
    market_matches: dict[str, int] = {}
    selection_counts: dict[str, int] = {}
    for m in all_matches:
        for name, lines in (m.get("markets") or {}).items():
            market_matches[name] = market_matches.get(name, 0) + 1
            selection_counts[name] = selection_counts.get(name, 0) + sum(len(x.get("prices") or []) for x in lines)
    output = {
        "source": "M88 / MSports public guest API full soccer groups",
        "odds_format": args.odds_format,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "matches": len(all_matches), "by_scope": by_scope,
            "market_matches": market_matches, "selections": selection_counts,
            "total_selections": sum(selection_counts.values()),
        },
        "sources": sources,
        "matches": all_matches,
    }
    jp, cp = Path(args.output_json), Path(args.output_csv)
    jp.parent.mkdir(parents=True, exist_ok=True); cp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_csv(cp, all_matches, args.odds_format)
    print(json.dumps(output["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
