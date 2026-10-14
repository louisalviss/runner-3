# Gate-first / Pump-Dump-secondary — as-of research checkpoint (Oct 14, 2026)

## Research scope
Historical timely full-universe price source: 15 accepted sessions, 3,035 unique securities, 41,244 symbol-sessions. Pump/Dump 1D absolute move >=7%: 1,139 episodes/observations for 707 names. Research triage (NOT an official production gate): issuer market cap >=$1B, average 20D dollar volume >=$10M, share price >=$5, signal-day volume >=1.5x 20D, and 5 US-business-session same-issuer cooldown. Output: **326 episodes / 301 symbols: 168 Pump and 158 Dump**; 235 historically selected for top80, 91 missed.

Gate-first retains every eligible company irrespective of Pump/Dump. P/D is only a secondary discovery stream; all assets must meet original Hard Persist, Score>=80, MQ>=3, realistic current net R/R>=2x, numeric Entry Zone, relevant risk/event checks and approved venue before BUY_SIGNAL. Never substitute price moves, RSS headlines, or hindsight returns for those economic inputs.

## Evidence sweep
326/326 date-bounded Google News RSS discovery queries responded successfully; 313 had at least one headline originally published no later than the accepted session packet timestamp; 13 did not. These are headline *leads* rather than primary verification. Keyword-based provisional research buckets: M&A 19, clinical/regulatory 29, financing 14, earnings/guidance 53, macro/sector 24, unattributed/mixed 174, no as-of headline 13. Keyword bucket names must NEVER be treated as verified catalyst categories.

## Primary-source as-of deal analysis

Three confirmed, as-of signed transaction cases with a plausible pre-announcement-price downside proxy. Upside = (announced consideration / next-session opening price -1)*100% less 0.5 percentage points for reference round-trip friction. Downside = 100% times (1 - pre-deal unaffected price / opening price). Net R/R = net upside / downside. Downside proxy is illustrative, NOT a guaranteed loss on a broken deal.

- ACVA Sep11 Pump: signed Sep10 Copart cash acquisition $10.50/share; Sep14 open $10.42. Net remaining upside +0.268%, potential reversion -30.505%; conservative scenario R/R 0.009x — RESEARCH_FAIL_RR under this scenario.
- PTC Oct05 Pump: signed Schneider all-cash deal $205/share; Oct06 open $193.00. Net remaining upside +5.718%, potential reversion -25.357%; R/R 0.225x — RESEARCH_FAIL_RR.
- RXO Oct05 Pump: signed CH Robinson $17.25 cash + 0.0856 CHRW shares, nominal $30.25/share October02 reference. Oct06 open $28.73. Reference remaining net upside +4.791%, potential reversion -18.379%; R/R ~0.261x. FLOATING equity consideration; research fail proxy, NOT certain cash takeout cap.

Original issuer primary links:
ACVA https://www.copart.com/content/us/en/press-releases/copart-to-acquire-acv
PTC https://investor.ptc.com/resources/news/news-details/2026/Schneider-Electric-to-acquire-PTC-creating-the-next-level-of-Energy-and-Industrial-Intelligence/default.aspx
RXO https://investor.chrobinson.com/news/press-releases/news-details/2026/C-H--Robinson-to-Acquire-RXO-Redefining-the-Future-of-Third-Party-Logistics-While-Unlocking-Significant-Shareholder-Value/default.aspx

Four additional contemporaneous-primary-case checks: XENE Sep18 temporary psychiatry enrollment pause (separate focal-seizure NDA survives); VKTX Sep22 positive VK2735 maintenance data; PCVX Oct05 positive OPUS-1 Phase3 PLUS concurrent proposed financing; GRAL Sep21 knew FDA advisory panel meeting scheduled Sep23 before future vote. The original Gate result on each remains UNKNOWN pending original financial downside/current R/R/venue. GRAL binary blackout must evaluate exact event timestamp; canonical Config window 24h, never import panel vote held after Sep21.

XENE https://xenonpharma.gcs-web.com/news-releases/news-release-details/xenon-announces-azetukalner-nda-submission-fda-focal-seizures
VKTX https://ir.vikingtherapeutics.com/2026-09-22-Viking-Therapeutics-Announces-Positive-Topline-Results-from-Maintenance-Study-of-GLP-1-GIP-Agonist-VK2735-Demonstrating-the-Promise-of-Multiple-Maintenance-Dosing-Regimens
PCVX https://investors.vaxcyte.com/
GRAL https://grail.com/press-releases/grail-announces-fda-advisory-committee-meeting-to-review-premarket-approval-application-for-the-galleri-multi-cancer-early-detection-test/

## Hindsight price-only benchmark, NOT Radar's trading results
Yahoo historical next NYSE-session adjusted OPEN to 1D/5D/20D close (50bps roundtrip deduction), 301/302 ticker price histories retrieved (one missing). Only maturities completed by US Oct13, 2026.
- 1D 315 price cases: mean -0.828%, 38.7% positive.
- 5D 286 cases: mean -0.222%, 44.1% positive. Pump subset N152 mean +0.009%, Dump N134 mean -0.483%.
- 20D only 86 cases: mean +4.803%, 59.3% positive, dominated by early correlated sessions, not an actionable edge.

Seven illustrative next-open 5D net reference outcomes: ACVA +0.076%, PTC +0.220%, RXO -0.639%, XENE -8.150%, VKTX -24.327%, PCVX -4.181%, GRAL +23.744%. Late material events (GRAL panel vote, additional PCVX financing etc) MUST NOT be imported backward into pre-event BUY qualification.

## Bottom line
Primary evidence was checked for 7 prioritized cases: 3 research-RR fails under explicitly stated downside scenarios; 4 UNKNOWN. The other 319 cases remain un-underwritten UNKNOWN — not FAILED and not bought. Historical actually recorded Radar BUY_SIGNAL remains 3 Gate-first trades (LMT and two LHX, just 2 issuers), no verified P/D-caused BUY; none can be invented from hindsight.

For real historical Gate replay, collect documents whose publication predates each packet, original score inputs and weights/model version, valuation and two-sided price scenario with expected downside, MQ, fresh approved venue and explicit original Entry/Execution decisions. Test independent future sessions before changing production.
