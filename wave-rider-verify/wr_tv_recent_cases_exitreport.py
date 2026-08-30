#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sys, types
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent

# Load the TradingView parity engine, but correct WIN REPORT attribution to match
# the frozen verifier/Pine behavior: a trade belongs to the window by EXIT time,
# not by signal time. Strategy logic is otherwise unchanged.
src=(HERE/'wr_tv_parity.py').read_text()
old="if p.report: trades.append({'signal':p.sig_t,'exit':b.ct,'side':'L' if p.d==1 else 'S','R':cr,'reason':reason,'e':p.e,'s':p.s,'t':p.t})"
new="if start_ms <= b.ct <= end_ms: trades.append({'signal':p.sig_t,'exit':b.ct,'side':'L' if p.d==1 else 'S','R':cr,'reason':reason,'e':p.e,'s':p.s,'t':p.t})"
if old not in src:
    raise RuntimeError('expected report-attribution line not found')
src=src.replace(old,new,1)
base=types.ModuleType('base_tv_parity_exitreport')
base.__file__=str(HERE/'wr_tv_parity.py')
sys.modules[base.__name__]=base
exec(compile(src,base.__file__,'exec'),base.__dict__)
base.START=datetime(2026,8,9,17,0,tzinfo=timezone.utc)  # 10 Aug 00:00 VN
base.END=datetime(2026,8,15,17,0,tzinfo=timezone.utc)    # 16 Aug 00:00 VN

spec=importlib.util.spec_from_file_location('recent_cases',HERE/'wr_tv_recent_cases.py')
recent=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=recent
spec.loader.exec_module(recent)
recent.base=base
recent.main()
