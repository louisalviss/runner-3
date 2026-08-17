#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXACT = ROOT / 'wave-rider-verify' / 'reference_verify_v2513_exact.py'
spec = importlib.util.spec_from_file_location('wr_v2513_exact_core', EXACT)
assert spec and spec.loader
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)

base = core.base
Bar = core.Bar
Plan = core.Plan
Trade = core.Trade


def normalize_time_based_bars(tf: int, bars):
    """Normalize source-specific close timestamps to Pine `time_close` semantics.

    Binance kline archives store close time as interval_end - 1 ms. Pine's `time_close`
    on a time-based chart is the exact scheduled close boundary. WR v2.5.13 uses
    `time_close` in report-window, news, and session-cutoff logic, so preserving the
    Binance -1 ms convention changes execution semantics at exact boundaries.
    """
    chart_ms = tf * 60_000
    out = []
    for b in bars:
        expected_ct = b.ot + chart_ms
        out.append(Bar(b.ot, expected_ct, b.o, b.h, b.l, b.c))
    return out


def run_window_exact(tf: int, bars, tick: float, report_start_ms: int, report_end_ms: int, *, engine_start_ms: int | None = None):
    pine_bars = normalize_time_based_bars(tf, bars)
    return core.run_window_exact(
        tf,
        pine_bars,
        tick,
        report_start_ms,
        report_end_ms,
        engine_start_ms=engine_start_ms,
    )
