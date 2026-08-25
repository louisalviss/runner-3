# Wave Rider Breakout/Retest Execution Module — Preregistration

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / RESULTS UNSEEN

## Research question

On the already-validated independent RSI E2 + SuperTrend 60m US-equity alpha, does a simple Wave-Rider-like breakout/retest execution geometry improve executable opportunity-level expectancy versus the frozen market-entry baseline?

This is NOT a WR standalone rescue and does not use the canonical WR v2.5.13 signal. It tests whether WR's market-structure idea has value as an execution layer on positive external alpha.

## Frozen parent alpha

Canonical Super RSI profile:
- US equities, 60m, LONG ONLY
- RSI(10), SMA(RSI,10)
- enter on second bullish RSI/SMA crossover while RSI < 50
- reset count after entry or RSI > 50
- exit on SuperTrend(10, 2.5) bearish flip
- chart price = midpoint
- source = Dukascopy paired M5 BID/ASK
- baseline entry = next 60m ASK open
- baseline exit = next 60m BID open after frozen SuperTrend exit signal
- universe = 68 symbols
- primary exclude = AAPL, AMZN, MSFT, NVDA, TSLA
- primary = 63 symbols

Frozen parent parity target from independent executable validation:
- primary trades = 4,023
- actual PF = 1.3937737824422902
- actual mean = +64.07886507098598 bps/trade
- actual sum return = 25.778927418057663

If reconstruction misses parent parity materially, result is `INFRASTRUCTURE_BLOCKED`, not PASS/FAIL.

## Entry geometry

All variants share the exact same external-alpha signal and frozen SuperTrend exit. No exit optimization is allowed.

Reference breakout level `L` = midpoint HIGH of the completed 60m bar that generated the RSI E2 entry signal.

Entry search starts at the external signal close and spans at most the next **120 regular-session minutes = 24 available M5 regular-session bars**, carrying across overnight/weekend gaps when necessary. It ends earlier if the frozen parent exit time is reached.

The 120-regular-session-minute window is fixed before results because retest entry is a two-phase structure and needs room for breakout followed by retest. No 60/90/180-minute sweep is allowed.

### A — MARKET baseline

Frozen parent execution: next 60m ASK open, frozen SuperTrend BID exit.

### B — BREAKOUT_STOP

A resting buy-stop is modeled at `L` during the fixed entry window.

On the first causal M5 bar where ASK high >= `L`:
- if ASK open >= `L`, fill at ASK open;
- otherwise fill at `L`.

Exit remains the frozen parent BID exit. If no trigger before the 24-bar entry window closes, opportunity return = 0.

No extra breakout buffer and no threshold sweep.

### C — BREAKOUT_RETEST

First detect the same breakout event as B.

To avoid same-M5 path ambiguity, retest eligibility begins strictly on the NEXT regular-session M5 bar after the breakout-trigger bar.

A buy-limit is then modeled at the same level `L` for the remainder of the same fixed 24-bar window:
- if ASK open <= `L`, fill at ASK open;
- else if ASK low <= `L`, fill at `L`.

Exit remains the frozen parent BID exit. If no breakout or no later retest before the 24-bar window closes, opportunity return = 0.

No tolerance band around `L`, no ATR buffer, and no retest-depth sweep.

## Causality and execution rules

- All entry decisions use only M5 bars available after the completed external-alpha signal bar.
- Only M5 bars inside the canonical US regular session are counted toward the 24-bar horizon.
- ASK side governs long entry triggers/fills.
- Frozen BID exit from the parent strategy is reused.
- If a candidate entry would occur at or after the frozen exit time, it is a miss and receives zero return.
- Missed entries remain in opportunity-level evaluation with return = 0; they are NOT dropped.
- M5 intrabar path is not inferred beyond OHLC. Retest cannot occur on the same M5 bar as breakout.

## Primary evaluation

Primary = the same 63-symbol external-alpha holdout lineage across 2022-2026.

For A/B/C report:
- opportunities
- executed entries and execution rate
- opportunity-level total return and mean bps
- PF including zero-return misses
- executed-trade mean/PF
- win rate
- max drawdown
- 2022/2023/2024/2025/2026
- per-symbol breadth

Incremental comparison uses opportunity-level B-A and C-A deltas so missed entries cannot disappear from the denominator.

## Frozen promotion gates

Each candidate B and C is evaluated independently. `PASS_WR_EXECUTION_MODULE = true` only if at least one candidate passes ALL gates below.

1. parent baseline parity: n=4,023; PF within 0.01; mean within 1.0 bps of frozen parent
2. causal quote/level coverage >=99%
3. execution rate between 15% and 85%
4. candidate opportunity mean >0
5. candidate PF > A PF
6. candidate opportunity mean >= A mean +10 bps
7. candidate positive opportunity mean in >=4 of 5 calendar years 2022-2026
8. candidate positive in both 2025 and 2026
9. >=60% of symbols with >=10 candidate executions have positive cumulative candidate return
10. day-block bootstrap candidate mean lower bound >0
11. day-block bootstrap candidate-minus-A mean delta lower bound >0

Multiplicity: two candidates are tested. For gates 10-11 use a Bonferroni-adjusted one-sided familywise alpha of 5%, i.e. the 2.5th percentile as the lower bound for each candidate.

Bootstrap:
- block = UTC calendar day of the external signal
- 5,000 resamples
- fixed RNG seed = 20260825

## No-rescue rule

After results are seen, do NOT:
- change the 24-M5 / 120-regular-session-minute horizon
- add breakout buffer
- change retest tolerance/depth
- switch to close-confirmation
- select symbols from observed PnL
- alter the parent exit
- add RSI/ATR/volume/regime gates
- compare extra parameterized variants.

If B and C fail, this WR execution-module hypothesis is CLOSED. Any materially different execution idea is a new preregistered lineage.