# WR M15 Native-Session Cross-Asset — 2026-09-22

Preregister SHA256: 10f4dd589c8545c31d495ab634b767497dba3f915ed728df11f2440eab73e339
Frozen runner commit: 5d6868254405a936e33ef61da48b6352266bd392

## Design
- WR v2.5.13 core unchanged.
- M15, Dukascopy canonical BID M5 cache, 2022-01-01 through 2026-08-14.
- Removed crypto-derived VN hour window.
- US stock CFDs use source regular session with inferred day close, WR no-entry 40m / forced-exit 15m, no overnight carry.
- Other classes retain canonical UTC daily lifecycle guard.
- Variant T: only NORMAL + T+1 weekdays.
- Variant ALL: all weekdays, T labels diagnostic only.

## Aggregate gross results
- T: n=1895, R=-103.372020, E=-0.054550, PF=0.916296; prereg gross survivors: [].
- ALL: n=3116, R=-90.603837, E=-0.029077, PF=0.954807; prereg gross survivors: ['AMZN', 'TSLA'].

## ALL gross survivors
- AMZN: n=68, +13.2290R, E +0.1945, PF 1.4849; early +11.4692R, late +1.7598R; BE friction 3.645 bps/side.
- TSLA: n=69, +7.2117R, E +0.1045, PF 1.2042; early +6.8303R, late +0.3814R; BE friction 3.197 bps/side.

## Commission-only stress (1% risk, $0.02/share, $10 minimum/order scenario)
- AMZN: $10k E -0.0055; $25k E 0.1086; $50k E 0.1273; $100k E 0.1290 R/trade.
- TSLA: $10k E -0.0955; $25k E 0.0245; $50k E 0.0625; $100k E 0.0763 R/trade.

## Exact-spread blocker
Historical ASK M5 fetch for AMZN/TSLA is currently returning HTTP 429 from Dukascopy even after stale research downloaders were stopped. No synthetic spread was substituted. Therefore AMZN/TSLA remain execution-unvalidated until BID/ASK replay is completed.

## Decision state
- Native-session + T filter: FAIL (0/19 gross survivors).
- Native-session + all weekdays: stock-specific hypothesis only; AMZN and TSLA pass gross + BE-friction gate.
- AMZN = primary execution-validation candidate.
- TSLA = secondary/weak because late-half gross edge is only +0.381R and commission stress is materially weaker.
- FX, metal, index families: no prereg gross survivor under this M15 native-session test.
- Forward remains OFF.
