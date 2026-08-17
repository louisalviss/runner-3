#!/usr/bin/env python3
import importlib.util, os, sys
from pathlib import Path
p=Path(__file__).with_name('wr_cross_asset_screen.py')
spec=importlib.util.spec_from_file_location('wr_screen',p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
g=os.environ['WR_GROUP']
if g not in m.GROUPS: raise SystemExit(f'unknown group {g}')
m.GROUPS={g:m.GROUPS[g]}
sys.argv=[sys.argv[0],'--out',f'wr_cross_asset_{g}.json']
m.main()
