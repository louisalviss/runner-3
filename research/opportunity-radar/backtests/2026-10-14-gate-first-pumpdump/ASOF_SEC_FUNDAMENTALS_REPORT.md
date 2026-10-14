# Radar: PIT SEC financial audit — 14 October 2026

Status: **NON-TRADING SHADOW research. No original Gate PASS or BUY_SIGNAL added.**

## Scope, hierarchy and as-of data
Gate-first considers all issuers with verified economics whether or not price is moving. Pump/Dump is SECONDARY discovery and must pass the SAME Hard Persist, Score >=80, MQ>=3, current net R/R>=2, numeric Entry Zone, binary risk blackout and viable venue to emit an advisory BUY_SIGNAL.

Original US market price universe: 15 timely complete snapshot sessions, 3,035 distinct symbols, 41,244 symbol-sessions; 1,139 daily Pump/Dump events on 707 symbols. Liquidity/volume/date de-duplication *for research priority only* produced 326 events across 301 symbols. The priority cut is not an official trading Gate and MUST NOT exclude Gate-first candidates.

SEC Edgar: 301/301 submissions + CompanyFacts downloaded. At an episode cutoff, each XBRL selected fact must belong to a report SEC ACCEPTED by that exact timestamp, with filing accession matched and report period ending no later than the source session. In 2,757 chosen fact-field entries: **0 future acceptance or period end leaks**. SEC historical snapshots are keyed by accession to prevent using facts from later restatements. Future 8-K/6-K within 3 days of the packet were excluded from input (19 episodes).

Data coverage out of 326 episodes: 325 with an earlier SEC financial report and 89 with some 8-K/6-K accepted in the preceding 7 days; 295 have >=4 out of 6 key financial fields, 2 have 3, 29 have zero. Field counts: cash296, assets297, liabilities254, equity292, revenue277, net income294, operating CF295, capex258, operating income282. Missing standard XBRL tags can reflect different reporting schemas; no presumption of Gate failure.

## Historical discovery triage, NOT Gate approval
- A: Nearby 8-K/6-K of any type + >=4 key financial groups: 73 episodes (39 Pump/34 Dump). Corporate filings are only potential leads, not guaranteed causative catalysts.
- B: Financial groups available but no nearby 8-K/6-K: 222.
- C: Incomplete standardized financial extraction: 31. Needs original 6-K/20-F and supporting financial statement extraction.
- Signed 2026 ACVA, PTC, RXO M&A examples have current deal-break scenario R/R substantially below 2x; these are research failures under specified assumptions, not backdated original production Gate classifications.
- Separate dated primary checks for XENE, VKTX, PCVX, GRAL are still UNKNOWN for current price-specific upside/downside and/or near-binary-event blackout. All unreviewed entries remain UNKNOWN.
- Latest reported net income + operating cash flow are both positive in 149 episodes, both negative in 80, mixed in 65, unavailable one/both in 32. Periods may be fiscal quarterly, YTD or annual; figures are **not standardized TTM** and can be economically incomparable. This is an exploratory data diagnostic, NOT quality Score/MQ.

## Hindsight outcomes diagnostic — not real buys
Research-only: next NYSE session adjusted OPEN to h-th close, reference 50 basis points roundtrip costs. 1D N315 mean -0.828%; 5D N286 mean -0.222%; 20D N86 mean +4.803% across only THREE start dates. Nothing here can qualify an original missing Gate decision.

Positive-reported-net-income AND positive-reported-operating-CF group: 5D N129 mean +0.852%, mean SPY excess +0.293 percentage points. Other/missing N157 mean -1.104%, mean SPY excess -1.444pp. When matching source dates, average group difference is just +0.705pp across 12 dates; simple 20,000-repeat date-level bootstrap percentile interval [-1.141,+2.467]pp includes zero. Selection is post-hoc and correlated; NOT proven alpha, NOT fit for promotion.

Nearby SEC-filing subset A N66 mature: mean 5D -2.425%; its positive-income/CF subgroup N33 mean -1.834%, confirming a nearby SEC report by itself is not a bullish filter. A positive-income/CF Dump N16 mean +1.183%; equivalent Pump N17 mean -4.675%. Tiny cohorts with no sealed independent OOS.

**Decision:** No certified new Gate PASS. Do not lower R/R, modify original historical BUYs, equate missing metrics with failure, or auto-place trades. Existing 3 documented Gate-first historical BUY_SIGNAL (LMT and 2 LHX) remain the only verified historical paper advisory entries; Pump/Dump plus Gate remains 0 verified historical entries.

## Files
- asof_sec_edgar_index_326.csv and asof_sec_summary.json: filings/times and leak exclusions.
- asof_sec_submissions_301.json.gz: original SEC acceptance/accession snapshot, compressed.
- asof_sec_companyfacts_compact_301.json.gz: raw extracted companyfacts tag series, compressed.
- asof_financial_fields_326.json: accession-scoped original-tag PIT facts.
- asof_fundamental_priority_queue_326.csv and asof_fundamental_priority_summary.json: 73/222/31 queues.
- asof_financial_5D_robustness.json: point-in-time diagnostic and 12-day matched uncertainty.

Next stage: inspect original 8-K/6-K text and exhibits for group A, establish relevance of catalyst to the price move, and model true bull/base/bear downside and R/R at the executable price using original known facts. In parallel keep the Gate-first lane alive across non-moving stocks; Pump/Dump is only a supplement.
