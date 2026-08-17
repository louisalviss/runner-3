# Trinity ATR SuperTrend audit backtest

Window: 2026-07-18T20:00:00+00:00 -> 2026-08-17T20:00:00+00:00 (90 days, 3m)
Defaults: ST1 3m, ST2 60m, ST3 240m, ATR 10, multiplier 1, triple alignment, SL=TP=1x 60m ATR.
Cost model: 5 bps per side. Clean model enters on next 3m bar open and uses only previously confirmed HTF bars.

| Symbol | Variant | Trades | Win % | Gross PF | Gross R | Net PF | Net R | MaxDD R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | ERROR: GET failed after 5 tries: https://api.bybit.com/v5/market/kline?category=linear&symbol=SOLUSDT&interval=3&start=1783195200000&end=1786996799999&limit=1000: HTTP Error 403: Forbidden | | | | | | | |
| ETHUSDT | ERROR: GET failed after 5 tries: https://api.bybit.com/v5/market/kline?category=linear&symbol=ETHUSDT&interval=3&start=1783195200000&end=1786996799999&limit=1000: HTTP Error 403: Forbidden | | | | | | | |
| XRPUSDT | ERROR: GET failed after 5 tries: https://api.bybit.com/v5/market/kline?category=linear&symbol=XRPUSDT&interval=3&start=1783195200000&end=1786996799999&limit=1000: HTTP Error 403: Forbidden | | | | | | | |

Notes: The published Pastebin file is an indicator, not a TradingView strategy. Therefore its claimed Strategy Tester metrics are not reproducible from that file alone. Max drawdown percent also cannot be uniquely reproduced because position sizing is absent.
