# SPMO validated outputs

## Canonical — use these

1. `leto_live_period_checks.csv` — exact 21-period Top-1 sequence extracted from Leto's video, using the Monday-after-rebalance close convention.
2. `leto_live_metrics.json` — independently reproduced growth/risk metrics plus transaction-cost sensitivity.
3. `live_tradability_audit.md` — look-ahead and live-execution audit, including the 2018/2021 reconstruction diagnosis.

Canonical headline result: **21.7071x, 34.4636% CAGR, 33.7201% annualized volatility, -38.9245% max drawdown** for 2016-03-21 through 2026-08-12 before costs/taxes.

## Archival — do not use as the strategy result

- `period_checks.csv`
- `legacy_audit_final.csv`
- `full_backtest_metrics.json`

These files document the earlier Friday-date / later-SEC-snapshot back-projection investigation. That method was useful for provenance work but is not a valid way to recover exact rebalance-time Top-1 weights. `full_backtest_metrics.json` is explicitly marked deprecated.

The raw SEC audits remain useful evidence about historical reported holdings; the error was using later snapshots to infer earlier rebalance rankings, not the SEC filings themselves.
