#!/usr/bin/env python3
import json
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape

src = pathlib.Path("publish/data.json")
out = pathlib.Path("publish/index.html")
data = json.loads(src.read_text())

generated = datetime.fromisoformat(data["generated_at"])
local = generated.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
stamp = local.strftime("%H:%M:%S · %d/%m/%Y VN")

order = ["winner", "top4", "relegation", "goalscorer"]
short = {
    "winner": "Winner",
    "top4": "Top 4",
    "relegation": "Relegation",
    "goalscorer": "Top Goalscorer",
}

sections = []
for key in order:
    market = data["markets"][key]
    rows = []
    for i, item in enumerate(market["selections"], 1):
        rows.append(
            f'<tr><td class="rank">{i}</td><td class="name">{escape(item["selection"])}</td>'
            f'<td class="odds">{item["decimal"]:,.2f}</td></tr>'
        )
    sections.append(
        f'''<section class="market" id="{key}">
        <div class="market-head"><h2>{escape(market["label"])}</h2><span>{market["selection_count"]} selections</span></div>
        <div class="table-wrap"><table><thead><tr><th>#</th><th>Selection</th><th>Decimal</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table></div></section>'''
    )

nav = "".join(f'<a href="#{k}">{v}</a>' for k, v in short.items())
board_time = escape(data.get("board_time", "SABA board"))

html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta http-equiv="refresh" content="300"><title>SABA EPL Futures</title>
<style>
:root{{--bg:#0d1016;--panel:#151a23;--line:#252d3a;--text:#eef3f8;--muted:#8e9baa;--accent:#dbe7f3;--odds:#ffffff}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}}
main{{max-width:900px;margin:auto;padding:18px 14px 50px}}header{{padding:10px 2px 14px}}h1{{font-size:26px;margin:0 0 7px;letter-spacing:-.5px}}.sub{{font-size:13px;color:var(--muted);line-height:1.45}}
nav{{display:flex;gap:8px;overflow-x:auto;padding:4px 0 14px;position:sticky;top:0;background:linear-gradient(var(--bg) 80%,transparent);z-index:2}}nav a{{white-space:nowrap;color:var(--text);text-decoration:none;background:#1b2230;border:1px solid var(--line);border-radius:999px;padding:8px 12px;font-size:13px;font-weight:650}}
.market{{background:var(--panel);border:1px solid var(--line);border-radius:16px;margin:0 0 14px;overflow:hidden;scroll-margin-top:58px}}.market-head{{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:14px 14px 10px}}h2{{font-size:18px;margin:0}}.market-head span{{font-size:12px;color:var(--muted)}}
.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px 12px;border-top:1px solid var(--line)}}th{{font-size:11px;color:var(--muted);text-align:left;text-transform:uppercase;letter-spacing:.06em}}td{{font-size:14px}}.rank{{width:42px;color:var(--muted)}}.name{{font-weight:560}}.odds{{text-align:right;font-variant-numeric:tabular-nums;font-weight:760;font-size:15px;color:var(--odds)}}th:last-child{{text-align:right}}
footer{{color:var(--muted);font-size:12px;line-height:1.5;padding:8px 2px}}.refresh{{color:var(--accent);text-decoration:none}}
@media(max-width:520px){{main{{padding:13px 10px 40px}}h1{{font-size:23px}}th,td{{padding:9px 10px}}.market{{border-radius:13px}}}}
</style></head><body><main>
<header><h1>SABA · EPL Futures 2026/27</h1><div class="sub">Snapshot: {stamp}<br>{board_time} · Decimal odds · Public guest board</div></header>
<nav>{nav}</nav>
{''.join(sections)}
<footer>Source: Dafabet OW / SABA public guest sportsbook. Feed refresh is scheduled; this page reloads every 5 minutes. <a class="refresh" href="">Refresh now</a>.</footer>
</main></body></html>'''
out.write_text(html)
print("RENDERED", out, "markets", len(order))
