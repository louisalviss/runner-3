# Wave Rider T + High-Volume Tick-Correction Revalidation — Preregistration

Date: 2026-09-21 Asia/Ho_Chi_Minh
Status: PREREGISTERED / RESULTS UNSEEN

## Why this rerun is mandatory
Runs `35548191674` and `35554525285` used synthetic crypto metadata containing `_tick`, while `wr_tv_parity.tv_tick()` reads `minmov/pricescale` and otherwise defaults them to `1/1`. Therefore runtime price tick became `1.0` for synthetic crypto regardless of inferred Binance tick. Those runs are invalid for crypto conclusions. This rerun changes infrastructure semantics only; it does not change T labels, volume thresholds, WR structural parameters, or choose filters after P/L.

## Mandatory preflight
Before any full result is accepted, the corrected generic harness must reproduce the existing TradingView/Binance 5m golden totals:
- BNBUSDT: 14 trades / +10.92089552238821R
- TRXUSDT: 14 trades / +12.4R
with runtime tick exactly equal to the inferred Binance tick.

## Frozen research inputs
- 5m Binance USDT futures archive.
- Signal period: 2025-01-01 through 2026-08-14.
- T: Vietnam-local T-2,T-1,T0,T+2,T+3 around actual CPI/NFP/FOMC; T+1, white days, weekends excluded.
- High volume: causal 24h quote volume >= USD100M AND prior-completed-day average 10D dollar-volume proxy > USD200M.
- Corrected Pine-compatible WR structural signal; next-bar stop-entry.
- Same candidate JSONs as the prior preregistered audit.
- No parameter, T-label, symbol, hour, or volume-threshold sweep after results.

## Frozen variants
1. `canonical_correct_tick`: canonical v2.5.13 lifecycle including EMA/session/news behavior, but correct tick metadata.
2. `fixed_guarded_correct_tick`: same guarded admission, fixed TP +2.3R / SL -1R only.
3. `fixed_pure_correct_tick`: 24/7 crypto signal admission, fixed TP +2.3R / SL -1R only.

For fixed variants, same-bar TP+SL ambiguity is conservative SL. Report gross and modeled 6bps sensitivity separately. Any unresolved report-period position at available data end is censored, not force-closed.
