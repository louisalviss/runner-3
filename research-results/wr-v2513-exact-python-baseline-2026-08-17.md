# WR v2.5.13 Exact-Python Parity Baseline — 2026-08-17

**This is NOT TradingView parity.** It is the current output of `reference_verify_v2513_exact.py` and exists only as the Python side of the source-of-truth comparison.

GitHub Actions run: `31994261915`

Exact reference blob:
`72c3d36bc41e9efefb085bf010c7f5ba0abc8e30`

Frozen report window:
- 5m
- Start `2025-01-01T00:00:00Z`
- End `2026-08-15T00:00:00Z` exclusive
- engine warmup/state begins before report start
- report inclusion by signal-candle close
- carry-out after report End allowed

## BNBUSDT

Current exact-Python output:
- Trades: **401**
- Total R: **+137.7855617671R**
- Avg R: **+0.3436048922R**
- Win rate: 40.8978%
- PF: 1.56373
- Pivot plateau diagnostics: 243 high ties / 228 low ties

Old Python-reference target previously presented for manual verification:
- 400 trades
- +145.3855617671R (displayed as +145.39R)

Difference from old lineage:
- **+1 trade**
- **-7.60R** approximately

## TRXUSDT

Current exact-Python output:
- Trades: **465**
- Total R: **+136.4266046339R**
- Avg R: **+0.2933905476R**
- Win rate: 39.7849%
- PF: 1.44613
- Pivot plateau diagnostics: 618 high ties / 479 low ties

Old Python-reference target previously presented for manual verification:
- 448 trades
- +136.3301134059R (displayed as +136.33R)

Difference from old lineage:
- **+17 trades**
- Total R changes by only about **+0.10R**.

That TRX result demonstrates why aggregate Total R can appear to agree while the trade sequence is materially different. Aggregate agreement is therefore not accepted as parity evidence.

## Data-boundary audit

The parity pack attempted carry-out data through 2026-08-17; daily archives for 2026-08-16/17 were not yet present in that run. This does not show an unresolved included position in the current run: exact-reference diagnostics have `pending_filled == TP + SL + EMA + NEWS + SESSION` for both symbols, so every filled position processed by the engine was closed in the available data.

## Next required input

A normalized one-row-per-closed-trade TradingView WINDOW REPORT sequence for each frozen symbol is still absent from Dropbox/ChatGPT Library. The existing `wave_rider_5m_manual_verification_pack.md` contains **targets/instructions**, not an executed PASS record.

Once a TradingView sequence is available, compare with:

`wave-rider-verify/tv_trade_diff.py`

The comparator fails on the first divergence and reports surrounding Python/TradingView trades. No full-universe rerun is permitted before zero divergence on both BNBUSDT and TRXUSDT.
