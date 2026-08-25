# Wave Rider Rich US Market Context 60m — Preregistration

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / RESULTS UNSEEN

## Research question

Does a fixed causal composite of broad US market state identify a subset of frozen WR v2.5.13 US-stock 60m executable trades with positive OOS expectancy?

This is a new market-context lineage after the simple US500 bullish gate and sector-relative lineage failed. It does not reopen WR parameter/timeframe/ticker optimization.

## Frozen parent

- parent WR verifier: `27797cf9c4ea0a91b1bc8d62059d052c2c843eb5`
- parent executable run: `32677300335`
- parent artifact: `wr-stock60-actual-final`
- 68-stock universe
- 60m WR v2.5.13 unchanged
- actual Dukascopy BID/ASK execution unchanged
- no WR parameter, TP/SL, session, ticker, or execution change

Primary OOS: 2024-01-01 through parent end date.

## Data sources and causality

Market/context data uses Dukascopy M5 data, midpoint from paired BID/ASK where available, aggregated to the same epoch-aligned 60m bars as the frozen parent tooling.

At WR signal close `T`, every context value must come from the completed 60m bar whose open timestamp is `T - 60m`. Exact timestamp matching only; no nearest or future-bar fallback.

Warmup starts before 2024 and cannot use future observations.

### Volatility-index source contract

The pre-PnL infrastructure probe may identify a true VIX cash-index instrument only from this frozen priority list:
1. `VIX.IDX/USD`
2. `VOL.IDX/USD`
3. `VIX.CMD/USD`

`VXX` is diagnostic only and is NOT an allowed primary substitute because of ETN roll/decay behavior. If no true VIX candidate above has usable M5 history and QQQ is unavailable, the primary test is `INFRASTRUCTURE_BLOCKED`.

## Frozen 5-component context score

For every scoreable WR trade, compute exactly five binary components. No threshold sweep or alternate combination is allowed after results.

### 1. SPY absolute trend

EMA50 of SPY 60m close with pandas `ewm(span=50, adjust=False, min_periods=50)`.

LONG component = 1 only if:
- SPY close > EMA50
- EMA50 current > EMA50 previous bar

SHORT component = 1 only if both inequalities are reversed.

### 2. QQQ relative to SPY

`RS_QQQ_SPY = QQQ_close / SPY_close`

EMA50 on the synchronized ratio with the same recursive semantics.

LONG component = 1 only if ratio > EMA50 and EMA50 slope > 0.
SHORT component = 1 only if ratio < EMA50 and EMA50 slope < 0.

### 3. VIX regime

EMA20 of VIX 60m close with `ewm(span=20, adjust=False, min_periods=20)`.

LONG component = 1 only if VIX close < EMA20 and EMA20 slope < 0.
SHORT component = 1 only if VIX close > EMA20 and EMA20 slope > 0.

### 4. Cross-sectional breadth

Use the same frozen 68-stock universe. For each completed 60m bar, each stock is `above` if close > its own EMA50.

Breadth fraction = `above_count / valid_count`.
A breadth row is valid only when at least 62 of 68 stocks have valid EMA50 state.

LONG component = 1 only if breadth > 0.55 and breadth is higher than the previous valid bar.
SHORT component = 1 only if breadth < 0.45 and breadth is lower than the previous valid bar.

### 5. Cross-sectional dispersion

For each completed 60m bar, compute the cross-sectional standard deviation of same-bar simple returns across the frozen 68-stock universe. A row is valid only when at least 62 stocks have a valid return.

Define the benchmark as the median dispersion of the prior 100 valid completed 60m bars, excluding the current bar.

For BOTH LONG and SHORT, component = 1 only if current dispersion > prior-100-bar median. The mechanism tested is whether WR breakout/retest requires an elevated cross-sectional opportunity regime rather than direction from dispersion itself.

## Primary selector

`context_score = sum(5 components)`.

A = every frozen parent OOS trade with all five components causally scoreable.
B = subset of A with `context_score >= 4`.

Scores 0..5 and individual components are diagnostic only. The primary threshold is fixed at >=4 and cannot be changed after PnL is observed.

## Coverage and sample gates

The experiment is alpha-interpretable only if:
- QQQ and a permitted true VIX source have usable data;
- >=95% of eligible frozen parent OOS trades are fully scoreable.

If coverage fails, formal status is `INFRASTRUCTURE_BLOCKED`. PnL diagnostics may still be reported but cannot promote the lineage.

## Primary metrics

Report:
- A/B n, total R, mean R/trade, PF, win rate, max DD
- retention rate
- B-A mean R delta
- LONG/SHORT decomposition
- yearly 2024/2025/2026
- symbol breadth
- context-score distribution
- component hit rates
- day-block bootstrap, 2,000 resamples, fixed seed 20260825

## Frozen promotion gate

`PASS_RICH_US_CONTEXT_WR = true` only if ALL:
1. full causal coverage >=95%
2. B n >=150
3. B retention between 10% and 70%
4. B mean R/trade >0
5. B PF >1.05
6. B mean R/trade >= A mean R/trade +0.10R
7. B total R >0
8. B positive in at least 2 of 2024, 2025, 2026
9. >=50% of symbols with >=5 B trades have positive cumulative B R
10. day-block bootstrap 95% lower bound for B mean R >0
11. day-block bootstrap 95% lower bound for B-A mean R delta >0

If this gate fails, do not tune EMA lengths, breadth thresholds, dispersion lookback, score threshold, component weights, VIX interpretation, or post-hoc ticker/sector subsets to rescue this lineage.

A materially different market-context rule must be preregistered as a new hypothesis.