# Gate-first candidate census and execution-corrected decision ledger — R5 companion

Research SHADOW, 15 October 2026. Canonical original price-zone execution audit: **research/opportunity-radar/backtests/2026-10-14-gate-first-pumpdump/GATE_FIRST_EXECUTION_CORRECTED_R4.md** and companion **gate_first_limit_fills_3.csv**, merged in PR #416. This supplement does not supersede those results.

## Priority and historical completeness
Gate-first has priority #1 across all tickers without any Pump/Dump requirement. Pump/Dump is priority #2, additional discovery and passes EXACT SAME Hard Persist, Score>=80, MQ>=3, realistic R/R>=2, Entry and Execution. No production changes or new BUY.

Drive Opportunity Radar native file lists 159 revision metadata records Aug09–Oct15; only selected revision exports were readable (some 429 rate-limited), NOT all 159 backtested. Three original BUY_SIGNAL timestamp events were verified using revision content and the original Paper_Trades ledger: LMT Sep10 17:52 +07, LHX Sep15 10:42 +07, LHX Sep16 09:14 +07. No signed real broker order/fill.

Current Oct15 Candidates has 43 curated rows; 7 are now Score>=80 + MQ>=3: **LHX, NOC, LMT, RTX, MRVL, P, SPXC**, all presently Entry NOT_READY. Do NOT backdate current Score/Entry into earlier snapshots. Market price archive has 3,035 ticker identities over 15 timing-qualified sessions and 41,244 symbol-session observations, not 3,035 archived economic Gate decisions. Unreviewed/absent Gate = UNKNOWN, never FAIL.

## Execution corrections from canonical R4
CRITICAL: **All three original following-market opens EXCEEDED their archived upper Entry caps.** Next-open market BUY reference in older price backtests is NOT allowed as a Gate-executable fill.

| Original advisory | Next US market open | Entry cap | Intraday US low | Market-open Gate eligible? | Limit cap touched by daily low? |
|---|---:|---:|---:|---|---|
| LMT Sep10 | $526.01 | $525 | $524.09 | NO | YES |
| LHX Sep15 | $251.90 | $250 | $247.87 | NO | YES |
| LHX Sep16 | $250.07 | $250 | $248.14 | NO | YES |

With a hypothetical resting limit order exactly at cap, if accepted/fillable at touch, after 0.5% total cost:

| Original advisory | Day 5 | Day 20 |
|---|---:|---:|
| LMT Sep10 | +1.833% | -5.410% |
| LHX Sep15 | -1.728% | -5.200% |
| LHX Sep16 | -4.544% | -6.612% |
| Mean 3 advisories, only 2 issuers | **-1.480%** | **-5.741%** |

No broker fills were observed, and OHLC does not prove queue priority, order submission before touch, spreads, or actual executable price. No independent three-position sample: two LHX tickets overlap, each nominal 10% of $1000 paper benchmark, meaning 20% same-issuer nominal virtual exposure, requiring issuer-level concentration/dedup review before real portfolio implementation. The non-Gate-valid next-open results have been segregated as **non_gate_valid_open_counterfactual_3.csv**; they are NOT official Gate entries.

NOC historical revision 260: Score85.6 MQ4 and estimated RR2.09, but $515.57 > $515 max entry. Following day's low $516.00 did not touch that cap: actionable no-trade. This demonstrates Score/MQ and R/R are necessary, never sufficient alone.

Historical 5 original Dropbox ORSNAP objects checked by R4: 3 decision_hash valid, 2 LMT mismatches; quarantine two LMT objects for immutable standalone evidence (hash mismatch does not prove tampering). Independent native sheet revision for original LMT BUY and Paper_Trades still exists; this report does not use mismatched LMT ORSNAP as a verified proof.

## Results/limits
- Gate-first historical documented advisory BUYs: 3 signals, 2 issuers.
- Immediate next-open MARKET purchase meeting zone: 0/3.
- Next-session intraday conditional resting limit touch: 3/3, no proven broker fills.
- Conditional limit 20D net outcome reference: mean -5.741%, 0/3 positive. This remains conditional, not realized P&L.
- Documented Pump/Dump+same FULL Gate BUYs: 0. Unknown P/D underwriting cannot be treated as FAIL.
- Exhaustive 3,035 symbol economic Gate backtest is unavailable without complete contemporaneous economic research/score/downside/entry decisions; do not manufacture historical buys or reuse current prices.

Artifacts: candidate_current_gate_census.csv (live Oct15 as-of only), original_buy_signal_ledger.json (original advisory IDs), non_gate_valid_open_counterfactual_3.csv (formerly nextopen ref, explicitly disallowed as full Gate purchases), gatefirst_documented_decisions_summary.json, QA_READBACK.json. For real executable limit scenarios, refer to R4 gate_first_limit_fills_3.csv. Production unchanged.
