# SPMO Top-1 — live tradability / look-ahead audit

## Verdict

**PASSED for the Leto Monday-close implementation.**

The live rule being validated is:

1. S&P 500 Momentum rebalances semi-annually, effective **after the close on the third Friday of March and September**.
2. On the following Monday, obtain SPMO's disclosed portfolio holdings and rank them by portfolio weight.
3. Buy the largest holding at that Monday's close (MOC is the closest practical execution convention).
4. Hold until the next rebalance Monday close; if the same ticker remains Top-1, do not trade.

This convention does not require future information. The Top-1 is knowable before the assumed Monday-close execution.

## Evidence for timing

### Index timing

S&P Dow Jones Indices' `S&P Momentum Indices Methodology` states that S&P 500 Momentum rebalances semi-annually, effective after the close on the third Friday of March and September. It also states that S&P provides pro-forma constituent files before rebalance; these contain the upcoming constituents, weights and index shares. Daily constituent/index-level data are a subscription product.

Implication: institutional/subscriber users can know the upcoming index composition before the Friday effective close. This is stronger than the information actually required for the Leto Monday-close implementation.

### Public ETF holdings — pre-Rule 6c-11 / 2018

PowerShares/Invesco Trust II SEC disclosure states that portfolio holdings were publicly disseminated each business day through financial/news services and publicly accessible Internet websites. Its basket composition file, including security names and share quantities, was publicly disseminated each day before the exchange opened via NSCC. Later Invesco Trust II disclosure explicitly applies this policy to SPMO and states that daily holdings and the pre-open basket were publicly disseminated.

Therefore for the March 2018 rebalance effective after the Friday 2018-03-16 close, the new portfolio was obtainable before/during Monday 2018-03-19 and certainly before a Monday-close trade.

### Public ETF holdings — 2021 onward

SEC Rule 6c-11 requires a relying ETF to publish each business day, before regular trading opens, the prior-close portfolio holdings that will form the basis of NAV. For each holding this includes ticker/identifier, quantity and portfolio percentage weight. The compliance transition was complete by late 2020.

Therefore for the March 2021 rebalance effective after the Friday 2021-03-19 close, the holdings/weights required to identify the Monday 2021-03-22 Top-1 were public before Monday's regular session and hence before Monday close.

## Why the old 17.756x reconstruction was wrong

The old canonical process did **not** possess a rebalance-date holdings file for every historical period. It took a later SEC quarterly/monthly snapshot and back-projected each security's snapshot market value to the earlier rebalance date using the stock's price ratio:

`estimated_rebalance_value = later_snapshot_value × price(rebalance_date) / price(snapshot_date)`

This assumes the later snapshot's share quantities / relative portfolio position can be treated as though they were the rebalance-date positions. That assumption is not safe for an ETF whose shares held can change because of creations/redemptions, portfolio maintenance and other trading between the two dates. It can reverse close rankings.

Two direct audits demonstrate the failure:

- **2018-04-30 raw SPMO SEC schedule:** Microsoft = $2,940,643; Amazon = $2,787,711. Microsoft is already #1 in the raw snapshot. The old back-projection nevertheless changed the inferred 2018-03 Top-1 to Amazon.
- **2021-05-31 raw SPMO N-PORT:** Microsoft = 9.214975% of portfolio; Amazon = 8.925517%; Apple = 8.814724%. The old back-projection inferred Amazon for 2021-03, while the actual rebalance table extracted from Leto's report identifies Apple on 2021-03-22. A May snapshot is not an authoritative substitute for March rebalance weights.

Thus the old `period_checks.csv` / `full_backtest_metrics.json` are retained only as an audit trail of the failed reconstruction method, not as the canonical Leto strategy.

## Canonical result

Use:

- `leto_live_period_checks.csv`
- `leto_live_metrics.json`

Exact independent reproduction, 2016-03-21 through 2026-08-12:

- Total multiple: **21.707120x**
- CAGR: **34.4636%** (calendar-day annualization)
- Annualized volatility: **33.7201%**
- Max drawdown: **-38.9245%**
- Sharpe with rf=0: **1.0481**
- 21 holding periods, **16 actual ticker switches**

The growth, volatility and drawdown claims from Leto are reproduced to close agreement. The remaining Sharpe difference is convention-dependent; Leto's exact risk-free-rate/Sharpe convention has not been independently proven.

## Practical execution rule

For a retail implementation that avoids any dependency on paid S&P pro-forma data:

- Do **not** attempt to trade the new Top-1 at the Friday rebalance close.
- After the official Friday-close rebalance, use the ETF's published holdings on the following Monday.
- Determine the highest portfolio percentage weight before the close.
- Execute at/near Monday close and hold until the next rebalance Monday.

This is the execution convention matched by the independently reproduced 21.707x backtest.

## Cost sensitivity

There are 16 ticker changes over the 21 periods. Counting initial purchase, every sell/buy switch, and final liquidation gives 34 transaction sides.

- 5 bps per side: 21.341x, CAGR 34.244%
- 10 bps per side: 20.981x, CAGR 34.024%
- 20 bps per side: 20.279x, CAGR 33.586%
- 50 bps per side: 18.306x, CAGR 32.277%

These are mechanical cost sensitivities only; they do not model taxes, tracking differences, inability to obtain a close fill, or future methodology changes.
