# Wave Rider checkpoint — 2026-08-22 23:59 +07

## Canonical validation order

FREEZE → truly unseen forward OOS → broker-realistic execution → portfolio construction + block Monte Carlo → paper 1–3 months → small capital.

Historical execution and portfolio diagnostics are supporting evidence only until the unseen forward OOS gate passes.

## Market-state OOS #2

- Verdict: `PASS_STATE_SELECTION`
- Universe: 68 US stocks
- Total feature/trade rows: 19,683
- No symbol identity feature
- Features: `atr_bps`, `atr_ratio_14_50`, `range_atr`, `body_atr`, `gap_atr`, `rv20_bps`, `trend20_atr`, `efficiency20`, `location20`, `session_frac`, `tf10`
- Model: HistGradientBoostingRegressor(max_iter=100, learning_rate=0.05, max_depth=2, min_samples_leaf=50, l2_regularization=10.0, random_state=7)
- Walk-forward folds: 2024 / 2025 / 2026, training only on prior years
- Canonical selector: training-prediction q70
- Selected canonical trades: 3,657
- Net @1bps: 2024 +740.9R; 2025 +728.9R; 2026 +368.8R; total +1,838.6R
- Net @2bps total: +1,663.7R
- Yearly PF roughly 2.05 / 2.15 / 2.10

## Execution proxy

Finalizer run: `32585837264`
Artifact: `wr-market-state-execution-finalizer`, artifact ID `9479266662`

Parity:
- canonical rows: 3,657
- execution rows: 19,683
- matched selected: 3,657
- missing selected: 0
- max |R diff|: 4.440892098500626e-16
- max |net1 diff|: 8.881784197001252e-16
- max |net2 diff|: 4.440892098500626e-16
- parity PASS

Observed round-trip spread:
- median 5.786 bps
- p95 20.700 bps
- p99 32.152 bps

Normal scenario:
- N 3,653
- +669.03R
- PF 1.2963
- max DD -29.75R

Stress scenario:
- N 3,653
- +461.99R
- PF 1.1955
- max DD -39.88R

Extreme scenario:
- N 3,653
- +137.70R
- PF 1.0545
- max DD -85.11R

Verdict: `PASS_EXECUTION_PROXY`; extreme survival = true.

Important: this is Dukascopy observed BID/ASK execution proxy, not yet the final named-broker execution proof. Final broker-specific quote/commission/slippage/swap testing remains after forward OOS.

## Portfolio diagnostic

- Historical portfolio diagnostic PASS/supportive.
- 3,657 trades.
- Max concurrency 11.
- Median absolute correlation about 0.046.
- p95 absolute correlation about 0.117.
- Top five symbols about 13.6% of total |R|.
- Max 5 positions: about +1,758.8R @1bps, PF 2.07, DD -17.6R.
- Monte Carlo should use day/episode block bootstrap, not naive trade shuffling.

## Forward unseen OOS — Gate 1

Primary holdout is frozen as:
- holdout start: `2026-08-22T00:00:00Z`
- holdout end: `2026-12-31T23:59:59Z`
- first live US session after freeze: 2026-08-24
- no retraining / no tuning
- universe fixed at the same 68 US stocks
- timeframes 5m and 10m
- selector fixed to prediction > frozen training-prediction q70
- target `net_1bps`
- performance hidden from routine status during holdout to reduce peeking/tuning pressure
- append-only ledger: previously recorded rows may not change

Preregistered primary review criteria:
- review not before 2027-01-01 UTC
- at least 100 selected trades
- net 1bps R > 0
- PF @1bps >= 1.20
- max DD >= -20R
- at least 15 distinct symbols
- max single-symbol |R| share <= 25%
- annualized return is not a primary gate

Implementation added on `main`:
- `wave-rider-verify/wr_market_state_freeze.py`
- `.github/workflows/wr-market-state-freeze.yml`
- frozen forward collector/finalizer + append-only ledger flow
- `.github/workflows/wr-market-state-forward-daily.yml`
- sklearn/joblib runtime pinned for freeze/replay reproducibility
- freeze workflow serialized to avoid concurrent model generation/push races

## Current state at checkpoint

The forward-OOS infrastructure is implemented, but the final frozen model files are **not yet present on `main`** at the latest check (`wave-rider-verify/frozen-market-state/` returned 404). Therefore Gate 1 is **not yet ARMED**. Do not count any forward sample until the frozen model + manifest have been persisted and verified.

Next action:
1. Verify the one-time freeze workflow completed.
2. Confirm frozen model + manifest exist on `main` and record model hash + q70 threshold.
3. Only then mark Gate 1 `ARMED` and let daily forward ledger accumulate unseen samples.
4. Do not modify model/features/universe/threshold during the holdout.
