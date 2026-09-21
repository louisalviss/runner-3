# Wave Rider M30 frozen forward collector

Frozen 2026-09-22.

- Shadow-only. Never sends exchange orders.
- SOLUSDT / ETHUSDT / XRPUSDT.
- M30.
- WR v2.5.13 canonical lifecycle.
- Weekends OFF.
- Admit weekday NORMAL / T-1 / T+1 only.
- Exclude any date overlapping T0 / T-2 / T+2 / T+3.
- T0 sources: official BLS CPI + Employment Situation ICS, and official Federal Reserve FOMC calendar.
- Market data: Binance USD-M public 1m daily archive, resampled deterministically to M30.
- Forward start: 2026-09-21T21:30:00Z.
- Promotion review requires >=50 closed trades plus net 5/2/5 E >=0.15R, PF >=1.25, break-even equivalent friction >=6bps.
- Timer runs four times daily. Archive latency is acceptable because this is validation, not execution.

Runtime path: `/opt/wr-m30-forward`.
Dropbox runtime mirror: `/stragety/wave-rider-recheck/forward/`.
