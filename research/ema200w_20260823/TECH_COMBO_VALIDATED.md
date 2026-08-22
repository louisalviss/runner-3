# EMA200W technical combo validation — 2026-08-23

Standalone strategy research; independent from Wave Rider.

## Best simple price-state setup

Rules:
- S&P 500 point-in-time member.
- First EMA200W touch after at least 52 weeks without a prior touch.
- EMA200W rising.
- Current 52-week drawdown no worse than -20% (`DD52 >= -20%`).
- Causal entry at prior completed week's EMA200W.

This simpler one-sided threshold was preferred over the initially discovered -10% to -25% band because performance improves smoothly as deep drawdowns are excluded; the lower -10% bound adds little and is unnecessarily fitted.

### Full usable history

| Horizon | N | Median return | Win rate | Mean matched excess | Median matched excess | Beat matched control |
|---|---:|---:|---:|---:|---:|---:|
| 13w | 470 | 7.9% | 72.1% | 2.8% | 2.9% | 59.7% |
| 26w | 468 | 8.3% | 69.9% | 2.4% | 0.9% | 51.9% |
| 52w | 462 | 15.0% | 71.4% | 3.5% | 2.3% | 53.5% |

Matched control uses same signal week, PIT S&P 500 membership, same setup-state filter, similar 52-week drawdown (+/-5pp, widened to +/-10pp if needed), excluding simultaneous EMA touches.

### 2015-2024 robustness slice

Not a clean untouched OOS because the rule family was explored on the full history; use only as a temporal robustness check.

| Horizon | N | Median return | Win rate | Mean matched excess | Median matched excess | Beat matched control |
|---|---:|---:|---:|---:|---:|---:|
| 13w | 233 | 8.7% | 76.4% | 4.0% | 3.4% | 63.1% |
| 26w | 231 | 9.3% | 74.0% | 3.7% | 3.9% | 56.8% |
| 52w | 225 | 19.1% | 79.1% | 9.3% | 7.9% | 63.6% |

### Earlier-history check

Pre-2015 at 13w: N=237, win 67.9%, median return 6.7%, median matched excess 1.6%, beat matched 56.4%. At 52w the setup is not stable: beat matched falls below 50%. This is why 13w is the primary candidate.

## SPY regime filter

Adding `SPY > SPY EMA200W` barely changes 13w raw win rate (72.3% vs 72.1%) and only modestly lifts beat-control (60.5% vs 59.7%). It reduces sample size. Therefore it is optional, not core.

## Drawdown relationship

For first-touch + rising-EMA events, outcomes deteriorate as the stock is deeper below its 52-week high. Examples at 13w: below -50% drawdown ~37% win; -40% to -35% ~59%; -25% to -20% ~67%; -20% to -15% ~71%. This supports the interpretation that the useful filter is avoiding structurally weak/falling-knife names, rather than a magical EMA level.

## Current decision

Best price-only candidate:

`first EMA200W touch after >=52w + EMA200W rising + DD52 >= -20%`

Primary horizon: 13 weeks.

This now shows a material matched-control advantage, unlike raw EMA200W touch. It is still an exploratory result because the threshold was selected after inspecting several variants; freeze the rule and run a genuinely untouched OOS/walk-forward validation before production.

Fundamental-quality validation remains a separate PIT test and should not be merged into the production rule until independently validated.
