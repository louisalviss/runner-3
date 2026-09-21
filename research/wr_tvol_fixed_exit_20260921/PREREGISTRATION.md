# Wave Rider T + High-Volume Fixed-Exit Diagnostic — Preregistration

Date: 2026-09-21 Asia/Ho_Chi_Minh
Status: PREREGISTERED / RESULTS UNSEEN
Purpose: resolve the discrepancy between manual WR chart checks and run 35548191674.

## Frozen inputs
- WR structural signal engine: corrected Pine-compatible v2.5.13 verifier.
- Market: Binance USDT futures 5m archive.
- Signal period: 2025-01-01 through 2026-08-14 inclusive by signal time.
- High-volume eligibility: causal 24h quote volume >= USD 100M AND prior-completed-day average 10D dollar-volume proxy > USD 200M.
- T eligibility: Vietnam-local T-2, T-1, T0, T+2, T+3 around actual CPI/NFP/FOMC release dates; T+1, white days, weekends excluded.
- Entry: canonical WR next-bar stop-entry from the signal structure.
- Target: +2.30R fixed.
- Stop: -1.00R fixed.
- Same-bar TP+SL ambiguity: conservative -> SL.
- No parameter or threshold sweep.

## Frozen variants
1. `fixed_guarded`
   - Preserve the prior run's session/news signal-admission gates.
   - REMOVE EMA/session/news exits after entry.
   - Exit only fixed TP/SL.

2. `fixed_pure`
   - Same WR structural signal + T + high-volume eligibility.
   - No session/news signal-admission gate for 24/7 crypto.
   - Exit only fixed TP/SL.

## Accounting
Report both:
- gross R (manual-chart comparable), and
- modeled net R at 6 bps using the same entry-distance cost geometry as run 35548191674.

Signals inside the report period may resolve after report end. Bars through 2026-08-31 are used only to settle already-open positions; no post-period signal is counted.
Any unresolved position at data end is censored and reported separately, never force-closed.

This is a semantics correction/diagnostic, not a post-hoc volume/T rescue. The fixed TP/SL lifecycle was specified before the prior result was observed.
