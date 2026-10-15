# Pump/Dump vs original Gate — R8 as-of research audit (16 Oct 2026)

Status SHADOW; no changes to scanner, Entry, BUY_SIGNAL or Paper_Trades. The user asks which Pump/Dump tickers passed the unchanged Gate, NOT a general Gate-first study.

## Direct answer and important uncertainty
Original time-valid market data: 15 US source sessions, 3,035 symbols, 1,139 1D abs>=7% P/D observations across 707 unique tickers.
Of 707, 12 ticker names have old economic Gate Candidate dossiers (22 P/D events): 10 dossier scores below 80, MRVL prior Score80.7/MQ4 and RR1.7x, P prior Score81.8/MQ4 and RR1.3x. No original documented P/D-to-BUY transition. But EVERY one of these dossiers was last evaluated before the later Pump/Dump event: NONE can be treated as re-priced, as-of-event original Gate PASS or FAIL. Other 695 ticker identities lack old full economic Gate dossiers entirely: UNKNOWN, not FAIL.

In the 326-event, 301-ticker liquidity-priority P/D research subset, only 8 events / 7 tickers have pre-event Gate dossier. 318 do not. There are **ZERO independently VERIFIED original as-of-P/D-event full-Gate BUYs** and ZERO complete original Score/MQ/price-specific RR/Entry/Execution records proven to cover all 326 event dates. This is an evidence gap, NOT proof of zero possible true passes.

## Better evidence join, with date discipline
Reproducible read-only Python source-data join covered all 326 episodes. An original SEC 8-K/6-K accepted no later than the original scan packet was recorded for 89 episodes. Positive, reasonably recent, reported net income and operating cashflow alone are not enough to buy. Six positive cashflow+NI signs recovered previously from the original Form 6-K sources in R3 are included, to avoid rejecting foreign issuers merely because US-GAAP CompanyFacts data omitted them.

Research queues, NOT official Gates (hypothetical BUY next US OPEN, exit 5th regular CLOSE, subtract 50bps roundtrip):
- A: SEC 8-K/6-K within 7d AND positive NI+CFO: **32 episodes, 29 matured, mean -1.879%**. Among the 318 absent-original-dossier cases, 31 such events, 30 issuer names; before original interim 6-K restoration the count was 29. Pump cohort A: N14, mean -5.551%; Dump A: N15, +1.547%.
- B: recent SEC filing but other/missing comparable finance: 57 events, N52 matured, -2.509%.
- C: positive NI+CFO but no recent 8-K/6-K: 108, N94, +1.854%. This does NOT establish an investable edge: the economic catalyst has not been validated and it is retrospective/cohort-correlated.
- D: remaining evidence gap: 129, N111, -0.475%.
- Entire 326 episode pool: 286 matured, -0.222%.

These price-only returns DO NOT obey a particular original Entry Zone/limit-fill nor certify an economic Gate PASS. Research selection itself is post-hoc, the event source days number only about 12 for matured five-day periods and positions are not independent. Future returns were never used to assign a historical Gate decision.

## Actual original SEC documents: important issuer cases
- ENVA Sep15 DUMP: withdrawal of bank-regulator applications for the proposed Grasshopper Bancorp acquisition. A source was published; not a certified positive valuation.
- GNRC Sep17 PUMP: Amazon generator supply agreement, expected $2.4bn of initial 2027-28 gross deliveries and contingent share warrants. Under a disclosed pre-Pump-price downside proxy and 50bps cost, next OPEN $209.52 would require independent bullish value at least ~$279.39 (about $4.12bn total uplift) to obtain 2x R/R. Contract gross sales alone cannot prove that valuation. Gate UNKNOWN.
- INOD Sep22 PUMP: nearby 8-K concerns independent director appointment, not proof of source for P/D; SEC-present filter is a false catalyst proxy.
- GLW Sep14 DUMP: up-to-$2bn at-the-market common equity capacity, NOT proof all shares issued.
- PBF Sep14 DUMP: announced intention for $500m exchangeable notes, debt/refinancing sensitivity.
- ARM Sep14 DUMP: nearest 6-K AGM voting results; not proven cause.
- BOOT Sep15 DUMP: reaffirmed Q2 outlook near high end, no independent price target.
- PAYX Sep23 DUMP: original quarterly results, valuation sensitivity unverified.
- ACAD Sep24 DUMP: original RADIANT clinical updates need probabilistic efficacy/approval economics and downside.
- CHRW Oct05 DUMP: RXO merger buyer, valuation needs synergistic integration and financing costs.
- DELL Sep11 PUMP: debt underwriting disclosure, not equity valuation proof.
- M Sep11 PUMP: quarterly earnings announcement, no certified price-specific 2x RR.

Previous source-reviewed ACVA/BWIN/PTC/RXO deal-break scenario R/R fell below 2x under explicit price reversion assumptions. These are research scenarios, NOT historical original Radar FAIL records.

## Verdict and next check
Exactly 0 VERIFIED P/D-origin Gate BUY from available records, but 326/326 priority events lack original completed full economic Gate at-event decision certification; preserve UNKNOWN. Cashflow and an SEC filing cannot replace an issuer-specific contemporaneous priced bull/base/bear target, valuation version, MQ/Score, numeric Entry, market hours/blackout and independent execution verification. A future pipeline should capture full PIT Gate snapshots for every ticker the scanner promotes.

Saved sources:
- replay_pd_gate_evidence_20261016.py, offline reproducible source join.
- pd_gate_asof_research_matrix_326.csv, per-event evidence & source availability.
- pd_gate_asof_research_summary_326.json, checked counts.
- pd_gate_asof_price_only_5d_research.json, observational 5D counterfactual.

No P/D market trades or approval created.
