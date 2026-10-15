# Gate-first R7 — Historical ENTRY_READY to executable-signal gap

READ-ONLY research. No production Gate, scanner, scheduling, paper trades or BUY_SIGNAL changes. Gate-first stays primary; Pump/Dump is secondary sourcing to the exact same Gate. This is not a full 3,035 issuer economic Gate backtest.

## Source coverage
Native Drive file metadata: 159 revisions from Aug09–Oct15 2026; previously audited 10 distinct version bodies in R6, plus 10 additional original version bodies in R7, or 20 DISTINCT versions total. 139 not yet exported. All source revision ID/timestamps and key LMT/LHX/NOC Gate states are in gatefirst_revision_extra_10_originals.json (IDs 218,230,240,247,249,251,273,282,294,297), and gatefirst_extra10_symbol_transitions.csv. Retained BUY and EXPIRED values in later versions are NOT automatically new signal events; latest revised entry states must not be carried backward.

No new distinct original BUY in this sample: three historical advisory BUYs already known (LMT Sep10, LHX Sep15 and Sep16) for two issuers. Two LHX signals overlap.

## Closed-session Entry Ready: possible missed Monday live recheck

Original Drive revision 282 (modified 2026-09-12T02:55:58Z):
- LHX Score85.8, MQ4, conservative R/R about 2.65x at Fri Sep11 source mark $245.54, Entry READY in $245-$250 preferred zone.
- Execution remained NONE because market CLOSED and eToro quotes DELAYED; required live executable price validation unavailable. This fail-closed choice was correct at that time.
- Next regular session Mon Sep14: Yahoo daily regular-session OHLC open $247.81, low $245.77, high $250.27, close $248.93. Monday opening was INSIDE the numeric zone and low also touched. A fresh market-open recheck could have evaluated the unchanged full Gate then.
- No Google Sheet revision was recorded between Sep12 (rev282) and Sep15 (rev291); the next archived original LHX BUY_SIGNAL is timestamped Sep15 10:42 +07, i.e. after the Mon Sep14 US regular session. No archived original BUY before Monday opening.
- Classification: POTENTIAL_MISSED_LIVE_RECHECK, not MISSED_BUY. Daily OHLC never proves eToro live price, event blackout, execution context, broker acceptance or actual fill.

At that Mon open $247.81, merely REUSING the last documented $300 base target / $225 bear from the Sep12 record would mechanically yield ~20.560% remaining upside after 50bps and ~9.205% bear-price downside, hence ~2.234x R/R; this is still above 2x. This is a mathematical consistency test of the unchanged last-known assumptions, NOT an independently refreshed valuation or certified live Gate at Sep14. No fresh eToro execution quote is archived.

For diagnostic context ONLY: hypothetical long Sep14 open $247.81, exit fifth US regular-session close, 50bps roundtrip = -0.710%; 20th close = -4.874%, SPY-relative 20D = -7.707 percentage points. NON-EXECUTED and NON-GATE-AUTHORIZED price-only counterfactual. Do not count this as a backtested Radar purchase.

## Other no-touch gate checks

NOC Sep08 cap515 vs low515.06 (miss $0.06); LMT Sep08 cap525 vs low531.37 (miss $6.37); NOC Sep10 cap515 vs low516.00 (miss $1.00); NOC Sep11 cap515 vs low515.25 (miss $0.25); NOC Sep14 cap515 vs low521.01 (original RR below 2x); LMT Sep14 cap525 vs low525.43 (miss $0.43, prior BUY expired and no new BUY). All are NO NEW TRADES and must not be counted as fills.

Entry-Ready only and intraday-cap touch DO NOT establish original BUY. The 7 session checks are in entry_ready_unissued_next_session_7.csv. R4 authoritative original three execution-signal conditional price-limit simulations remain: 3 potential OHLC cap touches but zero confirmed broker fills and mean 20D -5.741% after 50bps, 0/3 winners from only two issuers.

## Candidate next design (not deployed)

A next-NYSE-open shadow verification trigger for a closed-session Entry-Ready issuer could reduce false negatives: once market genuinely opens, re-evaluate fresh validated live venue/quote/spread, strict zone, R/R at executable price, canonical version, thesis/invalidation, binary blackout, MQ/Score and actual execution authorization. Never auto-buy or resurrect an expired old signal without a new complete Gate pass. Sep14 LHX is a regression fixture, NOT justification to loosen Gate or claim missed profit.

R6 fail-closed archived ORSNAP classifier still quarantines 2 invalid source hashes out of 5 original objects; 3 hash-valid objects had NO execution BUY. Neither repair the original objects nor manufacture any new trades.

Research-only artifacts: gatefirst_revision_extra_10_originals.json, gatefirst_extra10_symbol_transitions.csv, entry_ready_unissued_next_session_7.csv, QA_REVISION_R7.json.
