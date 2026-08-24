import backtest

# New follow-up hypotheses. These are evaluated after the first batch and therefore
# require a fresh 2025-2026 OOS gate before any production claim.
backtest.SPECS = {
    "LOWVOL20": {
        "signal": lambda x: x.vol_pct <= 0.20,
        "control": lambda x: x.vol_pct.between(0.40, 0.60),
        "mechanism": "cross-sectional low-risk / low-volatility anomaly",
    },
    "LOWVOL10": {
        "signal": lambda x: x.vol_pct <= 0.10,
        "control": lambda x: x.vol_pct.between(0.40, 0.60),
        "mechanism": "extreme cross-sectional low-risk / low-volatility anomaly",
    },
    "LOWVOL30_POSMOM": {
        "signal": lambda x: (x.vol_pct <= 0.30) & (x.mom12_1 > 0),
        "control": lambda x: (x.vol_pct <= 0.30) & (x.mom12_1 <= 0),
        "mechanism": "positive long-horizon trend conditional on low volatility",
    },
    "LOWVOL20_HIGH52": {
        "signal": lambda x: (x.vol_pct <= 0.20) & (x.prox52 >= -0.05),
        "control": lambda x: (x.vol_pct <= 0.20) & (x.prox52 <= -0.10),
        "mechanism": "52-week-high proximity conditional on low volatility",
    },
}

import run_rigorous  # executes the same PIT/month-clustered validation engine
