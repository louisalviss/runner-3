# Backtest 2026 manual rows — canonical WR v2.5.13 re-audit

Authority: `Wave Rider Strategy v2.5.13 WINDOW REPORT`, parity commit `5b2e3ad33171c859460ff4e479107223f0223b88`, frozen reference blob `2ba5f66d33e2e483a4c669c95f3b97778c80fcd0`.

Pipeline: Binance USD-M futures 1m -> canonical 5m aggregation -> parity engine. Manual sheet timestamp is treated as the signal-candle OPEN in VN GMT+7. Matching is exact same M5 signal candle only; no +/- bar matching.

## Result
- Manual rows: 297.
- Timestamped: 202; no timestamp: 95.
- Exact canonical WR trades at the same manual timestamp: 95.
- Not canonical WR setup: 101.
- Setup eligible but no canonical trade: 6 (3 active-position blocks; 3 next-bar stop entries not filled).
- Of 95 canonical trades, old R exact: 80; R corrections required: 15.
- Canonical total on those 95 trades: 37.557885709289R vs manual old 27.200000000000R; correction delta +10.357885709289R.
- Canonical 95-trade metrics: 39W/56L, WR 41.05%, avg 0.395346R, PF(R) 1.720298.

## 15 exact R corrections
|Row|Symbol|Date|Time|Old R|Canonical R|Exit|Delta|
|---:|---|---|---|---:|---:|---|---:|
|12|SOL|2025-12-12|01:10|0.4000|2.300000|TP|+1.900000|
|13|XRP|2023-08-02|01:15|2.3000|-1.000000|SL|-3.300000|
|26|BTC|2025-12-19|02:35|-0.7000|-0.327282|EMA|+0.372718|
|33|BTC|2025-12-28|03:00|-1.0000|2.300000|TP|+3.300000|
|73|SOL|2026-01-01|08:00|-1.0000|2.300000|TP|+3.300000|
|87|SUI|2025-11-05|09:50|-0.2000|-0.018750|EMA|+0.181250|
|96|XRP|2025-11-23|11:15|-1.0000|-0.786765|EMA|+0.213235|
|111|XRP|2023-10-26|12:45|-0.7000|-0.294118|EMA|+0.405882|
|119|XRP|2025-11-23|14:00|-0.7000|-0.404255|EMA|+0.295745|
|126|XRP|2025-11-10|14:35|-1.0000|-0.850000|EMA|+0.150000|
|127|SUI|2025-11-02|14:40|-1.0000|-0.702703|EMA|+0.297297|
|147|ETH|2025-12-18|17:15|-1.0000|-0.758242|EMA|+0.241758|
|158|BTC|2025-12-29|18:00|2.3000|-1.000000|SL|-3.300000|
|181|XRP|2023-08-31|21:00|-0.7000|2.300000|TP|+3.000000|
|196|XRP|2025-11-15|23:10|-1.0000|2.300000|TP|+3.300000|

## 6 setup-eligible rows that are not WR trades
|Row|Symbol|Date|Time|Old R|Canonical reason|
|---:|---|---|---|---:|---|
|29|SUI|2025-11-24|02:45|-1.0000|ACTIVE_POSITION|
|64|SOL|2025-12-03|07:15|-1.0000|NEXT_BAR_STOP_NOT_FILLED|
|125|BTC|2025-11-21|14:20|2.3000|NEXT_BAR_STOP_NOT_FILLED|
|162|SOL|2025-12-28|18:10|-1.0000|NEXT_BAR_STOP_NOT_FILLED|
|173|BTC|2025-12-24|19:35|-1.0000|ACTIVE_POSITION|
|200|SOL|2025-11-13|23:20|2.3000|ACTIVE_POSITION|

## Interpretation
The spreadsheet is not a canonical coded-WR trade ledger as-is. Only the 95 exact-timestamp rows above are validated as full WR v2.5.13 trades. The 101 non-setup rows and 6 no-trade rows must not contribute to a coded-WR performance total. The 95 rows without time cannot be validated exactly and are left unresolved rather than guessed.
