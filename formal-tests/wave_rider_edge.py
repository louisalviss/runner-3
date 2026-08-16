#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, math, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'wave-rider-verify' / 'reference_verify.py'
spec = importlib.util.spec_from_file_location('wrref', REF)
assert spec and spec.loader
wr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = wr
spec.loader.exec_module(wr)

BOOT = int(os.getenv('WR_BOOT', '10000'))
PERM = int(os.getenv('WR_PERM', '5000'))
SEED = int(os.getenv('WR_SEED', '2513'))
OUT = ROOT / 'formal-tests' / 'output'


def mean(a):
    return sum(a) / len(a) if a else None


def pf(a):
    gp = sum(x for x in a if x > 0)
    gl = -sum(x for x in a if x < 0)
    return gp / gl if gl > 0 else None


def longest(a, pred):
    best = cur = 0
    for x in a:
        if pred(x):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def lag1(a):
    if len(a) < 3:
        return None
    x, y = a[:-1], a[1:]
    mx, my = mean(x), mean(y)
    vx = sum((z-mx)**2 for z in x)
    vy = sum((z-my)**2 for z in y)
    if vx <= 0 or vy <= 0:
        return 0.0
    return sum((u-mx)*(v-my) for u, v in zip(x, y)) / math.sqrt(vx*vy)


def quantile(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    p = (len(s)-1)*q
    lo, hi = int(math.floor(p)), int(math.ceil(p))
    if lo == hi:
        return s[lo]
    return s[lo]*(hi-p) + s[hi]*(p-lo)


def block_bootstrap_ci(a, rng, reps=BOOT):
    n = len(a)
    if n < 2:
        return [None, None]
    L = max(2, min(n, round(n ** (1/3))))
    vals = []
    for _ in range(reps):
        sample = []
        while len(sample) < n:
            if n <= L:
                sample.extend(a)
                break
            st = rng.randrange(0, n-L+1)
            sample.extend(a[st:st+L])
        vals.append(mean(sample[:n]))
    return [quantile(vals, .025), quantile(vals, .975)]


def null_mean_p(a, rng, reps=BOOT):
    n = len(a)
    if n < 2:
        return None
    obs = mean(a)
    centered = [x-obs for x in a]
    ge = 0
    for _ in range(reps):
        m = sum(centered[rng.randrange(n)] for __ in range(n)) / n
        if m >= obs:
            ge += 1
    return (ge+1)/(reps+1)


def runs_test(a):
    s = [1 if x > 0 else 0 for x in a if abs(x) > 1e-12]
    n1, n0 = sum(s), len(s)-sum(s)
    if n1 == 0 or n0 == 0 or len(s) < 3:
        return {'runs': None, 'z': None, 'p_two_sided': None}
    runs = 1 + sum(s[i] != s[i-1] for i in range(1, len(s)))
    mu = 1 + 2*n1*n0/(n1+n0)
    var = 2*n1*n0*(2*n1*n0-n1-n0)/(((n1+n0)**2)*(n1+n0-1))
    if var <= 0:
        return {'runs': runs, 'z': None, 'p_two_sided': None}
    z = (runs-mu)/math.sqrt(var)
    p = math.erfc(abs(z)/math.sqrt(2))
    return {'runs': runs, 'z': z, 'p_two_sided': p}


def sequence_permutation(a, rng, reps=PERM):
    obs_ll = longest(a, lambda x: x < 0)
    obs_lw = longest(a, lambda x: x > 0)
    obs_ac = lag1(a)
    ge_ll = ge_lw = ge_ac = 0
    tmp = list(a)
    for _ in range(reps):
        rng.shuffle(tmp)
        if longest(tmp, lambda x: x < 0) >= obs_ll:
            ge_ll += 1
        if longest(tmp, lambda x: x > 0) >= obs_lw:
            ge_lw += 1
        ac = lag1(tmp)
        if obs_ac is not None and ac is not None and abs(ac) >= abs(obs_ac):
            ge_ac += 1
    return {
        'longest_loss_streak': obs_ll,
        'longest_win_streak': obs_lw,
        'lag1_r': obs_ac,
        'p_loss_streak_ge_random': (ge_ll+1)/(reps+1),
        'p_win_streak_ge_random': (ge_lw+1)/(reps+1),
        'p_abs_lag1_ge_random': (ge_ac+1)/(reps+1) if obs_ac is not None else None,
    }


def segment(a):
    n = len(a)
    if n == 0:
        return []
    c1 = max(1, int(n*.60))
    c2 = max(c1+1, int(n*.80)) if n >= 5 else n
    c2 = min(c2, n)
    parts = [('train60', a[:c1]), ('valid20', a[c1:c2]), ('final20', a[c2:])]
    out = []
    for name, x in parts:
        if not x:
            continue
        out.append({'name': name, 'n': len(x), 'avg_r': mean(x), 'total_r': sum(x), 'pf_r': pf(x)})
    return out


def blocks(a, size=50):
    out = []
    for st in range(0, len(a), size):
        x = a[st:st+size]
        if not x:
            continue
        out.append({'start_trade': st+1, 'end_trade': st+len(x), 'n': len(x), 'complete': len(x)==size,
                    'avg_r': mean(x), 'total_r': sum(x), 'pf_r': pf(x)})
    comp = [b for b in out if b['complete']]
    return out, {
        'complete_blocks': len(comp),
        'positive_complete_blocks': sum(b['avg_r'] > 0 for b in comp),
        'negative_complete_blocks': sum(b['avg_r'] < 0 for b in comp),
        'positive_share': (sum(b['avg_r'] > 0 for b in comp)/len(comp) if comp else None),
        'median_avg_r': quantile([b['avg_r'] for b in comp], .5) if comp else None,
        'min_avg_r': min((b['avg_r'] for b in comp), default=None),
        'max_avg_r': max((b['avg_r'] for b in comp), default=None),
    }


def analyze(trades, seed):
    a = [float(t.canon_r) for t in trades]
    rng = random.Random(seed)
    ci = block_bootstrap_ci(a, rng)
    p0 = null_mean_p(a, rng)
    seq = sequence_permutation(a, rng)
    run = runs_test(a)
    bs, bsum = blocks(a, 50)
    wf = segment(a)
    final = next((x for x in wf if x['name']=='final20'), None)
    low, high = ci
    if low is not None and low > 0 and p0 is not None and p0 < .05 and final and final['avg_r'] > 0 and (bsum['positive_share'] is None or bsum['positive_share'] >= .60):
        status = 'POSITIVE_EDGE_EVIDENCE'
    elif high is not None and high < 0:
        status = 'NEGATIVE_EXPECTANCY_EVIDENCE'
    else:
        status = 'EDGE_UNPROVEN_NOISE_COMPATIBLE'
    random_cluster_compatible = all(p is None or p >= .05 for p in [run['p_two_sided'], seq['p_loss_streak_ge_random'], seq['p_abs_lag1_ge_random']])
    return {
        'n': len(a), 'avg_r': mean(a), 'total_r': sum(a), 'pf_r': pf(a),
        'block_bootstrap_95ci_avg_r': ci,
        'p_one_sided_mean_le_0': p0,
        'runs_test': run,
        'sequence_permutation': seq,
        'random_cluster_compatible_at_5pct': random_cluster_compatible,
        'walk_forward_fixed_60_20_20': wf,
        'blocks_50': bs,
        'block_summary': bsum,
        'classification': status,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    one, tick, missing = wr.fetch_1m()
    st = int(datetime.fromisoformat(wr.START).replace(tzinfo=timezone.utc).timestamp()*1000)
    en = int((datetime.fromisoformat(wr.END).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp()*1000)-1
    result = {
        'strategy': 'Wave Rider 2.5.13 formal edge test',
        'symbol': wr.SYMBOL, 'start': wr.START, 'end': wr.END, 'tick': tick, 'missing_days': missing,
        'bootstrap_reps': BOOT, 'permutation_reps': PERM,
        'notes': [
            'Rules frozen at independent reference implementation defaults.',
            '50-trade blocks are chronological and not optimized.',
            '60/20/20 split is a mechanical temporal robustness split, not guaranteed pristine out-of-sample.',
            'Block-bootstrap CI preserves short local dependence; null p-value tests mean R > 0 using centered bootstrap.',
            'Runs/streak/lag-1 tests evaluate whether apparent clusters exceed what random ordering can generate.'
        ],
        'timeframes': {}
    }
    for tf in wr.TFS:
        tr, base = wr.run(tf, wr.agg(one, tf), tick, st, en)
        result['timeframes'][str(tf)] = {'base': base, 'formal': analyze(tr, SEED + tf)}
    p = OUT / f'{wr.SYMBOL}_{wr.START}_{wr.END}.json'
    p.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    print('\nFORMAL SUMMARY')
    for tf, x in result['timeframes'].items():
        f = x['formal']; ci = f['block_bootstrap_95ci_avg_r']; b=f['block_summary']; seq=f['sequence_permutation']; run=f['runs_test']
        print(f"{tf}m N={f['n']} AvgR={f['avg_r']:+.4f} CI95=[{ci[0]:+.4f},{ci[1]:+.4f}] p(mean<=0)={f['p_one_sided_mean_le_0']:.4f} blocks+={b['positive_complete_blocks']}/{b['complete_blocks']} runs_p={run['p_two_sided']} lossStreak_p={seq['p_loss_streak_ge_random']:.4f} lag1_p={seq['p_abs_lag1_ge_random']:.4f} => {f['classification']}")

if __name__ == '__main__':
    main()
