#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sys
from datetime import datetime, timezone

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'wave-rider-verify' / 'reference_verify.py'
spec = importlib.util.spec_from_file_location('wrbase', REF)
assert spec and spec.loader
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

Bar = base.Bar
Plan = base.Plan
Trade = base.Trade

# Pine ta.pivothigh/ta.pivotlow plateau semantics for parity work.
# Equal values are permitted on the LEFT side of the candidate, while the RIGHT
# side must be strictly lower/higher. This selects the right-most member of an
# equal-price plateau. The returned series is then shifted by [1], matching
# `ta.pivothigh(...)[1]` / `ta.pivotlow(...)[1]` in v2.5.13.
def _pine_pivots(v, left, right, high=True):
    raw = [None] * len(v)
    ties = 0
    for conf in range(left + right, len(v)):
        c = conf - right
        center = v[c]
        L = v[c-left:c]
        R = v[c+1:c+right+1]
        if high:
            ok = all(x <= center for x in L) and all(x < center for x in R)
            plateau = any(x == center for x in L)
        else:
            ok = all(x >= center for x in L) and all(x > center for x in R)
            plateau = any(x == center for x in L)
        if ok:
            raw[conf] = center
            if plateau:
                ties += 1
    return [None] + raw[:-1], ties

base.pivots = _pine_pivots

# Canonical v2.5.13 embedded high-impact news timestamps.
# Pine source uses America/New_York local timestamps.
NEWS_UTC_MS = tuple(
    int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp() * 1000)
    for y, m, d, hh, mm in (
        (2025, 11, 20, 13, 30),  # 08:30 ET
        (2025, 12, 10, 19,  0),  # 14:00 ET
        (2025, 12, 16, 13, 30),  # 08:30 ET
        (2025, 12, 18, 13, 30),  # 08:30 ET
    )
)
EXIT_BEFORE_NEWS_MIN = 15
RESUME_AFTER_NEWS_MIN = 15


def news_locked_at(t_ms: int) -> bool:
    before = EXIT_BEFORE_NEWS_MIN * 60_000
    after = RESUME_AFTER_NEWS_MIN * 60_000
    return any(t_ms >= e - before and t_ms < e + after for e in NEWS_UTC_MS)


def news_exit_at_bar_close(tc: int, chart_ms: int) -> bool:
    before = EXIT_BEFORE_NEWS_MIN * 60_000
    for e in NEWS_UTC_MS:
        cutoff = e - before
        if (tc < cutoff and tc + chart_ms >= cutoff) or (tc >= cutoff and tc < e):
            return True
    return False


def news_safe_for_new_setup(tc: int, chart_ms: int) -> bool:
    return (not news_locked_at(tc)) and (not news_locked_at(tc + chart_ms))


def _entry_fill(plan: Plan, bar) -> tuple[bool, float | None, float | None]:
    """Approximate TradingView historical stop-entry fill and path position after fill.

    Returns (filled, actual_fill_price, path_start_price_after_fill).
    The plan price remains the canonical planned entry used for R accounting.
    """
    pts = base.path(bar)
    # Stop order triggered through a gap: market fill at bar open.
    if plan.d == 1 and bar.o >= plan.e:
        return True, bar.o, bar.o
    if plan.d == -1 and bar.o <= plan.e:
        return True, bar.o, bar.o

    cur = pts[0]
    for z in pts[1:]:
        if plan.d == 1 and cur < plan.e <= z:
            return True, plan.e, plan.e
        if plan.d == -1 and cur > plan.e >= z:
            return True, plan.e, plan.e
        cur = z
    return False, None, None


def _bracket_after_entry(plan: Plan, bar, fill_px: float) -> tuple[str | None, float | None]:
    """Evaluate bracket only on the part of the historical OHLC path after entry."""
    pts = base.path(bar)

    # Gap-triggered entry at open: position is active from open.
    if abs(fill_px - bar.o) <= 1e-12:
        active = True
        cur = bar.o
        if plan.d == 1 and bar.o <= plan.s:
            return 'SL', bar.o
        if plan.d == 1 and bar.o >= plan.t:
            return 'TP', bar.o
        if plan.d == -1 and bar.o >= plan.s:
            return 'SL', bar.o
        if plan.d == -1 and bar.o <= plan.t:
            return 'TP', bar.o
        start_index = 1
    else:
        active = False
        cur = pts[0]
        start_index = 1

    for z in pts[start_index:]:
        pos = cur
        while True:
            if not active:
                crossed = (plan.d == 1 and pos < plan.e <= z) or (plan.d == -1 and pos > plan.e >= z)
                if not crossed:
                    break
                pos = plan.e
                active = True
                continue

            cand = []
            if base.cross(pos, z, plan.s) and abs(plan.s - pos) > 1e-12:
                cand.append((abs(plan.s - pos), 'SL', plan.s))
            if base.cross(pos, z, plan.t) and abs(plan.t - pos) > 1e-12:
                cand.append((abs(plan.t - pos), 'TP', plan.t))
            if not cand:
                break
            _, reason, px = min(cand)
            return reason, px
        cur = z

    return None, None


def run_window_exact(
    tf: int,
    bars,
    tick: float,
    report_start_ms: int,
    report_end_ms: int,
    *,
    engine_start_ms: int | None = None,
):
    """Wave Rider v2.5.13 exact-report semantics for parity work.

    Engine state is allowed to form before the report window. Returned trades are
    selected by SIGNAL-CANDLE close time in [report_start_ms, report_end_ms), just
    like the Pine WINDOW REPORT derivative. Signals at/after report_end_ms are not
    needed for the report and are suppressed once all pre-end state is resolved.
    """
    ind, pht, plt = base.calc_ind(bars)
    chart_ms = tf * 60_000
    eq = base.INIT
    peak = base.INIT
    pending = active = None
    entry_t = None
    actual_entry_px = None
    trades = []
    diag = dict(
        signals=0, pending_expired=0, pending_filled=0, ambiguous=0,
        tp=0, sl=0, ema=0, news=0, session=0,
        pivot_high_ties=pht, pivot_low_ties=plt,
    )
    cur_ls = max_ls = 0
    maxdd = 0.0

    if engine_start_ms is None:
        engine_start_ms = bars[0].ct if bars else report_start_ms

    def report_eligible(plan: Plan) -> bool:
        return report_start_ms <= plan.sig_t < report_end_ms

    def close_trade(i: int, reason: str, px: float):
        nonlocal active, entry_t, actual_entry_px, eq, peak, maxdd, cur_ls, max_ls

        both = (
            active is not None
            and reason in ('TP', 'SL')
            and bars[i].h >= max(active.s, active.t)
            and bars[i].l <= min(active.s, active.t)
        )
        if both:
            reason = 'AMBIG->SL'
            diag['ambiguous'] += 1

        if reason == 'TP':
            cr = base.TP_R
        elif reason in ('SL', 'AMBIG->SL'):
            cr = -1.0
        else:
            # Canonical managed exit R is measured from PLANNED entry.
            cr = (px - active.e) * (1 if active.d == 1 else -1) * active.qty / active.risk

        cash = cr * active.risk
        eq += cash
        peak = max(peak, eq)
        maxdd = max(maxdd, 100 * (peak - eq) / peak)
        if cash < 0:
            cur_ls += 1
            max_ls = max(max_ls, cur_ls)
        else:
            cur_ls = 0

        if report_eligible(active):
            trades.append(
                Trade(
                    tf,
                    'LONG' if active.d == 1 else 'SHORT',
                    base.iso(active.sig_t),
                    base.iso(entry_t),
                    base.iso(bars[i].ct),
                    active.sig_h,
                    active.sig_l,
                    active.e,
                    active.s,
                    active.t,
                    px,
                    reason,
                    cr,
                    active.risk,
                    active.qty,
                    both,
                )
            )

        active = None
        entry_t = None
        actual_entry_px = None

    for i, x in enumerate(bars):
        if x.ct < engine_start_ms:
            continue

        closed = False

        # Existing position: bracket orders can fill intrabar before managed exits.
        if active is not None:
            r, px = base.next_bracket(active, x, None)
            if r:
                diag['tp' if r == 'TP' else 'sl'] += 1
                close_trade(i, r, px)
                closed = True

        # Pending stop-entry is valid on exactly the next chart candle.
        if active is None and pending is not None and i == pending.sig_i + 1 and not closed:
            filled, fill_px, _ = _entry_fill(pending, x)
            if filled:
                active = pending
                pending = None
                entry_t = x.ot
                actual_entry_px = fill_px
                diag['pending_filled'] += 1
                r, px = _bracket_after_entry(active, x, fill_px)
                if r:
                    diag['tp' if r == 'TP' else 'sl'] += 1
                    close_trade(i, r, px)
                    closed = True

        allowed, session_exit = base.session_flags(x.ct, chart_ms)

        # Canonical priority after intrabar bracket: session > news > EMA.
        if active is not None and not closed:
            z = ind[i]
            long_ema = active.d == 1 and x.c < z['ema'] and not z['ha'] and not z['ema_up']
            short_ema = active.d == -1 and x.c > z['ema'] and not z['hb'] and bool(z['ema_up'])

            if session_exit:
                diag['session'] += 1
                close_trade(i, 'SESSION', x.c)
                closed = True
            elif news_exit_at_bar_close(x.ct, chart_ms):
                diag['news'] += 1
                close_trade(i, 'NEWS', x.c)
                closed = True
            elif long_ema or short_ema:
                diag['ema'] += 1
                close_trade(i, 'EMA', x.c)
                closed = True

        if pending is not None and i >= pending.sig_i + 1 and active is None:
            pending = None
            diag['pending_expired'] += 1

        # After report end, do not create irrelevant post-window signals.
        if x.ct >= report_end_ms:
            if active is None and pending is None:
                break
            continue

        if active is None and pending is None and not closed:
            z = ind[i]
            long_ready = z['ha'] and x.c > z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
            short_ready = z['hb'] and x.c < z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None

            nl = (
                allowed and news_safe_for_new_setup(x.ct, chart_ms) and z['sra_ok']
                and x.c > x.o and long_ready and x.c > z['res'] and x.l <= z['res']
            )
            ns = (
                allowed and news_safe_for_new_setup(x.ct, chart_ms) and z['sra_ok']
                and x.c < x.o and short_ready and x.c < z['sup'] and x.h >= z['sup']
            )

            if nl or ns:
                if nl:
                    d = 1
                    e = x.h + tick
                    s = x.l - tick
                    t = e + base.TP_R * (e - s)
                else:
                    d = -1
                    e = x.l - tick
                    s = x.h + tick
                    t = e - base.TP_R * (s - e)

                # For Canon R, qty-step rounding cancels from managed-exit R.
                # Keep the legacy reference's unit floor for archive-only parity.
                raw = (eq * base.RISK_PCT / 100) / abs(e - s)
                q = int(raw // 1)
                risk = abs(e - s) * q
                if q > 0 and risk > 0:
                    pending = Plan(d, e, s, t, risk, q, i, x.ct, x.h, x.l)
                    diag['signals'] += 1

    wins = sum(t.canon_r > 0 for t in trades)
    losses = sum(t.canon_r < 0 for t in trades)
    even = len(trades) - wins - losses
    total = sum(t.canon_r for t in trades)
    gp = sum(max(t.canon_r * t.risk_cash, 0) for t in trades)
    gl = sum(max(-t.canon_r * t.risk_cash, 0) for t in trades)

    return trades, dict(
        tf=tf,
        trades=len(trades),
        wins=wins,
        losses=losses,
        even=even,
        win_rate=(100 * wins / len(trades) if trades else None),
        total_r=total,
        avg_r=(total / len(trades) if trades else None),
        profit_factor=(gp / gl if gl else None),
        max_dd_pct=maxdd,
        max_losing_streak=max_ls,
        diagnostics=diag,
        report_semantics='signal close in [start,end), engine warmup before start, carry-out allowed',
        embedded_news_events=len(NEWS_UTC_MS),
    )
