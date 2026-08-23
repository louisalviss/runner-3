# Earnings Surprise + Price Underreaction — Frozen Backtest

Status: exploratory causal-layer test; not production.

## Frozen hypothesis
- Strong beat: EPS surprise >= +10%.
- Underreaction: strong beat + 2-session price reaction <= +3%.
- Reaction: previous close -> close of second trading session on/after announcement date.
- Entry: following trading session adjusted open.
- Primary: 13w (65 sessions); 4w/8w secondary.
- Discovery: 2010-2016; validation: 2017-2024.

This tests the freely available surprise + price-reaction layer only. Historical PIT analyst revisions/guidance are NOT present in this public dataset, so they are intentionally not claimed or synthesized.

## Coverage
- Raw earnings rows with numeric surprise, 2010-2024: 7,565
- Usable PIT S&P500 events with prices: 6,011
- Symbols: 117
- Event range: 2010-01-14 to 2024-10-22

## Results
| Split | Rule | Hold | N | Matched | Win | Median ret | Median excess | Beat matched | Mean excess CI95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| discovery | strong_beat | 4w | 666 | 643 | +56.01% | +0.80% | -0.40% | +47.59% | [-0.58%, +0.50%] |
| discovery | strong_beat | 8w | 666 | 643 | +60.36% | +2.76% | +0.33% | +51.17% | [-0.14%, +1.48%] |
| discovery | strong_beat | 13w | 666 | 643 | +61.41% | +4.27% | -1.02% | +47.28% | [-1.47%, +0.99%] |
| discovery | underreaction | 4w | 401 | 343 | +54.61% | +0.49% | +0.12% | +50.44% | [-0.95%, +0.71%] |
| discovery | underreaction | 8w | 401 | 343 | +60.35% | +2.77% | -0.57% | +48.40% | [-1.89%, +0.65%] |
| discovery | underreaction | 13w | 401 | 343 | +63.09% | +4.63% | +0.66% | +52.48% | [-2.13%, +1.44%] |
| validation | strong_beat | 4w | 1065 | 1056 | +57.65% | +0.99% | +0.31% | +51.52% | [-0.64%, +0.53%] |
| validation | strong_beat | 8w | 1065 | 1056 | +58.87% | +2.29% | -0.39% | +48.01% | [-0.58%, +0.86%] |
| validation | strong_beat | 13w | 1057 | 1048 | +62.35% | +3.60% | -0.54% | +48.66% | [-1.07%, +0.96%] |
| validation | underreaction | 4w | 661 | 620 | +56.58% | +0.96% | -0.99% | +45.65% | [-1.43%, +0.07%] |
| validation | underreaction | 8w | 661 | 620 | +59.30% | +2.15% | +0.61% | +52.90% | [-0.34%, +1.56%] |
| validation | underreaction | 13w | 657 | 617 | +62.40% | +3.60% | +0.50% | +52.19% | [-1.56%, +1.19%] |

## Pre-registered validation gate — Underreaction / 13w
- Matched N >= 100: PASS
- Median matched excess > 0: PASS
- Beat matched >= 55%: FAIL
- Mean excess 95% CI lower bound > 0: FAIL
- Overall: FAIL

Decision rule: if validation fails, do not retune the +10% surprise or +3% underreaction thresholds on 2017-2024 and call it validation. Any changed thresholds are a new hypothesis.
