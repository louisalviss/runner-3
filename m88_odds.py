#!/usr/bin/env python3

"""Normalize public MSports/M88 guest odds responses.

Input files are the JSON responses from /api/v1/m88/data/main for live/today/early.
The parser intentionally preserves raw values while exposing the market mapping used by
MSports' public frontend:
  a = FT Asian Handicap, b = FT O/U, c = FT Odd/Even, d = FT 1X2
  e = 1H Asian Handicap, f = 1H O/U, g = 1H 1X2, h = 1H Odd/Even

Rows without team names are alternate market lines for the preceding match, so they
are merged into that match instead of discarded.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MARKETS = {
    "a": ("ft_asian_handicap", "asian_handicap", ("home", "away")),
    "b": ("ft_over_under", "over_under", ("over", "under")),
    "c": ("ft_odd_even", "odd_even", ("odd", "even")),
    "d": ("ft_1x2", "1x2", ("home", "draw", "away")),
    "e": ("fh_asian_handicap", "asian_handicap", ("home", "away")),
    "f": ("fh_over_under", "over_under", ("over", "under")),
    "g": ("fh_1x2", "1x2", ("home", "draw", "away")),
    "h": ("fh_odd_even", "odd_even", ("odd", "even")),
}

SCOPE_FILES = ("live", "today", "early")


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def number(value: Any):
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return text


def parse_price(raw: Any) -> dict[str, Any] | None:
    text = clean_text(raw)
    if not text:
        return None
    parts = text.split("|")
    primary = clean_text(parts[0]) if parts else ""
    secondary = clean_text(parts[1]) if len(parts) > 1 else ""
    choice_id = clean_text(parts[2]) if len(parts) > 2 else ""
    return {
        "value": number(primary),
        "secondary": number(secondary),
        "choice_id": choice_id or None,
        "raw": text,
    }


def league_fields(row: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    raw = clean_text(row.get("event_name"))
    league_id = clean_text(row.get("no_event"))
    if not raw:
        return previous
    parts = raw.split("|")
    return {
        "id": league_id or previous.get("id"),
        "name": clean_text(parts[0]),
        "raw": raw,
    }


def market_line(row: dict[str, Any], suffix: str) -> dict[str, Any] | None:
    market_name, family, selections = MARKETS[suffix]
    game_type = clean_text(row.get(f"game_type_{suffix}"))
    prices = []
    for idx, selection in enumerate(selections, start=1):
        parsed = parse_price(row.get(f"odds_{idx}_{suffix}"))
        if parsed is not None:
            prices.append({"selection": selection, **parsed})
    if not game_type or not prices:
        return None

    item: dict[str, Any] = {
        "market": market_name,
        "family": family,
        "game_type": game_type,
        "sub_partai": clean_text(row.get(f"sub_partai_{suffix}")) or None,
        "status_raw": clean_text(row.get(f"status_{suffix}")) or None,
        "cash_out_raw": clean_text(row.get(f"cash_out_{suffix}")) or None,
        "prices": prices,
    }
    if family in {"asian_handicap", "over_under"}:
        item["line"] = number(row.get(f"hdc_ori_{suffix}"))
        item["line_display_raw"] = clean_text(row.get(f"hdc_display_{suffix}")) or None
    return item


def line_key(line: dict[str, Any]) -> str:
    return json.dumps(
        {
            "market": line.get("market"),
            "game_type": line.get("game_type"),
            "sub_partai": line.get("sub_partai"),
            "line": line.get("line"),
            "prices": [(p.get("selection"), p.get("raw")) for p in line.get("prices", [])],
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def add_markets(match: dict[str, Any], row: dict[str, Any]) -> None:
    seen = match.setdefault("_market_keys", set())
    for suffix in MARKETS:
        line = market_line(row, suffix)
        if line is None:
            continue
        key = line_key(line)
        if key in seen:
            continue
        seen.add(key)
        match["markets"].setdefault(line["market"], []).append(line)


def parse_scope(payload: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    league: dict[str, Any] = {"id": None, "name": "", "raw": ""}
    current: dict[str, Any] | None = None

    if payload.get("status") != 1:
        return matches

    blocks = payload.get("data") or []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        sport_id = clean_text(block.get("spid")) or None
        rows = block.get("data") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            league = league_fields(row, league)
            home = clean_text(row.get("club_home"))
            away = clean_text(row.get("club_away"))

            # A row with teams starts a match. Team-less rows are alternate market
            # lines belonging to the preceding match in the same league.
            if home or away:
                current = {
                    "scope": scope,
                    "sport_id": sport_id,
                    "league": dict(league),
                    "match_id": clean_text(row.get("no_partai")) or None,
                    "match_date": clean_text(row.get("match_date")) or None,
                    "home": home,
                    "away": away,
                    "home_score": clean_text(row.get("home_score")) or None,
                    "away_score": clean_text(row.get("away_score")) or None,
                    "live_timer": clean_text(row.get("live_timer")) or None,
                    "is_live": clean_text(row.get("is_live")) or None,
                    "is_neutral": clean_text(row.get("is_neutral")) or None,
                    "markets": {},
                    "_market_keys": set(),
                }
                matches.append(current)
            elif current is None:
                continue

            # Do not attach a team-less alternate row across a newly declared league
            # boundary unless it still follows a real match in that league.
            if current is not None:
                if league.get("name") and current["league"].get("name") != league.get("name") and not (home or away):
                    continue
                add_markets(current, row)

    for match in matches:
        match.pop("_market_keys", None)
    return matches


def load_scope(input_dir: Path, scope: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = input_dir / f"{scope}.json"
    if not path.exists():
        return [], {"scope": scope, "file": str(path), "present": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return [], {"scope": scope, "file": str(path), "present": True, "error": str(exc)}
    matches = parse_scope(payload, scope)
    return matches, {
        "scope": scope,
        "file": str(path),
        "present": True,
        "api_status": payload.get("status") if isinstance(payload, dict) else None,
        "matches": len(matches),
    }


def write_csv(path: Path, matches: list[dict[str, Any]], odds_format: str) -> None:
    fields = [
        "scope", "league", "match_id", "match_date", "live_timer", "home", "away",
        "home_score", "away_score", "market", "game_type", "sub_partai", "line",
        "line_display_raw", "selection", "price", "secondary", "raw_price", "odds_format",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for match in matches:
            for market_name, lines in match.get("markets", {}).items():
                for line in lines:
                    for price in line.get("prices", []):
                        writer.writerow({
                            "scope": match.get("scope"),
                            "league": match.get("league", {}).get("name"),
                            "match_id": match.get("match_id"),
                            "match_date": match.get("match_date"),
                            "live_timer": match.get("live_timer"),
                            "home": match.get("home"),
                            "away": match.get("away"),
                            "home_score": match.get("home_score"),
                            "away_score": match.get("away_score"),
                            "market": market_name,
                            "game_type": line.get("game_type"),
                            "sub_partai": line.get("sub_partai"),
                            "line": line.get("line"),
                            "line_display_raw": line.get("line_display_raw"),
                            "selection": price.get("selection"),
                            "price": price.get("value"),
                            "secondary": price.get("secondary"),
                            "raw_price": price.get("raw"),
                            "odds_format": odds_format,
                        })


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize public M88/MSports odds JSON")
    parser.add_argument("--input-dir", default="evidence")
    parser.add_argument("--output-json", default="evidence/m88_odds.json")
    parser.add_argument("--output-csv", default="evidence/m88_odds.csv")
    parser.add_argument("--odds-format", default="decimal")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    all_matches: list[dict[str, Any]] = []
    sources = []
    for scope in SCOPE_FILES:
        matches, source = load_scope(input_dir, scope)
        all_matches.extend(matches)
        sources.append(source)

    counts = {scope: sum(1 for m in all_matches if m.get("scope") == scope) for scope in SCOPE_FILES}
    market_line_counts: dict[str, int] = {}
    for match in all_matches:
        for name, lines in match.get("markets", {}).items():
            market_line_counts[name] = market_line_counts.get(name, 0) + len(lines)

    output = {
        "source": "M88 / MSports public guest API",
        "odds_format": args.odds_format,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"matches": len(all_matches), "by_scope": counts, "market_lines": market_line_counts},
        "sources": sources,
        "matches": all_matches,
    }

    json_path = Path(args.output_json)
    csv_path = Path(args.output_csv)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(csv_path, all_matches, args.odds_format)

    sample = []
    for match in all_matches[:5]:
        sample.append({
            "scope": match.get("scope"),
            "league": match.get("league", {}).get("name"),
            "home": match.get("home"),
            "away": match.get("away"),
            "markets": {k: len(v) for k, v in match.get("markets", {}).items()},
        })
    print(json.dumps({"counts": output["counts"], "sample": sample}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
