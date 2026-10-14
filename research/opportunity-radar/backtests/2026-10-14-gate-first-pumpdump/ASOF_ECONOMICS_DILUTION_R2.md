# Radar R2 — Gate-first economic stress and PIT freshness (2026-10-15)

**Status: SHADOW research, no production changes.** Gate-first can BUY with no P/D, and P/D remains a secondary source of possible candidates. An event with enough data to compute a hypothetical downside is NOT equivalent to an original historically approved Master/Entry/Execution Gate, and no BUY_SIGNAL is created in this report.

## Dataset hygiene: material correction before economic gates

Historical 326 liquid, volume-abnormal P/D episodes, 301 companies. Data from accepted SEC CompanyFacts accessions and company 8-K prior to archived market packet. Previous audit reported 295/326 with at least four of six core financial fields present. But "present" includes stale data. **108/326** episodes contain at least one selected SEC field whose period end is **more than 185 days** before signal; debt_long=59, cash=15, assets=14, liabilities=18, equity=26, revenue=17, net_income=20, CFO=16, capex=36, operating_income=19 stale observations (fields can overlap). Examples: HPE liabilities from 2018 and MGY liabilities from 2018, which cannot be joined with June 2026 cash. Requiring four **fresh** fields among cash, assets, liabilities, revenue, net income and operating cashflow leaves **281/326**, not 295; 14 previously "present" cases fail the stronger freshness test, 45 total lack four fresh fields. Financial absence/staleness = **UNKNOWN / needs refresh**, never economic FAIL.

Prior "positive NI + CFO" vs "negative NI + CFO" 5D research check already guarded **both signs by <=185d freshness**: comparison remains **+0.879% N117** vs **-2.650% N68** after assumed 50bps; matched 11-source-date bootstrap CI [-0.857,+4.531]pp includes zero. Not a gate or investable positive alpha; all these signed NI/CFO cases fall inside 281 with >=4 fresh core fields.


### Do not equate stale extracted fields with stale company reporting

The 14 episodes that drop below the 4-of-6 fresh-core threshold are NOT confirmed to lack newer company disclosures. Thirteen are foreign-issuer observations with newer Form 6-K interim filings not covered by standardized US-GAAP CompanyFacts (ODD, TEN, NVMI, CAMT, BULL, GENI, ZTO, NICE, NBIS, ARCO, FUTU; repeat issuers). The one other case, HUM Oct09, has a 2026-Q2 10-Q accepted July29 even though the SEC CompanyFacts endpoint does not contain its Q2 observations for selected US-GAAP keys (confirmed by re-query).

Mark all as NEEDS_ALTERNATIVE_PIT_REPORT_EXTRACTION. Inspect original 6-K/10-Q contemporaneous exhibits, not just CompanyFacts. Never remove these issuers from Gate-first or label FAIL because extracted fields lack freshness. File asof_fundamental_missing_interim_14.csv has time-correct SEC document URLs and classification. This is a DATA COVERAGE test, NOT a fundamental judgment or production gate.


### Initial alternative 6-K recovery (source availability proven)

The newer SEC foreign-issuer interim exhibits are accessible before these original market snapshots; a standardized US-GAAP feed is not the only way to underwrite:
- ODD: September 9, 2026 Form 6-K Exhibit 99.1 reports June-Q2 **$181m revenue** and **$13m net income**, June 30 cash and cash equivalents **$167.274m**, and approximately **$561m cash plus marketable securities**. The latter cannot be counted as pure cash. Original exhibit https://www.sec.gov/Archives/edgar/data/1907085/000110465926106126/tm2624995d1_ex99-1.htm
- CAMT: August 10, 2026 6-K provides Q2 **$133.2m revenue**, **$23.3m GAAP net income**, **$12.2m operating cashflow**, and **$815.8m combined cash/deposits/marketable securities**. Original https://www.sec.gov/Archives/edgar/data/1109138/000117891326003975/zk2635905.htm
- GENI: August 6, 2026 6-K Exhibit 99.1 shows June 30 cash **$155.076m** in its interim balance sheet; remaining financial values still need manual validation. Original https://www.sec.gov/Archives/edgar/data/1834489/000119312526336663/geni-ex99_1.htm

All 3 were accepted before their historical market packet. These primary-document examples prove recovery is feasible. They do NOT certify complete economic underwriting, a 4-of-6 repaired financial screen for every original record, or historical Gate PASS. Machine-readable exhibit pointers/selected validated values are in asof_interim_6k_recovery_3.csv.

## GNRC Sep17 — economic hurdle instead of fabricated valuation target

SEC Sep16 8-K confirms Amazon long-term generator supply agreement, **expected initial deliveries totaling $2.4bn in 2027-28**, and aggregate up-to-$8bn contingent **payment milestones linked to warrants**; the latter is NOT $8bn of binding profit, revenue, or incremental guaranteed orders. Warrants allow purchase of up to 1,693,745 GNRC shares at $200.9266, with 307,954 vested on issuance.

As-of SEC 2026-Q2 10-Q (filed Aug04): 59,006,361 shares outstanding at July31, Q2 revenue $1.17351bn, Q2 net income $143.244m. These company financial totals are NOT Amazon contract margins. At the next regular Sep18 price $209.52, a price-break scenario returning to the **pre-Sep17 price** ~$175.11 implies 16.423% downside. The R/R 2x algebra with 0.5% reference cost requires **$279.39 bull target** (33.35% above entry), an additional **$4.12bn equity value versus the entry share-count basis**. This is a **required valuation hurdle**, not a forecast.

Check contract-profit arithmetic for first expected $2.4bn deliveries over two years:
- 5% hypothetical aftertax net margin = $120m total, at 12% discounted approximately 1.5 years PV ~$101m.
- 10% = $240m total, PV ~$202m.
- 15% = $360m total, PV ~$304m.
- 20% = $480m total, PV ~$405m.

Margins and discounting timing are illustrations, not management guidance. Even the 20% margin stress contributes **<$0.5bn**, far smaller than the **$4.12bn incremental equity hurdle**. A broader recurring franchise, market-share re-rating, margins, and further independent contracts could create additional value, but none has yet been rigorously established at this entry. Up to-$8bn gross payments at a hypothetical 20% net margin would yield up to $1.6bn undiscounted, and still should NOT be counted as firm commitment. **No historical Gate PASS.** The 1,693,745 conditional warrants represent up to ~2.87% of the July share baseline (2.79% post-issue holder ownership dilution, without considering exercise cash and other changes).

Primary SEC: GNRC 8-K https://www.sec.gov/Archives/edgar/data/1474735/000143774926030550/gnrc20260915_8k.htm ; June 2026 10-Q https://www.sec.gov/Archives/edgar/data/1474735/000143774926025669/gnrc20260630_10q.htm

## ATM / security issuance: separate capacity from executed dilution

At as-of SEC common-share count last available and next adjusted OPEN, **IF** the whole announced ATM capacity were hypothetically sold at THAT price (which is not a prediction nor proof of any issue):
- OKLO, Sep11 Dump: new ATM **up to $1bn**, next opening $34.95, 186,017,650 SEC shares (Aug04). Hypothetically ~28.61m new shares / **15.38% of existing**, existing holder share ownership reduction ~**13.33%** after issue. Prior up-to-$1bn authorization terminated and MUST NOT be added to new as $2bn. Actual sale shares, cash inflow, prices and dates unknown.
- PLSE, Sep16 Dump: new ATM **up to $85m**, next opening $49.46, **71,322,607** last SEC common shares (July31). Hypothetical ~1.72m new shares / **2.41%**, post-share ownership reduction **2.35%**. Importantly, substantial issuance (~$68.8m gross) under August ATM was **after the July share-count reference**; therefore the July denominator is stale as a current cap table and this percentage is only a sensitivity, not actual prospective dilution. Cash balances also must reflect interim issuance proceeds.

- LEU, Sep11 Dump: 500,000 offered common shares + 2,005,513 pre-funded warrant shares; **6,992,382** *conditional* common-warrant share capacity with high and different strike prices. A contemporaneous DEI common-share count was not confirmed; market cap / as-of close approximates **19.23m shares** as a proxy, NOT authoritative outstanding shares. Offered common plus pre-funded capacity ~13.03% of this proxy; separate conditional common warrants ~36.35%. Do NOT sum these as immediately issued or assign dilution loss directly; issuance proceeds and strike conditions matter.

Primary SEC: OKLO https://www.sec.gov/Archives/edgar/data/1849056/000110465926106897/tm2625056d1_8k.htm ; PLSE https://www.sec.gov/Archives/edgar/data/1625101/000143774926030456/plse20260914_8k.htm ; LEU https://www.sec.gov/Archives/edgar/data/1065059/000110465926107103/tm2625019d5_8k.htm

## Conclusion / decision status

**GNRC** has genuine economic catalyst but fails to PROVE that a price target sufficient for 2x R/R is justified by the explicitly disclosed initial $2.4bn of deliveries alone; original Gate outcome UNKNOWN. **OKLO, PLSE, LEU** each have financing/equity capacity requiring capital-structure adjusted two-sided valuations; original Gate outcome UNKNOWN. **Four signed M&A** (ACVA/BWIN/PTC/RXO) had <2x net R/R under stated deal-break reversion scenarios (from R1), not original archived Gate FAILs. **Historical P/D+Gate BUY SIGNAL still 0 verified.** No as-of full Gate playbook for all price events; the next valid operation is independent val/catalyst research on untested names, then prospective confirmation on untouched future snapshots.

Machine-auditable files: asof_financial_freshness_326.csv, asof_financial_freshness_summary.json, issuer_asof_dilution_and_GNRC_economics_R2.json. SEC as-of source links, fiscal ends, old report key preservation and 50bps scenario assumptions are explicit. No production Master, RR, Entry, paper buys, or sealed OOS changes.
