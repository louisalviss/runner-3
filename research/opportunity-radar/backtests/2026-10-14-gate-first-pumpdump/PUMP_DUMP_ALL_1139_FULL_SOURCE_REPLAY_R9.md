# Opportunity Radar — complete 1,139-event Pump/Dump evidence sweep (R9, 2026-10-16)

Status: SHADOW research. No production scanner, economic Gate, Entry Zone, Execution Signal or paper-trading changes.

## Answer

The archived P/D source covers 1,139 observations of absolute 1D returns >=7% for 707 stocks over 15 timestamp-valid US sessions. **All 1,139/1,139 have been processed through historical market/liquidity data, original SEC filing timestamps, standardized GAAP financial availability, and next-executable-open price-only reference outcomes.** The older 326-event R8 sample is only a research-priority subset.

**0 event-date original complete Gate PASS are independently verified, 0 archived P/D-origin BUY are verified; 1,139 are UNKNOWN for original full Gate.** This does NOT mean 1,139 economic Gate failures or zero economically possible opportunities. No as-of complete Score, MQ, independent bull/bear fair value, realistic net R/R, approved Entry and venue snapshots were stored for every P/D event; raw price and financial source data alone cannot recreate them without inventing the subjective historical research. Original 12 prior Candidate dossiers predated each P/D event: 10 prior Scores<80; MRVL prior Score80.7/MQ4/RR1.7x, P prior Score81.8/MQ4/RR1.3x. Their stale previous scores cannot be used as at-P/D FAIL. Just 22 events across these 12 names, and 8 of the 326-priority episodes.

## Full market and SEC stage

| Historical evidence source | Events / names |
|---|---:|
| 1D P/D events checked | 1,139; 579 PUMP / 560 DUMP; 707 unique names |
| Research market cap >=$1B, 20D average daily dollar turnover >=$10M, price >=$5 | 797 events |
| Those market criteria + event volume >=1.5x 20D | 418 events |
| 5-session cooldown prioritized subset from earlier research | 326 episodes (301 names) |
| Current SEC symbol-to-CIK matched | 701 of 707 issuer names; six missing mappings |
| Prior annual/quarterly SEC financial report available at event | 1,119 events (some old) |
| Original 8-K/6-K accepted strictly within past 168 hours | 258 events |
| Four or more of six standardized US-GAAP financial groups fiscal-end <=185d old | 963 events |
| All six fields fresh | 725 events |
| Net income and operating cashflow positive | 336 events |
| Both negative | 365 events |
| Mixed positive/negative signs | 227 events |
| Missing or stale NI/operating CF comparison | 211 events |

The six financial groups are cash, assets, liabilities, revenue, net income and operating cashflow. These are **data availability and screening descriptors, not canonical Master/Entry Gate PASS**. Current CIK mapping cannot resolve all renamed/delisted tickers; standardized US-GAAP facts do not consistently represent foreign 6-K sources, which require manual primary-exhibit extraction.

SEC point-in-time: selected CompanyFacts data only if associated SEC 10-Q/10-K/20-F/40-F accession was accepted at or before the original source packet timestamp and underlying period ended by the P/D session. QA detected zero later-filed accession references.

## Price-only hypothetical next NYSE open, NOT Gate trading

Reference buy at the first NYSE regular-session 09:30 America/New_York open strictly after the original archived packet timestamp, then exit at the 1st/5th/20th regular-session close. Yahoo adjusted OHLC and matching SPY, subtract 0.50 percentage points round-trip cost. Price availability 703/708 chart series (707 stocks and SPY), 1,126/1,139 reference entries; five unavailable tickers. Last completed US session at audit capture (2026-10-16 01:57 UTC+07, Oct15 14:57 NY) is Oct14 2026. The cached Oct15 DAILY BAR WAS INTRADAY, therefore all Oct15 exits were discarded.

| Research cohort | Fully matured 5D observations | Mean 5D net | % positive | Excess vs SPY |
|---|---:|---:|---:|---:|
| All Pump/Dump | 951 | -0.482% | 44.5% | -0.938pp |
| Pump | 519 | -1.051% | 42.4% | -1.348pp |
| Dump | 432 | +0.201% | 47.0% | -0.446pp |
| $1B/$10M/$5 market filter | 689 | +0.414% | 48.2% | -0.096pp |
| Same filter + volume>=1.5x | 372 | -0.132% | 45.2% | -0.508pp |
| Prior 326-priority | 286 | -0.222% | 44.1% | -0.661pp |
| Positive NI and operating cashflow | 294 | +1.094% | 53.7% | +0.452pp |
| Negative NI and operating cashflow | 286 | -2.323% | 37.4% | -2.614pp |
| Recent original SEC 8-K/6-K | 217 | -2.529% | 35.9% | -3.006pp |

**Financial-sign hypothesis:** Positive minus negative group spread +3.417 percentage points per event over 5D. However, only 12 independent source dates matured; positive-group mean becomes -0.475% using equal weights for dates. In 12 matched dates, mean difference +2.726pp, 9/12 positive, cluster-bootstrap 95% CI **[-0.128,+5.449]pp contains zero**. One event per issuer and 2.5/97.5% winsorized checks are in the robustness JSON. Correlation, sector mix and ex-post grouping remain unresolved. Do NOT promote an entry rule on this basis.

Matured 1D: 1,126 cases, mean -1.438% net after assumed cost. Matured 20D: only 326 cases from four original source days, mean -0.356% after cost; 106 previous 20D exits dated Oct15 were prematurely marked complete and are now REMOVED. This is too concentrated to certify strategy profitability.

There is **no confirmed original Gate-compliant limit fill in these 1,139 rows**, because original numeric entry zones and execution-state evidence are missing. The price-only returns are not actual or paper trading P&L.

## Strict conclusion and remaining missing evidence

1. The original issue was procedural: earlier work processed the 326 priority subset and 12 existing Gate dossiers, not every P/D event. The full **1,139 source events and 707 names have now been screened**, financial fields checked and price-only outcomes calculated.
2. Four previously researched known acquisition cases ACVA/BWIN/PTC/RXO had below-2x R/R under explicit deal-break price reversion assumptions; this is research-scenario evidence, not a recorded original economic Gate failure.
3. Full as-of economic Gate cannot be reconstructed by calling SEC earnings, a 7-day 8-K or past price movement a Score/valuation. Missing contemporaneous issuer-level thesis, bull/base/bear equity values, MQ, Score, price-specific R/R, numeric Entry Zone, catalyst publication time, event blackout and approved execution source must remain **UNKNOWN**.
4. Next test must be prospective immutable per-event full-Gate snapshots or explicit NEW shadow underwriting of each event, separately identified as a new experimental strategy rather than fabricated old Gate. Keep unchanged Gate-first primary intake and P/D secondary intake; never create BUY from a proxy.

## Exact durable artifacts

- PD_ALL_1139_GATE_EVIDENCE_MATRIX.csv — all 1,139 event/market records and older dossier provenance.
- PD_ALL_1139_SEC_PIT_SOURCE_COVERAGE.csv — public SEC accepted filing/source links.
- PD_ALL_1139_ASOF_FINANCIAL_GATE_INPUTS.csv — six SEC as-of fields, reporting fiscal ends and accessions.
- PD_ALL_1139_NEXTOPEN_PRICE_ONLY_OUTCOMES.csv — hypothetical next NYSE open, adjusted 1D/5D/20D, matured dates and SPY comparisons.
- PD_ALL_1139_*SUMMARY.json, PD_ALL_1139_FINANCIAL_AB_ROBUSTNESS.json, PD_ALL_1139_INTEGRITY_QA.json.
- Public-source caches (gzip) for additional 406 submissions/400 facts/708 OHLC, plus original 301 ticker archives already tracked.
- replay_pd_all_1139_prices.py for the fixed-source-period Yahoo collection; all price and SEC decisions remain research-only.

**Zero production or trading mutations.**
