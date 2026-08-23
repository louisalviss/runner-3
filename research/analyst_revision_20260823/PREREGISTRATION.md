# Analyst Revision Validation — Preregistration — 2026-08-23

Status: FROZEN BEFORE RETURN OUTCOMES

## Economic hypothesis
A point-in-time upward revision in the Current Year EPS consensus may contain incremental information that predicts future relative returns versus otherwise similar PIT S&P 500 stocks without an upward revision.

## Source
Authority: DoltHub `post-no-preference/earnings`, table `eps_estimate`.
Transport/cache for the historical run: `siddharthmb/stocks-earnings-eps_estimate` parquet mirror, after source audit established matching schema/history and direct authority parity on historical samples.

No SOV.AI terminal/backfilled earnings-surprise estimate fields may be used.

## Frozen signal: EPSUp28_CurrentYear_Monthly
1. Use `period == Current Year` only.
2. Use the first available source snapshot for each symbol in each calendar month. This avoids choosing a later monthly snapshot with future knowledge.
3. Compare the current consensus with the latest observation for the SAME `symbol + period_end_date` at or before `current_date - 21 days`, requiring that observation to be no more than 45 days old.
4. Require analyst count >= 3 at both observations.
5. Signal iff `consensus_now > consensus_prior`.
6. No revision magnitude threshold, percentile threshold, symbol whitelist, sector whitelist, technical filter, or ML model.
7. Source observation date is not treated as a tradable close. Map it to the first completed weekly price bar strictly after the source date; enter at the following week's adjusted open.

## Universe / prices
- Point-in-time S&P 500 membership.
- Existing FINSABER S&P500 including-delisted price framework from the standalone research pipeline.
- Weekly adjusted prices.

## Controls
For each EPSUp28 event:
- same mapped signal week;
- PIT S&P500 member;
- valid Current Year same-target 21–45d revision comparison with analyst count >=3 at both observations;
- no upward EPS consensus revision under the same rule (`delta <= 0`);
- exclude the event symbol;
- match pre-signal 52-week return within ±10 percentage points;
- widen once to ±20pp if fewer than 5 controls;
- require at least 3 valid control horizon returns.

Sector matching is deliberately omitted because no audited PIT sector-history source has been established in this lineage. Do not add static current-sector metadata after seeing outcomes.

## Time split
- Discovery: 2018-01-01 through 2020-12-31.
- Validation: 2021-01-01 through 2024-12-31, limited by available forward price outcomes.
- 2025–2026 source observations are hard-excluded before feature construction and remain untouched unless validation passes.

## Horizons
- Primary: 13 weeks.
- Secondary diagnostic: 26 weeks.
- Do not switch primary horizon after seeing results.

## Primary validation gate
PASS only if ALL are true at 13w:
1. matched N >= 300;
2. median matched excess > +1.0%;
3. beat matched >= 52.5%;
4. week-cluster bootstrap 95% CI lower bound for mean excess > 0.

Raw win rate is reported but is not a promotion gate; this is a cross-sectional information-edge hypothesis.

## Anti-rescue rules
If validation fails:
- do not change 21–45d to another revision window;
- do not change Current Year to Current Quarter / Next Year;
- do not add magnitude thresholds or rank cutoffs;
- do not use the secondary 26w cell as a rescue;
- do not touch 2025–2026;
- close the branch as a negative result.

If validation passes, freeze this exact rule before any untouched 2025–2026 evaluation.
