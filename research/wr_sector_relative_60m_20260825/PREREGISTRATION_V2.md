# Wave Rider Sector-Relative Alignment — Preregistration V2

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / RESULTS UNSEEN

V1 run `32804183022` was `INFRASTRUCTURE_BLOCKED` before any WR PnL scoring because Dukascopy did not resolve XLC and XLRE. The run's validate stage was skipped. No alpha outcome was observed.

This V2 changes ONLY the unavailable benchmark proxies:
- Communication Services: `XLC -> VOX` (Vanguard Communication Services ETF)
- Real Estate: `XLRE -> VNQ` (Vanguard Real Estate ETF)

All stock membership, WR parent trades, 60m timeframe, causal timestamp contract, EMA50 ratio rule, slope rule, primary 2024-2026 window, metrics, bootstrap, and promotion gates remain exactly as V1.

Broad-market benchmark remains SPY.

Frozen sector proxies V2:
- XLK Technology
- VOX Communication Services
- XLY Consumer Discretionary
- XLP Consumer Staples
- XLE Energy
- XLF Financials
- XLV Health Care
- XLI Industrials
- XLU Utilities
- VNQ Real Estate

If VOX or VNQ fails Dukascopy resolution, V2 is `INFRASTRUCTURE_BLOCKED`; no further proxy substitution is permitted inside V2.

`PASS_SECTOR_RELATIVE_WR` gates remain unchanged from V1.