# Opportunity Radar — R3 original SEC interim report recovery (2026-10-15)

**SHADOW only.** Gate-first primary, Pump/Dump+same Gate secondary. No production gate, paper, or BUY change.

## Scope and source controls

A historical 326-episode Pump/Dump research cohort of 301 tickers had 14 date-ticker events (12 companies) where at least four original standardized US-GAAP fields appeared present, but four recent core fields could not be verified (<185 days since fiscal end). This is not a valid fundamental FAIL.

Recovered **14/14 event-time primary financial documents**, **13 unique SEC documents**, and **44 source-audited numeric entries**. All source filings accepted by SEC before the original market packet; original HTML hash verified for all 13. Of 44 number checks, 42 textual matches plus two explicit normalizations: NBIS negative net loss appears as parentheses, and ARCO 1.3 billion equals approximately 1,300 million. No hidden future reports, no empty fields treated as zero. Each number has its SEC document source URL, time, unit and period in asof_interim_sec_primary_recovery_14.csv; QA in asof_original_sec_recovery_QA_R3.json.

## Example recovered Q2 / H1 data from original exhibits

- ODD Sep11: Sept09 6-K exhibit Q2 revenue ~$181m, NI $13m, June company cash $167.274m. Combined ~$561m cash and investments is not all cash.
- TEN Sep11: May23 6-K exhibit **Q1** net income $89m, operating CF $97.181m; a later Sep18 Q2 report cannot be used here.
- NVMI Sep14: Aug06 6-K Q2 revenues $254.958m, NI $75.010m, CFO $40.918m, cash $124.846m.
- CAMT Sep14: Aug10 6-K Q2 revenues $133.2m, GAAP NI $23.3m, CFO $12.2m. $815.8m reported as cash/deposits/investments combined, not cash alone.
- BULL Sep16: Sep12 6-K Q2 revenue $198.831m, NI $24.343m, company cash $701.621m. Separately segregated customer cash is not deployable.
- GENI Sep18 and Sep25: Aug06 6-K interim exhibit confirms June company cash $155.076m; revenue/NI/CFO remain unverified in this batch.
- ZTO Sep21: Aug19 6-K USD translated Q2 revenue $2,144.4m, NI $453.6m, CFO $672.6m, June cash $1,460.096m; do not mix RMB with translated USD.
- NICE Sep21: Aug05 6-K Q2 revenue $782.3m, NI $83.2m, CFO $122.7m, June cash $315.384m.
- TEN Sep23: Sep18 6-K H1 NI $234.743m, H1 CFO $281.2m, June cash $463.989m; not quarterly flows.
- NBIS Sep24: Aug13 6-K Q2 revenue $582.3m, Q2 NI **loss $190.4m**, H1 continuing-operations CFO $4,504.1m, June cash $8,042.1m. Q2 loss and H1 CFO are NOT matching-period evidence; keep research-finance sign UNKNOWN, not mixed.
- ARCO Oct05: Aug13 6-K Q2 revenue approx $1.3bn, NI $45m, June cash $259.990m.
- FUTU Oct05: Aug20 6-K Q2 USD translated revenue $918.2m, NI $464.4m, issuer cash $2,343.911m; cash held on behalf of clients is NOT corporate free liquidity.
- HUM Oct09: Jul29 original 10-Q Q2 revenues $40,867m, NI $693m, June cash $6,893m, despite missing standardized Q2 CompanyFacts keys.

## Financial class and return A/B, after stricter period matching

Six issuer-session events now have verified same-period positive NI AND positive CFO (TEN Sep11 Q1, TEN Sep23 H1, NVMI, CAMT, ZTO, NICE). NBIS has mismatched NI/CFO intervals and remains UNKNOWN. This corrects a temporary assumption that there were seven new comparable cases.

Of 326 episodes, original sign research class count was 134 positive, 78 loss+burn, 60 other mixed, 54 missing. After original source recovery: **140 positive, 78 burn, 60 mixed, 48 missing/noncomparable**.

Hypothetical reference only: next NYSE open to day-5 close, deduct 0.50 percentage points roundtrip; NOT Radar BUY trades:
- Positive finance originally 117 matured, net 5D +0.879%; after recovery **123 matured, +0.974%**.
- Negative finance unchanged 68 matured, net 5D **-2.650%**.
- Raw difference +3.624pp, but **11 date-matched mean difference +1.581pp and day-cluster bootstrap 95% [-0.917,+4.489]pp includes zero**. Unsealed retrospective observation; no positive trading alpha established.

## Decision

Do not automatically reject issuers due to standardized CompanyFacts omissions. A future reader must seek contemporaneously accepted 6-K/10-Q original interim or exhibits, verify fiscal period and currency, separate client funds, and only then perform original Master Score, MQ, catalyst, valuation, independent downside, net R/R and executable Entry checks. **No original P/D+complete Gate BUY verified, no Gate rule promotion, no portfolio P&L created.**

Companion machine files: asof_interim_sec_primary_recovery_14.csv, asof_original_sec_recovery_QA_R3.json, asof_primary_recovered_financial_ab_r3.json. Original SEC URLs and hashes per CSV row.
