# WR US Stocks 30m — Validation Preregistration

Date: 2026-08-24

## Frozen candidate
- Strategy: WR 2.5.13 frozen base
- Timeframe: 30m only
- Universe: the 68 symbols with valid 30m results in run 32657035483
- No RS
- No Market-State/regime filter
- No parameter changes
- No symbol selection based on 30m PnL
- No post-result tuning

## Primary question
Does the untuned WR 30m candidate remain positive under actual Dukascopy BID/ASK execution, and is the edge chronologically stable rather than dependent on 2026 alone?

## Execution methodology — corrected before full-universe result
The archived execution simulator from PR #129 is reused without changing alpha rules, but the executable quote base interval is **5m**, not 1m.

Reason for the correction: an initial one-symbol smoke test on ADP showed Dukascopy 1m history missing from 2023-11 through 2025-08 even though the M5 baseline source contains those periods. Using 1m would therefore compare different samples and invalidate midpoint→actual degradation. The partial 1m result is diagnostic only and must not be used as strategy evidence.

M5 is the exact source resolution used by run 32657035483 to build the 30m midpoint bars, so the BID/ASK execution audit must use the same M5 BID/ASK observations and the same monthly coverage.

Execution contract:
- Signals generated from the exact M5 BID+ASK midpoint source aggregated to 30m.
- Long stop entries trigger/fill on ASK.
- Short stop entries trigger/fill on BID.
- Long exits execute on BID.
- Short exits execute on ASK.
- Six 5m executable-side quote bars resolve entries/TP/SL inside each 30m chart bar.
- If TP and SL are both touched inside the same 5m quote bar, resolve conservatively to SL.
- Session/news/EMA exit rules remain frozen.
- Audit midpoint trade count/R must reconcile closely with the frozen 30m baseline before actual-execution conclusions are accepted.

## Chronological / walk-forward reporting
Because no parameters are fitted, walk-forward is an expanding-history diagnostic rather than a retuning procedure.

Report OOS folds exactly as:
- Fold 1: prior history 2022–2023; OOS = 2024
- Fold 2: prior history 2022–2024; OOS = 2025
- Fold 3: prior history 2022–2025; OOS = 2026 YTD

Also report:
- pre-2026 total (2022–2025)
- each calendar year
- Long vs Short
- symbol breadth
- trade count
- R, expectancy, PF, max DD
- midpoint aggregate vs actual-execution aggregate
- median entry/exit spread bps

## Promotion gate
30m can only move beyond PROMISING if:
1. Full-universe actual execution aggregate is positive.
2. PF under actual execution is > 1.0.
3. Result is not solely explained by 2026: pre-2026 actual execution should be at least non-negative, or there must be convincing positive OOS evidence across more than one post-2023 fold.
4. Positive symbol breadth is not narrowly concentrated in a few names.
5. Recomputed M5 midpoint aggregate reconciles with the frozen baseline sufficiently to establish same-sample validity.

If actual execution is negative, or only 2026 is positive while earlier OOS folds fail, keep/reject the candidate rather than tuning filters after seeing the result.
