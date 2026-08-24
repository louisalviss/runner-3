# WR 10m Timing Matched A/B on RSI E2 + SuperTrend External Alpha

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / B RESULTS UNSEEN
Parent external-alpha lineage: PR #222 / `PASS_EXECUTABLE_EXTERNAL_ALPHA=true`
Parent result commit: `70652643f8ac5ed80a9b0cc419f295d35f1ad268`
External-alpha preregistration: `e40a18777f26ce449140604cace83e07b35b1579`

## 1. Question

Given the already validated RSI E2 + SuperTrend 60m long opportunity set, does the frozen Wave Rider 10m long setup improve entry timing/execution enough to raise net expectancy after real BID/ASK friction?

This is an incremental timing test only. It does not reopen WR standalone alpha.

## 2. Frozen A/B opportunity set

Source of truth: final artifact from run `32772722993`, artifact `9537584643` (`external-alpha-rsi-e2st-60m-final`).

Primary gate uses exactly the same 63-stock holdout as PR #222 (AAPL, AMZN, MSFT, NVDA, TSLA excluded from primary because they were seen before the external-alpha holdout). All-68 remains secondary diagnostics.

Each closed external-alpha trade is one matched opportunity.

### A — Baseline

Use the exact stored external-alpha executable trade:
- 60m RSI(10) / SMA(RSI,10), second bullish cross below 50.
- next 60m bar ASK-open entry.
- SuperTrend(10,2.5) bearish flip exit at next 60m bar BID open.
- Stored `actual_return` is A return.

### B — WR timing/execution overlay

External alpha and its exit remain frozen.

After the external 60m signal close, search only the next 60 minutes for a canonical WR 2.5.13 LONG setup on 10m midpoint bars.

Frozen WR 10m long setup uses canonical `reference_verify.py` commit `27797cf9c4ea0a91b1bc8d62059d052c2c843eb5` indicator semantics:
- left/right pivots 10/10, rightmost-tie semantics;
- EMA 21, direction smoothing 2;
- >=12 consecutive closes above EMA;
- EMA angle period 4, ATR 10, angle threshold 5 degrees, bullish angle acceleration;
- CHOP(14) < 50;
- signal candle range <= 1.5 x ATR(14);
- resistance exists;
- bullish candle;
- close > EMA;
- close > resistance and low <= resistance (break/retest);
- US regular-session guard active;
- no new WR timing setup if the signal bar is within/approaches the final 40 minutes of the regular session, matching canonical session-guard intent.

Timing-layer state clarification, frozen before B is run:
- evaluate the raw canonical WR LONG setup condition independently on every completed 10m bar;
- do NOT import WR standalone position lifecycle or suppress a timing setup because a hypothetical unrelated WR standalone trade would still be active;
- this is intentional: B tests the WR setup as an entry-timing layer attached to each external-alpha opportunity, not the standalone WR trade engine;
- only the one-bar pending stop-entry state described below applies;
- if multiple qualifying WR setups/fills occur within one external-alpha timing window, use the earliest actual fill only.

WR entry execution:
- planned stop entry = 10m signal high + $0.01 tick;
- pending order is valid ONLY during the immediately following 10m bar;
- actual long fill uses paired M5 ASK quotes: if ASK open >= stop, fill at ASK open; else if ASK high reaches stop, fill at the planned stop price;
- if no fill in that next 10m bar, that WR setup expires and later WR setups may still qualify while inside the frozen 60-minute timing window;
- first valid WR fill wins;
- no WR TP, SL, EMA exit, news exit, or session exit is allowed in B. Only WR entry timing/execution is being tested.

B exit:
- exactly the same external-alpha exit timestamp and stored executable BID exit price as A;
- if B has no valid WR fill before the external-alpha exit, B return for that opportunity = 0 (missed opportunity), not silently dropped;
- if B fills, `B_return = stored_A_actual_exit / B_actual_entry - 1`.

Entry improvement for long = `(A_actual_entry - B_actual_entry) / A_actual_entry * 10,000` bps; positive means WR obtained a cheaper entry.

No parameter/timeframe/window/ticker/sector tuning after B results are visible.

## 3. Data / causality

- 10m WR chart is built from timestamp-paired Dukascopy M5 BID/ASK midpoint data, regular US session anchored at 09:30 America/New_York.
- Signals use completed 10m midpoint bars only.
- Fills use executable ASK M5 data only after the WR signal close.
- Parent A trade/exit data is read from the frozen artifact, not recomputed or selected from B outcomes.

## 4. Primary metrics

On the 63-stock primary holdout:
- A and B mean return per ORIGINAL external-alpha opportunity (missed B = 0);
- paired mean delta bps/opportunity;
- B executed-trade PF and A PF;
- B execution rate / missed rate;
- median entry improvement bps conditional on B fill;
- per-symbol opportunity-return delta and positive-symbol breadth;
- yearly A vs B mean opportunity return for 2022–2026;
- pre-2026 A vs B mean opportunity return;
- day-block paired bootstrap of mean delta (2,000 resamples), grouped by external signal-entry calendar date.

## 5. Frozen incremental-value gate

`PASS_WR_TIMING_INCREMENTAL=true` only if ALL hold on the 63-stock primary holdout:

1. Matched opportunity count equals the frozen parent primary set (expected 4,023; any discrepancy must be explained and blocks PASS unless caused only by unreadable artifact corruption).
2. B mean return per original opportunity >= A mean + 10 bps.
3. B executed-trade PF >= A PF + 0.05.
4. Median conditional entry improvement > 0 bps.
5. B executes at least 20% of original opportunities (missed rate <= 80%).
6. Pre-2026 B mean return/opportunity >= pre-2026 A mean return/opportunity.
7. B beats A mean return/opportunity in at least 2 of 2024, 2025, 2026.
8. Paired day-block bootstrap 95% lower confidence bound for `(B-A)` mean return is > 0 bps/opportunity.
9. At least 55% of primary symbols have cumulative matched B opportunity return >= their cumulative A opportunity return OR the median per-symbol `(B-A)` mean opportunity return is > 0; report both diagnostics.

## 6. Interpretation

If PASS:
- WR is promoted only as `INCREMENTAL_TIMING_EXECUTION_LAYER` for this validated external alpha.
- WR standalone alpha remains CLOSED.
- Next work may study cost-aware expected-net-EV / portfolio allocation or forward shadow, but not retune the A/B rules on this sample.

If FAIL:
- Do not tune the 10m WR parameters, timing window, ticker/sector list, or external-alpha parameters as rescue within this lineage.
- Record failure and keep the validated external alpha without WR timing.
