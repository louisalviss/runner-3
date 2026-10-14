# Gate-first Radar — refreshed as-of financial filter (2026-10-14)

Status: SHADOW research, no original BUY_SIGNAL/Score/RR/Entry change. Price-move research cohort only: 326 Pump/Dump episodes across 301 unique securities drawn from 15 timestamp-valid US sessions. Main Gate-first lane continues across the full universe independently of Pump/Dump.

## PIT data hygiene
Original SEC CompanyFacts values match accession of an SEC report accepted before the source packet, with filing period end no later than detection. For reported net income and operating cashflow, suppress stale periods >185 days old relative to source session. Latest cashflow can be 3/6/9/12-month YTD; we only compare SIGN, never confuse reported amounts with quarterly or TTM. Bank/fintech and pre-revenue biotech require specialized methodology. Cash alone omits marketable securities and is not sufficient to infer biotech runway. Rough market-cap-to-annualized-revenue in companion CSV is a RESEARCH PROXY, not fair value.

As-of reported sign classes: 134 positive NI AND CFO, 78 negative NI AND CFO, 60 mixed, 54 uncomparable/missing.

## Ex-post 5D comparison (not trading strategy results)
Reference buy = next NYSE opening after source timestamp, sell = close of trading session 5, deduct 0.50 percentage points roundtrip:

- Positive net income and operating CF: N117, mean +0.879%, median +0.174%, 51.3% winning, average excess SPY +0.291pp.
- Negative net income and operating CF: N68, mean -2.650%, median -1.934%, 30.9% winning, average excess SPY -3.036pp.
- Mixed signs: N52, mean -0.316%, win 46.2%.
- Uncomparable/missing: N49, mean +0.620%, win 42.9%.

Raw difference positive minus burn +3.529pp. One event per issuer: N111 +0.820% versus N65 -2.756%. Winsorize whole sample 2.5%/97.5%: means +0.556% versus -2.305%. DATE-MATCHED 11-day mean gap +1.594pp, 8/11 days positive, 95% day-cluster bootstrap percentile [-0.857,+4.531]pp INCLUDES ZERO. Mature samples concentrated in September; October contributes only one source day. These data do not support any rule promotion.

Positive NI/CFO by move sign: Pump N58 mean +0.296%, Dump N59 +1.452%. Negative NI/CFO: Pump N34 -2.469%, Dump N34 -2.831%. These are correlated, non-independent observations and cannot establish out-of-sample edge.

## Nearby SEC form presence is NOT an economic catalyst Gate
Among 326 episodes, 89 had an 8-K/6-K accepted in prior seven days, but filing presence is not a verified economic driver. Joint exploratory groups:
- Recent 8-K/6-K plus positive NI/CFO: 30 events; 5D mature N27, mean -2.003%.
- Recent 8-K/6-K plus other/unknown finance: 59; 5D N54, mean -2.424%.
- No recent filing plus positive NI/CFO: 104; 5D N90, mean +1.744%.
- Remaining: 133; 5D N115 mean -0.308%.

A presence-only SEC item trigger is NOT a good proxy for BUY. Must inspect original filing relevance, upside/downside and completed Entry.

## Original full Gate decision
Prior original BUY_SIGNAL: LMT once and LHX twice (3 paper signals, only 2 underlying issuers); NO verified historic Pump/Dump-sourced full-Gate BUY. Pump/Dump rows without time-correct complete catalyst/valuation/MQ/RR/venue stay UNKNOWN, not FAIL, and are not backfilled as BUY. Previous transaction-price scenario ACVA/PTC/RXO illustrative R/R <2 is not a historical recorded Gate result. No change to production/strategies, no sealed OOS accessed.

Next: inspect original SEC Item 1.01/2.02/8.01/7.01 to confirm actual causal economic event; build conservatively priced bullish/base/bear cases using contemporaneous original financial history for candidate cohort, require Master and Entry Gate unchanged, then validate independent later sessions before promotion.

Files: asof_fundamental_quality_AB_326.csv, fundamental_market_response_AB_326.json, asof_sec_edgar_index_326.csv, original as-of SEC companyfacts and historical price snapshot files.
