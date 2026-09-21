# WR canonical T + symbol filter scan — 2026-09-22

Authority: only the 95 manual-sheet rows that replay as actual canonical `Wave Rider Strategy v2.5.13 WINDOW REPORT` trades under the full lifecycle. R values are canonical replay R, not the old spreadsheet R.

T-class source: date-cell background colours in `Backtest 2026 / 5m Wave Rider crypto`:
- white/default = NORMAL
- blue `FF4A86E8` = T+1
- cyan `FF00FFFF` = T-1
- green `FF00FF00` = T0
- orange `FFFF9900` = CLUSTER_OTHER (T-2/T+2/T+3 family)

## Baseline
95 trades, +37.5579R, E +0.39535R/trade, PF 1.7203.

## Current asset rule: SOL + ETH + XRP
All T classes: 60 trades, +27.7066R, E +0.46178, PF 1.8633.

By T within SOL/ETH/XRP:
- NORMAL: n47, +20.0691R, E +0.42700, PF 1.7739.
- T+1: n3, +6.9R, E +2.3 (too small to promote independently).
- T-1: n1, +2.3R, E +2.3 (far too small to promote independently).
- T0: n3, -3.0R, E -1.0.
- CLUSTER_OTHER: n6, +1.4375R, E +0.23958, PF 1.4545.

Grouped according to current Finalized doc:
- CLUSTER = T-2/T-1/T0/T+2/T+3: n10, +0.7375R, E +0.07375, PF 1.1197.
- NONCLUSTER = T+1 + no-news NORMAL: n50, +26.9691R, E +0.53938, PF 2.0400.

Thus, under T+symbol only, the current cluster thesis is weak: removing all cluster trades cuts 10 trades but loses only +0.7375R and raises E from +0.46178 to +0.53938.

## Granular T filter candidate
Keep NORMAL + T+1 + T-1; skip T0 + CLUSTER_OTHER.
With SOL/ETH/XRP: n51, +29.2691R, E +0.57390, WR 47.06%, PF 2.1287.
This removes 9 trades whose combined contribution is -1.5625R, so total R rises while trade count falls.
Bootstrap trade-resampling 95% interval for E: approximately [+0.125, +1.020]R; P(bootstrap mean > 0) ~99.45%.
Caveat: T-1 contributes only one current-symbol canonical trade, so its inclusion is not independently established.

## More aggressive expectancy-max candidate inside current family
ETH + SOL, keep NORMAL + T+1 + T-1: n23, +19.9R, E +0.86522, WR 56.52%, PF 2.99.
Bootstrap 95% E interval ~[+0.148,+1.583]R.
This is higher expectancy but materially smaller sample and must not be promoted without OOS/forward confirmation.

## Practical provisional interpretation
The strongest sample-size-aware T+symbol evidence is:
1. Keep the existing asset family SOL/ETH/XRP for the robust version.
2. Prefer NONCLUSTER (NORMAL + T+1) over CLUSTER.
3. T0 is specifically poor inside the current asset family (0W/3L, -3R).
4. Orange cluster-other is weak (+0.2396R/trade) and removing it together with T0 improves both total R and expectancy in-sample.
5. T-1 looks good but has n=1 within SOL/ETH/XRP; classify as unresolved, not proven good.

Do not alter Finalized production rule from this scan alone. The current Finalized rule couples T class to time windows; this scan intentionally tests only T + symbol, per user instruction. Time must be layered next before promotion.
