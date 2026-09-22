# WR M30 breadth/time conclusion — 2026-09-22

## Scope
Coded WR v2.5.13, M30, fee schedule entry taker 5bps / TP maker 2bps / other exits taker 5bps.

## AAVE time-filter ablation
Exact 5m->M30 replay, 2021-01-01 through 2026-08-14.

Authority baseline `NORMAL + T+1`, weekday, VN windows 14:00-17:59 and 21:00-23:59:
- n=36
- net +9.0611R
- E +0.2517R
- PF 1.3965
- break-even equivalent 27.69bps
- exact parity vs prior AAVE authority: 36/36.

Removing the time window while keeping `NORMAL + T+1`:
- n=80
- net +21.7011R
- E +0.2713R
- PF 1.4493
- break-even 31.18bps.

However the time relaxation is regime-dependent:
- 2022: -5.7110R net
- 2025: +10.4578R net
- 2026 through Aug14: +4.4362R net.
- 2021-23 half: E +0.0997R, PF 1.1573
- 2024-26 half: E +0.5286R, PF 1.9460.

Fresh untouched window 2026-08-15 through 2026-09-18 for the all-time rule:
- 1 filled trade
- -1.1143R net
Therefore `AAVE_ALLTIME` is NOT promoted.

Adding T-1 while retaining original windows degrades the historical result:
- n=42, net +5.5804R, E +0.1329, PF 1.1957.
All weekdays with original windows: n=60, net +9.3593R, E +0.1560, PF 1.2333.
All weekdays all-time: n=130, net +7.0254R, E +0.0540, PF 1.0786.

A simple time-rule walk-forward also does not justify replacing the original windows. Using 2021-23 only, the original-window rule beats all-time; on 2024-26 it remains positive (+2.6887R net / 15 trades, E +0.1792, PF 1.2677).

## Expanded-symbol follow-up
The broad 45-symbol M30 expansion failed aggregate economics, but AAVE was the only symbol passing the strict preregistered stability diagnostic.

A relaxed breadth gate was defined after the broad scan for further research only:
- n >= 20 on 2022-2026-08-14
- net > +2R
- positive net in both 2022-24 and 2025-26 halves.
Only AAVE and RUNE satisfy it.

### AAVE
2022-2026-08-14: n=33, net +5.5603R, E +0.1685, PF 1.2551.
Independent 2021 holdout: n=3, net +3.5008R, E +1.1669, PF 4.3106.
Fresh 2026-08-15 to 09-18: 0 trades.

### RUNE
2022-2026-08-14: n=25, net +2.9491R, E +0.1180, PF 1.1732.
Independent 2021 holdout: n=4, net +1.5443R, E +0.3861, PF 2.1478.
RUNE 2021 was rechecked using exact 5m->M30 resampling and matched direct-M30 4/4 signal timestamps.
Fresh 2026-08-15 to 09-18: 0 trades.

### AAVE + RUNE candidate
Keeping the original time windows and T rule:
- full 2021 through 2026-08-14: n=65
- gross +20.6709R
- net +13.5545R
- net E +0.2085R/trade
- net PF 1.3288
- 2022-2026-08-14 selection window: n=58, net +8.5094R, E +0.1467R
- independent 2021 combined holdout: n=7, net +5.0450R, E +0.7207R
- fresh 2026-08-15 to 09-18: no AAVE/RUNE trades.

## Rejected breadth candidates
CRV looked mildly positive in the 2022+ scan but failed independent 2021 holdout decisively:
- 5 trades
- 5 SL
- -5.2526R net
Fresh 2026 window: 0 trades.
Therefore AAVE+CRV is rejected.

## Current status
- `AAVE_ALLTIME = NOT_PROMOTED`
- `CRV_M30 = REJECTED_BY_2021_HOLDOUT`
- `AAVE_RUNE_M30 = PRIMARY_BREADTH_CANDIDATE`
- `AAVE_RUNE_RULE = NORMAL+T+1, ORIGINAL_TIME_WINDOWS`
- `FORWARD = STILL_PAUSED`

The AAVE+RUNE selection is still research-selected from the 2022+ universe scan. Its 2021 holdout is encouraging but small (7 trades), so it is not yet production/forward-ready by itself.

## Additional timeframe check: AAVE M15
Exact 5m->M15, same `NORMAL+T+1` and original VN windows:
- n=50
- gross +13.5135R
- net 5/2/5 +6.6942R
- net E +0.1339R
- PF 1.2034
- max DD 7.2208R
- median stop distance ~0.706%
- negative net years: 2021, 2024, 2026 through Aug14.

M15 increases trade count but is materially less stable than AAVE M30, so it is secondary research only and does not replace M30.

## Cost robustness of AAVE+RUNE M30
Full 2021 through 2026-08-14, n=65:
- fee 5/2/5: +13.5545R, E +0.2085, PF 1.3288, max DD 6.8557R
- fee 4.5/1.8/4.5: +14.2661R, E +0.2195, PF 1.3501
- 6bps equivalent: +15.9030R, E +0.2447, PF 1.4047
- all-maker 2/2: +17.4910R, E +0.2691, PF 1.4562
- equivalent break-even friction ~26.01bps.

But temporal stability is weak after combining RUNE:
- 2024: -5.6632R net
- 2026 through Aug14: -1.0582R net
- combined 2024-26 is negative despite positive full-history total.
Thus AAVE+RUNE remains a breadth research candidate, not a stronger replacement for AAVE M30 alone.
