# Trinity ATR SuperTrend audit backtest

Window: 2026-05-19T20:00:00+00:00 -> 2026-08-17T20:00:00+00:00 (90 days, 3m)
Defaults: ST1 3m, ST2 60m, ST3 240m, ATR 10, multiplier 1, triple alignment, SL=TP=1x 60m ATR.
Cost model: 5 bps per side. Clean model enters on next 3m bar open and uses only previously confirmed HTF bars.

| Symbol | Variant | Trades | Win % | Gross PF | Gross R | Net PF | Net R | MaxDD R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | ERROR: GET failed after 5 tries: https://fapi.binance.com/fapi/v1/klines?symbol=SOLUSDT&interval=3m&startTime=1778011200000&endTime=1786996799999&limit=1500: HTTP Error 451:  | | | | | | | |
| ETHUSDT | ERROR: GET failed after 5 tries: https://fapi.binance.com/fapi/v1/klines?symbol=ETHUSDT&interval=3m&startTime=1778011200000&endTime=1786996799999&limit=1500: HTTP Error 451:  | | | | | | | |
| XRPUSDT | ERROR: GET failed after 5 tries: https://fapi.binance.com/fapi/v1/klines?symbol=XRPUSDT&interval=3m&startTime=1778011200000&endTime=1786996799999&limit=1500: HTTP Error 451:  | | | | | | | |

Notes: The published Pastebin file is an indicator, not a TradingView strategy. Therefore its claimed Strategy Tester metrics are not reproducible from that file alone. Max drawdown percent also cannot be uniquely reproduced because position sizing is absent.
