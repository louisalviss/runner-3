# Trinity ATR SuperTrend audit backtest

Window: 2026-07-19T00:00:00+00:00 -> 2026-08-18T00:00:00+00:00 (90 days, 3m)
Defaults: ST1 3m, ST2 60m, ST3 240m, ATR 10, multiplier 1, triple alignment, SL=TP=1x 60m ATR.
Cost model: 5 bps per side. Clean model enters on next 3m bar open and uses only previously confirmed HTF bars.

| Symbol | Variant | Trades | Win % | Gross PF | Gross R | Net PF | Net R | MaxDD R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | Original lookahead + same-bar | 170 | 60.0 | 1.5 | 34.0 | 1.03 | 2.397 | 9.396 |
| SOLUSDT | Confirmed HTF, same-bar | 161 | 50.31 | 1.012 | 1.0 | 0.684 | -30.143 | 34.111 |
| SOLUSDT | Confirmed HTF + next-bar | 159 | 50.94 | 1.038 | 3.0 | 0.701 | -27.769 | 31.736 |
| ETHUSDT | Original lookahead + same-bar | 148 | 56.76 | 1.312 | 20.0 | 0.863 | -10.455 | 14.425 |
| ETHUSDT | Confirmed HTF, same-bar | 132 | 44.7 | 0.808 | -14.0 | 0.518 | -42.636 | 47.24 |
| ETHUSDT | Confirmed HTF + next-bar | 132 | 44.7 | 0.808 | -14.0 | 0.518 | -42.636 | 47.24 |
| XRPUSDT | Original lookahead + same-bar | 166 | 58.43 | 1.406 | 28.0 | 0.928 | -5.97 | 10.069 |
| XRPUSDT | Confirmed HTF, same-bar | 147 | 44.9 | 0.815 | -15.0 | 0.534 | -45.579 | 46.402 |
| XRPUSDT | Confirmed HTF + next-bar | 146 | 46.58 | 0.872 | -10.0 | 0.571 | -40.353 | 41.176 |

Notes: The published Pastebin file is an indicator, not a TradingView strategy. Therefore its claimed Strategy Tester metrics are not reproducible from that file alone. Max drawdown percent also cannot be uniquely reproduced because position sizing is absent.
