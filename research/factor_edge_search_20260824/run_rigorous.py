import numpy as np
import pandas as pd
import backtest

_cache = {}

def fast_nearest_control(sig, pool, spec):
    key = (str(sig["week"]), spec["mechanism"])
    c = _cache.get(key)
    if c is None:
        wp = pool[pool.week.eq(sig["week"])]
        c = wp[spec["control"](wp)].copy()
        _cache[key] = c
    if c.empty:
        return None
    c2 = c[c.symbol.ne(sig.symbol)]
    if not c2.empty:
        c = c2
    dd_sig = -float(sig.prox52)
    dd_c = -c.prox52.astype(float)
    vol_sig = float(sig.vol13)
    scale_v = max(float(c.vol13.median()), 1e-6)
    dist = (dd_c - dd_sig).abs() / 0.10 + (c.vol13.astype(float) - vol_sig).abs() / scale_v
    return int(dist.idxmin())

def cluster_ci(weeks, excess, reps=3000):
    d = pd.DataFrame({"week": weeks, "excess": excess}).dropna()
    wm = d.groupby("week", observed=True).excess.mean().to_numpy(dtype=float)
    if len(wm) < 8:
        return (np.nan, np.nan)
    rng = np.random.default_rng(20260824)
    means = np.empty(reps)
    n = len(wm)
    for i in range(reps):
        means[i] = np.mean(wm[rng.integers(0, n, n)])
    return tuple(np.quantile(means, [0.025, 0.975]))

def evaluate_cluster(base, start, end, name, spec):
    p = base[base.week.between(start, end)].copy()
    sig = p[spec["signal"](p)].copy()
    pairs = []
    for idx, s in sig.iterrows():
        ci = fast_nearest_control(s, p, spec)
        if ci is not None:
            pairs.append((idx, ci))
    rows = []
    for h in backtest.HORIZONS:
        col = f"ret{h}"
        allsig = sig[col].dropna()
        vals = []
        weeks = []
        for si, ci in pairs:
            a = p.at[si, col]; b = p.at[ci, col]
            if pd.notna(a) and pd.notna(b):
                vals.append((float(a), float(b)))
                weeks.append(p.at[si, "week"])
        if vals:
            z = np.asarray(vals, dtype=float)
            ex = z[:, 0] - z[:, 1]
            lo, hi = cluster_ci(weeks, ex)
            medex = float(np.median(ex)); meanex = float(np.mean(ex)); beat = float(np.mean(ex > 0)); mn = len(ex)
        else:
            lo = hi = medex = meanex = beat = np.nan; mn = 0
        rows.append({
            "strategy": name, "mechanism": spec["mechanism"], "horizon": h,
            "signal_n": int(len(allsig)), "matched_n": int(mn),
            "win_rate": float((allsig > 0).mean()) if len(allsig) else np.nan,
            "median_return": float(allsig.median()) if len(allsig) else np.nan,
            "median_excess": medex, "mean_excess": meanex, "beat_matched": beat,
            "ci_lo": float(lo), "ci_hi": float(hi),
        })
    return rows

backtest.nearest_control = fast_nearest_control
backtest.evaluate = evaluate_cluster
backtest.main()
