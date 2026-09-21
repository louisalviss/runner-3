# WR T + high-volume fresh OOS — 2026-09-21

Frozen before OOS P/L inspection.

## Question
Does the corrected-tick Wave Rider fixed +2.3R/-1R rule retain positive gross expectancy on fresh data after the prior sample ended 2026-08-14?

## OOS window
- Signal window: 2026-08-15 through 2026-09-17 VN-relevant dates; implementation report boundary through 2026-09-18 00:00 UTC.
- Settlement bars: through 2026-09-19 UTC (Binance archive availability at run time).
- Market: Binance USDT perpetual futures, 5m.

## T rule — frozen
Actual release timestamp converted to Asia/Ho_Chi_Minh calendar date, then calendar offsets T-2,T-1,T0,T+2,T+3; Saturday/Sunday excluded.
Official release anchors:
- Employment Situation: 2026-09-04 08:30 ET => T0 2026-09-04 VN.
- CPI: 2026-09-11 08:30 ET => T0 2026-09-11 VN.
- FOMC statement: 2026-09-16 14:00 ET => 2026-09-17 01:00 VN => T0 2026-09-17 VN.
No other event family is added.

## High-volume rule — frozen
Reconstruct from Binance 5m archive using the original Stage1 checkpoint semantics:
- rolling 24h quote volume >= USD 100M;
- prior-completed-UTC-day average 10D dollar-volume proxy > USD 200M;
- data alive <=10m;
- current TRADIFI perpetuals excluded;
- first qualifying checkpoint per session_date; only signals at/after firstq eligible.
vol7 and ADR14 are NOT required in this volume-only test.

## WR execution — frozen
- corrected Pine-compatible WR structural signal;
- tick inferred from Binance precision and supplied as TradingView minmov/pricescale (tick bug fixed);
- next-bar stop entry;
- fixed TP +2.3R / SL -1R only;
- conservative same-bar ambiguity => SL;
- no EMA/session/news exits after entry.

## Reporting
- Gross R, mean R, PF, win rate, max DD.
- Cost sensitivities 1, 2, 2.5, 2.9, 3, 6 bps-equivalent.
- T-label and symbol diagnostics are descriptive only; no subgroup is promoted from this run.
- Open/censored positions reported explicitly.

No threshold sweep, no symbol whitelist, no T-label rescue, no timeframe/TP/SL change after P/L is observed.
