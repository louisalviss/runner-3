# WR v2.5.13 Parity — Confirmed Pine `time_close` Input Fix — 2026-08-17

## Status

Parity remains **BLOCKED**. This note records a confirmed Python-input semantic bug discovered after replacing the old full-universe reference lineage.

## Bug

Binance kline archives encode bar close time as `interval_end - 1 ms` (for example a 5m bar closes in the archive at `23:39:59.999`). Pine v2.5.13 uses the chart's exact `time_close` in:

- WINDOW REPORT inclusion;
- session no-entry/forced-exit cutoffs;
- news lockout/forced-exit cutoffs.

For a time-based 5m TradingView chart, the strategy arithmetic is based on the exact scheduled close boundary (for example `23:40:00.000`).

Because Pine explicitly tests expressions such as `tc + chartMs >= exitCutoff`, preserving Binance's `-1 ms` convention can delay a cutoff by an entire chart candle, not merely change a displayed timestamp.

## Falsification test

A raw-vs-Pine-close sensitivity was run on the same exact engine and OHLC sequence, changing only bar close timestamp from the Binance archive value to:

`time_close = open_time + timeframe`

### BNBUSDT 5m

Raw archive-close input:
- 401 trades
- +137.7855617671R
- 3 SESSION exits

Pine-time_close-normalized input:
- 401 trades
- **+138.4048561945R**
- 5 SESSION exits

First economic divergence: trade #18.
- Same SHORT signal/entry/stop/target.
- Raw model exits SESSION at `23:44:59.999`, price 722.04, `-0.472727R`.
- Pine-close-normalized model exits SESSION at `23:40:00.000`, price 721.22, `+0.272727R`.

### TRXUSDT 5m

Raw archive-close input:
- 465 trades
- +136.4266046339R

Pine-time_close-normalized input:
- **461 trades**
- **+136.1259552833R**

First economic divergence: trade #24.
- Same SHORT signal/entry/stop/target.
- Raw model exits SESSION at `23:44:59.999`, price 0.22439, `+0.096970R`.
- Pine-close-normalized model exits SESSION at `23:40:00.000`, price 0.22385, `+0.424242R`.

This proves the `-1 ms` convention changes execution state and later trade count.

## Fix architecture

Do not mutate raw Binance OHLC files. Preserve source data and normalize only at the TradingView-parity boundary.

Added:

- `wave-rider-verify/reference_v2513_tv_adapter.py`
  - exact core remains `reference_verify_v2513_exact.py`;
  - adapter converts time-based bars to Pine `time_close = open + timeframe` before report/session/news logic.
- `formal-tests/wr_v2513_tv_parity_pack.py`
  - routes BNB/TRX parity exports through that adapter and records adapter blob provenance.

Pinned lineage for the next TV comparison:

- exact core blob: `72c3d36bc41e9efefb085bf010c7f5ba0abc8e30`
- TV parity adapter blob: `57b67ff2795d4aab97494f01a6398ffe3118699b`

## Current Python-side targets after the confirmed fix

These are **NOT TradingView-confirmed**. They are only the current Python side that must now be compared trade-by-trade against TradingView WINDOW REPORT.

- BNBUSDT 5m: **401 trades / +138.4048561945R**
- TRXUSDT 5m: **461 trades / +136.1259552833R**

The old 400/+145.39 and 448/+136.33 targets remain invalid as TradingView parity evidence.

## Next hard gate

A TradingView executed closed-trade sequence for the frozen WINDOW REPORT is still required. The connected Dropbox/ChatGPT Library contains the Manual Verification Pack and Pine source but no executed BNB/TRX PASS record or trade export.

When that sequence exists, use `wave-rider-verify/tv_trade_diff.py` and fix only the first divergence until both BNB and TRX have zero ordered trade divergence. No full-universe/family/forward rerun before then.
