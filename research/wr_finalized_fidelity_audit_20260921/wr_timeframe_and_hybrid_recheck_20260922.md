# WR timeframe + hybrid recheck — 2026-09-22

Scope: research/recheck only. The fresh 2026-08-15..2026-09-18 window has already been observed and is no longer a clean OOS source for any new rescue hypothesis.

Frozen symbol/day context used for the diagnostics:
- symbols: ETH, SOL, SUI, XRP unless otherwise stated
- day filter: weekday NORMAL + T+1 + T-1; exclude any date overlapping T0/T-2/T+2/T+3
- Binance USD-M data
- WR v2.5.13 structural setup

## Fresh-window timeframe cost-geometry diagnostic
Period 2026-08-15..2026-09-18.

Canonical lifecycle:
- M5: n50, gross +6.1291R, E +0.1226, median stop 0.238%, break-even ~2.41bps, 6bps -9.1149R, fee 5/2/5 -16.4393R.
- M15: n15, gross +2.4455R, E +0.1630, median stop 0.726%, break-even ~5.63bps, 6bps -0.1586R, fee 5/2/5 -1.6539R.
- M30: n6, gross +3.9R, E +0.65, median stop 1.092%, break-even ~41.36bps, 6bps +3.3342R, fee 5/2/5 +3.1745R. Sample far too small.
- M60: n3, gross +0.3R, E +0.10, median stop 0.950%, break-even ~10.24bps, fee 5/2/5 +0.0244R. Sample unusably small.

Conclusion: higher timeframe fixes cost geometry mechanically, but fresh-window sample is too small to infer alpha.

## Long retrospective timeframe diagnostic
Period 2025-01-01..2026-08-14.

Canonical lifecycle:
- M15: n201, gross -7.0786R. FAIL before costs.
- M30: n112, gross +9.8067R, E +0.08756, median stop 0.895%, break-even ~6.69bps; 6bps +1.0146R; fee 5/2/5 -3.3507R; all-maker 2/2 +3.9434R.
  - 2025: n72, gross +1.3071R, 6bps -3.8028R, 5/2/5 -6.2785R.
  - 2026 through Aug14: n40, gross +8.4996R, 6bps +4.8174R, 5/2/5 +2.9278R.
- M60 canonical: n44, gross -4.3143R. FAIL before costs.
- M60 fixed: n44, gross +2.2R but 6bps -0.4369R and fee 5/2/5 -1.7713R.

Thus only M30 remains research-interesting, but its long-run executable edge is marginal and unstable by year.

## M5 hybrid tests
Preregistered before results in this recheck turn; no threshold sweep:
1. `COST06`: admit M5 signal only if planned entry-to-stop distance >= 0.60% of entry. Threshold comes from cost geometry: 6bps would then cost <= ~0.10R on the one-way-equivalent proxy.
2. `M15CONF`: last completed M15 close must be on the same side of EMA21 as trade direction and EMA21 slope over the canonical 2-bar lookback must point in the same direction.
3. `COST06_M15`: both gates.

Long retrospective 2025-01-01..2026-08-14, canonical lifecycle:
- BASE: n722, gross +37.0644R, break-even 1.30bps, 6bps -134.3723R.
- COST06: n84, gross +3.4071R, break-even 3.16bps, 6bps -3.0653R, fee 5/2/5 -6.5017R.
- M15CONF: n714, gross +28.5644R, break-even 1.01bps, 6bps -141.4032R.
- COST06_M15: identical to COST06 on this sample.

Conclusion: M15 same-direction confirmation does not meaningfully filter WR; cost gate removes most trades but the surviving wide-stop subset does not retain enough edge. Hybrid hypothesis FAILS retrospectively.

## Prior-symbol M30 check
Using the pre-existing Finalized symbol family SOL/ETH/XRP (not chosen after viewing the M30 result):

Long retrospective, canonical M30:
- n87
- gross +9.4182R, E +0.10826, PF 1.1734
- break-even equivalent friction ~7.70bps
- 6bps +2.0752R, E +0.02385
- fee 5/2/5: -1.5367R, E -0.01766
- BNB-style 10% discount 4.5/1.8/4.5: -0.4412R
- all-maker 2/2: +4.5231R
- break-even scaling of the 5/2/5 schedule is ~85.97%, equivalent roughly 4.30 / 1.72 / 4.30 bps.

Year split:
- 2025: n53, gross +3.5082R; 6bps -0.5590R; fee 5/2/5 -2.4954R.
- 2026 through Aug14: n34, gross +5.9100R; 6bps +2.6342R; fee 5/2/5 +0.9587R.

Fresh-window diagnostic for the same prior symbol family:
- n4
- gross +2.6R
- 6bps +2.1166R
- fee 5/2/5 +1.9874R
This is only 4 trades and MUST NOT be treated as validation.

## Current interpretation
- `M15_RESCUE = FAIL`
- `M60_RESCUE = FAIL`
- `M5_COST_GATE_RESCUE = FAIL`
- `M5_M15_CONFIRM_RESCUE = FAIL`
- `M30_RESEARCH_CANDIDATE = WATCH_ONLY`
- `M30_SOL_ETH_XRP = WATCH_ONLY / FORWARD_REQUIRED`

M30 solves the fee geometry better than M5, but the edge is still too small and historically unstable to promote. The only clean next step is forward collection under a frozen M30 rule and actual-account fee tier. Do not remove ETH or tune T/time based on these results and then reuse the same history as validation.
