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
MAIN_MARKETS = [
    "ft_asian_handicap", "ft_over_under", "ft_1x2",
    "fh_asian_handicap", "fh_over_under", "fh_1x2",
]
MARKET_TITLES = {
    "ft_asian_handicap": "CƯỢC CHẤP TOÀN TRẬN",
    "ft_over_under": "TÀI / XỈU TOÀN TRẬN",
    "ft_1x2": "1X2 TOÀN TRẬN",
    "fh_asian_handicap": "CƯỢC CHẤP HIỆP 1",
    "fh_over_under": "TÀI / XỈU HIỆP 1",
    "fh_1x2": "1X2 HIỆP 1",
    "ft_odd_even": "TOÀN TRẬN LẺ / CHẴN",
    "fh_odd_even": "HIỆP 1 LẺ / CHẴN",
    "double_chance": "CƠ HỘI KÉP",
    "ht_ft": "H1 / T.T",
    "correct_score": "CƯỢC TỈ SỐ",
    "ft_total_goals": "TỔNG BÀN THẮNG TOÀN TRẬN",
    "fh_total_goals": "TỔNG BÀN THẮNG HIỆP 1",
    "first_last_goal": "BÀN THẮNG ĐẦU / CUỐI",
}
MARKET_ORDER = MAIN_MARKETS + [
    "double_chance", "ht_ft", "correct_score",
    "ft_total_goals", "fh_total_goals",
    "first_last_goal", "ft_odd_even", "fh_odd_even",
]


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def fmt_price(v):
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "—"


def league_name(m):
    return (m.get("league") or {}).get("name") or "Khác"


def is_virtual(m):
    s = " ".join([league_name(m), m.get("home") or "", m.get("away") or ""])
    return bool(VIRTUAL_RE.search(s))


def fmt_updated(value):
    try:
        return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%H:%M:%S · %d/%m/%Y")
    except Exception:
        return value or "unknown"


def fmt_match_date(value):
    s = str(value or "")
    try:
        return datetime.strptime(s[:12], "%Y%m%d%H%M").strftime("%d/%m %H:%M")
    except Exception:
        return s or "Prematch"


def home_score(raw):
    s = str(raw or "")
    if "_" in s:
        p = s.split("_")
        return p[1] if len(p) > 1 and p[1] != "" else p[0]
    return s or "0"


def away_score(raw):
    s = str(raw or "")
    return (s.split("_")[0] if "_" in s else s) or "0"


def live_clock(m):
    raw = str(m.get("live_timer") or "LIVE").replace("`", "'")
    round_id = str(m.get("event_round") or "")
    mm = re.search(r"(\d{1,3})", raw)
    base = mm.group(1) if mm else ""
    if not round_id and base.isdigit():
        round_id = "1" if int(base) <= 45 else "3"
    prefix = {"1": "1H", "2": "HT", "3": "2H"}.get(round_id, "")
    shown = "HT" if round_id == "2" else f"{prefix} {raw}".strip()
    attrs = f'data-live-clock data-raw="{esc(raw)}" data-round="{esc(round_id)}"'
    if base and "+" not in raw:
        attrs += f' data-base-min="{esc(base)}"'
    return f'<span class="clock" {attrs}>{esc(shown)}</span>'


def line_value(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return f"{v:g}"
    return str(v)


def selection_label(sel, family, line=None):
    s = str(sel or "")
    low = s.lower()
    mapping = {
        "home": "Nhà", "away": "Khách", "draw": "Hòa",
        "over": "Tài", "under": "Xỉu", "odd": "Lẻ", "even": "Chẵn",
        "1x": "1X", "12": "12", "x2": "X2",
        "home_home": "Nhà / Nhà", "home_draw": "Nhà / Hòa", "home_away": "Nhà / Khách",
        "draw_home": "Hòa / Nhà", "draw_draw": "Hòa / Hòa", "draw_away": "Hòa / Khách",
        "away_home": "Khách / Nhà", "away_draw": "Khách / Hòa", "away_away": "Khách / Khách",
        "first_goal_home": "Bàn đầu Nhà", "first_goal_away": "Bàn đầu Khách",
        "last_goal_home": "Bàn cuối Nhà", "last_goal_away": "Bàn cuối Khách", "no_goal": "Không bàn",
    }
    base = mapping.get(low, s)
    if family in {"asian_handicap", "over_under"} and line is not None:
        return f"{base} {line_value(line)}"
    return base


def price_cell(p, family, line=None):
    label = selection_label(p.get("selection"), family, line)
    return f'<div class="odd"><span>{esc(label)}</span><b>{fmt_price(p.get("value"))}</b></div>'


def market_group(name, lines):
    if not lines:
        return ""
    family = (lines[0] or {}).get("family") or ""
    title = MARKET_TITLES.get(name, name.replace("_", " ").upper())
    blocks = []
    for line in lines:  # deliberately no cap: show every available line
        prices = [p for p in (line.get("prices") or []) if p.get("value") is not None]
        if not prices:
            continue
        if family in {"correct_score", "ht_ft"}:
            cls = "grid3"
        elif len(prices) == 3:
            cls = "grid3"
        elif len(prices) == 2:
            cls = "grid2"
        elif len(prices) == 4:
            cls = "grid2"
        else:
            cls = "grid3"
        cells = "".join(price_cell(p, family, line.get("line")) for p in prices)
        blocks.append(f'<div class="odds-grid {cls}">{cells}</div>')
    if not blocks:
        return ""
    return f'<section class="market"><h3>{esc(title)}</h3>{"".join(blocks)}</section>'


def market_panel(m, names, panel_name):
    markets = m.get("markets") or {}
    body = "".join(market_group(n, markets.get(n) or []) for n in names)
    if not body:
        body = '<div class="no-market">M88 hiện không mở thị trường nào trong nhóm này.</div>'
    return f'<div class="market-panel" data-panel="{panel_name}">{body}</div>'


def match_details(m, scope, idx):
    markets = m.get("markets") or {}
    available = [n for n in MARKET_ORDER if markets.get(n)]
    extras = [n for n in available if n not in MAIN_MARKETS]
    if scope == "live":
        status = f'<span class="live-tag">LIVE</span><span class="detail-score">{esc(home_score(m.get("home_score")))} : {esc(away_score(m.get("away_score")))}</span>{live_clock(m)}'
    else:
        status = f'<span class="kickoff">{esc(fmt_match_date(m.get("match_date")))}</span>'
    main_panel = market_panel(m, MAIN_MARKETS, "main")
    other_panel = market_panel(m, extras, "other")
    market_count = len(available)
    return f'''
<details class="match" id="match-{scope}-{idx}">
  <summary class="match-summary">
    <span class="match-name"><b>{esc(m.get("home"))}</b> <em>vs</em> {esc(m.get("away"))}</span>
    <span class="match-meta">{status}</span>
    <span class="more">+{market_count}</span>
  </summary>
  <div class="detail">
    <div class="detail-head">
      <button class="back" type="button" data-close-details>‹</button>
      <div class="detail-title"><div>{esc(m.get("home"))} <strong>vs</strong> {esc(m.get("away"))}</div><small>{status} · {esc(league_name(m))}</small></div>
      <span class="refresh">↻</span>
    </div>
    <div class="detail-tabs"><button type="button" class="active" data-tab="main">Thị trường chính</button><button type="button" data-tab="other">Thị trường khác <i>{len(extras)}</i></button></div>
    {main_panel}{other_panel}
  </div>
</details>'''


def league_sections(rows, scope):
    if not rows:
        return '<div class="empty">Không có trận trong mục này.</div>'
    out = []
    current = None
    items = []
    idx = 0
    def flush(name, ms, start):
        if not ms:
            return "", start
        cards = []
        for x in ms:
            cards.append(match_details(x, scope, start)); start += 1
        return f'<section class="league"><div class="league-head"><span>⌃</span><b>{esc(name)}</b><i>{len(ms)}</i><em>↻</em></div>{"".join(cards)}</section>', start
    for m in rows:
        ln = league_name(m)
        if current is None:
            current = ln
        if ln != current:
            block, idx = flush(current, items, idx); out.append(block)
            current, items = ln, []
        items.append(m)
    block, idx = flush(current, items, idx); out.append(block)
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    matches = [m for m in (data.get("matches") or []) if not is_virtual(m)]
    grouped = {s: [m for m in matches if m.get("scope") == s] for s in SCOPES}
    counts = {s: len(v) for s, v in grouped.items()}
    generated = data.get("live_generated_at") or data.get("generated_at") or ""
    updated = fmt_updated(generated)
    sections = {s: league_sections(rows, s) for s, rows in grouped.items()}
    total_selections = (data.get("counts") or {}).get("total_selections") or 0

    doc = f'''<!doctype html><html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1"><meta name="theme-color" content="#151d2b"><meta name="apple-mobile-web-app-capable" content="yes"><title>M88 · Bóng đá</title>
<style>
:root{{--navy:#151d2b;--navy2:#1d2940;--league:#566783;--peach:#faebe7;--red:#c92816;--gold:#d8b675;--yellow:#f1c927;--blue:#5e8be2;--ink:#273852;--muted:#7b8494;--line:#eadedb}}
*{{box-sizing:border-box}}html,body{{margin:0;background:#fff;color:var(--ink);font-family:Arial,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}}button{{font:inherit}}input.scope{{position:absolute;opacity:0;pointer-events:none}}summary{{list-style:none}}summary::-webkit-details-marker{{display:none}}
.app{{max-width:900px;margin:0 auto;background:#fff;min-height:100vh;padding-bottom:73px}}
.header{{background:var(--navy);color:#fff;position:sticky;top:0;z-index:100}}.head-row{{height:73px;display:flex;align-items:center;padding:0 14px;gap:9px}}.logo{{width:108px;display:flex;align-items:center;gap:7px;flex:none}}.logo-box{{width:44px;height:44px;background:#a31e1c;border:2px solid #e5c879;box-shadow:inset 0 0 0 2px #791512;color:#fff;font:900 28px Georgia;display:flex;align-items:center;justify-content:center}}.logo-txt{{font-size:11px;font-weight:800;line-height:1.15;white-space:nowrap}}.logo-txt small{{display:block;font-size:9px;font-weight:500;color:#d4d9e2;margin-top:3px}}.auth{{margin-left:auto;display:flex;align-items:center;gap:8px}}.auth button{{height:40px;border-radius:23px;padding:0 15px;font-size:12px;font-weight:800}}.login{{background:transparent;color:#fff;border:2px solid #fff}}.register{{background:var(--gold);color:#223047;border:0}}.hamb{{font-size:29px;margin-left:2px}}
.nav{{height:48px;display:flex;align-items:center;gap:28px;padding:0 16px;overflow:auto;white-space:nowrap;color:#c7cbd3;font-size:13px;font-weight:800;scrollbar-width:none}}.nav::-webkit-scrollbar{{display:none}}.nav .active{{color:#fff}}.hot{{background:#d93a57;color:#fff;padding:5px;border-radius:3px;font-size:9px;margin-left:4px}}.notice{{height:39px;background:#223151;display:flex;align-items:center;padding:0 12px;font-size:11px}}.notice span{{color:#d8b777;margin-left:3px}}.notice small{{margin-left:auto;color:#d7dde7}}
.scope-tabs{{height:46px;display:flex;background:#fff;border-bottom:1px solid #dce1e7;position:sticky;top:121px;z-index:90}}.scope-tabs label{{flex:1;display:flex;align-items:center;justify-content:center;gap:5px;color:#6e798b;font-size:12px;font-weight:800;border-right:1px solid #e4e8ed}}.scope-tabs b{{background:#e9edf1;border-radius:9px;padding:2px 6px;font-size:9px}}#scope-live:checked~.app label[for=scope-live],#scope-today:checked~.app label[for=scope-today],#scope-early:checked~.app label[for=scope-early]{{background:#172137;color:var(--yellow);border-bottom:3px solid var(--yellow)}}#scope-live:checked~.app label[for=scope-live] b,#scope-today:checked~.app label[for=scope-today] b,#scope-early:checked~.app label[for=scope-early] b{{background:var(--red);color:#fff}}
.panel{{display:none}}#scope-live:checked~.app .live-panel,#scope-today:checked~.app .today-panel,#scope-early:checked~.app .early-panel{{display:block}}
.league{{margin-bottom:10px}}.league-head{{min-height:51px;background:var(--league);color:#fff;display:grid;grid-template-columns:25px 1fr 34px 27px;align-items:center;padding:8px 10px;text-transform:uppercase}}.league-head>span{{font-size:22px}}.league-head>b{{font-size:13px;font-weight:500;line-height:1.3}}.league-head>i{{font-style:normal;background:var(--red);width:27px;height:27px;display:flex;align-items:center;justify-content:center;font-size:11px}}.league-head>em{{font-style:normal;font-size:20px;text-align:right}}
.match{{background:var(--peach);border-bottom:8px solid #fff}}.match-summary{{position:relative;min-height:106px;padding:18px 66px 17px 16px;cursor:pointer}}.match-name{{display:block;font-size:15px;line-height:1.45}}.match-name b{{color:var(--red);font-weight:500}}.match-name em{{font-style:normal;color:#233552}}.match-meta{{display:flex;align-items:center;gap:8px;margin-top:12px;color:#5c6c84;font-size:13px;flex-wrap:wrap}}.live-tag{{background:var(--red);color:#fff;font-size:10px;font-weight:800;padding:5px 8px}}.clock{{color:#5c6c84;font-weight:500}}.more{{position:absolute;right:16px;top:50%;transform:translateY(-50%);width:41px;height:41px;background:var(--blue);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800}}details[open]>.match-summary{{display:none}}
.detail{{background:#fae8e4}}.detail-head{{min-height:102px;background:#161f30;color:#fff;display:grid;grid-template-columns:35px 1fr 28px;align-items:center;padding:12px}}.back{{border:0;background:transparent;color:#fff;font-size:34px;padding:0;text-align:left;cursor:pointer}}.detail-title{{font-size:16px;line-height:1.35;min-width:0}}.detail-title>div{{word-break:break-word}}.detail-title strong{{color:var(--yellow);font-weight:500}}.detail-title small{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:7px;color:#c7ccd5;font-size:11px;text-transform:uppercase}}.detail-score{{color:var(--yellow);font-weight:800}}.refresh{{font-size:23px;text-align:right}}.detail-tabs{{height:50px;background:#223252;display:flex}}.detail-tabs button{{flex:1;border:0;background:transparent;color:#abb4c5;font-size:13px;cursor:pointer}}.detail-tabs button.active{{color:var(--yellow);border-bottom:3px solid var(--yellow)}}.detail-tabs i{{font-style:normal;background:#ffffff18;padding:2px 5px;border-radius:8px;font-size:9px}}
.market-panel{{padding:14px 7px 20px}}.js .market-panel{{display:none}}.js .market-panel.active{{display:block}}.market{{margin-bottom:18px}}.market h3{{margin:0 0 5px;text-align:center;color:#2c3e5b;font-size:15px;font-weight:500}}.odds-grid{{display:grid;gap:2px;margin-bottom:2px}}.grid2{{grid-template-columns:repeat(2,1fr)}}.grid3{{grid-template-columns:repeat(3,1fr)}}.odd{{min-height:62px;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:5px 3px;text-align:center}}.odd span{{font-size:12px;color:#7d8695;line-height:1.2}}.odd b{{font-size:16px;color:#263751;font-weight:500;margin-top:4px}}.no-market,.empty{{padding:32px 15px;text-align:center;color:#7c8798}}
.footer{{padding:12px 10px 82px;text-align:center;color:#8b929b;font-size:10px}}.bottom{{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(900px,100%);height:66px;padding-bottom:env(safe-area-inset-bottom);background:#111a2a;color:#d3d8e1;display:grid;grid-template-columns:repeat(5,1fr);z-index:110;box-shadow:0 -1px 5px #0005}}.bottom div{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;font-size:9px}}.bottom i{{font-style:normal;font-size:23px;line-height:1}}.bottom .active{{color:var(--yellow)}}.updated{{font-size:10px;color:#8793a4;padding:7px 10px;text-align:right;background:#f6f7f9}}
@media(min-width:821px){{.app{{box-shadow:0 0 20px #0002}}.match-summary{{min-height:88px}}}}
@media(max-width:390px){{.head-row{{padding:0 10px}}.logo{{width:95px}}.auth button{{padding:0 11px;font-size:11px}}.nav{{gap:21px;padding:0 12px}}.match-summary{{padding-left:14px;padding-right:61px}}.match-name{{font-size:14px}}.odd b{{font-size:15px}}}}
</style>
<script>document.documentElement.classList.add('js')</script></head>
<body data-snapshot="{esc(generated)}">
<input class="scope" type="radio" name="scope" id="scope-live" checked><input class="scope" type="radio" name="scope" id="scope-today"><input class="scope" type="radio" name="scope" id="scope-early">
<div class="app">
<header class="header"><div class="head-row"><div class="logo"><div class="logo-box">M</div><div class="logo-txt">ĐẤU TRƯỜNG<br>CHÂU Á<small>– VIỆT –</small></div></div><div class="auth"><button class="login">ĐĂNG NHẬP</button><button class="register">ĐĂNG KÝ</button><span class="hamb">☰</span></div></div><nav class="nav"><span>TRANG CHỦ</span><span class="active">THỂ THAO <i class="hot">HOT</i></span><span>THỂ THAO ĐIỆN TỬ</span><span>CASINO</span></nav><div class="notice">Chào mừng đến với <span>Trang Thể Thao Mới</span><small>Decimal · {esc(updated)}</small></div></header>
<div class="scope-tabs"><label for="scope-live">Trực tiếp <b>{counts['live']}</b></label><label for="scope-today">Hôm nay <b>{counts['today']}</b></label><label for="scope-early">Sắp tới <b>{counts['early']}</b></label></div>
<div class="updated">Full market feed · {esc(total_selections)} selections</div>
<main><section class="panel live-panel">{sections['live']}</section><section class="panel today-panel">{sections['today']}</section><section class="panel early-panel">{sections['early']}</section></main>
<div class="footer">M88 / MSports public guest odds · chỉ xem dữ liệu · Virtual/PES/eSoccer đã loại</div>
<nav class="bottom"><div><i>▷</i>Phát Hình</div><div><i>◉</i>Trực Tiếp</div><div class="active"><i>⚽</i>Bóng đá</div><div><i>▤</i>D.Sách Cược</div><div><i>•••</i>Thêm</div></nav></div>
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
     if(round==='1') m=Math.min(m,45); if(round==='3') m=Math.min(m,90);
     el.textContent=(round==='1'?'1H ':round==='3'?'2H ':'')+m+"'";
   }});
 }}
 tick(); setInterval(tick,15000);
 document.addEventListener('click',e=>{{
   const close=e.target.closest('[data-close-details]');
   if(close){{const d=close.closest('details');if(d)d.open=false;return;}}
   const tab=e.target.closest('[data-tab]');
   if(tab){{const d=tab.closest('.detail');d.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===tab));d.querySelectorAll('[data-panel]').forEach(x=>x.classList.toggle('active',x.dataset.panel===tab.dataset.tab));}}
 }});
 document.querySelectorAll('.detail').forEach(d=>{{const p=d.querySelector('[data-panel="main"]');if(p)p.classList.add('active')}});
 async function freshness(){{try{{const r=await fetch('data.json?t='+Date.now(),{{cache:'no-store'}});if(!r.ok)return;const d=await r.json();const ts=Date.parse(d.live_generated_at||d.generated_at||'');if(Number.isFinite(ts)&&Number.isFinite(snapshot)&&ts>snapshot+5000)location.replace(location.pathname+'?v='+ts);}}catch(e){{}}}}
 setTimeout(freshness,5000);setInterval(freshness,20000);
}})();
</script></body></html>'''
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(doc, encoding="utf-8")
    print(f"REAL_LIVE_MATCHES={counts['live']}")
    print(f"REAL_TODAY_MATCHES={counts['today']}")
    print(f"REAL_EARLY_MATCHES={counts['early']}")
    print(f"FULL_SELECTIONS={total_selections}")


if __name__ == "__main__":
    main()
