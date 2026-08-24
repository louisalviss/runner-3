import backtest

_cache = {}

def pd_ts(x):
    return str(x)

def fast_nearest_control(sig, pool, spec):
    key = (pd_ts(sig["week"]), spec["mechanism"])
    c = _cache.get(key)
    if c is None:
        week_pool = pool[pool.week.eq(sig["week"])]
        c = week_pool[spec["control"](week_pool)].copy()
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

backtest.nearest_control = fast_nearest_control
backtest.main()
