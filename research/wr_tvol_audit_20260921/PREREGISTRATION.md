# WR T + Volume Audit — frozen before batch result

Primary lineage: Wave Rider v2.5.13 canonical, Binance USDT futures, 5m, 2025-01-01 through 2026-08-14 signals, 6 bps modeled cost.

Frozen filters:
- T-only: Vietnam-local calendar date belongs to union of T-2, T-1, T0, T+2, T+3 around actual CPI, Employment Situation (NFP), or regular FOMC statement releases.
- T+1 excluded; white days excluded; Saturday/Sunday excluded.
- T0 is the Vietnam-local calendar date of the actual release timestamp.
- High-volume only: causal Stage-1 session union after 24h quote volume >= USD 100M AND prior-completed-day 10D average dollar-volume proxy > USD 200M.
- Do NOT require 7D volatility or ADR14 in the volume-only variants.
- No threshold sweep, ticker whitelist, side-only rescue, year removal, timeframe change, TP/SL change, or post-result parameter adjustment.

Variants fixed before result:
1. fullstage_t = old full Stage1 (volume + vol7 + ADR14) + exact T gating.
2. volume_all = volume-only causal Stage1, no T gating.
3. volume_t = volume-only causal Stage1 + exact T gating. PRIMARY.

Strong-pass diagnostic fixed before result for PRIMARY:
- n >= 80
- total net R > 0
- mean net R > 0
- PF > 1.05
- 2025 total R > 0 and 2026 total R > 0
- day-block bootstrap 95% lower bound of mean R > 0
- >= 50% positive symbols among symbols with >=5 trades
