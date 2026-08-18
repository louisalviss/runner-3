# SPMO Top-N independent test — data status

## Status

**Not independently reproduced yet.**

The recovered Leto source gives the exact 21-period Top-1 sequence and aggregate Top-20 metrics, but it does not expose exact rebalance-date ranks/weights 2..20 for every period.

A Runner-3 probe of Invesco's public ETF holdings download route tested the current route plus likely historical parameters (`asOfDate`, `date`, `holdingsDate`, `asof`) for 2018-03-19 and 2021-03-22. Every request returned HTTP 406 with an empty body from the GitHub-hosted runner. Workflow run: `31972078490`.

Therefore no Top-2/3/5/10/20 series was fabricated. Later SEC portfolio snapshots must not be used as substitutes for exact rebalance-date ranking because the earlier audit demonstrated that back-projecting later holdings can reverse Top-1 rankings.

Leto's reported Top-20 result remains source-only pending exact historical rebalance holdings: CAGR 22.83%, Sharpe 0.95, max drawdown 29.3%.
