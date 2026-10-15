# Pump/Dump ALL 1,139 — as-of SEC original documents and R/R hurdles (R10)

**16 October 2026 — SHADOW. No production Gate, Entry, or Paper_Trades changes.**

R9 already processed **1,139/1,139** original market events (707 symbols; 579 PUMP / 560 DUMP), merging PR422 and fixing a still-open US bar in PR425. R10 adds the original SEC source-text evidence and mathematical R/R hurdle for the complete population.

## Original SEC source, exactly before original packet

258 of the 1,139 events (206 issuers) link to an SEC 8-K or 6-K accepted **within the strictly previous 168 hours**. Their documents total 222 distinct original SEC URLs: **222/222 HTTP 200**. Original bytes hashed SHA256. 881 others had no 8-K/6-K in this specific window, which does **not** imply absent catalysts. Machine nonexclusive keyword leads across 222 documents: acquisition/agreement 23, contract heading 36, earnings/guidance 12, debt 20, equity financing 9, FDA/trials 4, management 32, administrative 164. Legal boilerplate may match any of these: document presence is NOT economic or causal verification.

## Reverse 2x R/R target sensitivity, not a stock valuation

From a purely hypothetical next US market OPEN E, assumed 0.5 percentage point friction and independently assumed downside fraction d, 2x net R/R requires target at least **E*(1.005+2d)**. Generic bear losses 10/20/30% imply **1.205E / 1.405E / 1.605E** bull targets. This mathematics was completed on **1,139/1,139** events; a true valuation, numeric live Entry Zone and fill have NOT been verified.

For 571 of the 579 PUMP events where the implied pre-PUMP price lies below the next US open, using **reversion to that price as a technical bear scenario only** yields required bull upside: <10%:31; 10–20%:331; 20–30%:151; 30–50%:48; 50%+:10. Other eight Pumps could not use that scenario. For DUMP, the previous close may be recovery upside, NEVER downside. Next-opening prices were available for 1,126 events. None of these algebraic targets is a proven fundamental fair-value estimate.

## Narrow research queue and remaining Gate evidence gap

Without using future returns, SEC filing within 168h + as-of positive net income AND operating cashflow + source-liquidity/volume filter gives **34 issuer-date observations across 28 names**. Four involve Form 8-K Item 1.01, eight Item 2.02 without Item 1.01, six Item 8.01, other sixteen elsewhere. This is a **due-diligence queue**, NOT Gate passes, and can include previously stressed deals with R/R below 2x. Needed next: issuer-specific true economic catalyst and timing, new aftertax cashflow less funding/warrant dilution, independently derived bull/base/bear value, Score/MQ, realistic priced RR, original Entry Zone, market-hours and Execution.

**Original P/D-full-Gate BUY verified = 0; original complete at-event economic Gate PASS/FAIL outcomes = UNKNOWN on all 1,139.** Missing historical issuer valuation and decision snapshots cannot be manufactured from SEC filing presence, daily changes, or today's revised valuations. Three actual old BUY_SIGNALs are LMT and LHX twice, with no documented P/D sourcing.

Price-only R9 outcome (NOT trading strategy P&L): fifth-session reference mean **-0.482%** on 951 matured events after 0.5% friction (PUMP N519 mean -1.051%, DUMP N432 +0.201%). The synthetic opening ignores execution Gate and cannot prove alpha.

Artifacts: pd_original_sec_222_docs_R10.json, pd_original_sec_filing_event_join_258.csv, pd_original_sec_222_summary_R10.json, pd_reverse_rr_frontier_all1139_R10.csv, pd_reverse_rr_frontier_all1139_summary_R10.json, pd_diligence_queue_34_R10.csv, pd_diligence_queue_summary_R10.json, pd_R10_integrity_QA.json.

Production, user real trading, Gate rules and source Paper_Trades unchanged. Gate-first universe primary; P/D discovery secondary with identical Gate.
