# WR M10/M15 Cross-Asset Conclusion — 2026-09-22

Status: RESEARCH CHECKPOINT — NO FORWARD / NO PRODUCTION

## Frozen test
- Source: market-data-crossasset-m5-20260821 (Dukascopy BID M5)
- Period: 2022-01-01 through 2026-08-14
- Universe: 19 assets from frozen release cache
- Core: Wave Rider v2.5.13
- Admission: NORMAL + T+1, original VN time windows
- Timeframes: M10 and M15
- Gate preregistered before outcomes: N>=50, gross E>=+0.10R, PF>=1.15, early>0, late>0, >=3 positive years, break-even friction >=2bps/side
- Fast runner parity gate: US500 M30 matched authority exactly: 30 trades, -11.90111813869442R, PF 0.5041200775543991

## Aggregate
### M10
- 702 trades, -76.0732R gross, weighted E -0.1084R/trade
- US stocks: 110 trades, +19.6679R
- FX: 472 trades, -60.1088R
- Index CFDs: 58 trades, -43.1918R
- Metal: 62 trades, +7.5595R
- Gross gate pre-cost: 0/19

Notable but rejected:
- XAUUSD: 62 trades, +7.5595R, E +0.1219, PF 1.193; early +13.177R, late -5.618R -> regime instability
- GBPUSD: 39 trades, +9.707R -> sample below gate
- META: 19 trades, +12.726R -> sample below gate
- EURUSD: 42 trades, +6.454R -> sample below gate / only 2 positive years

### M15
- 454 trades, -7.0575R gross, weighted E -0.0155R/trade
- US stocks: 86 trades, +6.5113R
- FX: 288 trades, -7.0451R
- Index CFDs: 54 trades, -8.8322R
- Metal: 26 trades, +2.3085R
- Gross gate pre-cost: 0/19

Notable but rejected:
- EURUSD: 20 trades, +15.526R, E +0.776, PF 2.814 -> sample far below gate
- USDCAD: 27 trades, +9.138R, E +0.338, PF 1.571 -> sample below gate
- GBPUSD: 19 trades, +7.971R, E +0.420, PF 1.910 -> sample below gate
- XAUUSD: 26 trades, +2.309R, E +0.089, PF 1.143 -> below expectancy/PF/sample gates

## Decision
M10 and M15 do not solve the M5-vs-M30 trade-off under the original crypto-derived admission windows.
- M5: enough sample, but stop/cost geometry fails.
- M10: more sample, but broad gross edge collapses.
- M15: better gross quality in isolated small cells, but still too few trades and no 19-asset survivor meets the frozen gate.
- M30: better cost geometry, but sparse.

Therefore do NOT relax the preregistered gate post-hoc and do NOT promote any M10/M15 symbol from this screen.

Next clean research question: test the WR core on TradFi using session-native/no-crypto-time-window admission, preregistered separately by asset class. This is a new hypothesis and must not be called OOS validation of the current rule.
