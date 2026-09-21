# WR M30 expanded-symbol conclusion — 2026-09-22

Scope: backtest/research only. Forward remains paused.

## Preregistered universe
- Source universe: prior WR liquidity universe.
- Selection criterion frozen before PnL: Binance USD-M present by Jan-2022 and still present in Aug-2026.
- 45 symbols passed; EOS was excluded for missing Aug-2026 continuity.
- Common comparison period: 2022-01-01 through 2026-08-14.
- Rule frozen: WR v2.5.13, M30, weekday NORMAL + T+1 only, VN 14:00-17:59 and 21:00-23:59, any cluster overlap OFF.
- Cost: entry taker 5bps / TP maker 2bps / other exit taker 5bps.
- Parity gate: PASS 42/42 SOL+ETH signals against existing exact authority.

## Universe result
- 45-symbol aggregate: n=927, gross -91.2077R, net 5/2/5 -201.0686R, E -0.2169R, PF 0.7181.
- Original SOL/ETH/XRP on same common period: n=59, net +2.0060R, E +0.0340R, PF 1.0478.
- Therefore broad symbol expansion is decisively rejected. WR edge is not cross-sectional across the liquid universe.

## Stability diagnostic
Preregistered descriptive gate: n>=30, positive net overall, positive net in both halves (2022-24 and 2025-26), and >=3 positive calendar years.

Only AAVEUSDT passed:
- 2022-2026-Aug14: n=33, gross +9.8005R, net 5/2/5 +5.5603R, E +0.16849R, PF 1.2551.
- Positive years: 5/5.
- 2022-24: +3.9452R net.
- 2025-26: +1.6152R net.
- break-even equivalent friction ~20.75bps.

Other positive-total symbols were materially less stable. Examples:
- XLM: late half negative.
- LPT: late half negative.
- DOGE: early half negative.
- DUSK/PEOPLE/SNX/FIL: late half negative.
- RUNE positive in both halves but n=25 and only 2/5 positive calendar years.
- CRV positive in both halves but only n=15; insufficient sample for the preregistered stability gate.

## Exact AAVE verification
AAVE was rerun using Binance USD-M 5m archive -> exact M30 aggregation, not direct-M30 shortcut.
- 2022+ identity parity vs expanded scan: 33/33 signals, 0 mismatch.
- 2021 temporal holdout (not used in symbol ranking): n=3, net +3.5008R, E +1.1669R, PF 4.31. Sample is too small to count as independent validation.
- Full 2021-Aug2026 exact: n=36, gross +13.4005R, net 5/2/5 +9.0611R, E +0.25170R, PF 1.3965.

## Untouched later holdout
The prior fresh window 2026-08-15..2026-09-18 had never evaluated AAVE when AAVE was selected.
Exact AAVE 5m->M30 replay produced 0 trades in this window.
Result: no validation and no rejection; it is informationally neutral.

## Portfolio diagnostic (post-scan, research only)
Common period 2022-Aug2026:
- AAVE alone: n33, +5.5603R net, E +0.1685, PF 1.255, max DD ~4.96R, 5/5 positive years.
- Original SOL/ETH/XRP: n59, +2.0060R, E +0.0340, PF 1.048, max DD ~10.69R, 2/5 positive years.
- Original3 + AAVE: n92, +7.5664R, E +0.0822, PF 1.119, max DD ~10.08R, 2/5 positive years.
Thus AAVE improves total R of the old basket but the unstable old symbols dilute AAVE's quality.

AAVE+CRV appears better on a post-scan diagnostic (n48, +6.8476R, E +0.1427, PF 1.225, 4/5 positive years) but CRV was selected after seeing the scan and must NOT be treated as validated.

## Current status
- `BROAD_45_SYMBOL_EXPANSION = FAIL`
- `AAVE_M30 = PRIMARY_RESEARCH_CANDIDATE`
- `AAVE_EXACT_REPLAY = PASS`
- `AAVE_INDEPENDENT_VALIDATION = INSUFFICIENT` (2021 n=3; later fresh holdout n=0)
- `FORWARD = PAUSED`
- Do not restart forward yet unless the backtest phase is explicitly closed.
