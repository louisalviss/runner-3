#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, os, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('wrfull', HERE/'wr_dukascopy_full_robustness.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
orig=mod.resolve_symbol
mod.resolve_symbol=lambda symbol: 'FB.US/USD' if symbol.upper()=='META' else orig(symbol)
mod.run_symbol('META')
