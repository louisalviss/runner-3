# Wave Rider M30 recheck — backtest status 2026-09-22

## Scope
Backtest/research only. Forward collector is paused. No production promotion.

Coded strategy authority: Wave Rider Strategy v2.5.13 WINDOW REPORT.
Market/data: Binance USD-M futures, 5m archive aggregated to M30.
History evaluated: 2021-01-01 through 2026-08-14.
Symbols under original Finalized family: SOL, ETH, XRP.
Cost models include 6bps equivalent and entry taker5 / TP maker2 / other taker5.
Official CPI/NFP/FOMC calendars are used to classify T dates.

## Original Finalized T/time schedule on M30 — exact admission
- Weekends OFF.
- Cluster = T-2/T-1/T0/T+2/T+3: VN 00:00-11:59, 14:00-17:59, 21:00-23:59.
- NORMAL/T+1: VN 14:00-17:59, 21:00-23:59.
- Symbols SOL/ETH/XRP.

Result 2021-01-01..2026-08-14:
- n=174
- gross +15.7772R; E +0.09067; PF 1.1448
- 6bps equivalent +2.5108R; E +0.01443; PF 1.0214
- fee 5/2/5 = -4.1260R; E -0.02371; PF 0.9665

Yearly 5/2/5 net:
- 2021 -1.0275R
- 2022 -4.5203R
- 2023 +2.7694R
- 2024 +1.2978R
- 2025 +0.7816R
- 2026 through Aug14 -3.4270R

By day class under original schedule:
- NORMAL n58: -0.6133R net 5/2/5
- T+1 n10: +9.5202R net 5/2/5 (tiny sample; unstable across longer diagnostics)
- CLUSTER n106: -13.0328R net 5/2/5

Conclusion: original Finalized cluster thesis FAILS on M30 executable history. The full original M30 schedule is not production-ready.

## Reduced T/time scan
Using fixed pre-existing time windows and scanning only symbol/T subsets produced an aggregate candidate:
`SOL + ETH / NORMAL + T+1 / M30 / Finalized NORMAL time windows`.

Exact admission rerun (not post-filter ledger approximation):
- n=50
- gross +15.0520R
- net 6bps +11.0729R; E +0.22146; PF 1.3555
- net 5/2/5 +9.1702R; E +0.18340; PF 1.2801
- discounted 4.5/1.8/4.5 +9.7584R
- max DD under 5/2/5 ~8.484R
- max losing streak 6
- win rate 40% (20W/30L)
- break-even equivalent friction ~22.70bps

Yearly 5/2/5 net:
- 2021 +7.9991R
- 2022 -4.1379R
- 2023 +3.7026R
- 2024 -2.3345R
- 2025 +3.0316R
- 2026 through Aug14 +0.9093R

Stability problem:
- NORMAL contributes n42, only +0.6792R net; it is negative in 4/6 years.
- T+1 contributes n8, +8.4910R net; T+1 is negative in 2021-22 and strongly positive from 2023 onward.
- Thus most aggregate edge comes from only eight regime-dependent T+1 trades.
- 2021-23 half: +7.5638R net; 2024-26 half: +1.6064R net.

Conclusion: aggregate candidate is interesting but NOT robust enough to promote. It is a post-recheck research candidate only.

## Full reduced-day M30 context
SOL/ETH/XRP, weekday NORMAL+T-1+T+1, cluster dates excluded, no time filter, 2021..2026-Aug14:
- n266
- gross +9.9124R
- net 5/2/5 -20.6176R
- E -0.0775
Therefore time filtering is material but does not by itself establish stable alpha.

## Current status
- `FORWARD = PAUSED`
- `ORIGINAL_FINALIZED_M30 = FAIL_EXECUTABLE`
- `M30_REDUCED_AGGREGATE_CANDIDATE = RESEARCH_ONLY`
- `ROBUST_M30_RULE = NOT_YET_ESTABLISHED`
- Do not tune from 2026 results and reuse the same history as validation.
