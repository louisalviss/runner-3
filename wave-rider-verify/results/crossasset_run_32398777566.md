# Wave Rider v2.5.15 Cross-Asset Transfer — Run 32398777566

- Source: Dukascopy public historical M5 BID
- Evaluation: 2022-01-01 through 2026-08-20 UTC; state warmup from 2021-12-01
- Development: 2022-2024; validation: 2025; final OOS: 2026 through 2026-08-20
- Timeframes: native 5m and strict 10m (exactly two contiguous 5m children; incomplete buckets rejected)
- Signal parity guard: LONG close > open; SHORT close < open; canonical v2.5.15 verifier pinned
- Primary transfer mode below: CORE_NO_CRYPTO_SESSION. CANONICAL_SESSION was also run as a robustness diagnostic.
- Base round-trip friction sensitivity: EURUSD 1.2bps; GBPUSD/AUDUSD/USDCAD 1.8; USDJPY/EURGBP 1.5; USDCHF/NZDUSD/EURJPY 2.0; GBPJPY 2.5; XAUUSD 2.0; US500/NAS100 1.5; US stock CFDs 3.0.
- US500/NAS100 are Dukascopy index CFDs (proxies for US equity index behavior), not CME ES/NQ futures. US stocks are Dukascopy stock CFDs, not exchange prints.
- META job failed only because Dukascopy exposes Meta under legacy `FB.US/USD`; 18 instruments completed.

## Primary all-period results

| Symbol | Group | 5m n | 5m gross R | 5m net R | 10m n | 10m gross R | 10m net R | 10m 2025 net | 10m 2026 net |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | FX | 785 | -49.00 | -413.97 | 350 | -6.72 | -127.23 | -31.33 | -28.72 |
| GBPUSD | FX | 753 | +38.28 | -457.47 | 398 | -8.19 | -189.38 | -33.69 | -50.83 |
| USDJPY | FX | 753 | -57.80 | -440.45 | 416 | -51.67 | -190.47 | -37.29 | -34.54 |
| AUDUSD | FX | 828 | -61.71 | -415.82 | 392 | -44.20 | -163.83 | -51.67 | -23.00 |
| USDCAD | FX | 824 | -62.51 | -744.73 | 413 | -33.07 | -280.49 | -67.18 | -30.87 |
| USDCHF | FX | 829 | +26.45 | -560.23 | 425 | -121.31 | -327.66 | -64.24 | -47.04 |
| NZDUSD | FX | 809 | +1.32 | -396.83 | 428 | -65.00 | -208.55 | -57.87 | -22.94 |
| EURJPY | FX | 778 | -26.07 | -492.96 | 362 | -14.13 | -160.48 | -23.30 | -33.13 |
| GBPJPY | FX | 801 | -4.71 | -555.72 | 329 | -60.64 | -228.85 | -56.85 | -34.37 |
| EURGBP | FX | 690 | -94.33 | -564.14 | 308 | -32.36 | -186.39 | -27.23 | -20.56 |
| XAUUSD | METAL | 767 | -22.55 | -297.53 | 352 | -30.73 | -123.39 | -27.60 | +4.97 |
| US500 | INDEX_CFD | 642 | +65.97 | -145.83 | 353 | -47.76 | -137.11 | -22.18 | -17.77 |
| NAS100 | INDEX_CFD | 680 | +35.16 | -132.38 | 339 | -32.57 | -95.40 | +0.23 | -24.76 |
| AAPL | US_STOCK_CFD | 209 | -8.18 | -44.40 | 122 | +1.77 | -12.68 | -2.28 | -3.73 |
| MSFT | US_STOCK_CFD | 270 | -1.75 | -53.60 | 131 | +0.97 | -18.27 | -16.02 | -4.45 |
| NVDA | US_STOCK_CFD | 224 | -7.40 | -28.22 | 119 | -19.21 | -27.65 | -16.97 | -4.17 |
| AMZN | US_STOCK_CFD | 245 | +1.58 | -32.93 | 111 | +10.01 | -0.56 | -12.54 | -0.49 |
| TSLA | US_STOCK_CFD | 246 | -29.68 | -49.83 | 138 | +11.63 | +2.67 | +8.86 | -9.62 |

## Fixed pass rule
PASS requires base-cost net R > 0 in both 2025 and 2026, with >=20 validation trades and >=10 OOS trades. **0/18 completed instruments PASS in either 5m or 10m, in both CORE_NO_CRYPTO_SESSION and CANONICAL_SESSION modes.**

## Group findings
- FX: 10/10 pairs fail net after base friction on both 5m and 10m. At 10m, even gross all-period is negative for all 10 pairs.
- XAUUSD: all-period negative gross and net on both 5m/10m. 10m 2026 alone is +4.97R net, but 2025 is -27.60R and prior years are negative; therefore no stable transfer.
- US500/NAS100: 5m gross is positive over the full sample, but both turn strongly negative after base friction. 10m all-period is negative. Isolated year positives do not persist 2025 -> 2026.
- US stock CFDs: 10m is closest to flat. TSLA is +2.67R net over the full sample, AMZN -0.56R, but no stock is net-positive in both 2025 and 2026. TSLA specifically is +8.86R in 2025 then -9.62R in 2026.

## Conclusion
This run falsifies the hypothesis that Wave Rider v2.5.15 is a portable standalone alpha across liquid FX, gold, US equity indices, and large-cap US stocks. The pattern may still have value as an execution trigger conditioned on an independent higher-timeframe alpha/regime selector, but the standalone signal is not stationary enough to justify further market-by-market threshold mining.
