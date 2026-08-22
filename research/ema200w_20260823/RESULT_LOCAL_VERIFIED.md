# EMA200W standalone US-stock backtest — verified local run

Date: 2026-08-23

## Scope

- Price source: FINSABER S&P 500 historical price archive, 2000-01-03 through 2024-12-31, including delisted symbols.
- Point-in-time S&P 500 membership: fja05680/sp500 historical membership table.
- Weekly rows after aggregation: 984,281.
- Historical price symbols: 1,017; symbols matching PIT S&P 500 membership: 919.
- Causal touch rule: prior completed week's 200-week EMA is the executable limit level; current week's adjusted high/low must trade through it.
- Adjusted OHLC reconstructed using adjusted_close / raw close.
- Forward horizons: 13, 26, 52, 104 weeks.
- Matched control: same signal week, PIT S&P 500 members, similar 52-week drawdown (+/-5 percentage points, widened to +/-10 only if needed), excluding simultaneous touches. Refined variants also match the corresponding pre-signal state filter.

## Core EMA200W touch

| Horizon | N | Median return | Win rate | Mean matched excess | Median matched excess | Beat matched |
|---|---:|---:|---:|---:|---:|---:|
| 13w | 17,733 | 3.80% | 59.9% | 0.29% | -0.04% | 49.8% |
| 26w | 17,549 | 5.78% | 60.7% | 0.34% | -0.09% | 49.8% |
| 52w | 17,084 | 10.16% | 63.0% | 0.80% | -0.35% | 49.4% |
| 104w | 15,966 | 20.57% | 68.9% | 2.27% | -1.13% | 48.8% |

Interpretation: positive raw returns mostly reflect long-run equity drift / recovery after drawdown. The median event does not outperform a same-week, same-drawdown control; fewer than half of base EMA-touch events beat the matched control at 52 and 104 weeks. Positive mean excess is right-skewed by large winners rather than a broad event-level advantage.

## Cleaner setup: first touch after 52 weeks with no prior EMA touch

| Horizon | N | Median return | Win rate | Mean matched excess | Median matched excess | Beat matched |
|---|---:|---:|---:|---:|---:|---:|
| 13w | 2,490 | 5.31% | 63.5% | 1.79% | 0.15% | 50.7% |
| 26w | 2,476 | 5.56% | 61.4% | 1.33% | -0.42% | 49.0% |
| 52w | 2,435 | 10.88% | 63.7% | 2.36% | 0.42% | 50.7% |
| 104w | 2,346 | 22.10% | 68.7% | 4.89% | 0.75% | 50.8% |

The 13-week version is the only setup with a clearly interesting short-horizon matched-excess signal in this exploratory sweep. It is still regime-dependent and is not production-ready.

## Era stability, 52-week horizon

Base EMA touch:
- 2004-2009: median +0.10%, win 50.1%, matched excess mean -1.12%, matched median -1.62%, beat matched 47.1%.
- 2010-2019: median +12.39%, win 66.7%, matched excess mean +0.41%, matched median -0.07%, beat matched 49.9%.
- 2020-2024: median +17.64%, win 71.7%, matched excess mean +3.64%, matched median +1.08%, beat matched 51.5%.

First touch after 52 weeks:
- 2004-2009: median -4.02%, win 45.4%, matched median -1.79%, beat matched 46.2%.
- 2010-2019: median +14.98%, win 69.3%, matched median +1.72%, beat matched 52.7%.
- 2020-2024: median +19.21%, win 73.4%, matched median +1.76%, beat matched 53.3%.

Conclusion: substantial regime dependence. The setup fails the simple definition of a stable all-regime standalone edge.

## Drawdown after entry

For the base EMA-touch sample over the following 52 weeks:
- median adverse excursion from entry: about -15.4% using subsequent weekly lows;
- 40.96% of events later suffered at least a -20% drawdown;
- 17.77% later suffered at least a -40% drawdown;
- 10th-percentile adverse excursion: about -51.9%.

EMA200W therefore should not be treated as a hard support / low-risk entry by itself.

## EMA vs SMA

200-week SMA touch at 52 weeks:
- N 15,210;
- median return +9.80%;
- win rate 62.7%;
- mean matched excess +0.66%;
- median matched excess -0.79%;
- beat matched 48.7%.

EMA and SMA results are economically similar. There is no evidence here that the exponential construction itself is the source of the effect.

## SPY comparison

For base EMA-touch events at 52 weeks, median excess return versus SPY was negative and the event beat SPY less than half the time in both SPY-above-200W-EMA and SPY-below-200W-EMA regimes. A simple SPY 200W-EMA market filter did not repair the instability seen in 2004-2009.

## Decision

Reject `buy any S&P 500 stock at a 200-week EMA touch` as a standalone production strategy.

Keep only as an exploratory location/filter. The strongest follow-up hypothesis is `first touch after >=52 weeks without a touch`, especially a 13-week mean-reversion horizon, then freeze the rule and validate out-of-sample with an institutional-quality survivorship/delisting dataset before considering deployment.

## Caveats

- FINSABER includes delisted symbols, but this is not CRSP-grade delisting-return validation.
- When an ended listing lacks a requested future horizon, final observed adjusted price is used as a practical proxy; active names beyond the dataset end are censored.
- Multiple variants were explored, so the best-looking row is subject to multiple-testing / selection bias.
- This is an event-study / edge-validation backtest, not yet a fully specified portfolio simulation with position sizing, turnover and capital constraints.
