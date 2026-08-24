# RSI E2 + SuperTrend 60m — Executable Holdout Result

Run: 32772722993
Artifact: 9537584643
Artifact digest: sha256:1ee2adede2e819ca3e3e388dfffd95abdcb58ffa9992b60696a4d41a87e70fc6
Preregistration commit: e40a18777f26ce449140604cace83e07b35b1579
Status: PASS_EXECUTABLE_EXTERNAL_ALPHA = true

## Primary 63-stock holdout

- Coverage: 63 / 63
- Closed trades: 4,023
- Actual BID/ASK PF: 1.3937737824
- Actual mean trade: +64.0789 bps
- Actual median trade: +5.7659 bps
- Actual win rate: 50.6836%
- Midpoint PF: 1.5297592451
- Midpoint mean trade: +81.6218 bps
- Positive symbols: 49 / 63 = 77.7778%
- Median per-symbol PF (>=5 trades): 1.2849295546
- Pre-2026 actual PF: 1.3718569105
- Median entry spread: 7.9667 bps
- Median exit spread: 8.0871 bps

## Yearly actual BID/ASK

- 2022: n=906, PF=1.0266, mean=+5.38 bps
- 2023: n=817, PF=1.6015, mean=+78.65 bps
- 2024: n=928, PF=1.7050, mean=+92.23 bps
- 2025: n=837, PF=1.3590, mean=+60.07 bps
- 2026: n=535, PF=1.5106, mean=+98.69 bps

Recent-years gate: 2024, 2025 and 2026 all have actual PF > 1.05.

## Secondary all-68 diagnostic

- Coverage: 68 / 68
- Closed trades: 4,356
- Actual BID/ASK PF: 1.3927132380
- Actual mean trade: +64.9619 bps
- Positive symbols: 53 / 68 = 77.9412%
- Median per-symbol PF (>=5 trades): 1.3002520259

## Frozen gate outcome

Every preregistered gate passed:

- coverage >= 60/63: PASS
- trades >= 300: PASS
- actual PF >= 1.20: PASS
- actual mean >= +10 bps: PASS
- midpoint PF >= 1.25: PASS
- midpoint mean > 0: PASS
- positive-symbol fraction >= 60%: PASS
- median symbol PF >= 1.05: PASS
- pre-2026 actual PF >= 1.10: PASS
- at least 2 of 2024–2026 PF > 1.05: PASS

## Decision

Promote to `EXECUTABLE_EXTERNAL_ALPHA_CANDIDATE`.

This result does NOT modify or resurrect Wave Rider standalone alpha. The only permitted next step is a separately preregistered matched A/B:

1. Base: RSI E2 + SuperTrend 60m executable signal exactly as validated here.
2. Treatment: the same external-alpha signals with WR timing/execution overlay only.
3. No RSI/SMA/SuperTrend parameter tuning, ticker/sector whitelist, or post-hoc regime filtering in this lineage.

A WR overlay is useful only if it improves executable expectancy / risk-adjusted behavior without destroying breadth or trade count.
