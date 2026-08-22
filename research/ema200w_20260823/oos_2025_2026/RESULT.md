# EMA200W frozen-rule true OOS — 2025–2026

Rule frozen before reading OOS: `first EMA200W touch after >=52 weeks without a prior touch + EMA200W rising + DD52 >= -20%`; causal entry at prior completed week's EMA200W; primary horizon 13 weeks.

## Data

- Independent price source: `paperswithbacktest/Stocks-Daily-Price`.
- Daily price coverage loaded: 2018-01-05 to 2026-08-07.
- OOS starts: 2025-01-01.
- PIT membership source: fja05680/sp500 start/end history.
- Historical member symbols represented in price data: 596.
- OOS expected PIT member symbols: 538; with at least one OOS price row: 532; completely missing: 6.
- Adjusted OHLC is reconstructed using `adj_close / close`, matching the discovery implementation.

## Results

| Hold | N | Win rate | Median return | Mean return | Median matched excess | Beat matched | Mean excess 95% cluster-bootstrap CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 13w | 30 | 66.67% | 5.17% | 5.96% | -2.49% | 46.67% | -6.22% to 4.88% |
| 26w | 24 | 70.83% | 6.08% | 6.34% | -4.12% | 29.17% | -7.99% to 9.86% |
| 52w | 18 | 72.22% | 20.98% | 17.52% | 9.26% | 61.11% | -5.21% to 27.59% |

## 13-week pre-registered gates

- Win rate >=65%: PASS (66.67%).
- Median return >0: PASS (5.17%).
- Median matched excess >=+1.5%: FAIL (-2.49%).
- Beat matched-control >=55%: FAIL (46.67%).
- Overall frozen gate: **FAIL**.
- Top-5 winners as share of total positive 13w return: 49.43% (concentration diagnostic, not a gate).

## By calendar year

| Year | Hold | N | Win | Median return | Median excess | Beat matched |
|---:|---:|---:|---:|---:|---:|---:|
| 2025 | 13w | 24 | 66.67% | 6.78% | -0.31% | 50.00% |
| 2025 | 26w | 24 | 70.83% | 6.08% | -4.12% | 29.17% |
| 2025 | 52w | 18 | 72.22% | 20.98% | 9.26% | 61.11% |
| 2026 | 13w | 6 | 66.67% | 3.10% | -7.25% | 33.33% |
| 2026 | 26w | 0 | NA | NA | NA | NA |
| 2026 | 52w | 0 | NA | NA | NA | NA |

## Observable cutoffs

- 13w outcomes are fully observable only for signals through approximately 2026-05-08; later signals are retained in `events.csv` but censored for that horizon.
- 26w outcomes are fully observable only for signals through approximately 2026-02-06; later signals are retained in `events.csv` but censored for that horizon.
- 52w outcomes are fully observable only for signals through approximately 2025-08-08; later signals are retained in `events.csv` but censored for that horizon.

## Caveats

- This is independent price data, but not CRSP/Sharadar-grade security-master validation. Missing historical/delisted symbols are explicitly reported.
- Dividend-adjusted history can be retroactively rescaled by later distributions; this matches the discovery implementation but is not a perfect point-in-time adjustment model.
- 2026 has a shorter observable window and therefore fewer completed 13-week signals.
- No thresholds were changed after reading these OOS results. Any later rule change must be treated as a new research hypothesis, not as part of this OOS test.

## Decision

The frozen rule fails at least one previously stated OOS gate. Do not promote it to production. Preserve this result and treat any modification as a new hypothesis requiring a new untouched validation set.
