# As-of SEC catalysts and R/R — Radar shadow audit, 2026-10-15

**SHADOW research; no production BUY, Score, RR, Entry or Paper changes.** Gate-first examines all valid securities independently of Pump/Dump; Pump/Dump only supplies extra discovery candidates to exactly the same Gate.

## Original evidence
326 eligible episodes / 301 issuers. Original full point-in-time market inventory 15 timely sessions / 3,035 securities. A recent 8-K/6-K was available in 89 episodes. Retrieved each of 89 original SEC primary HTML documents HTTP 200 with SHA256 and full source URL, all SEC accepted before source packet generation. Bounded excerpts and preliminary keyword categories are stored in asof_filing_primary_text_index_89.json; keyword matches may be routine text/boilerplate and do not establish relevance.

Eight source-material mechanisms were manually checked. Four are merger R/R stress cases, three are financing/dilution review, one is a commercially material new contract requiring valuation. Other 81 8-K/6-K cases and 237 episodes without recent 8-K/6-K remain UNKNOWN; not Gate FAIL.

## Merger R/R scenario: four conservative failures

Reference buy at next NYSE adjusted OPEN, reference 0.5 percentage point cost, downside if break to price BEFORE announcement inferred from transaction premium. This break-reversion assumption is a scenario, not official Radar underwriting. RXO price includes floating share consideration, not fixed-cash cap.

| Symbol | Trigger | Next open | Offer basis | Net upside | Bear reversion | R/R |
|---|---|---:|---:|---:|---:|---:|
| ACVA | Sep11 Pump | $10.42 | $10.50 cash | +0.268% | -30.505% | 0.0088x |
| BWIN | Sep14 Pump | $32.00 | $32.50 cash | +1.062% | -45.977% | 0.0231x |
| PTC | Oct05 Pump | $193.00 | $205 cash | +5.718% | -25.357% | 0.2255x |
| RXO | Oct05 Pump | $28.73 | $17.25 cash + 0.0856 CHRW; nominal $30.25 Oct02 | +4.791% ref | -18.379% | 0.2607x ref |

All fail net R/R>=2 under THIS scenario; none is labeled an actual archived historical Radar FAIL.

Primary SEC documents:
ACVA https://www.sec.gov/Archives/edgar/data/1637873/000095010326013780/dp253207_8k.htm
BWIN https://www.sec.gov/Archives/edgar/data/1781755/000095010326013874/dp253297_8k.htm
PTC https://www.sec.gov/Archives/edgar/data/857005/000119312526413124/d174191d8k.htm
RXO https://www.sec.gov/Archives/edgar/data/1929561/000114036126038548/ef20083265_8k.htm

## Material economics beyond headline

GNRC Sep17 Pump: Sep16 Amazon long-term agreement, initial generator delivery expectations $2.4bn 2027-28, conditional aggregate customer payments up to $8bn used for vesting Amazon warrant up to 1,693,745 GNRC shares with exercise $200.9266. $8bn is NOT guaranteed unconditional contract sales and the warrants may dilute. Next opening Sep18 $209.52. Taking pre-Pump close $175.11 as an illustrative bear-price downside 16.423%, the required bull target for 2x R/R at 50bps reference cost is **at least $279.39**. Not a validated fair value: needs cashflow margin, execution, equity dilution and independent bear estimate. Gate UNKNOWN.

OKLO Sep11 Dump: filed new up-to-$1bn at-the-market share sale authorization, replacing terminating up-to-$1bn earlier ATM (not additive $2bn). Sep14 next opening $34.95; 5D reference +8.227%. Financing/dilution must be analyzed; Gate UNKNOWN.

LEU Sep11 Dump: SEC underwriting 500,000 shares plus pre-funded warrants for up to 2,005,513 shares and conditional common warrants for up to 6,992,382 shares. Different strikes/conditions; not all immediately outstanding stock. Next opening $150.00, 5D reference -3.680%. Gate UNKNOWN.

PLSE Sep16 Dump: new ATM up to $85m, previous August ATM $68.8m already sold by Sep14. These are sale authorizations and completed prior proceeds, not proof all new shares have been issued. Next opening $49.46, 5D reference +4.595%. Gate UNKNOWN.

Primary SEC documents:
GNRC https://www.sec.gov/Archives/edgar/data/1474735/000143774926030550/gnrc20260915_8k.htm
OKLO https://www.sec.gov/Archives/edgar/data/1849056/000110465926106897/tm2625056d1_8k.htm
LEU https://www.sec.gov/Archives/edgar/data/1065059/000110465926107103/tm2625019d5_8k.htm
PLSE https://www.sec.gov/Archives/edgar/data/1625101/000143774926030456/plse20260914_8k.htm

## Reverse-R/R target threshold on ALL 326

A synthetic risk frontier is calculated with contemporaneous event close, source 1D return, and next actual NYSE opening (price after event). To reach R/R 2, target equals entry times [1 + 0.005 + 2x an independently justifiable downside percentage]. For Pump, an illustrative pre-Pump price reversion scenario is the prior daily close derived from the event's 1D return, provided it lies below next opening. 167 of 168 Pump events meet this condition; required net-bull targets ABOVE entry: less than 10% (6), 10-20% (82), 20-30% (57), 30-50% (17), at least 50% (5). These are MINIMUM TARGETS NEEDED, NOT legitimate fair-value targets. None is automatically approved to buy.

For Dump, the pre-Dump close is a potential recovery upside, NOT downside. Companion CSV provides only sensitivity targets at hypothetical downside rates 10%, 20%, 30% for all 326; true bear valuation and stop invalidation remain necessary.

## Gate and next action

A signed deal or a discovered shock is not enough: confirmed as-of economic catalyst, Score>=80, MQ>=3, independent bull/base/bear valuation, net R/R>=2 at realistic executable entry, no binary-event blackout, approved venue and Execution Gate must all pass. P/D events lacking those fields remain UNKNOWN and are NOT counted as buys or as full-Gate fails. No historical P/D+Gate BUY reconstructed; previously recorded Gate-first LMT and 2 LHX remain the only validated paper BUYs. Full history across the Gate-first non-P/D universe still lacks original underwriting snapshots and cannot be backfilled from price alone.

Artifacts: original SEC index for 89 source documents, 89-row triage, four-scenario deal R/R, all-326 mathematical RR threshold screen and source-SHA audit. Research stage only, sealed OOS and live filters untouched.
