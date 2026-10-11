# Opportunity Radar V3 — Shock / Pump cross-session recall audit
Updated: 2026-10-11 (VN); branch: `audit/opportunity-radar-cross-session-replay-20261011`
Status: **DIAGNOSTIC / HOLD RULE PROMOTION**

## Question
Can MARKET_PRICING capture broad 1D/5D price dumps and pumps without dropping pre-existing Shock/Early signals, and why are others excluded?

## Evidence and provenance
- Live source: `data/opportunity-radar/market-health.json`, `market-prefilter.json`, `market-signals.json`. Source packets are committed per session.
- Prior PR #394: all 13,297 listed symbols now receive universe-stage reason codes; 2,763/2,767 fresh for US session 2026-10-09.
- Git archive replay engine: `scripts/opportunity_radar_recall_history.py`; strict per-symbol `last_date`, every emitted source last_date, source-session identity, SHA-256 and packet counts. Earliest validated archived COMPLETE packet for each session, no retroactive discovery timestamps.
- Historical archive: 2 sessions pass strict evidence gates (2026-10-08, 2026-10-09). Invalid *archive commits* may trigger multiple rejection codes; these counts are **not distinct bad sessions**: PREFILTER_SYMBOL_SESSION_STALE: 22; SIGNAL_SYMBOL_SESSION_STALE: 9; PREFILTER_SHA_MISMATCH: 2; NOT_COMPLETE: 3; INSUFFICIENT_FRESH_COVERAGE: 3.
- CI replay [PR #395](https://github.com/louisalviss/runner-3/pull/395), [Actions run](https://github.com/louisalviss/runner-3/actions/runs/38094797704): 5/5 new tests PASS, archived replay PASS.

## Two strictly verified sessions — price-event *discovery* recall
| Predicate | Total | Actual production baseline | 28/28/16/8 quota | Preserve-baseline-Shock+Early with up to 24 new pumps |
|:--|--:|--:|--:|--:|
| 1D Pump >= +7% | 65 | 19 | 33 | 36 |
| 5D Pump >= +15% | 65 | 10 | 37 | 34 |
| 1D Shock <= -7% | 58 | 48 | 38 | 48 |
| 5D Shock <= -15% | 47 | 43 | 28 | 43 |

The fixed 28/28/16/8 quota **FAILS Shock non-regression**. Do not promote it. The protected-policy diagnostic preserved 40/40 historical baseline EARLY_WATCH labels and 48/48 1D / 43/43 5D Shock detections; 34 new symbols would be substituted for 34 old baseline symbols across the 2 sessions. Those displaced signals may include valuable sector/noise-adjusted setups; evaluate first.

## Displaced-signal audit — 2026-10-11 follow-up

A reproducible two-session PIT replay now emits full *per-symbol* evidence for every baseline displacement and each proposed Pump addition. **34/34 displaced baseline signals were `SECTOR_UNDERPERFORM` only**; none belonged to the already-emitted direct 1D/5D Shock or EARLY_WATCH groups. This is an attribution, **not** evidence that sector divergence signals are low quality.

On the October 9 frozen packet alone:
- Baseline 1D Pump 8/42, 5D Pump 6/38; direct 1D Shock 17/18, 5D Shock 23/24.
- Protected Shock/Early + up to 24 new Pumps yields 1D Pump **23/42**, 5D Pump **22/38**, and retains 1D Shock **17/18** and 5D Shock **23/24**.
- 24 baseline `SECTOR_UNDERPERFORM`-only entries are displaced by 24 raw Pump candidates. Each added item remains `REQUIRES_HARD_PERSIST_REVIEW`; displaced signals are `VALUE_NOT_YET_ASSESSED`.
- A separate fixed-quota design continues to fail Shock non-regression.

Forward capture is added to the regular market shadow diagnostic only: `market-recall-shadow.json` now includes `protected_review_queue.added` and `protected_review_queue.displaced`, baseline trigger evidence, signed returns, volume ratios and reason counts. **Live 80 Signals, D1, Sheet, execution, paper-trade orders and existing selection rules remain unchanged.**

## First forward price-reaction diagnostic — added vs displaced

Read-only archived replay PR #397 (GitHub Actions run 38095420978), 8/8 deterministic tests PASS.

For 2026-10-08 selected raw signals, strictly validated adjacent completed session 2026-10-09:
- `PROTECTED_PUMP_ADDITIONS`: 10/10 adjusted one-day next-close returns observed, **9 positive / 1 negative**, mean **+4.4001%**, median **+4.1768%**.
- `DISPLACED_SECTOR_ONLY_BASELINE`: 10/10 observed, **5 positive / 5 negative**, mean **+0.1209%**, median **+0.3767%**.
- 2026-10-09 additions/displacements: 24/24 each remain **UNOBSERVED** because the archive has no independently verified subsequent completed market session yet.

Critical limitations: these numbers are **non-executable next-close price-reaction labels** only, not portfolio gains, mark-to-market entry P&L, R/R, mispricing or verified tradable alpha. In particular, 2026-10-08 archived packet's publishing/recording time may have been after the next session opened; no retroactive fill at the original close or next open is implied. Single forward session, n=10/group, cannot support rule promotion. Next check needs 5D/20D when eligible, independent economic catalyst verification, signal capture latency, provider split/dividend guards, venue/exchange calendar validation and measured trading costs. Missing symbols/future sessions must stay unavailable, never filled with current hindsight prices.

## Validity boundaries
- 2 verified sessions is not an independent out-of-sample evaluation, and same stock can occur on both days: no precision, false-positive economics, alpha, or expected P&L is demonstrated.
- Archive claim is limited to symbols with valid same-session adjusted price data, not all listed stocks.
- NO candidate promotion, real/paper order or ENTRY_READY allowed from diagnostic trigger alone. Existing curated Hard Persist and Master/Entry/Execution gates unchanged.
- Do not backfill missing prior valid snapshots by downloading today's adjusted history. Keep missing cases labeled `HISTORICAL_PACKET_NOT_ELIGIBLE` for promotion-grade replay.
- No D1/Sheet/production market signal modification from this replay code.

## Next verification gate
1. Accumulate genuine new completed session snapshots under the improved freshness integrity, keeping immutable per-session digests rather than only the current JSON path.
2. Compare protected Shock/Early + Pump, fixed quota, and baseline on cross-session **prospective** recall of corporate-action-clean moves and economic-catalyst quality.
3. Review displaced sector signals, false-positive rate, freshness failure modes and all hard Persist decisions. Only nominate a single production rule when passing both recall nonregression and precision/cost/tail-risk gates.
4. Keep original `Rule_Experiments!4` status `SHADOW` and Replay N=0 promotion-grade; valid historical diagnostics = 2 sessions (not 2 trade outcomes).

## 2026-10-12 operational follow-up — keep *all* raw Pump/Shock predicates

- PR [#398](https://github.com/louisalviss/runner-3/pull/398) merged at `2b5ad4a3`, introducing `scripts/opportunity_radar_market_event_ledger.py` and `data/opportunity-radar/market-move-events.jsonl`.
- The append-only ledger records each `source-session|ticker|1D_PUMP/5D_PUMP/1D_SHOCK/5D_SHOCK` predicate from the COMPLETE same-session adjusted-price shadow, **even if omitted from the capped live top-80 signals**. Early source generated timestamps are retained; append time is actual, never backdated.
- QA historical October 09 packet: **122 direct price-predicate observations** (42 1D Pump +38 5D Pump +18 1D Shock +24 5D Shock; distinct predicates, not 122 unique tickers). 26/26 suite PASS (market source/session 9, shadow selection 11, append-only ledger 6), including duplicate-ticker, degraded source, tampered threshold and idempotent re-run protections.
- Production scan schedule shifted from `21:02 UTC` to **`22:45 UTC Mon–Fri` = `05:45 Asia/Ho_Chi_Minh Tue–Sat`**, at least 105 minutes after US standard-time close instead of 2 minutes, with per-symbol freshness gate unchanged.
- Ledger is immutable first-observed raw *screening* evidence only: **NOT** a trade, ranking, edge, prediction, backtest fill, BUY or SHORT. Entry, Hard Persist, Curated Signals, D1 and execution remain unchanged. The historical initial 2026-10-09 population is NOT a retroactive live alert.
- Forward validation: compare per-session direct-event coverage to all eligible price flags; continue measuring independent economic catalyst/false positives, close-to-close follow-through and real capture latency. Do not auto-promote 28/28/16/8 quota or protected Pump policy without qualification.


## 2026-10-12 completed-session High/Low reversal audit (PR #399)

Production readback: [PR #399](https://github.com/louisalviss/runner-3/pull/399), squash merge `d61e66ce7cb750fcffa3f58744ffe9922ae16e85`; [Actions run 38175608778](https://github.com/louisalviss/runner-3/actions/runs/38175608778) **scan/persist/freshness SUCCESS**. US source session **2026-10-09** (not a fresh Oct-12 market session). `market-health.json` COMPLETE; valid adjusted OHLC for 2,763 securities, same 99.855% close-session coverage. 33/33 regression tests PASS.

- `INTRADAY_HIGH_PUMP` ≥ +7% relative to preceding session's adjusted close at the *completed daily High*: **95** event predicates, of which **53** did not also meet +7% at the same-day adjusted Close.
- `INTRADAY_LOW_SHOCK` ≤ −7% at completed daily Low: **29** event predicates, of which **11** did not also meet −7% at same-day adjusted Close.
- The **64** close-reverted threshold hits are counts of *predicate observations*, not necessarily 64 distinct tickers, and not executable intraday alerts. OHLC has no event timestamp. Adjusted high/low is today's raw high/low × (`Adj Close / Close`), compared with prior adjusted close, with fail-closed OHLC integrity and corporate-action guards.
- Existing 1D/5D close-based event ledger: **122** records preserved byte-for-byte; new completed-bar High/Low events: **124**; append-only `market-move-events.jsonl` now **246 unique event IDs**, source-session only, no backdating of actual log time.
- Live `market-signals.json` still **80/80**; ordered symbol + raw trigger identity exactly unchanged compared with the pre-PR saved packet. D1, Google Sheet curated Signals, Paper Trades, Entry/Execution and production selection algorithm unchanged.
- Source of truth: `data/opportunity-radar/market-recall-shadow.json` has `intraday_daily_ohlc_extreme_moves` and `intraday_extremes_not_reaching_corresponding_close_threshold`; append-only evidence in `data/opportunity-radar/market-move-events.jsonl`.

**Limit:** This solves missing *within-session completed-bar extremes* (ex post), NOT live market intraday alerting. Cannot recover securities outside the eligible/fresh universe, or moves from unsupported pre/after-hours data. No score/BUY rule promotion. Future work is prospective multi-session false-positive and catalyst/forward return review before deciding on expensive real-time quote coverage.
