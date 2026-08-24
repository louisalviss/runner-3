# RSI E2 + SuperTrend 60m — Executable External-Alpha Validation Preregistration

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / RESULTS UNSEEN
Lineage: NEW INDEPENDENT EXTERNAL ALPHA — NOT A WAVE RIDER RESCUE

## 1. Purpose

Validate whether the open-source RSI second-cross + SuperTrend strategy has independent executable long alpha on a broad US-stock universe before any Wave Rider timing/execution experiment is allowed.

Wave Rider logic is not used anywhere in this validation. Existing WR infrastructure may be reused only for public market-data retrieval / BID-ASK execution plumbing.

## 2. Frozen strategy

Timeframe: 60m regular US equity session.
Direction: LONG ONLY.

Entry signal, evaluated on completed midpoint chart bars:
- RSI length = 10 (Wilder/RMA implementation matching Pine `ta.rsi` construction).
- RSI signal line = SMA(RSI, 10).
- `bullCross = crossover(RSI, RSI_SMA10)`.
- Maintain `crossCount`.
- If RSI > 50: reset `crossCount = 0`.
- If `bullCross` and RSI < 50: increment count.
- Entry signal when the incremented count equals 2.
- Immediately reset count after the entry signal.

Exit signal:
- Pine-compatible SuperTrend ATR length = 10, factor = 2.5.
- Exit when SuperTrend direction flips bearish: `change(direction) > 0` under Pine's `ta.supertrend` sign convention.

No divergence logic. No WR filters. No EMA/CCI/CHOP/news/session-selection filters. No ticker/sector whitelist selected from outcome.

## 3. Frozen execution model

Source: Dukascopy paired M5 BID/ASK quotes.
Chart: midpoint = (BID + ASK) / 2, aggregated to regular-session 60m bars anchored at 09:30 America/New_York. The final regular-session partial bar may be retained so the chart follows the exchange session rather than UTC clock buckets.

Orders are market orders generated on the completed 60m signal bar and executed causally on the next available regular-session M5 open:
- LONG entry = ASK open.
- LONG exit = BID open.
- Midpoint comparator uses midpoint open at the same execution timestamp.

Spread is therefore embedded in executable returns. No synthetic spread is added. No intrabar TP/SL path assumptions are required because the strategy has no bracket stop/target.

If an entry signal occurs while already long, it is ignored (Pine pyramiding default = 0). Exit is processed before any new entry at a shared execution timestamp.

## 4. Frozen universe and dates

Universe: the same 68 US stocks used by the prior 60m execution data pipeline:

AAPL, ADBE, ADI, ADP, ADSK, AEP, ALNY, AMAT, AMD, AMGN, AMZN, AVGO, BKR, CDNS, CMCSA, COST, CPRT, CSCO, CSGP, CSX, CTSH, DXCM, EA, EXC, FANG, FTNT, GILD, GOOG, GOOGL, HON, IDXX, INTC, INTU, ISRG, KHC, LRCX, MAR, MCHP, MDLZ, META, MPWR, MRVL, MSFT, MU, NFLX, NVDA, ODFL, ORLY, PANW, PAYX, PCAR, PEP, PLTR, PYPL, QCOM, REGN, ROST, SBUX, SNPS, TMUS, TSLA, TTWO, TXN, VRTX, WDAY, WDC, WMT, ZS.

Data period: 2022-01-01 through the latest common data available no later than 2026-08-24.
Warm-up may begin 2021-12-01.

### Primary holdout universe

The following five stocks were already observed in the earlier TradingView cross-equity ablation and are excluded from the PRIMARY promotion gate:
- AAPL
- AMZN
- MSFT
- NVDA
- TSLA

Primary holdout = the remaining 63 stocks. Their RSI-E2+ST executable outcomes have not been inspected before this preregistration.

All-68 results are secondary diagnostics only.

## 5. Frozen metrics

Returns are equal-notional fractional trade returns, not WR R-multiples.

For primary holdout and all-68 report:
- closed trade count
- profitable trade rate
- profit factor = sum positive returns / abs(sum negative returns)
- arithmetic mean trade return (bps)
- median trade return (bps)
- midpoint PF / mean trade return
- actual BID/ASK PF / mean trade return
- per-symbol PF, mean return, trade count
- positive-symbol fraction, where positive means cumulative equal-notional trade return > 0
- median per-symbol PF (symbols with at least 5 closed trades)
- yearly aggregate PF and mean return for 2022–2026
- pre-2026 aggregate PF and mean return
- median entry and exit spread bps

No portfolio compounding metric is a primary gate because positions across symbols may overlap.

## 6. Primary promotion gate — frozen before results

`PASS_EXECUTABLE_EXTERNAL_ALPHA = true` only if ALL of the following hold on the 63-stock primary holdout:

1. Coverage >= 60 of 63 holdout symbols with usable paired BID/ASK history.
2. Closed trades >= 300.
3. Actual BID/ASK profit factor >= 1.20.
4. Actual arithmetic mean trade return >= +10 bps.
5. Midpoint profit factor >= 1.25 and midpoint mean trade return > 0.
6. Positive-symbol fraction >= 60%.
7. Median per-symbol PF >= 1.05 among symbols with >= 5 trades.
8. Pre-2026 actual PF >= 1.10.
9. At least 2 of calendar years 2024, 2025, 2026 have actual PF > 1.05.

The gate cannot be changed after validation results are visible.

## 7. Interpretation rules

If PASS:
- Promote only to `EXECUTABLE_EXTERNAL_ALPHA_CANDIDATE`.
- Then a separate preregistered matched A/B may compare base external-alpha executions vs WR timing/execution overlays.
- PASS does not imply production deployment; prospective/forward validation remains desirable.

If FAIL:
- Do not combine with WR.
- Do not rescue by tuning RSI length, SMA length, threshold 50, cross count, SuperTrend ATR/factor, timeframe, sector/ticker whitelist, or post-hoc regime filters from this sample.
- Any materially changed mechanism must be a new lineage with its own preregistration.

## 8. Known caveat frozen in advance

This is a broad executable historical holdout, not a prospective future-data trial. Five previously inspected US names are explicitly excluded from the primary gate to reduce leakage. The remaining 63-symbol breadth and real BID/ASK execution are the decisive historical validation layer for whether the candidate is strong enough to justify a subsequent WR matched A/B.
