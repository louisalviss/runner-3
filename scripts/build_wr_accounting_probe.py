#!/usr/bin/env python3
from pathlib import Path
import hashlib, os

src=Path('/tmp/wr2513-base.pine').read_text()
rs=os.environ.get('REPORT_START_MS','1785110400000')
re=os.environ.get('REPORT_END_MS','1786924800000')

old='startTime=input.time(1785171600000,"Start (VN)",group=groupWindow)'
new=f'startTime=input.time({rs},"Start (VN)",group=groupWindow)'
if src.count(old)!=1: raise SystemExit(f'start anchor count={src.count(old)}')
src=src.replace(old,new,1)
old='endTime=input.time(1786813200000,"End (VN, exclusive)",group=groupWindow)'
new=f'endTime=input.time({re},"End (VN, exclusive)",group=groupWindow)'
if src.count(old)!=1: raise SystemExit(f'end anchor count={src.count(old)}')
src=src.replace(old,new,1)

decl='var bool activeInReportWindow=false\n'
if src.count(decl)!=1: raise SystemExit(f'decl anchor count={src.count(decl)}')
src=src.replace(decl,decl+'''\n// PARITY PROBE ONLY: report/debug arrays, never consumed by execution.\nvar string[] __parityRows=array.new_string()\nvar int __parityFirstTime=time\n''',1)

anchor='            float canonicalCash=canonicalR*riskCash\n'
if src.count(anchor)!=1: raise SystemExit(f'cash anchor count={src.count(anchor)}')
audit='''            // PARITY PROBE ONLY: exact report-row values before canonical equity mutates.\n            if reportEligible\n                string __pr="WRP#"+str.tostring(i+1)+"|entryMs="+str.tostring(strategy.closedtrades.entry_time(i))+"|exitMs="+str.tostring(strategy.closedtrades.exit_time(i))+"|qty="+str.tostring(tradeQty)+"|risk="+str.tostring(riskCash)+"|planE="+str.tostring(planEntry)+"|planS="+str.tostring(planStop)+"|planT="+str.tostring(planTarget)+"|actualE="+str.tostring(actualEntry)+"|actualX="+str.tostring(actualExit)+"|canonR="+str.tostring(canonicalR)+"|exit="+canonicalExit+"|report=1|eqBefore="+str.tostring(canonicalEquity)+"|nativePnl="+str.tostring(tradeProfitNative)+"|both="+(bothTouched?"1":"0")\n                array.push(__parityRows,__pr)\n'''
src=src.replace(anchor,audit+anchor,1)

src += '''\n\n// PARITY PROBE ONLY: expose exact accounting state in a DOM-readable table.\nvar table __parityTable=table.new(position.top_left,1,32,border_width=1,force_overlay=true)\nif barstate.islast\n    table.clear(__parityTable,0,0,0,31)\n    string __meta="WRMETA|firstMs="+str.tostring(__parityFirstTime)+"|lastMs="+str.tostring(time_close)+"|mintick="+str.tostring(syminfo.mintick)+"|mincontract="+str.tostring(syminfo.mincontract)+"|pointvalue="+str.tostring(syminfo.pointvalue)+"|rows="+str.tostring(array.size(__parityRows))+"|canonEq="+str.tostring(canonicalEquity)+"|canonTrades="+str.tostring(canonicalTrades)+"|windowTrades="+str.tostring(windowTrades)+"|windowR="+str.tostring(windowTotalR)\n    table.cell(__parityTable,0,0,__meta,text_color=color.white,bgcolor=color.black,text_size=size.tiny)\n    if array.size(__parityRows)>0\n        int __n=math.min(array.size(__parityRows),31)\n        for __k=0 to __n-1\n            table.cell(__parityTable,0,__k+1,array.get(__parityRows,__k),text_color=color.white,bgcolor=color.black,text_size=size.tiny)\n'''

Path('/tmp/wr2513-accounting-probe.pine').write_text(src)
print('ACCOUNTING_PROBE_SHA256='+hashlib.sha256(src.encode()).hexdigest())
