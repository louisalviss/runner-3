# WR US Stocks 15m/30m Base — Frozen Test

Decision question: does increasing frozen WR 2.5.13 from 10m to 15m/30m improve economic viability, rather than merely reduce turnover/loss rate?

Frozen before outcomes:
- Same Fusion/Nasdaq-100 guaranteed-core universe as prior WR scan.
- Dukascopy BID+ASK midpoint M5 source, aggregated to 15m and 30m.
- Same frozen WR 2.5.13 reference and parity engine lineage.
- No RS, market regime, indicator filter, parameter tuning, symbol whitelist, or year selection.
- Report gross and 0.25/0.5/1/2 bps cost stress.
- Report overall, Long, Short, 2022–2026 by year, and symbol dispersion.
- Compare against existing 10m baseline evidence only after 15m/30m outcomes are complete.

Interpretation gate:
- If gross remains negative, higher timeframe does not create alpha even if costs improve.
- If gross is positive but fails at 0.5 bps or is concentrated in one year/few symbols, classify as non-robust.
- Do not tune timeframe-adjacent parameters as a rescue after seeing results.
