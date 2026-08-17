#!/usr/bin/env python3

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VIRTUAL_RE = re.compile(r"virtual|esoccer|e-soccer|pes\s?\d|simulated|cyber", re.I)
SCOPES = {
    "live": ("Live", "ALL LIVE"),
    "today": ("Hôm nay", "TODAY"),
    "early": ("Sắp tới", "EARLY"),
}


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def price(value):
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "—"


def league_name(match):
    return (match.get("league") or {}).get("name") or "Other"


def is_virtual(match):
    text = " ".join([league_name(match), match.get("home") or "", match.get("away") or ""])
    return bool(VIRTUAL_RE.search(text))


def fmt_updated(value):
    try:
        dt = datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        return dt.strftime("%H:%M:%S · %d/%m/%Y")
    except Exception:
        return value or "unknown"


def fmt_match_date(value):
    text = str(value or "")
    try:
        return datetime.strptime(text[:12], "%Y%m%d%H%M").strftime("%d/%m %H:%M")
    except Exception:
        return text or "Prematch"


def market_cell(lines, market, max_lines=2):
    if not lines:
        return '<div class="market-cell muted-cell">—</div>'
    rendered = []
    for line in lines[:max_lines]:
        line_value = line.get("line")
        opts = []
        for p in line.get("prices") or []:
            sel = (p.get("selection") or "").lower()
            if market == "ah":
                prefix = {"home": "H", "away": "A"}.get(sel, sel[:1].upper())
                line_txt = "" if line_value is None else f" {line_value:g}" if isinstance(line_value, (int, float)) else f" {line_value}"
                label = f"{prefix}{line_txt}"
            elif market == "ou":
                prefix = {"over": "O", "under": "U"}.get(sel, sel[:1].upper())
                line_txt = "" if line_value is None else f" {line_value:g}" if isinstance(line_value, (int, float)) else f" {line_value}"
                label = f"{prefix}{line_txt}"
            else:
                label = {"home": "1", "draw": "X", "away": "2"}.get(sel, sel[:1].upper())
            opts.append(
                '<span class="odd-btn" title="View-only odds">'
                f'<span class="odd-label">{esc(label)}</span>'
                f'<b>{price(p.get("value"))}</b>'
                '</span>'
            )
        if opts:
            rendered.append(f'<div class="odd-line">{"".join(opts)}</div>')
    return f'<div class="market-cell">{"".join(rendered)}</div>' if rendered else '<div class="market-cell muted-cell">—</div>'


def event_row(match, scope):
    markets = match.get("markets") or {}
    if scope == "live":
        timer = match.get("live_timer") or "LIVE"
        hs = match.get("home_score")
        aw = match.get("away_score")
        score = ""
        if hs is not None or aw is not None:
            score = f'<span class="score">{esc(hs or "0")}-{esc(aw or "0")}</span>'
        meta = f'<span class="live-clock">● {esc(timer)}</span>{score}'
    else:
        meta = f'<span class="kickoff">{esc(fmt_match_date(match.get("match_date")))}</span>'

    visible_markets = {"ft_asian_handicap", "ft_over_under", "ft_1x2", "fh_asian_handicap"}
    extra = sum(len(v or []) for k, v in markets.items() if k not in visible_markets)
    more = extra + len(markets.get("fh_over_under") or []) + len(markets.get("fh_1x2") or [])

    return (
        '<div class="event-row">'
        '<div class="event-info">'
        f'<div class="event-meta">{meta}</div>'
        f'<div class="team"><span class="home-dot"></span>{esc(match.get("home"))}</div>'
        f'<div class="team"><span class="away-dot"></span>{esc(match.get("away"))}</div>'
        '</div>'
        f'{market_cell(markets.get("ft_asian_handicap") or [], "ah", 2)}'
        f'{market_cell(markets.get("ft_over_under") or [], "ou", 2)}'
        f'{market_cell(markets.get("ft_1x2") or [], "1x2", 1)}'
        f'{market_cell(markets.get("fh_asian_handicap") or [], "ah", 2)}'
        f'<div class="more-cell"><span>+{more}</span></div>'
        '</div>'
    )


def league_sections(rows, scope):
    out = []
    current = None
    for match in rows:
        league = league_name(match)
        if league != current:
            current = league
            out.append(
                '<div class="league-head">'
                '<span class="chev">⌄</span>'
                f'<span>{esc(league)}</span>'
                '<span class="star">☆</span>'
                '</div>'
            )
        out.append(event_row(match, scope))
    if not out:
        out.append('<div class="empty">Không có trận bóng đá thật trong mục này ở snapshot hiện tại.</div>')
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    matches = [m for m in data.get("matches") or [] if not is_virtual(m)]
    grouped = {scope: [m for m in matches if m.get("scope") == scope] for scope in SCOPES}
    counts = {scope: len(rows) for scope, rows in grouped.items()}
    updated = fmt_updated(data.get("generated_at"))

    sections = {scope: league_sections(rows, scope) for scope, rows in grouped.items()}

    doc = f'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#163d63">
<meta http-equiv="refresh" content="60">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>MSports · M88 Odds</title>
<style>
:root{{--navy:#123555;--navy2:#17476f;--blue:#1e5f94;--blue2:#2b77ae;--sky:#eaf3f8;--panel:#f4f6f8;--line:#d6dde3;--text:#22313f;--muted:#778794;--white:#fff;--live:#e64b4b;--odd:#edf4f8;--odd-hover:#dcecf6;--accent:#f5a623;color-scheme:light}}
*{{box-sizing:border-box}}html,body{{margin:0;background:#e8edf1;color:var(--text);font-family:Arial,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:12px}}body{{min-height:100vh}}
input.scope{{position:absolute;opacity:0;pointer-events:none}}
.topbar{{height:48px;background:linear-gradient(180deg,#1c527e,#153d61);color:#fff;display:flex;align-items:center;padding:0 14px;gap:22px;position:sticky;top:0;z-index:30;box-shadow:0 1px 4px rgba(0,0,0,.25)}}
.brand{{font-size:21px;font-weight:800;letter-spacing:-.5px;white-space:nowrap}}.brand span{{color:#f7b32b}}.brand small{{font-size:11px;color:#d6e6f0;margin-left:4px;font-weight:700}}.topnav{{display:flex;align-items:stretch;height:100%;gap:3px;overflow:auto}}.topnav span{{display:flex;align-items:center;padding:0 13px;font-weight:700;color:#dceaf5;white-space:nowrap}}.topnav span.active{{background:rgba(255,255,255,.12);color:#fff;border-bottom:3px solid #f5a623}}.updated{{margin-left:auto;color:#c8d9e6;white-space:nowrap;font-size:11px}}
.layout{{max-width:1440px;margin:0 auto;display:grid;grid-template-columns:190px minmax(620px,1fr) 278px;gap:8px;padding:8px}}
.left,.right,.board{{background:#fff;border:1px solid #cbd5dc;box-shadow:0 1px 2px rgba(0,0,0,.04)}}.left,.right{{align-self:start;position:sticky;top:56px}}
.side-title{{background:#194b74;color:#fff;padding:11px 12px;font-weight:800;text-transform:uppercase}}.sport{{padding:10px 11px;border-bottom:1px solid #e3e7ea;display:flex;align-items:center;gap:8px;color:#4d5c68}}.sport.active{{background:#e9f3f9;color:#174f79;font-weight:800;border-left:3px solid #1d6599;padding-left:8px}}.sport .n{{margin-left:auto;background:#dce7ee;color:#567080;border-radius:10px;padding:1px 6px;font-size:10px}}
.favorites{{padding:11px;border-bottom:1px solid #e3e7ea;color:#6e7c87}}.favorites b{{color:#334957}}
.board-head{{background:#f5f7f9;border-bottom:1px solid #cbd5dc}}.board-title{{display:flex;align-items:center;padding:9px 10px;background:#174c75;color:#fff}}.board-title b{{font-size:14px}}.board-title span{{margin-left:auto;color:#cfe0eb;font-size:11px}}
.scope-tabs{{display:flex;background:#fff;border-bottom:1px solid #d4dce2;overflow:auto}}.scope-tabs label{{padding:10px 18px;cursor:pointer;font-weight:800;color:#61727e;border-right:1px solid #e1e6ea;white-space:nowrap}}.scope-tabs label b{{background:#e7edf1;padding:2px 6px;border-radius:9px;font-size:10px;margin-left:4px;color:#435662}}
#scope-live:checked~.app label[for=scope-live],#scope-today:checked~.app label[for=scope-today],#scope-early:checked~.app label[for=scope-early]{{background:#1d669a;color:#fff}}#scope-live:checked~.app label[for=scope-live] b,#scope-today:checked~.app label[for=scope-today] b,#scope-early:checked~.app label[for=scope-early] b{{background:rgba(255,255,255,.22);color:#fff}}
.market-header,.event-row{{display:grid;grid-template-columns:minmax(210px,1.6fr) minmax(145px,1fr) minmax(145px,1fr) minmax(140px,.95fr) minmax(145px,1fr) 42px}}.market-header{{background:#e7edf1;color:#53636f;font-weight:800;border-bottom:1px solid #cbd5dc}}.market-header>div{{padding:7px 6px;text-align:center;border-left:1px solid #d5dde3}}.market-header>div:first-child{{text-align:left;border-left:0;padding-left:10px}}
.scope-panel{{display:none}}#scope-live:checked~.app .panel-live,#scope-today:checked~.app .panel-today,#scope-early:checked~.app .panel-early{{display:block}}
.league-head{{height:31px;background:#d7e6ef;border-top:1px solid #b7cad6;border-bottom:1px solid #b8cbd7;display:flex;align-items:center;padding:0 8px;color:#284c62;font-weight:800;text-transform:uppercase;letter-spacing:.1px;position:sticky;top:48px;z-index:4}}.league-head .chev{{margin-right:7px}}.league-head .star{{margin-left:auto;color:#7793a4;font-size:15px}}
.event-row{{border-bottom:1px solid #dde3e7;background:#fff;min-height:62px}}.event-row:nth-of-type(odd){{background:#fbfcfd}}.event-info{{padding:6px 9px;border-right:1px solid #dfe5e9;min-width:0}}.event-meta{{height:18px;display:flex;align-items:center;gap:7px;color:#7b8993;font-size:10px}}.live-clock{{color:#dc4343;font-weight:800}}.score{{font-weight:800;color:#203848}}.team{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:17px;font-weight:700;color:#2f3f4a}}.home-dot,.away-dot{{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:5px;background:#5d8aa8}}.away-dot{{background:#a6b5bf}}
.market-cell{{border-right:1px solid #dfe5e9;padding:4px;display:flex;flex-direction:column;gap:3px;justify-content:center;min-width:0}}.muted-cell{{align-items:center;color:#aeb8bf}}.odd-line{{display:flex;gap:3px;min-width:0}}.odd-btn{{min-width:0;flex:1;background:var(--odd);border:1px solid #d5e3eb;border-radius:2px;padding:4px 4px;display:flex;justify-content:space-between;align-items:center;gap:4px;color:#506574}}.odd-btn b{{color:#155b8c;font-size:12px}}.odd-label{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:10px}}.more-cell{{display:flex;align-items:center;justify-content:center;color:#1f6593;font-weight:800;background:#f3f7fa}}.more-cell span{{border:1px solid #c9dce8;background:#fff;border-radius:2px;padding:5px 4px}}
.right-head{{height:39px;background:#174b74;color:#fff;display:flex;align-items:center;padding:0 11px;font-weight:800}}.right-tabs{{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #d6dde2}}.right-tabs div{{padding:9px;text-align:center;font-weight:800;color:#657681}}.right-tabs div:first-child{{color:#155c8e;border-bottom:2px solid #1d699e}}.slip-empty{{padding:34px 20px;text-align:center;color:#87949d;line-height:1.55}}.slip-icon{{font-size:28px;color:#b5c3cc;margin-bottom:9px}}.view-only{{margin:0 10px 12px;background:#eef4f7;border:1px solid #d7e3ea;color:#60727e;padding:9px;text-align:center;font-size:11px}}
.mobile-bottom{{display:none}}
.empty{{padding:50px 20px;text-align:center;color:#82909a}}
.footer-note{{padding:9px 10px;color:#7b8993;background:#f7f9fa;border-top:1px solid #d7dfe4;font-size:10px}}
@media(max-width:1100px){{.layout{{grid-template-columns:170px minmax(600px,1fr)}}.right{{display:none}}}}
@media(max-width:820px){{body{{background:#fff}}.topbar{{height:44px;padding:0 9px;gap:10px}}.brand{{font-size:18px}}.topnav span{{padding:0 10px;font-size:11px}}.updated{{display:none}}.layout{{display:block;padding:0;max-width:none}}.left,.right{{display:none}}.board{{border:0;box-shadow:none}}.board-title{{padding:8px 9px}}.scope-tabs{{position:sticky;top:44px;z-index:20}}.scope-tabs label{{flex:1;text-align:center;padding:9px 8px}}.market-header{{position:sticky;top:79px;z-index:10;grid-template-columns:minmax(142px,1.45fr) minmax(112px,1fr) minmax(112px,1fr) minmax(108px,.95fr) 34px;min-width:508px}}.market-header .fh{{display:none}}.event-row{{grid-template-columns:minmax(142px,1.45fr) minmax(112px,1fr) minmax(112px,1fr) minmax(108px,.95fr) 34px;min-width:508px}}.event-row>.market-cell:nth-of-type(5){{display:none}}.league-head{{top:108px;min-width:508px}}.scope-panel{{overflow-x:auto}}.scope-panel::-webkit-scrollbar{{display:none}}.mobile-bottom{{position:fixed;display:flex;bottom:0;left:0;right:0;height:48px;background:#174b74;color:#fff;z-index:40;align-items:center;justify-content:space-around;padding-bottom:env(safe-area-inset-bottom);box-shadow:0 -2px 7px rgba(0,0,0,.2)}}.mobile-bottom span{{font-weight:700;font-size:11px}}.footer-note{{padding-bottom:60px}}}}
</style>
</head>
<body>
<input class="scope" type="radio" name="scope" id="scope-live" checked>
<input class="scope" type="radio" name="scope" id="scope-today">
<input class="scope" type="radio" name="scope" id="scope-early">
<div class="app">
<header class="topbar">
  <div class="brand">M<span>88</span> <small>MSports</small></div>
  <nav class="topnav"><span>Streaming</span><span class="active">All Live</span><span>All Sports</span><span>Bet List</span><span>More</span></nav>
  <div class="updated">Updated {esc(updated)} VN · Decimal</div>
</header>
<div class="layout">
  <aside class="left">
    <div class="side-title">Sports</div>
    <div class="favorites">☆ <b>My Favourites</b></div>
    <div class="sport active">⚽ Soccer <span class="n">{sum(counts.values())}</span></div>
    <div class="sport">🏀 Basketball</div><div class="sport">🎾 Tennis</div><div class="sport">🏐 Volleyball</div><div class="sport">⚾ Baseball</div><div class="sport">🏒 Ice Hockey</div><div class="sport">🎮 E-Sports</div><div class="sport">＋ More Sports</div>
  </aside>
  <main class="board">
    <div class="board-head">
      <div class="board-title"><b>⚽ Soccer</b><span>Asian View · Odds: Decimal</span></div>
      <div class="scope-tabs">
        <label for="scope-live">Live <b>{counts["live"]}</b></label>
        <label for="scope-today">Today <b>{counts["today"]}</b></label>
        <label for="scope-early">Early <b>{counts["early"]}</b></label>
      </div>
      <div class="market-header"><div>Event</div><div>FT HDP</div><div>FT O/U</div><div>1X2</div><div class="fh">1H HDP</div><div>+</div></div>
    </div>
    <section class="scope-panel panel-live">{sections["live"]}</section>
    <section class="scope-panel panel-today">{sections["today"]}</section>
    <section class="scope-panel panel-early">{sections["early"]}</section>
    <div class="footer-note">M88 / MSports public guest odds · View only · Virtual/PES/eSoccer excluded · Page reloads every 60s</div>
  </main>
  <aside class="right">
    <div class="right-head">BET SLIP</div>
    <div class="right-tabs"><div>Single</div><div>Multiple</div></div>
    <div class="slip-empty"><div class="slip-icon">▤</div><b>Your bet slip is empty</b><br>Select an odd from the sportsbook board.</div>
    <div class="view-only">View-only dashboard — no wagers are submitted from this page.</div>
  </aside>
</div>
<div class="mobile-bottom"><span>⚽ Sports</span><span>▤ Bet Slip</span><span>☰ More</span></div>
</div>
</body>
</html>'''

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"REAL_LIVE_MATCHES={counts['live']}")
    print(f"REAL_TODAY_MATCHES={counts['today']}")
    print(f"REAL_EARLY_MATCHES={counts['early']}")
    print(f"ONE_PAGE_MATCHES={sum(counts.values())}")


if __name__ == "__main__":
    main()
