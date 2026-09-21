# WR frozen T+symbol fresh OOS — 2026-08-15 to 2026-09-18

## Frozen candidate
No post-result changes:
- symbols: ETH, SOL, SUI, XRP
- timeframe: M5
- T filter admitted at signal time: NORMAL + T+1 + T-1
- excluded: T0, T-2, T+2, T+3
- no volume filter
- Binance USD-M 1m public archive -> M5
- correct inferred crypto tick metadata
- WR v2.5.13 structural setup

Signal window UTC: 2026-08-15 00:00 through 2026-09-18 23:59:59.
Settlement loaded through 2026-09-21 where available. Binance Vision daily file 2026-09-21 was unavailable for all four symbols, but `open_censored=0` in every symbol/variant, so the missing settlement day does not affect any scored trade.

T0 VN anchors inherited from the preregistered fresh OOS calendar:
- NFP 2026-09-04
- CPI 2026-09-11
- FOMC 2026-09-17

## Canonical lifecycle result
- n = 57
- gross = +6.0402245R
- gross expectancy = +0.105969R/trade
- gross PF = 1.16715
- break-even equivalent one-way friction = ~1.9573 bps
- 1bps-equivalent: +2.9543R
- 2bps-equivalent: -0.1317R
- 2.9bps-equivalent: -2.9091R
- 6bps-equivalent: -12.4756R
- fee scenario entry taker5 / TP maker2 / other taker5: -21.6122R, E -0.37916R
- same with 10% BNB-style discount 4.5/1.8/4.5: -18.8470R
- all-maker 2/2: -6.3059R

By symbol, gross canonical:
- ETH: 16 trades, -7.0805R
- SOL: 13, +6.8R
- SUI: 17, +3.6596R
- XRP: 11, +2.6611R

By admitted T class:
- NORMAL: 48, +7.8967R
- T-1: 9, -1.8565R
- T+1: 0 trades in this holdout

## Fixed +2.3R/-1R result
Signal admission was rerun inside the engine; trades were not merely post-filtered.
- n = 57
- gross = +5.7R
- gross expectancy = +0.10R/trade
- gross PF = 1.15
- break-even equivalent one-way friction = ~1.8471 bps
- 2bps-equivalent: -0.4719R
- 6bps-equivalent: -12.8158R
- fee scenario 5/2/5: -21.9112R, E -0.38441R
- 4.5/1.8/4.5: -19.1501R
- all-maker 2/2: -6.6471R

## Comparison to older WR rejection
Older corrected in-sample broad fixed variant:
- 1450 trades
- +120.8R gross
- +0.08331R/trade
- break-even ~2.917 bps
- 6bps-equivalent -127.64R

Older fresh T+volume OOS:
- 64 trades
- -17.8R gross
- already failed before fees

The manual-derived T+symbol candidate initially appeared much stronger in the selected historical intersection (68 trades, +36.6477R, E +0.53894R gross), but the frozen fresh OOS does NOT retain that edge magnitude. It falls back to about +0.10R/trade gross and becomes negative around 2bps-equivalent friction.

## Status
`FROZEN_T_SYMBOL_CANDIDATE = FAIL_EXECUTABLE_OOS`
`OLD_COST_GEOMETRY_CONCERN = CONFIRMED`
`POST_OOS_SYMBOL_OR_T_RESCUE = PROHIBITED_ON_THIS_HOLDOUT`

Do not remove ETH, T-1, or otherwise re-optimize based on these OOS results and then reuse this same holdout as validation.
