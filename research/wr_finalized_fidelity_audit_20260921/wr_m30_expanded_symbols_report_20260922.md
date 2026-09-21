# WR M30 expanded-symbol backtest — 2026-09-22

Common window: 2022-01-01 through 2026-08-14. Frozen universe: 45 symbols.

Parity: PASS 42/42 SOL+ETH signals vs existing exact authority.

## Aggregate
- all universe: n=927, net525=-201.0686R, E=-0.2169, PF=0.7181
- original SOL/ETH/XRP on same window: n=59, net525=2.0060R, E=0.0340, PF=1.0478

## Top symbols by net 5/2/5
- AAVEUSDT: n=33, net=5.5603R, E=0.1685, PF=1.255, positive_years=5/5, early=3.945R, late=1.615R
- XLMUSDT: n=24, net=3.8134R, E=0.1589, PF=1.237, positive_years=2/5, early=5.235R, late=-1.421R
- LPTUSDT: n=18, net=3.0144R, E=0.1675, PF=1.295, positive_years=3/5, early=3.767R, late=-0.753R
- RUNEUSDT: n=25, net=2.9491R, E=0.1180, PF=1.173, positive_years=2/5, early=0.858R, late=2.091R
- DOGEUSDT: n=23, net=2.8042R, E=0.1219, PF=1.184, positive_years=4/5, early=-1.642R, late=4.446R
- DUSKUSDT: n=22, net=1.9741R, E=0.0897, PF=1.130, positive_years=2/5, early=4.944R, late=-2.970R
- SOLUSDT: n=22, net=1.9408R, E=0.0882, PF=1.129, positive_years=2/5, early=-0.025R, late=1.966R
- PEOPLEUSDT: n=19, net=1.7442R, E=0.0918, PF=1.163, positive_years=2/5, early=5.640R, late=-3.896R
- SNXUSDT: n=17, net=1.6069R, E=0.0945, PF=1.149, positive_years=3/5, early=4.780R, late=-3.174R
- CRVUSDT: n=15, net=1.2873R, E=0.0858, PF=1.149, positive_years=3/5, early=0.677R, late=0.611R
- FILUSDT: n=24, net=0.9705R, E=0.0404, PF=1.057, positive_years=3/5, early=3.251R, late=-2.280R
- XRPUSDT: n=17, net=0.8349R, E=0.0491, PF=1.067, positive_years=3/5, early=-0.169R, late=1.004R
- MKRUSDT: n=18, net=0.3273R, E=0.0182, PF=1.025, positive_years=3/5, early=0.228R, late=0.099R
- BAKEUSDT: n=13, net=0.3225R, E=0.0248, PF=1.037, positive_years=3/5, early=-1.979R, late=2.302R
- LITUSDT: n=10, net=-0.2676R, E=-0.0268, PF=0.958, positive_years=3/5, early=-2.580R, late=2.313R
- DASHUSDT: n=14, net=-0.4932R, E=-0.0352, PF=0.948, positive_years=2/5, early=-8.053R, late=7.560R
- HBARUSDT: n=17, net=-0.5318R, E=-0.0313, PF=0.958, positive_years=2/5, early=-3.737R, late=3.205R
- ETHUSDT: n=20, net=-0.7697R, E=-0.0385, PF=0.947, positive_years=2/5, early=-2.745R, late=1.975R
- ONTUSDT: n=26, net=-3.2678R, E=-0.1257, PF=0.800, positive_years=2/5, early=-3.254R, late=-0.014R
- UNIUSDT: n=19, net=-3.4270R, E=-0.1804, PF=0.767, positive_years=2/5, early=-8.000R, late=4.573R

## Stability diagnostic (not a production rule)
Symbols satisfying n>=30, positive net overall, positive in both 2022-24 and 2025-26 halves, and >=3 positive calendar years: AAVEUSDT

This expanded-symbol scan is in-sample research. Any selected symbol subset requires a separate untouched holdout or forward validation.
