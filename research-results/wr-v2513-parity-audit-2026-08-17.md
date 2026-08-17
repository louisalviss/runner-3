# Wave Rider v2.5.13 Parity Audit — 2026-08-17

## Status

**PARITY BLOCKED.** TradingView/Pine v2.5.13 WINDOW REPORT is the source of truth. No downstream full-universe, family-selection, holdout, or forward conclusion may be promoted until trade-by-trade parity is proven.

Machine-readable gate: `wave-rider-verify/PARITY_STATUS.json`.

## Confirmed pipeline defect

The legacy full-universe audit lineage was not based on the exact v2.5.13 parity implementation:

- `wave-rider-verify/reference_verify.py` blob: `2ba5f66d33e2e483a4c669c95f3b97778c80fcd0`
- `wave-rider-verify/reference_verify_v2513_exact.py` blob at incident discovery: `72c3d36bc41e9efefb085bf010c7f5ba0abc8e30`
- full-universe audit pinned the old `2ba5f66...` implementation.

The exact implementation exists specifically to close Pine/TradingView semantic gaps, including:

1. `ta.pivothigh` / `ta.pivotlow` plateau semantics;
2. the four embedded v2.5.13 news timestamps;
3. `run_window_exact()` report semantics.

## Circular verification defect

`wave-rider-full-universe/full_universe_audit.py` contains hard-coded BNB/TRX expected Python metrics and checks fresh Python output against those expected Python metrics.

That is useful as a regression/self-consistency test, but it is **not independent TradingView parity evidence**.

Therefore the prior statement that the full-universe runner was “verified against TradingView” is withdrawn.

## WINDOW REPORT source-of-truth semantics

Canonical Pine WINDOW REPORT behavior:

- Start/End do not gate signals, pending state, orders, exits, sizing, or production equity.
- The window is reporting-only.
- Inclusion key is the **signal candle close time** in `[Start, End)`.
- State before Start continues into the window.
- A qualifying pre-End signal may fill or exit after End.
- Out-of-window activity still runs and affects state/equity.

Frozen parity window:

- symbols: `BNBUSDT`, `TRXUSDT`
- chart: `BINANCE:<SYMBOL>.P`
- timeframe: `5m`
- report start: `2025-01-01T00:00:00Z`
- report end: `2026-08-15T00:00:00Z` exclusive
- commission: 0
- slippage: 0
- Bar Magnifier: OFF

## Suspended conclusions

Until parity PASS:

- BNB5 `400 / +145.39R` and TRX5 `448 / +136.33R` are classified only as historical Python-reference targets, **not TradingView-confirmed results**.
- 757-symbol full-universe conclusions are suspended.
- Post-friction breadth/ratios from that lineage are suspended as strategy evidence.
- The 14-symbol frozen 10m family selected from that audit is suspended.
- Its holdout is suspended.
- Forward-count/forward observations using the `2ba5f66...` lineage are suspended.

Reusable assets are retained: raw Binance data, download/cache infrastructure, audit/reporting framework, and friction model.

## Remediation protocol

1. Export exact-reference BNB5 and TRX5 Python trade sequences using `reference_verify_v2513_exact.py` + `run_window_exact()`.
2. Obtain TradingView WINDOW REPORT closed-trade sequences for the exact same chart/settings/window.
3. Compare ordered trades with `wave-rider-verify/tv_trade_diff.py`.
4. Match at minimum: signal close, side, entry time, planned entry, exit time, exit price, exit reason, Canon R; stop/target where available.
5. On FAIL, inspect the **first divergence only** and its surrounding bars/state.
6. Fix the implementation cause, rerun from trade #1, and repeat.
7. Do not accept aggregate trade count / Total R as a substitute for sequence parity.
8. Set `PARITY_STATUS.json` to `PASS` only after **zero divergence on both BNBUSDT and TRXUSDT**.
9. Only after PASS: regenerate full-universe outputs from the corrected exact lineage, then redo family selection and untouched validation from scratch.

## Workflow safety changes

The following workflows were changed to manual-only and hard-gated by `wave-rider-verify/assert_parity_gate.py`:

- `.github/workflows/wave-rider-full-universe-audit.yml`
- `.github/workflows/wr-full-universe-5m.yml`
- `.github/workflows/wave-rider-family-holdout.yml`
- `.github/workflows/wave-rider-forward-count.yml`

The exact parity-investigation workflow remains enabled because it is the remediation path, not a downstream promotion path.
