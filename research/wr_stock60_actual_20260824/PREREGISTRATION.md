# Wave Rider US Stocks 60m Actual Execution — Preregistration

Date: 2026-08-24
Status: PREREGISTERED BEFORE OUTCOME

## Research question
Does the frozen canonical Wave Rider v2.5.13 stock engine become economically viable at 60-minute bars when evaluated with executable BID/ASK sides rather than midpoint-only PnL?

This is a timeframe/microstructure hypothesis, not an indicator/filter rescue.

## Frozen engine and universe
- Wave Rider v2.5.13 research substrate.
- Canonical rightmost-tie pivot verifier lineage: commit `27797cf9c4ea0a91b1bc8d62059d052c2c843eb5`.
- Same 68-stock guaranteed-core universe used by prior 10m/15m/30m WR stock research.
- No ticker whitelist based on prior results.
- No RS, CCI, sector, market-regime, news-model, AI, or ML filter added.
- No TP/SL/angle/CHOP/EMA parameter tuning.

## Data / bar construction
- Source: Dukascopy historical BID and ASK M5 bars, same broad source lineage as the prior 30m execution audit.
- Candidate chart bars: midpoint from paired M5 BID/ASK bars, aggregated to 60m.
- Execution path: 12 executable-side M5 bars inside each 60m chart bar.
- Long stop entry/fill: ASK.
- Short stop entry/fill: BID.
- Long exits: BID.
- Short exits: ASK.
- Same-M5 TP+SL ambiguity: conservative SL.
- Gap-through stop entry fills at executable-side open when already beyond the requested trigger.

This is an executable-side M5 replay, not a claim of tick-perfect historical execution.

## Window
- State warmup starts 2021-12-01.
- Reported research window: 2022-01-01 through 2026-08-21, matching prior stock lineage coverage.
- No fit/training parameters exist; chronological slices are diagnostics for temporal stability.

## Primary outputs
Report:
- midpoint trade count and gross R
- actual executable BID/ASK trade count, total R, avg R/trade, PF, win rate, max drawdown R
- Long/Short decomposition
- yearly 2022–2026
- pre-2026 result
- chronological OOS-style yearly slices 2024/2025/2026
- symbol breadth
- median entry and exit spread bps
- midpoint-to-actual R delta

## Standalone 60m PASS gate
`PASS_STANDALONE_60M` requires ALL:
1. actual executable total R > 0
2. actual PF > 1.0
3. actual average R/trade > 0
4. at least 50% of symbols with executable trades have positive total R
5. pre-2026 actual R >= 0
6. at least 2 of the three 2024/2025/2026 yearly slices have positive actual R

If any condition fails, 60m is NOT a deployable standalone WR edge.

## Frozen cost-geometry follow-up eligibility
A separate cost-geometry A/B may be launched only if standalone 60m fails but remains economically borderline.

`COST_GEOMETRY_ELIGIBLE` requires ALL:
1. midpoint gross R > 0
2. actual executable trade count >= 300
3. actual 60m fails the standalone gate
4. EITHER actual PF >= 0.95 OR actual avg R/trade >= -0.02R

If this eligibility gate fails, do not run cost-geometry, sector alignment, AI meta-layer, or further WR rescue filters from this result.

## Anti-rescue rules
After observing the 60m result, do NOT:
- sweep 45m/60m/90m/120m
- change TP/SL or WR internals
- whitelist winning symbols
- retune spread/cost threshold from the result
- add EMA/RSI/CCI/RS filters to rescue this test
- use a single good year as promotion evidence

## Interpretation
- PASS = 60m survives executable-side economics and deserves robustness / cleaner-data confirmation.
- FAIL but COST_GEOMETRY_ELIGIBLE = only the preregistered execution-geometry follow-up is allowed next.
- FAIL and not eligible = retire standalone WR stock alpha without further filter mining.
