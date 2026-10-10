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
