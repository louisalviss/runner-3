# Pump/Dump R12 — price-only filter robustness (17 Oct 2026)

**Research SHADOW; no BUY or original Gate rules modified.** R9 captured 1,139 P/D events / 707 issuers from 15 originally valid US scan sessions. Of these, **951** event-date episodes have 5 regular US session future close within the historical data cutoff. The other **188 are right-censored**; no outcome is imputed. The full original issuer-level Score, MQ, valued bull/bear R/R, exact Entry and execution Gate were NOT recorded for all events, and cannot be retroactively certified.

R10 predefined (on historical as-of evidence, without future returns) a diligence priority of 34 events / 28 names using an SEC 8-K/6-K accepted <=168h before the original packet + two positive reported financial signs (net income and operating cashflow) + liquidity and volume. R11 read original economic mechanisms. R12 now tests whether this R10 triage actually outperformed.

## Mechanical next-opening price-only long outcomes

Every price-only result uses next regular US adjusted OPEN, close of the 5th subsequent regular trading session and **0.50 percentage point combined friction**. This entry can VIOLATE the original Entry Zone, and none is an actual Gate trade.

| Group | 5D matured N | Net 5D avg | Median | Win% | Relative to SPY |
|---|---:|---:|---:|---:|---:|
| Entire P/D source | 951 | -0.4823% | -1.097% | 44.48% | -0.9385 pp |
| R10 selected with SEC + profitable cashflows + liquidity | **30** | **-1.2871%** | -1.8357% | **33.33%** | -1.9400 pp |
| Not selected | 921 | -0.4561% | -1.0453% | 44.84% | -0.9059 pp |
| R10 selected PUMP | 15 | -3.0645% | -1.8924% | 33.33% | -3.6173 pp |
| R10 selected DUMP | 15 | +0.4903% | -1.4352% | 33.33% | -0.2626 pp |
| R10 selected without FPS | 27 | **-2.2386%** | -2.8293% | 29.63% | -2.8266 pp |
| R10 selected first event per ticker only | 24 | +0.0309% | -1.351% | 37.50% | -0.7893 pp |

Four R10 events lack an R9 matured 5D close (Oct09 ALHC, AVNT, BKD; Oct12 FICO) and are censored, not failures.

**Matched-date-and-direction:** Compare each of the 30 selected events to other P/D with the exact same original source session AND direction (Pump vs Dump), after outcome observation, without altering selection. All 30 have matched controls. Average selected minus contemporaneous control **-0.9473 pp**, mean of equal-day differences **-1.5071 pp**. Cluster bootstrap resampling 12 entire source dates (25,000 replications, RNG seed 20261017) produced observation-weighted 95% percentile interval **[-3.705,+1.477] pp**, containing zero. So it is NOT a statistically supported investable edge, positive or negative. Only 12 clusters, overlapping 5D windows and repeated issuers.

## Exploratory financial-sign hypothesis: NOT a registered historical Gate

The R9 as-of financial fields allow reporting-period NI and operating CF signs. They may represent quarter versus 6/9/12-month YTD and are not standardized TTM. Exploratory decomposition chosen AFTER seeing screen returns:

| Financial state | Matured N | 5D net avg | Win% |
|---|---:|---:|---:|
| Both net income and operating cashflow positive | 294 | +1.094% | 53.7% |
| Both negative | 286 | -2.323% | 37.4% |
| Mixed | 196 | -0.044% | 46.4% |
| Not comparable | 175 | -0.614% | 38.3% |

Positive NI+CFO compared to nonpositive episodes after controlling each original day AND Pump/Dump side yields **+0.3514 pp**, 25,000 day-bootstrap 95% **[-1.721,+2.785] pp**. The interval contains zero.

Most visually promising is positive-finance **DUMP**, N156: +2.2343% net 5D and 58.3% wins; compared with remaining DUMP N276: -0.9482%, 40.6% wins. After matching by same source day, effect shrinks to **+0.3949 pp**, 11 source days and 30,000 day-bootstrap 95% **[-2.648,+3.641] pp**. Repeated issuer first DUMP occurrence N140 yields +2.653%, but still no independent positive alpha proof. Requiring liquidity/volume among profitable DUMP N72 mean +1.313%, 51.4% wins.

Positive NI+CFO with a recent SEC 8-K/6-K N53 mean **-0.191%**; same financial signs without a recent 8-K/6-K N241 mean **+1.377%**. SEC form existence is NOT a bullish filter: earnings, equity financing, executive changes and one-off disclosures can all occur just before a dump.

## Decision and next valid experiment

- **Do not promote R10 SEC+positive-income+volume to live Gate**: no advantage is demonstrated in price-only observational replay, and it lacks issuer-valued downside / exact Entry / Execution.
- Keep positive-finance Dump as an exploratory research hypothesis only, selected posthoc. For a real test, freeze eligibility BEFORE a fresh, previously untouched sequence of market dates, then measure subsequent actual Gate decisions, spreads, limit fills, same-day DUMP controls and issuer caps. Existing 11–12 date-clusters cannot prove performance for year-round trading.
- Canonical Gate-first remains priority 1; Pump/Dump only priority-2 discovery, with unchanged full Gate. Original full issuer-date P/D Gate PASS/FAIL remains UNKNOWN for 1,139 events; verified P/D-origin Gate BUY_SIGNAL remains 0.

Artifacts: pd_34_5d_shadow_results_R12.json; pd_34_5d_shadow_matched_outcomes_R12.csv; pd_asof_financial_sign_exploratory_R12.json; pd_dump_profit_cfo_matched_R12.json; pd_R12_integrity_QA.json.
