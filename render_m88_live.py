#!/usr/bin/env python3

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VIRTUAL_RE = re.compile(r"virtual|esoccer|e-soccer|pes\s?\d|simulated|cyber", re.I)


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def price(value):
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "—"


def is_virtual(match):
    league = (match.get("league") or {}).get("name") or ""
    text = " ".join([league, match.get("home") or "", match.get("away") or ""])
    return bool(VIRTUAL_RE.search(text))


def market_block(title, lines, max_lines=2):
    if not lines:
        return ""
    chunks = []
    for line in lines[:max_lines]:
        line_value = line.get("line")
        line_label = f'<div class="lineval">Line {esc(line_value)}</div>' if line_value is not None else ""
        odds = []
        for p in line.get("prices") or []:
            odds.append(
                '<div class="odd">'
                f'<span>{esc(p.get("selection"))}</span>'
                f'<b>{price(p.get("value"))}</b>'
                '</div>'
            )
        cls = "odds two" if len(odds) == 2 else "odds"
        chunks.append(f'{line_label}<div class="{cls}">{"".join(odds)}</div>')
    return f'<section class="market"><div class="markettitle">{esc(title)}</div>{"".join(chunks)}</section>'


def card(match):
    markets = match.get("markets") or {}
    timer = match.get("live_timer") or "LIVE"
    blocks = "".join([
        market_block("FT Asian Handicap", markets.get("ft_asian_handicap") or []), 2),
        market_block("FT Over / Under", markets.get("ft_over_under") or [], 2),
        market_block("FT 1X2", markets.get("ft_1x2") or [], 1),
        market_block("1H Asian Handicap", markets.get("fh_asian_handicap") or [], 2),
    ])
    return (
        '<article class="match">'
        '<div class="matchhead">'
        '<div>'
        f'<div class="teams">{esc(match.get("home"))} <i>vs</i> {esc(match.get("away"))}</div>'
        f'<div class="meta">{esc(timer)}</div>'
        '</div>'
        f'<div class="live">LIVE {esc(timer)}</div>'
        '</div>'
        f'<div class="markets">{blocks}</div>'
        '</article>'
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    matches = [m for m in data.get("matches") or [] if m.get("scope") == "live" and not is_virtual(m)]

    generated = data.get("generated_at")
    try:
        dt = datetime.fromisoformat(generated).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        updated = dt.strftime("%H:%M:%S · %d/%m/%Y VN")
    except Exception:
        updated = generated or "unknown"

    body = []
    last_league = None
    for m in matches:
        league = (m.get("league") or {}).get("name") or "Other"
        if league != last_league:
            last_league = league
            body.append(f'<div class="league">{esc(league)}</div>')
        body.append(card(m))

    if not body:
        body.append('<div class="empty">No real football matches are live in this snapshot.</div>')

    doc = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0d10">
<meta http-equiv="refresh" content="60">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>M88 Live Odds</title>
<style>
:root{{--bg:#0b0d10;--card:#12151a;--line:#252a32;--muted:#8c96a5;--text:#f2f5f8;--good:#55d187;--accent:#ffb14a;--chip:#1b2027;color-scheme:dark}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:760px;margin:auto;padding:env(safe-area-inset-top) 12px calc(28px + env(safe-area-inset-bottom))}}
header{{position:sticky;top:0;z-index:5;background:rgba(11,13,16,.94);backdrop-filter:blur(16px);padding:14px 2px 11px;border-bottom:1px solid rgba(255,255,255,.05)}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.title{{font-size:21px;font-weight:780;letter-spacing:-.02em}}.state{{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px}}.dot{{width:8px;height:8px;border-radius:99px;background:var(--good);box-shadow:0 0 0 4px rgba(85,209,135,.09)}}
.updated{{font-size:12px;color:var(--muted);margin-top:4px}}.summary{{display:flex;gap:8px;margin:12px 0;overflow:auto}}.pill{{white-space:nowrap;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:7px 10px;font-size:12px;color:#c7ced8}}.pill b{{color:#fff}}
.league{{margin:18px 2px 8px;color:#aeb7c4;font-size:12px;font-weight:720;text-transform:uppercase;letter-spacing:.045em}}.match{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:13px;margin-bottom:9px}}.matchhead{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}}.teams{{font-size:15px;font-weight:700;line-height:1.35}}.teams i{{font-style:normal;color:#596372;font-weight:500}}.meta{{font-size:12px;color:var(--muted);margin-top:4px}}.live{{white-space:nowrap;font-size:11px;font-weight:760;color:var(--good);background:rgba(85,209,135,.09);padding:5px 7px;border-radius:8px}}
.markets{{display:grid;grid-template-columns:1fr;gap:8px;margin-top:11px}}.market{{background:#0e1115;border:1px solid #20252c;border-radius:12px;padding:9px}}.markettitle{{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:7px}}.lineval{{font-size:11px;color:var(--accent);margin:6px 0 3px}}.odds{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}.odds.two{{grid-template-columns:1fr 1fr}}.odd{{background:var(--chip);border-radius:8px;padding:7px 6px;text-align:center}}.odd span{{display:block;color:var(--muted);font-size:10px;margin-bottom:2px;text-transform:capitalize}}.odd b{{font-size:14px;color:#fff}}.empty{{padding:40px 16px;text-align:center;color:var(--muted)}}.foot{{text-align:center;color:#687281;font-size:11px;margin-top:22px}}.refresh{{text-decoration:none;color:#fff;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:7px 10px;font-size:12px;font-weight:650}}
@media(min-width:620px){{.markets{{grid-template-columns:1fr 1fr}}.match{{padding:15px}}}}
</style>
</head>
<body><div class="wrap">
<header><div class="top"><div class="title">M88 Live Odds</div><div class="state"><span class="dot"></span>Live feed</div></div><div class="updated">Snapshot: {esc(updated)}</div></header>
<div class="summary"><span class="pill"><b>{len(matches)}</b> real live matches</span><span class="pill">Feed refresh ~<b>5m</b></span><span class="pill">Page reload <b>60s</b></span><a class="refresh" href="./index.html">Refresh</a></div>
<main>{''.join(body)}</main>
<div class="foot">M88 / MSports public guest odds · Decimal · Virtual/PES/eSoccer excluded</div>
</div></body></html>'''

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"REAL_LIVE_MATCHES={len(matches)}")


if __name__ == "__main__":
    main()
