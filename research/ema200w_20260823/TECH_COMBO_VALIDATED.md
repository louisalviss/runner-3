# EMA200W technical combo validation — 2026-08-23

Standalone strategy research; independent from Wave Rider.

## Best exploratory technical setup

Rules:
- S&P 500 point-in-time member.
- First EMA200W touch after at least 52 weeks without a prior touch.
- EMA200W rising.
- 52-week drawdown at signal between -10% and -25%.
- Causal entry at prior completed week's EMA200W.

Results:

| Horizon | N | Median return | Win rate | Mean matched excess | Median matched excess | Beat matched control |
|---|---:|---:|---:|---:|---:|---:|
| 13w | 861 | 7.00% | 69.80% | 3.34% | 1.61% | 56.02% |
| 26w | 857 | 8.12% | 68.03% | 2.01% | 0.95% | 52.54% |
| 52w | 844 | 13.95% | 68.25% | 3.14% | 3.35% | 55.47% |

Matched control uses same signal week, PIT S&P 500 membership, same setup-state filter, similar 52-week drawdown (+/-5pp, widened to +/-10pp if needed), excludes simultaneous EMA touches.

## Market filter

Adding SPY > its own EMA200W:

| Horizon | N | Median return | Win rate | Mean matched excess | Median matched excess | Beat matched control |
|---|---:|---:|---:|---:|---:|---:|
| 13w | 764 | 7.01% | 70.42% | 3.41% | 1.69% | 56.35% |
| 26w | 760 | 8.18% | 68.68% | 1.74% | 0.95% | 52.53% |
| 52w | 747 | 14.17% | 68.01% | 3.80% | 4.05% | 56.83% |

Requiring SPY EMA200W itself to also be rising adds essentially no incremental value.

## Stability warning

The narrow -10% to -25% drawdown band was selected from a small exploratory sweep, so selection bias / multiple-testing risk exists. Historical era breakdown is not uniformly strong: the setup is much weaker around 2004-2009, and the 52-week beat-control rate also weakens in 2020-2024. Treat this as a hypothesis to freeze and validate OOS, not production-ready proof.

## Current decision

The best price-only candidate is:

`first EMA200W touch >=52w + EMA200W rising + drawdown 10-25% + SPY above EMA200W`

13-week horizon is the cleanest candidate by win rate and matched-control behavior. Fundamental-quality validation is a separate PIT test and should not be merged into the production rule until its independent result is available.
