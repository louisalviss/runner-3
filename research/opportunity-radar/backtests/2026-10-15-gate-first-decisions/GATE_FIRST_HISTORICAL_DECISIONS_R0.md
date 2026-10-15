# Opportunity Radar — Gate-first historical decision audit (15 October 2026)

**SHADOW RESEARCH.** Gate-first always comes FIRST across eligible issuers, whether or not any Pump/Dump is present. Pump/Dump is SECONDARY discovery and never substitutes for the same original Hard Persist, Master Score, MQ, net RR>=2, Entry and Execution Gate. No production change.

## Historical sources and coverage

1. Native Google Sheet Opportunity Radar V2 Drive has **159 version-history revision metadata records**, Aug09–Oct15. Only selected revision export bodies were accessed, NOT the complete 159-revision replay (rate-limited). Revision 270 captured original LMT BUY Sep10 17:52 +07, revision 291 original LHX BUY Sep15 10:42 +07, revision 293 original LHX BUY Sep16 09:14 +07. Each revision was timestamped after the BUY but before the next market session was lost. Revision 298 Oct04 still retained all three paper IDs.
2. Current Oct15 Candidates: **43 rows for 43 unique ticker symbols**. Score>=80 and MQ>=3 currently 7 symbols (**LHX, NOC, LMT, RTX, MRVL, P, SPXC**); all seven NOW have Entry NOT_READY, zero current BUY_SIGNAL. A CURRENT state cannot be backdated to previous triggers.
3. Original Paper_Trades has 3 advisory BUY event IDs, 2 distinct issuers, both LHX entries overlapping and correlated. Paper marks represent prior US session closing reference, NOT real executed orders.
4. Historic Git price prefilter: 15 complete timing-valid sessions, 3,035 symbols, 41,244 symbol-session price observations. No original PIT Score/MQ/catalyst, two-sided valuation, price-specific R/R, approved execution venue or Entry Gate for each of 3,035 symbols. **Unobserved full Gate = UNKNOWN, NOT FAIL**. The 43 curated rows cannot stand for 3,035 issuer economic underwrites.

## Original paper BUYs replayed with a tradable-time reference

Signal timestamp precedes US 09:30 New York opening; next actual US regular-session adjusted OPEN is reference entry. Exit at 1D/5D/20D session CLOSE, subtract assumed total 50bps, compare SPY over matching interval:

| Signal +07 | Issuer | Next entry | Net 1D | Net 5D | Net 20D | 20D excess vs SPY |
|---|---|---|---|---|---|---|
| Sep10 17:52 | LMT | Sep10 $526.01 | +0.281% | +1.637% | **-5.593%** | -8.379pp |
| Sep15 10:42 | LHX | Sep15 $251.90 | -1.389% | -2.473% | **-5.919%** | -8.538pp |
| Sep16 09:14 | LHX | Sep16 $250.07 | -0.232% | -4.571% | **-6.638%** | -9.330pp |

Mean net 5D **-1.802%**, mean net 20D **-6.050%**, mean 20D excess vs SPY **-8.749pp**, 0/3 positive at 20D. Only **two independent companies**, correlated signals; not a statistically tested edge. With 10% original-capital weight per virtual signal and uninvested remaining 70%, summed 20D labels imply -1.815% of starting capital, **NOT actual time-aligned portfolio NAV** because exit dates differ, positions overlap and there are no broker fills.

Original BUY_SIGNAL lane was Deep Bottleneck (Gate-first). No historically documented P/D-origin plus FULL-Gate BUYs, but this does not prove all other unknown P/D candidates would fail if PIT inputs existed.

## Correct inference and next dependency

Source reconstruction now supports a **verified historical decision BUY ledger**, not an exhaustive full economic Gate backtest over all 3,035 issuers. Reusing current Gate scores/entry status for all past days or calling all other source-price tickers rejects is invalid. A proper test requires immutable snapshot at every detection of original as-of documents, catalyst thesis, score, MQ, bull/base/bear valuation, net RR, entry zone, binary blackout, venue and model version. Then replay exact BUY transitions and use next executable NYSE prices with matched SPY and capital allocation; measure incremental P/D+Gate without weakening Gate. Use untouched later sessions for independent validation.

Saved data: candidate_current_gate_census.csv (Oct15, NOT historical), original_buy_signal_ledger.json, historical_buy_nextopen_returns_3.csv, gatefirst_documented_decisions_summary.json and QA_READBACK.json. NO edits to live Candidates, Paper_Trades, Gate, scan top80 or production.
