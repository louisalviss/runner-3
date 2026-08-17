#!/usr/bin/env python3

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VIRTUAL_RE = re.compile(r"virtual|esoccer|e-soccer|pes\s?\d|simulated|cyber|\(v\)", re.I)
SCOPES = {"live": "Live", "today": "Today", "early": "Early"}


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


def display_home_score(raw):
    text = str(raw or "")
    if "_" in text:
        parts = text.split("_")
        return parts[1] if len(parts) > 1 else parts[0]
    return text or "0"


def display_away_score(raw):
    text = str(raw or "")
    return (text.split("_")[0] if "_" in text else text) or "0"


def line_text(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


def market_cell(lines, market, max_lines=2, mobile_title=""):
    if not lines:
        return f'<div class="market-cell muted-cell" data-title="{esc(mobile_title)}">—</div>'
    rendered = []
    for line in lines[:max_lines]:
        lv = line_text(line.get("line"))
        opts = []
        for p in line.get("prices") or []:
            sel = (p.get("selection") or "").lower()
            if market == "ah":
                prefix = {"home": "H", "away": "A"}.get(sel, sel[:1].upper())
                label = f"{prefix} {lv}".strip()
            elif market == "ou":
                prefix = {"over": "O", "under": "U"}.get(sel, sel[:1].upper())
                label = f"{prefix} {lv}".strip()
            else:
                label = {"home": "1", "draw": "X", "away": "2"}.get(sel, sel[:1].upper())
            opts.append(
                '<span class="odd-btn">'
                f'<span class="odd-label">{esc(label)}</span>'
                f'<b>{price(p.get("value"))}</b>'
                '</span>'
            )
        if opts:
            rendered.append(f'<div class="odd-line">{"".join(opts)}</div>')
    return f'<div class="market-cell" data-title="{esc(mobile_title)}">{"".join(rendered)}</div>'


def live_clock(match):
    raw = str(match.get("live_timer") or "LIVE").replace("`", "'")
    round_id = str(match.get("event_round") or "")
    minute_match = re.search(r"(\d{1,3})", raw)
    base = minute_match.group(1) if minute_match else ""
    if not round_id and base.isdigit():
        round_id = "1" if int(base) <= 45 else "3"
    attrs = f'data-live-clock data-raw="{esc(raw)}" data-round="{esc(round_id)}"'
    if base and "+" not in raw:
        attrs += f' data-base-min="{esc(base)}"'
    prefix = {"1": "1H", "2": "HT", "3": "2H"}.get(round_id, "")
    shown = f"{prefix} {raw}".strip() if prefix != "HT" else "HT"
    return f'<span class="live-clock" {attrs}>● {esc(shown)}</span>'


def event_row(match, scope):
    markets = match.get("markets") or {}
    if scope == "live":
        hs = display_home_score(match.get("home_score"))
        aw = display_away_score(match.get("away_score"))
        meta = f'{live_clock(match)}<span class="score">{esc(hs)} - {esc(aw)}</span>'
    else:
        meta = f'<span class="kickoff">{esc(fmt_match_date(match.get("match_date")))}</span>'

    visible_markets = {"ft_asian_handicap", "ft_over_under", "ft_1x2", "fh_asian_handicap"}
    extra = sum(len(v or []) for k, v in markets.items() if k not in visible_markets)
    more = extra + len(markets.get("fh_over_under") or []) + len(markets.get("fh_1x2") or [])

    return (
        '<div class="event-row">'
        '<div class="event-info">'
        f'<div class="event-meta">{meta}</div>'
        f'<div class="team home"><span class="home-dot"></span>{esc(match.get("home"))}</div>'
        f'<div class="team away"><span class="away-dot"></span>{esc(match.get("away"))}</div>'
        '</div>'
        f'{market_cell(markets.get("ft_asian_handicap") or [], "ah", 2, "HDP")}'
        f'{market_cell(markets.get("ft_over_under") or [], "ou", 2, "O/U")}'
        f'{market_cell(markets.get("ft_1x2") or [], "1x2", 1, "1X2")}'
        f'{market_cell(markets.get("fh_asian_handicap") or [], "ah", 2, "1H")}'
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
                f'<span class="league-name">{esc(league)}</span>'
                '<span class="star">☆</span>'
                '</div>'
            )
        out.append(event_row(match, scope))
    if not out:
        out.append('<div class="empty">Không có trận bóng đá thật trong mục này.</div>')
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
    generated_at = data.get("live_generated_at") or data.get("generated_at") or ""
    updated = fmt_updated(generated_at)
    sections = {scope: league_sections(rows, scope) for scope, rows in grouped.items()}

    doc = f'''<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1">
<meta name="theme-color" content="#174b74">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>M88 · MSports</title>
<style>
:root{{--navy:#153f64;--navy2:#1b527f;--blue:#1c6598;--pale:#eaf2f7;--league:#dceaf2;--line:#d5dfe5;--text:#293944;--muted:#7b8992;--odd:#edf4f8;--odd-border:#d3e2eb;--red:#df4444;--orange:#f5a623}}
*{{box-sizing:border-box}}html,body{{margin:0;background:#e9eef2;color:var(--text);font-family:Arial,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:12px;-webkit-text-size-adjust:100%}}input.scope{{position:absolute;opacity:0;pointer-events:none}}
.topbar{{height:48px;background:linear-gradient(#1b527f,#153f64);color:white;display:flex;align-items:center;padding:0 13px;gap:18px;position:sticky;top:0;z-index:50;box-shadow:0 1px 3px #0004}}.brand{{font-size:21px;font-weight:900;white-space:nowrap}}.brand em{{font-style:normal;color:#f6b12c}}.brand small{{font-size:10px;margin-left:4px;color:#d7e5ee}}.topnav{{display:flex;height:100%;align-items:stretch;overflow:auto}}.topnav span{{display:flex;align-items:center;padding:0 12px;color:#dce9f2;font-weight:700;white-space:nowrap}}.topnav .active{{background:#ffffff12;border-bottom:3px solid var(--orange);color:#fff}}.updated{{margin-left:auto;color:#cbdde9;white-space:nowrap;font-size:10px}}.mobile-actions{{display:none;margin-left:auto;font-size:18px;gap:15px}}
.layout{{max-width:1440px;margin:auto;display:grid;grid-template-columns:188px minmax(650px,1fr) 270px;gap:8px;padding:8px}}.left,.right,.board{{background:#fff;border:1px solid #cad4db}}.left,.right{{align-self:start;position:sticky;top:56px}}.side-title,.right-head{{background:#194b74;color:#fff;padding:10px 11px;font-weight:800}}.favorites,.sport{{padding:10px;border-bottom:1px solid #e1e6e9}}.sport{{display:flex;gap:7px;align-items:center}}.sport.active{{background:#e8f2f8;border-left:3px solid #1d6599;color:#174f79;font-weight:800}}.sport .n{{margin-left:auto;background:#dce7ee;border-radius:10px;padding:1px 6px}}
.board-head{{background:#f5f7f9}}.board-title{{background:#174c75;color:#fff;padding:9px 10px;display:flex;justify-content:space-between}}.scope-tabs{{display:flex;background:#fff;border-bottom:1px solid var(--line)}}.scope-tabs label{{padding:10px 18px;font-weight:800;color:#657581;border-right:1px solid #e1e6ea;cursor:pointer}}.scope-tabs b{{font-size:10px;background:#e6edf1;border-radius:9px;padding:2px 6px;margin-left:3px}}
#scope-live:checked~.app label[for=scope-live],#scope-today:checked~.app label[for=scope-today],#scope-early:checked~.app label[for=scope-early]{{background:#1d669a;color:#fff}}#scope-live:checked~.app label[for=scope-live] b,#scope-today:checked~.app label[for=scope-today] b,#scope-early:checked~.app label[for=scope-early] b{{background:#ffffff33;color:#fff}}.scope-panel{{display:none}}#scope-live:checked~.app .panel-live,#scope-today:checked~.app .panel-today,#scope-early:checked~.app .panel-early{{display:block}}
.market-header,.event-row{{display:grid;grid-template-columns:minmax(220px,1.6fr) minmax(145px,1fr) minmax(145px,1fr) minmax(135px,.9fr) minmax(145px,1fr) 42px}}.market-header{{background:#e7edf1;color:#53636f;font-weight:800;border-bottom:1px solid #c8d3da}}.market-header>div{{padding:7px 6px;text-align:center;border-left:1px solid #d5dde3}}.market-header>div:first-child{{text-align:left;border-left:0;padding-left:10px}}
.league-head{{height:31px;background:var(--league);border-top:1px solid #b9ccd8;border-bottom:1px solid #bcced9;display:flex;align-items:center;padding:0 8px;color:#28516a;font-weight:800;text-transform:uppercase;position:sticky;top:48px;z-index:5}}.league-head .chev{{margin-right:7px}}.league-head .star{{margin-left:auto;color:#7894a4;font-size:15px}}.event-row{{border-bottom:1px solid #dde4e8;min-height:62px;background:#fff}}.event-info{{padding:6px 9px;border-right:1px solid #dfe5e9;min-width:0}}.event-meta{{min-height:18px;display:flex;gap:8px;align-items:center;color:var(--muted);font-size:10px}}.live-clock{{color:var(--red);font-weight:800}}.score{{font-weight:800;color:#243b4b}}.team{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:17px;font-weight:700}}.home-dot,.away-dot{{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:5px;background:#5b8ba9}}.away-dot{{background:#a5b4be}}
.market-cell{{border-right:1px solid #dfe5e9;padding:4px;display:flex;flex-direction:column;gap:3px;justify-content:center;min-width:0}}.muted-cell{{align-items:center;color:#aab4bb}}.odd-line{{display:flex;gap:3px;min-width:0}}.odd-btn{{flex:1;min-width:0;background:var(--odd);border:1px solid var(--odd-border);border-radius:2px;padding:4px;display:flex;justify-content:space-between;align-items:center;gap:3px;color:#526775}}.odd-label{{font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.odd-btn b{{color:#155c8d;font-size:12px}}.more-cell{{display:flex;align-items:center;justify-content:center;background:#f3f7fa;color:#1d6594;font-weight:800}}.more-cell span{{border:1px solid #c8dce8;background:#fff;padding:5px 4px;border-radius:2px}}.right-tabs{{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #ddd}}.right-tabs div{{padding:9px;text-align:center;font-weight:700}}.slip-empty{{padding:32px 18px;text-align:center;color:#87949d;line-height:1.5}}.view-only{{margin:0 10px 12px;padding:8px;background:#eef4f7;color:#677984;text-align:center}}.mobile-bottom{{display:none}}.empty{{padding:45px 15px;text-align:center;color:#82909a}}.footer-note{{padding:9px;color:#7b8993;background:#f7f9fa;border-top:1px solid #d7dfe4;font-size:10px}}
@media(max-width:1100px){{.layout{{grid-template-columns:165px minmax(600px,1fr)}}.right{{display:none}}}}
@media(max-width:820px){{
 html,body{{background:#fff;overflow-x:hidden}}.topbar{{height:46px;padding:0 10px;gap:8px}}.brand{{font-size:19px}}.topnav,.updated{{display:none}}.mobile-actions{{display:flex}}.layout{{display:block;padding:0;max-width:none}}.left,.right{{display:none}}.board{{border:0}}.board-title{{height:36px;padding:0 10px;align-items:center;font-size:11px}}.scope-tabs{{position:sticky;top:46px;z-index:30}}.scope-tabs label{{flex:1;text-align:center;padding:10px 4px;font-size:12px;border-right:1px solid #dde5ea}}.market-header{{position:sticky;top:82px;z-index:25;display:grid;grid-template-columns:1fr 1fr 1fr 36px;width:100%;min-width:0}}.market-header>div:first-child,.market-header .fh{{display:none}}.market-header>div{{padding:7px 2px;font-size:10px}}.market-header>div:last-child{{display:block}}
 .scope-panel{{width:100%;overflow:visible}}.league-head{{position:relative;top:auto;height:30px;width:100%;min-width:0;padding:0 7px;font-size:10px;white-space:nowrap;overflow:hidden}}.league-name{{overflow:hidden;text-overflow:ellipsis}}.event-row{{display:grid;grid-template-columns:1fr 1fr 1fr 36px;width:100%;min-width:0;min-height:0}}.event-info{{grid-column:1/-1;padding:6px 8px 5px;border-right:0;border-bottom:1px solid #e4e9ec;display:grid;grid-template-columns:1fr auto;column-gap:8px;align-items:center}}.event-meta{{grid-column:2;grid-row:1/3;justify-content:flex-end;flex-direction:column;gap:1px;min-width:54px}}.team{{grid-column:1;line-height:18px;padding-right:4px}}.team.home{{grid-row:1}}.team.away{{grid-row:2}}.event-row>.market-cell{{padding:4px 3px;border-right:1px solid #e0e6ea;min-height:44px;position:relative}}.event-row>.market-cell:nth-of-type(2){{grid-column:1}}.event-row>.market-cell:nth-of-type(3){{grid-column:2}}.event-row>.market-cell:nth-of-type(4){{grid-column:3}}.event-row>.market-cell:nth-of-type(5){{display:none}}.market-cell:before{{content:attr(data-title);display:none}}.more-cell{{grid-column:4;min-height:44px}}.odd-line{{gap:2px}}.odd-btn{{padding:5px 3px;min-height:28px;flex-direction:column;justify-content:center;gap:0}}.odd-label{{font-size:9px;line-height:11px}}.odd-btn b{{font-size:12px;line-height:14px}}.mobile-bottom{{display:flex;position:fixed;left:0;right:0;bottom:0;height:49px;padding-bottom:env(safe-area-inset-bottom);background:#174b74;color:#fff;z-index:60;align-items:center;justify-content:space-around;box-shadow:0 -1px 5px #0004}}.mobile-bottom span{{font-size:10px;font-weight:700}}.footer-note{{padding-bottom:58px}}}}
@media(max-width:390px){{.odd-btn b{{font-size:11px}}.odd-label{{font-size:8px}}.event-info{{grid-template-columns:minmax(0,1fr) 52px}}}}
</style>
</head>
<body data-snapshot="{esc(generated_at)}">
<input class="scope" type="radio" name="scope" id="scope-live" checked><input class="scope" type="radio" name="scope" id="scope-today"><input class="scope" type="radio" name="scope" id="scope-early">
<div class="app">
<header class="topbar"><div class="brand">M<em>88</em> <small>MSports</small></div><nav class="topnav"><span>Streaming</span><span class="active">All Live</span><span>All Sports</span><span>Bet List</span><span>More</span></nav><div class="updated">Updated {esc(updated)} VN · Decimal</div><div class="mobile-actions"><span>⌕</span><span>◎</span><span>☰</span></div></header>
<div class="layout"><aside class="left"><div class="side-title">Sports</div><div class="favorites">☆ <b>My Favourites</b></div><div class="sport active">⚽ Soccer <span class="n">{sum(counts.values())}</span></div><div class="sport">🏀 Basketball</div><div class="sport">🎾 Tennis</div><div class="sport">🏐 Volleyball</div><div class="sport">⚾ Baseball</div><div class="sport">🏒 Ice Hockey</div><div class="sport">🎮 E-Sports</div></aside>
<main class="board"><div class="board-head"><div class="board-title"><b>⚽ Soccer</b><span>Asian View · Decimal</span></div><div class="scope-tabs"><label for="scope-live">Live <b>{counts['live']}</b></label><label for="scope-today">Today <b>{counts['today']}</b></label><label for="scope-early">Early <b>{counts['early']}</b></label></div><div class="market-header"><div>Event</div><div>HDP</div><div>O/U</div><div>1X2</div><div class="fh">1H</div><div>+</div></div></div>
<section class="scope-panel panel-live">{sections['live']}</section><section class="scope-panel panel-today">{sections['today']}</section><section class="scope-panel panel-early">{sections['early']}</section><div class="footer-note">M88 / MSports public guest odds · view only · page checks freshness automatically</div></main>
<aside class="right"><div class="right-head">BET SLIP</div><div class="right-tabs"><div>Single</div><div>Multiple</div></div><div class="slip-empty"><b>Your bet slip is empty</b><br>Select an odd from the board.</div><div class="view-only">View-only dashboard</div></aside></div>
<div class="mobile-bottom"><span>⚽ Sports</span><span>▤ Bet Slip</span><span>☰ More</span></div></div>
<script>
(function(){{
 const snapshot=Date.parse(document.body.dataset.snapshot||'');
 function tick(){{
   if(!Number.isFinite(snapshot)) return;
   const age=Math.max(0,Math.floor((Date.now()-snapshot)/60000));
   document.querySelectorAll('[data-live-clock]').forEach(el=>{{
     const raw=el.dataset.raw||'LIVE', round=el.dataset.round||'', base=parseInt(el.dataset.baseMin||'',10);
     if(!Number.isFinite(base)||raw.includes('+')) return;
     let m=base+age;
     if(round==='1') m=Math.min(m,45);
     if(round==='3') m=Math.min(m,90);
     const prefix=round==='1'?'1H ':round==='2'?'HT ':round==='3'?'2H ':'';
     el.textContent='● '+(round==='2'?'HT':prefix+m+"'");
   }});
 }}
 tick(); setInterval(tick,15000);
 setTimeout(()=>location.reload(),60000);
}})();
</script>
</body></html>'''

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"REAL_LIVE_MATCHES={counts['live']}")
    print(f"REAL_TODAY_MATCHES={counts['today']}")
    print(f"REAL_EARLY_MATCHES={counts['early']}")
    print(f"ONE_PAGE_MATCHES={sum(counts.values())}")


if __name__ == "__main__":
    main()
