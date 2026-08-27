# WR 30m Hyperliquid — Full-History Counterfactual Cost Overlay

Date: 2026-08-24

## Evidence class
- Post-result diagnostic; NOT preregistered OOS evidence.
- No WR parameter changes, no symbol selection by PnL.
- Uses frozen WR 30m Dukascopy-midpoint results from run 32657035483, restricted to the 19 symbols that currently overlap live HIP-3 markets in run 32671347873.
- Applies current Hyperliquid fee/L2 economics from run 32671347873 as a counterfactual historical cost overlay.
- This is NOT historical Hyperliquid execution and does not assume historical L2 was equal to today's book.

## Aggregate
- Overlap symbols: 19
- WR trades: 627
- Gross WR R before venue friction: +1.3666R
- Tier-0 fee-only proxy (0.9 bps/fill × 2 fills): -15.5275R
- Fee + current live L2 $1k proxy: -59.0269R
- Fee + current live L2 $10k proxy: -125.2693R
- Gross-positive symbols: 8/19
- Net-positive symbols at $1k proxy: 7/19
- Net-positive symbols at $10k proxy: 6/19
- Cost sensitivity: 9.3856R lost per 1 bps of uniform round-trip friction across the overlap sample.
- Break-even all-in round-trip friction: 0.1456 bps.
- Current sensitivity-weighted all-in $1k proxy: 6.4347 bps.

## Interpretation
- The overlap universe is essentially flat before venue costs, so execution cannot rescue it.
- Hyperliquid tier-0 fees alone are far above the historical break-even friction.
- Paid S3 historical L2 is therefore not justified as the next gate for this candidate: even an unrealistically favorable assumption of zero spread/slippage but current fee-only economics turns the sample negative.
- S3 should only be reconsidered if a materially different execution model is proposed, e.g. predominantly maker entries/exits with demonstrated fill probability and no adverse-selection assumption.

## Per-symbol

| Symbol | Trades | Gross R | All-in bps $1k | Net R $1k | All-in bps $10k | Net R $10k |
|---|---:|---:|---:|---:|---:|---:|
| AAPL | 27 | -6.968 | 2.123 | -8.196 | 4.166 | -9.376 |
| AMAT | 25 | +7.179 | 13.225 | +2.214 | 24.810 | -2.136 |
| AMD | 40 | -3.525 | 3.262 | -4.891 | 5.334 | -5.758 |
| AMZN | 34 | -6.227 | 3.712 | -8.077 | 6.453 | -9.443 |
| AVGO | 38 | -0.838 | 11.713 | -8.101 | 13.294 | -9.080 |
| COST | 31 | -8.641 | 20.553 | -24.719 | 63.805 | -58.554 |
| GOOGL | 33 | -4.521 | 2.896 | -6.492 | 4.228 | -7.399 |
| INTC | 38 | +3.055 | 3.475 | +1.174 | 4.493 | +0.622 |
| LRCX | 27 | +7.394 | 12.019 | +2.545 | 17.801 | +0.212 |
| META | 33 | -3.851 | 4.334 | -6.439 | 5.276 | -7.001 |
| MRVL | 28 | -0.495 | 3.409 | -1.407 | 5.617 | -1.998 |
| MSFT | 31 | +0.594 | 3.457 | -1.630 | 4.166 | -2.086 |
| MU | 33 | +4.693 | 1.904 | +3.947 | 3.031 | +3.506 |
| NFLX | 37 | -0.648 | 4.268 | -2.845 | 8.385 | -4.964 |
| NVDA | 35 | -2.949 | 2.259 | -3.976 | 2.592 | -4.128 |
| PLTR | 41 | +5.339 | 4.557 | +3.576 | 6.161 | +2.955 |
| QCOM | 27 | -2.029 | 10.380 | -6.427 | 33.510 | -16.229 |
| TSLA | 37 | +5.280 | 2.132 | +4.384 | 3.554 | +3.786 |
| WDC | 32 | +8.524 | 5.665 | +6.333 | 17.380 | +1.801 |

## Cost formula
- Frozen baseline cost sensitivity for each symbol is derived from its 0 bps vs 1 bps WR 30m result.
- Hyperliquid all-in proxy bps = 2 × tier-0 taker fee per fill + current round-trip L2 crossing/depth bps.
- Net R = gross R - (R sensitivity per 1 bps × all-in proxy bps).

## Source lineage
- WR 30m baseline run: 32657035483
- Hyperliquid HIP-3 validation run: 32671347873
- Draft research PR: #193
