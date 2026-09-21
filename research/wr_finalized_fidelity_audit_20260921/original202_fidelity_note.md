# Original WR timestamped corpus fidelity — 2026-09-21

## Source authority
Google Sheet `Backtest 2026`, tab `Update 5m Wave Rider crypto`.
- original tab header: 297 trades
- update tab header: 298 trades
- update-only extra row: BTC 22/04 06:35 +2.3R
- original timestamped corpus: rows 2:203 = 202 trades with symbol/date/time
- remaining original rows lack entry time (mostly DASH/LTC/DOGE), so they cannot be candle-matched 1:1 from the sheet alone.

Market feed for fidelity: Binance USD-M futures, corresponding to the user's USDT perpetual / TradingView `*.USDT.P` trading surface. Spot is not the trading feed.
Timestamp convention: the sheet time is interpreted as the VN (GMT+7) open time of the M5 signal candle.

## v2.5.13 recall on all 202 timestamped manual WR trades
- exact same M5 signal: 101 / 202 = 50.00%
- within ±5m: 110 / 202 = 54.46%
- within ±10m: 113 / 202 = 55.94%

Exact by symbol:
- BTC 14/37
- DASH 1/7
- ETH 10/24
- SOL 20/30
- SUI 23/45
- XRP 33/59

Among 101 exact misses, failing v2.5.13 gates (overlap allowed):
- signal range <=1.5 ATR: 74
- same-bar pivot break+retest: 35
- regime 12-candle side requirement: 8
- CHOP: 4
- angle: 2

Break/retest decomposition:
- 27 manual trades satisfy the current pivot break but fail only the same-bar retest portion;
- 8 do not satisfy the current pivot break itself.

## Recognition-only ablation (NO P/L used)
This is a semantic fidelity diagnostic, not an alpha optimization.
- current v2.5.13: 101/202 = 50.00%
- remove signal-range gate only: 158/202 = 78.22%
- remove signal-range + same-bar retest, still require current pivot break: 184/202 = 91.09%
- additionally replace 12-bar regime with simple EMA-side: 188/202 = 93.07%
- literal written sheet proxy: signal candle direction + current S/R exists + close breaks current S/R (EMA-side adds no extra exclusions among these breaking cases): 194/202 = 96.04%

The final 8/202 mismatch therefore primarily reflects current machine pivot S/R not matching the manual red/green S/R line used in the historical chart review, not the other v2.5.13 filters.

## Manual confirmation subset
Column G contains 25 `Ok` and 5 `Hit` manual confirmations.

`Ok` (25):
- v2.5.13 exact: 18/25
- literal written break proxy: 24/25
- only written-break mismatch: BTC 2025-12-17 19:00 VN, explicitly marked `Ok` in the sheet.

`Hit` (5):
- v2.5.13 exact: 4/5
- literal written break proxy: 5/5

`Ok + Hit` (30):
- v2.5.13 exact: 22/30
- literal written break proxy: 29/30

## Authority interpretation
- The 48-trade set is the downstream Finalized-WR asset/day/time subset, NOT the WR setup fidelity corpus.
- The correct setup-replication corpus is the 202 original trades with timestamps.
- v2.5.13 is not an exact replica of the historical manual WR setup (50% exact recall on the 202 positive/manual examples).
- The largest semantic additions in v2.5.13 relative to the sheet rule are the 1.5 ATR signal-range gate and same-bar pivot retest requirement.
- The manual sheet explicitly says: enter only when the signal candle CLOSES THROUGH support/resistance; it does not state a same-bar retest requirement.
- A replacement detector must recover the manual S/R line semantics. Do not simply delete filters and call it validated: the 202 rows are positive examples and do not measure false-positive precision.
- Any detector calibrated on these 202 trades requires negative/control examples plus a new blind holdout before forward use.

## S/R pivot-strength diagnosis on manually confirmed Line-test subset

The 30 rows explicitly labeled `Ok` or `Hit` in column G are the strongest manual S/R-break oracle in the workbook.

Fixed Pine-style confirmed-pivot strength recall on these 30 positive Line-test examples:
- 2/2: 20/30
- 3/3: 22/30
- 4/4: 24/30
- 5/5: 27/30
- 6/6: 28/30
- 7/7: 28/30
- 8/8: 28/30
- 9/9: 30/30
- 10/10: 29/30 (misses BTC 2025-12-17 19:00 VN, labeled `Ok`)

For that BTC `Ok` case, strengths 2 through 9 all identify a break; 10/10 selects a much older/higher resistance and rejects it.

Important: repository/history search found no provenance that historical/manual WR used fixed 9/9 pivots. Later machine lineage uses 10/10. Therefore `9/9 = 30/30` is **HYPOTHESIS ONLY / recall clue**, not an authorized replacement rule. These are positive examples only; precision/false-positive behavior is unknown.

Three unlabeled historical rows that do not break any 2..10 wick pivot (XRP 2023-08-18 14:00, XRP 2023-08-11 15:25, SUI 2025-11-22 20:05) should not be used to redefine Line-test semantics because they were not marked `Ok/Hit` in column G. This reinforces the distinction between the 202 timestamped WR trade corpus and the 30 manually confirmed S/R Line-test oracle.
