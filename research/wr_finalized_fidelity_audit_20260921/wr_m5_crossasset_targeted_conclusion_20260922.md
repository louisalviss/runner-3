# WR M5 cross-asset targeted diagnostic — 2026-09-22

Scope frozen before M5 outcomes:
- WR v2.5.13 core setup unchanged
- M5
- NORMAL + T+1 only
- VN windows 14:00-17:59 and 21:00-23:59
- Source: canonical Dukascopy BID M5 release `market-data-crossasset-m5-20260821`
- Period: 2022-01-01 through 2026-08-14
- M30-selected FX candidates tested at M5: NZDUSD, EURJPY, USDCAD
- Negative/control cross-asset checks: XAUUSD, NAS100, US500

## M30-selected FX candidates forced to M5
- NZDUSD: 137 trades, gross -30.4825R, E -0.2225, PF 0.6885. Early -22.9201R; late -7.5625R.
- EURJPY: 145 trades, gross -26.9675R, E -0.1860, PF 0.7337. Early -7.7388R; late -19.2287R.
- USDCAD: 125 trades, gross -6.6892R, E -0.0535, PF 0.9185. Early -3.5335R; late -3.1558R.

Conclusion: M5 increases trade count roughly 5-7x versus the M30 versions, but destroys gross edge before transaction costs.

## Other cross-asset M5 checks
- NAS100: 113 trades, gross -7.8014R, E -0.0690, PF 0.8986. FAIL gross.
- XAUUSD: 140 trades, gross +14.1294R, E +0.1009, PF 1.1626; early +5.4362R, late +8.6931R, but 2025 and 2026 negative.
- US500: 109 trades, gross +23.1175R, E +0.2121, PF 1.3596; early 2022-23 only +0.0686R, late 2024-26 +23.0489R.

## Cost geometry gate (base commission scenario only; spread not yet deducted)
Using the already frozen non-FX CFD commission scenario of $52.5 per $1M per side:
- XAUUSD median stop = 0.08263%; commission-only net = -6.8855R, E -0.0492, PF 0.9316. Equivalent friction break-even ≈ 0.706 bps total model. FAIL before spread.
- US500 median stop = 0.06679%; commission-only net = +0.9981R, E +0.00916, PF 1.0126. Equivalent friction break-even ≈ 1.097 bps. Any realistic spread/slippage likely consumes remaining edge. Not execution-ready.

At a legacy 6bps-equivalent stress:
- XAUUSD = -105.9569R
- US500 = -103.2852R

## Decision
`M5_CROSS_ASSET_TRADE_COUNT = SOLVED`
`M5_CROSS_ASSET_EDGE_QUALITY = FAIL`
`M5_COST_GEOMETRY = FAIL`

Do not lower the whole WR cross-asset system to M5 solely to increase trade count. M30 remains structurally safer on cost geometry. If M5 is revisited, it requires a different economic setup (wider structural stop / different entry model), not the unchanged WR v2.5.13 stop geometry.
