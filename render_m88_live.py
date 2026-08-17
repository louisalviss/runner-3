#!/usr/bin/env python3

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VIRTUAL_RE = re.compile(r"virtual|esoccer|e-soccer|pes\s?\d|simulated|cyber|\(v\)", re.I)
SCOPES = {"live": "Trực tiếp", "today": "Hôm nay", "early": "Sắp tới"}
MARKET_TITLES = {
    "ft_asian_handicap": "CƯỢC CHẤP TOÀN TRẬN",
    "ft_over_under": "TÀI / XỈU TOÀN TRẬN",
    "ft_1x2": "1X2 TOÀN TRẬN",
    "ft_odd_even": "TOÀN TRẬN LẺ/CHẴN",
    "fh_asian_handicap": "CƯỢC CHẤP HIỆP 1",
    "fh_over_under": "TÀI / XỈU HIỆP 1",
    "fh_1x2": "1X2 HIỆP 1",
    "fh_odd_even": "HIỆP 1 LẺ/CHẴN",
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


def live_clock_parts(match):
    raw = str(match.get("live_timer") or "LIVE").replace("`", "'")
    round_id = str(match.get("event_round") or "")
    mm = re.search(r"(\d{1,3})", raw)
    base = mm.group(1) if mm else ""
    if not round_id and base.isdigit():
        round_id = "1" if int(base) <= 45 else "3"
    prefix = {"1": "1H", "2": "HT", "3": "2H"}.get(round_id, "")
    shown = "HT" if round_id == "2" else f"{prefix} {raw}".strip()
    return raw, round_id, base, shown


def live_clock(match, compact=False):
    raw, round_id, base, shown = live_clock_parts(match)
    attrs = f'data-live-clock data-raw="{esc(raw)}" data-round="{esc(round_id)}"'
    if base and "+" not in raw:
        attrs += f' data-base-min="{esc(base)}"'
    dot = "" if compact else "● "
    return f'<span class="live-clock" {attrs}>{dot}{esc(shown)}</span>'


def desktop_market_cell(lines, market, max_lines=2, title=""):
    if not lines:
        return f'<div class="market-cell muted-cell" data-title="{esc(title)}">—</div>'
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
            opts.append(f'<span class="odd-btn"><span class="odd-label">{esc(label)}</span><b>{price(p.get("value"))}</b></span>')
        if opts:
            rendered.append(f'<div class="odd-line">{"".join(opts)}</div>')
    return f'<div class="market-cell" data-title="{esc(title)}">{"".join(rendered)}</div>'


def desktop_event_row(match, scope):
    markets = match.get("markets") or {}
    if scope == "live":
        hs = display_home_score(match.get("home_score"))
        aw = display_away_score(match.get("away_score"))
        meta = f'{live_clock(match)}<span class="score">{esc(hs)} - {esc(aw)}</span>'
    else:
        meta = f'<span class="kickoff">{esc(fmt_match_date(match.get("match_date")))}</span>'
    visible = {"ft_asian_handicap", "ft_over_under", "ft_1x2", "fh_asian_handicap"}
    more = sum(len(v or []) for k, v in markets.items() if k not in visible) + len(markets.get("fh_over_under") or []) + len(markets.get("fh_1x2") or [])
    return (
        '<div class="event-row">'
        f'<div class="event-info"><div class="event-meta">{meta}</div><div class="team home">{esc(match.get("home"))}</div><div class="team away">{esc(match.get("away"))}</div></div>'
        f'{desktop_market_cell(markets.get("ft_asian_handicap") or [], "ah", 2, "HDP")}'
        f'{desktop_market_cell(markets.get("ft_over_under") or [], "ou", 2, "O/U")}'
        f'{desktop_market_cell(markets.get("ft_1x2") or [], "1x2", 1, "1X2")}'
        f'{desktop_market_cell(markets.get("fh_asian_handicap") or [], "ah", 2, "1H")}'
        f'<div class="more-cell"><span>+{more}</span></div></div>'
    )


def desktop_leagues(rows, scope):
    out, current = [], None
    for match in rows:
        league = league_name(match)
        if league != current:
            current = league
            out.append(f'<div class="league-head"><span class="chev">⌃</span><span class="league-name">{esc(league)}</span><span class="star">☆</span></div>')
        out.append(desktop_event_row(match, scope))
    return "".join(out) or '<div class="empty">Không có trận bóng đá thật trong mục này.</div>'


def vi_selection(selection, family, line):
    sel = (selection or "").lower()
    base = {
        "home": "Nhà", "away": "Khách", "draw": "Hòa",
        "over": "Tài", "under": "Xỉu", "odd": "Lẻ", "even": "Chẵn",
    }.get(sel, sel.title() or "Kèo")
    if family in {"asian_handicap", "over_under"} and line is not None:
        return f"{base} {line_text(line)}"
    return base


def mobile_market_group(key, lines):
    if not lines:
        return ""
    blocks = []
    for line in lines[:3]:
        family = line.get("family") or ""
        cells = []
        for p in line.get("prices") or []:
            label = vi_selection(p.get("selection"), family, line.get("line"))
            cells.append(f'<div class="m-odd"><span>{esc(label)}</span><b>{price(p.get("value"))}</b></div>')
        if cells:
            cls = "three" if len(cells) == 3 else "two"
            blocks.append(f'<div class="m-odd-grid {cls}">{"".join(cells)}</div>')
    if not blocks:
        return ""
    title = MARKET_TITLES.get(key, key.replace("_", " ").upper())
    return f'<section class="m-market"><h3>{esc(title)}</h3>{"".join(blocks)}</section>'


def mobile_detail(match, scope, detail_id):
    markets = match.get("markets") or {}
    if scope == "live":
        hs = display_home_score(match.get("home_score"))
        aw = display_away_score(match.get("away_score"))
        status = f'{live_clock(match, True)} <span class="m-detail-score">{esc(hs)} : {esc(aw)}</span>'
    else:
        status = f'<span class="kickoff">{esc(fmt_match_date(match.get("match_date")))}</span>'
    main_keys = ["ft_asian_handicap", "ft_over_under", "ft_1x2", "fh_asian_handicap", "fh_over_under", "fh_1x2"]
    other_keys = ["ft_odd_even", "fh_odd_even"]
    main = "".join(mobile_market_group(k, markets.get(k) or []) for k in main_keys)
    other = "".join(mobile_market_group(k, markets.get(k) or []) for k in other_keys)
    if not main:
        main = '<div class="m-no-market">Chưa có thị trường chính.</div>'
    if not other:
        other = '<div class="m-no-market">Chưa có thị trường khác.</div>'
    return f'''
    <div class="m-detail" id="{detail_id}">
      <div class="m-detail-head">
        <button class="m-back" type="button" data-close-detail="{detail_id}">‹</button>
        <div class="m-detail-title"><div>{esc(match.get("home"))} <em>vs</em> {esc(match.get("away"))}</div><small>{status} · {esc(league_name(match))}</small></div>
        <span class="m-refresh">↻</span>
      </div>
      <div class="m-detail-tabs"><button class="active" type="button" data-market-tab="main">Thị trường chính</button><button type="button" data-market-tab="other">Thị trường khác</button></div>
      <div class="m-market-panel active" data-market-panel="main">{main}</div>
      <div class="m-market-panel" data-market-panel="other">{other}</div>
    </div>'''


def mobile_match(match, scope, idx):
    markets = match.get("markets") or {}
    market_count = sum(len(v or []) for v in markets.values())
    detail_id = f"detail-{scope}-{idx}"
    if scope == "live":
        hs = display_home_score(match.get("home_score"))
        aw = display_away_score(match.get("away_score"))
        meta = f'<span class="m-live-badge">LIVE</span><span class="m-score">{esc(hs)} : {esc(aw)}</span>{live_clock(match, True)}'
    else:
        meta = f'<span class="m-kickoff">{esc(fmt_match_date(match.get("match_date")))}</span>'
    return f'''
    <article class="m-match">
      <button class="m-match-summary" type="button" data-open-detail="{detail_id}">
        <span class="m-match-name"><b>{esc(match.get("home"))}</b> <em>vs</em> {esc(match.get("away"))}</span>
        <span class="m-match-meta">{meta}</span>
        <span class="m-more">+{market_count}</span>
      </button>
      {mobile_detail(match, scope, detail_id)}
    </article>'''


def mobile_leagues(rows, scope):
    out, current, league_rows = [], None, []
    def flush(name, items, start_idx):
        if not items:
            return "", start_idx
        cards = []
        for m in items:
            cards.append(mobile_match(m, scope, start_idx))
            start_idx += 1
        block = f'<section class="m-league"><div class="m-league-head"><span class="m-chev">⌃</span><span>{esc(name)}</span><b>{len(items)}</b><i>↻</i></div>{"".join(cards)}</section>'
        return block, start_idx
    idx = 0
    for match in rows:
        league = league_name(match)
        if current is None:
            current = league
        if league != current:
            block, idx = flush(current, league_rows, idx)
            out.append(block)
            league_rows = []
            current = league
        league_rows.append(match)
    if current is not None:
        block, idx = flush(current, league_rows, idx)
        out.append(block)
    return "".join(out) or '<div class="m-empty">Không có trận trong mục này.</div>'


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
    desktop = {scope: desktop_leagues(rows, scope) for scope, rows in grouped.items()}
    mobile = {scope: mobile_leagues(rows, scope) for scope, rows in grouped.items()}

    doc = f'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1"><meta name="theme-color" content="#121a2a"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><title>M88 · Bóng đá</title>
<style>
:root{{--navy:#121a2a;--navy2:#1b263b;--nav:#151e2f;--league:#52627d;--peach:#f8e9e5;--red:#c92513;--gold:#d8b674;--blue:#5b88df;--ink:#263651;--muted:#7f8999;--line:#e7dfdc;--white:#fff}}
*{{box-sizing:border-box}}html,body{{margin:0;font-family:Arial,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#e9eef2;color:#283643;-webkit-text-size-adjust:100%}}button{{font:inherit}}input.scope{{position:absolute;opacity:0;pointer-events:none}}
/* desktop */
.d-shell{{display:block}}.d-top{{height:48px;background:#153f64;color:#fff;display:flex;align-items:center;padding:0 14px;gap:20px;position:sticky;top:0;z-index:30}}.d-brand{{font-size:22px;font-weight:900}}.d-brand em{{font-style:normal;color:#f4ae29}}.d-nav{{display:flex;height:100%;align-items:center;gap:18px;font-weight:700;color:#d9e6ee}}.d-updated{{margin-left:auto;font-size:11px;color:#cbdce7}}.d-layout{{max-width:1440px;margin:auto;display:grid;grid-template-columns:185px minmax(650px,1fr) 270px;gap:8px;padding:8px}}.d-side,.d-board,.d-slip{{background:#fff;border:1px solid #cad4db;align-self:start}}.d-side h3,.d-slip h3{{margin:0;background:#194b74;color:#fff;padding:10px}}.d-side div{{padding:10px;border-bottom:1px solid #e1e6ea}}.d-side .active{{background:#e8f2f8;color:#174f79;font-weight:800}}.d-board-head{{background:#174c75;color:#fff;padding:9px 10px;font-weight:800}}.scope-tabs{{display:flex;background:#fff;border-bottom:1px solid #d8e0e5}}.scope-tabs label{{padding:10px 18px;font-weight:800;color:#657581;border-right:1px solid #e1e6ea;cursor:pointer}}.scope-tabs b{{font-size:10px;background:#e7edf1;padding:2px 6px;border-radius:9px}}#scope-live:checked~.app label[for=scope-live],#scope-today:checked~.app label[for=scope-today],#scope-early:checked~.app label[for=scope-early]{{background:#1d669a;color:#fff}}.scope-panel{{display:none}}#scope-live:checked~.app .panel-live,#scope-today:checked~.app .panel-today,#scope-early:checked~.app .panel-early{{display:block}}.market-header,.event-row{{display:grid;grid-template-columns:minmax(220px,1.6fr) minmax(145px,1fr) minmax(145px,1fr) minmax(135px,.9fr) minmax(145px,1fr) 42px}}.market-header{{background:#e7edf1;font-size:11px;font-weight:800}}.market-header>div{{padding:7px;text-align:center;border-left:1px solid #d5dde3}}.market-header>div:first-child{{text-align:left;border-left:0}}.league-head{{height:31px;background:#dceaf2;display:flex;align-items:center;padding:0 8px;font-size:11px;font-weight:800;color:#28516a;border-top:1px solid #b9ccd8}}.league-head .league-name{{flex:1}}.event-row{{min-height:62px;border-bottom:1px solid #dde4e8;background:#fff}}.event-info{{padding:6px 9px;border-right:1px solid #e0e5e8}}.event-meta{{font-size:10px;display:flex;gap:7px;color:#788690;min-height:18px}}.live-clock{{color:var(--red);font-weight:800}}.score{{font-weight:800;color:#26394a}}.team{{line-height:17px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.market-cell{{padding:4px;border-right:1px solid #e0e5e8;display:flex;flex-direction:column;gap:3px;justify-content:center}}.muted-cell{{align-items:center;color:#aaa}}.odd-line{{display:flex;gap:3px}}.odd-btn{{flex:1;min-width:0;background:#edf4f8;border:1px solid #d3e2eb;padding:4px;display:flex;justify-content:space-between;gap:3px}}.odd-label{{font-size:10px}}.odd-btn b{{color:#155c8d}}.more-cell{{display:flex;align-items:center;justify-content:center;background:#f3f7fa;color:#1d6594;font-weight:800}}.d-slip p{{padding:25px 15px;text-align:center;color:#89949c}}
/* mobile clone-like */
.m-shell{{display:none}}
@media(max-width:820px){{html,body{{background:#fff;overflow-x:hidden}}.d-shell{{display:none}}.m-shell{{display:block;padding-bottom:76px;background:#fff;min-height:100vh}}.m-header{{background:var(--navy);color:#fff;position:sticky;top:0;z-index:80;box-shadow:0 1px 0 #283348}}.m-head-row{{height:72px;display:flex;align-items:center;padding:0 14px;gap:9px}}.m-logo{{width:105px;display:flex;align-items:center;gap:7px;flex:0 0 auto}}.m-logo-box{{width:43px;height:43px;background:#a51f1d;border:2px solid #e6c879;display:flex;align-items:center;justify-content:center;color:#fff;font-family:Georgia,serif;font-size:27px;font-weight:900;box-shadow:inset 0 0 0 2px #7d1614}}.m-logo-text{{font-size:11px;font-weight:800;line-height:1.15;white-space:nowrap}}.m-logo-text small{{display:block;font-size:9px;font-weight:500;margin-top:3px;color:#d7dbe3}}.m-auth{{margin-left:auto;display:flex;gap:8px;align-items:center}}.m-auth button{{height:39px;border-radius:23px;padding:0 15px;font-weight:800;font-size:12px;letter-spacing:.2px}}.m-login{{background:transparent;border:2px solid #f3f5f8;color:#fff}}.m-register{{background:var(--gold);border:0;color:#1e293c}}.m-menu{{font-size:31px;line-height:1;color:#fff;padding-left:2px}}.m-mainnav{{height:47px;display:flex;align-items:center;gap:29px;padding:0 16px;overflow-x:auto;white-space:nowrap;color:#c8ccd5;font-size:13px;font-weight:800;scrollbar-width:none}}.m-mainnav::-webkit-scrollbar{{display:none}}.m-mainnav .active{{color:#fff}}.hot{{background:#d93856;color:#fff;border-radius:3px;font-size:9px;padding:6px 5px;margin-left:4px;vertical-align:2px}}.m-announcement{{height:39px;background:#21304f;color:#fff;display:flex;align-items:center;padding:0 12px;font-size:11px}}.m-announcement span{{color:#d7b777;margin-left:3px}}.m-announcement i{{margin-left:auto;font-style:normal;color:#d7dde8}}.m-scope-tabs{{display:flex;height:45px;background:#fff;border-bottom:1px solid #d8dde4;position:sticky;top:119px;z-index:70}}.m-scope-tabs label{{flex:1;display:flex;align-items:center;justify-content:center;gap:5px;font-size:12px;font-weight:800;color:#68758a;border-right:1px solid #e3e7ed}}.m-scope-tabs b{{font-size:9px;background:#e9edf2;padding:2px 6px;border-radius:8px}}#scope-live:checked~.app .m-scope-tabs label[for=scope-live],#scope-today:checked~.app .m-scope-tabs label[for=scope-today],#scope-early:checked~.app .m-scope-tabs label[for=scope-early]{{color:#efc933;border-bottom:3px solid #efc933;background:#172136}}#scope-live:checked~.app .m-scope-tabs label[for=scope-live] b,#scope-today:checked~.app .m-scope-tabs label[for=scope-today] b,#scope-early:checked~.app .m-scope-tabs label[for=scope-early] b{{background:#c92211;color:#fff}}.m-panel{{display:none}}#scope-live:checked~.app .m-panel-live,#scope-today:checked~.app .m-panel-today,#scope-early:checked~.app .m-panel-early{{display:block}}.m-league{{margin:0 0 10px}}.m-league-head{{min-height:50px;background:var(--league);color:#fff;display:grid;grid-template-columns:25px 1fr 34px 26px;align-items:center;padding:8px 10px;font-size:13px;text-transform:uppercase;letter-spacing:.1px}}.m-league-head b{{justify-self:center;background:#c92513;min-width:27px;height:27px;display:flex;align-items:center;justify-content:center;font-size:11px}}.m-league-head i{{font-style:normal;font-size:20px;justify-self:end}}.m-chev{{font-size:22px}}.m-match{{background:var(--peach);border-bottom:8px solid #fff}}.m-match-summary{{position:relative;width:100%;border:0;background:transparent;text-align:left;padding:18px 67px 17px 16px;color:var(--ink);min-height:106px}}.m-match-name{{display:block;font-size:15px;line-height:1.45}}.m-match-name b{{color:#c82717;font-weight:500}}.m-match-name em{{font-style:normal;color:#213452}}.m-match-meta{{display:flex;align-items:center;gap:8px;margin-top:12px;font-size:13px;color:#596a83}}.m-live-badge{{background:#c92513;color:#fff;padding:5px 8px;font-size:10px;font-weight:800}}.m-score{{font-size:14px;color:#596a83}}.m-kickoff{{font-size:12px;color:#586981}}.m-more{{position:absolute;right:16px;top:50%;transform:translateY(-50%);width:39px;height:39px;background:var(--blue);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800}}.m-detail{{display:none;background:#fae8e4;border-top:1px solid #e0d0cc}}.m-detail.open{{display:block}}.m-detail-head{{min-height:96px;background:#151f31;color:#fff;display:grid;grid-template-columns:32px 1fr 28px;align-items:center;padding:12px 12px}}.m-back{{border:0;background:transparent;color:#fff;font-size:31px;padding:0;text-align:left}}.m-detail-title{{font-size:16px;line-height:1.35}}.m-detail-title em{{font-style:normal;color:#efc52e}}.m-detail-title small{{display:block;margin-top:7px;font-size:11px;color:#c5cad4;text-transform:uppercase}}.m-detail-score{{color:#efc52e;font-weight:800}}.m-refresh{{font-size:23px;text-align:right}}.m-detail-tabs{{height:49px;background:#213252;display:flex}}.m-detail-tabs button{{flex:1;border:0;background:transparent;color:#aeb7c8;font-size:13px}}.m-detail-tabs button.active{{color:#f2c928;border-bottom:3px solid #f2c928}}.m-market-panel{{display:none;padding:13px 7px 20px}}.m-market-panel.active{{display:block}}.m-market{{margin:0 0 16px}}.m-market h3{{margin:0 0 4px;text-align:center;font-size:15px;font-weight:500;color:#2d405d}}.m-odd-grid{{display:grid;gap:2px;margin-bottom:2px}}.m-odd-grid.two{{grid-template-columns:1fr 1fr}}.m-odd-grid.three{{grid-template-columns:repeat(3,1fr)}}.m-odd{{min-height:59px;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:5px 3px}}.m-odd span{{font-size:12px;color:#7f8998;line-height:1.2;text-align:center}}.m-odd b{{font-size:16px;color:#253752;margin-top:3px;font-weight:500}}.m-no-market,.m-empty{{padding:30px 15px;text-align:center;color:#798697}}.m-bottom{{position:fixed;left:0;right:0;bottom:0;height:65px;padding-bottom:env(safe-area-inset-bottom);background:#111a2a;color:#d4d8e1;display:grid;grid-template-columns:repeat(5,1fr);z-index:100;box-shadow:0 -1px 4px #0005}}.m-bottom div{{display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:9px;gap:4px}}.m-bottom i{{font-style:normal;font-size:23px;line-height:1}}.m-bottom .active{{color:#f0c728}}.m-bottom .badge{{position:absolute;margin:-20px 0 0 25px;background:#c92513;color:#fff;border-radius:12px;padding:2px 5px;font-size:8px}}
}}
@media(max-width:390px){{.m-head-row{{padding:0 10px}}.m-logo{{width:94px}}.m-auth button{{padding:0 12px;font-size:11px}}.m-mainnav{{gap:22px;padding:0 12px}}.m-match-summary{{padding-left:14px;padding-right:61px}}.m-match-name{{font-size:14px}}}}
</style></head>
<body data-snapshot="{esc(generated_at)}">
<input class="scope" type="radio" name="scope" id="scope-live" checked><input class="scope" type="radio" name="scope" id="scope-today"><input class="scope" type="radio" name="scope" id="scope-early">
<div class="app">
<div class="d-shell"><header class="d-top"><div class="d-brand">M<em>88</em> MSports</div><div class="d-nav"><span>Streaming</span><span>All Live</span><span>All Sports</span><span>Bet List</span><span>More</span></div><div class="d-updated">Updated {esc(updated)} VN · Decimal</div></header><div class="d-layout"><aside class="d-side"><h3>SPORTS</h3><div class="active">⚽ Soccer · {sum(counts.values())}</div><div>🏀 Basketball</div><div>🎾 Tennis</div><div>🏐 Volleyball</div><div>🎮 E-Sports</div></aside><main class="d-board"><div class="d-board-head">⚽ Soccer · Asian View · Decimal</div><div class="scope-tabs"><label for="scope-live">Live <b>{counts['live']}</b></label><label for="scope-today">Today <b>{counts['today']}</b></label><label for="scope-early">Early <b>{counts['early']}</b></label></div><div class="market-header"><div>Event</div><div>HDP</div><div>O/U</div><div>1X2</div><div>1H</div><div>+</div></div><section class="scope-panel panel-live">{desktop['live']}</section><section class="scope-panel panel-today">{desktop['today']}</section><section class="scope-panel panel-early">{desktop['early']}</section></main><aside class="d-slip"><h3>BET SLIP</h3><p>View-only dashboard</p></aside></div></div>
<div class="m-shell"><header class="m-header"><div class="m-head-row"><div class="m-logo"><div class="m-logo-box">M</div><div class="m-logo-text">ĐẤU TRƯỜNG<br>CHÂU Á<small>— VIỆT —</small></div></div><div class="m-auth"><button class="m-login" type="button">ĐĂNG NHẬP</button><button class="m-register" type="button">ĐĂNG KÝ</button></div><div class="m-menu">☰</div></div><nav class="m-mainnav"><span>TRANG CHỦ</span><span class="active">THỂ THAO <b class="hot">HOT</b></span><span>THỂ THAO ĐIỆN TỬ</span><span>CASINO</span></nav></header><div class="m-announcement">Chào mừng đến với <span>Trang Thể Thao Mới</span><i>Cập nhật {esc(updated.split(' · ')[0])}</i></div><div class="m-scope-tabs"><label for="scope-live">TRỰC TIẾP <b>{counts['live']}</b></label><label for="scope-today">HÔM NAY <b>{counts['today']}</b></label><label for="scope-early">SẮP TỚI <b>{counts['early']}</b></label></div><main><section class="m-panel m-panel-live">{mobile['live']}</section><section class="m-panel m-panel-today">{mobile['today']}</section><section class="m-panel m-panel-early">{mobile['early']}</section></main><nav class="m-bottom"><div><i>▶</i><span>Phát Hình</span></div><div><i>◉</i><span class="badge">{counts['live']}</span><span>Trực Tiếp</span></div><div class="active"><i>⚽</i><span>Bóng đá</span></div><div><i>▤</i><span>D.Sách Cược</span></div><div><i>•••</i><span>Thêm</span></div></nav></div>
</div>
<script>
(function(){{
 const snapshot=Date.parse(document.body.dataset.snapshot||'');
 function tick(){{
   if(!Number.isFinite(snapshot)) return;
   const age=Math.max(0,Math.floor((Date.now()-snapshot)/60000));
   document.querySelectorAll('[data-live-clock]').forEach(el=>{{
     const raw=el.dataset.raw||'LIVE', round=el.dataset.round||'', base=parseInt(el.dataset.baseMin||'',10);
     if(!Number.isFinite(base)||raw.includes('+')||round==='2') return;
     let m=base+age;
     if(round==='1') m=Math.min(m,45);
     if(round==='3') m=Math.min(m,90);
     const prefix=round==='1'?'1H ':round==='3'?'2H ':'';
     el.textContent=prefix+m+"'";
   }});
 }}
 tick(); setInterval(tick,15000);
 document.addEventListener('click',e=>{{
   const open=e.target.closest('[data-open-detail]');
   if(open){{document.getElementById(open.dataset.openDetail)?.classList.add('open');return;}}
   const close=e.target.closest('[data-close-detail]');
   if(close){{document.getElementById(close.dataset.closeDetail)?.classList.remove('open');return;}}
   const tab=e.target.closest('[data-market-tab]');
   if(tab){{const detail=tab.closest('.m-detail');detail.querySelectorAll('[data-market-tab]').forEach(x=>x.classList.toggle('active',x===tab));detail.querySelectorAll('[data-market-panel]').forEach(x=>x.classList.toggle('active',x.dataset.marketPanel===tab.dataset.marketTab));}}
 }});
 async function freshness(){{
   try{{const r=await fetch('data.json?t='+Date.now(),{{cache:'no-store'}});if(!r.ok)return;const d=await r.json();const ts=Date.parse(d.live_generated_at||d.generated_at||'');if(Number.isFinite(ts)&&Number.isFinite(snapshot)&&ts>snapshot+5000)location.replace(location.pathname+'?v='+ts);}}catch(e){{}}
 }}
 setInterval(freshness,20000); setTimeout(freshness,5000);
}})();
</script></body></html>'''

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"REAL_LIVE_MATCHES={counts['live']}")
    print(f"REAL_TODAY_MATCHES={counts['today']}")
    print(f"REAL_EARLY_MATCHES={counts['early']}")
    print(f"ONE_PAGE_MATCHES={sum(counts.values())}")


if __name__ == "__main__":
    main()
