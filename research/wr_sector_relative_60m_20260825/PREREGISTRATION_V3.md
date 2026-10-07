# Wave Rider Sector-Relative Alignment — Preregistration V3

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / RESULTS UNSEEN

V1 and V2 were infrastructure-blocked before validate/PnL scoring. V1 showed the `dukascopy_python.instruments` registry does not list XLC/XLRE. V2 showed VOX is also absent from that registry while VNQ is present. No WR PnL outcome has been observed.

V3 restores the original economically exact SPDR benchmarks XLC and XLRE and changes only instrument resolution:
- XLC is addressed explicitly as literal Dukascopy instrument `XLC.US/USD`.
- XLRE is addressed explicitly as literal Dukascopy instrument `XLRE.US/USD`.
- All other benchmarks continue through the frozen helper resolver.

Before any PnL scoring, the probe must perform a real M5 Dukascopy fetch on both literal instruments and require non-empty data. If either direct fetch fails or returns no data, V3 is `INFRASTRUCTURE_BLOCKED` and validate is skipped.

All hypothesis semantics remain V1-original:
- stock / exact SPDR sector ETF relative ratio;
- sector ETF / SPY relative ratio;
- causal completed 60m bars only;
- recursive EMA50 with one-bar EMA slope;
- LONG requires both ratios above EMA50 and both slopes positive;
- SHORT exact inverse;
- frozen WR v2.5.13 parent executable trades from run 32677300335;
- primary OOS 2024-2026;
- unchanged 11 promotion gates from V1.

No PnL-based benchmark substitution is allowed.