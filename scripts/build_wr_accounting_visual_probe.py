#!/usr/bin/env python3
from pathlib import Path
import hashlib, os

src=Path('/tmp/wr2513-base.pine').read_text()
rs=os.environ.get('REPORT_START_MS','1785110400000')
re=os.environ.get('REPORT_END_MS','1786924800000')
nonce=os.environ.get('GITHUB_RUN_ID','local')

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
arrays='''\n// PARITY VISUAL PROBE ONLY. These arrays never feed signals/orders/accounting.\nvar int[] __vn=array.new_int()\nvar float[] __vq=array.new_float()\nvar float[] __vrisk=array.new_float()\nvar float[] __vR=array.new_float()\nvar string[] __vexit=array.new_string()\nvar float[] __veq=array.new_float()\nvar float[] __vE=array.new_float()\nvar float[] __vS=array.new_float()\nvar float[] __vX=array.new_float()\n'''
src=src.replace(decl,decl+arrays,1)

anchor='            float canonicalCash=canonicalR*riskCash\n'
if src.count(anchor)!=1: raise SystemExit(f'cash anchor count={src.count(anchor)}')
audit='''            // PARITY VISUAL PROBE ONLY: capture exact runtime values BEFORE Canon equity mutates.\n            if reportEligible\n                array.push(__vn,i+1)\n                array.push(__vq,tradeQty)\n                array.push(__vrisk,riskCash)\n                array.push(__vR,canonicalR)\n                array.push(__vexit,canonicalExit)\n                array.push(__veq,canonicalEquity)\n                array.push(__vE,planEntry)\n                array.push(__vS,planStop)\n                array.push(__vX,actualExit)\n'''
src=src.replace(anchor,audit+anchor,1)

src += '''\n\n// PARITY VISUAL PROBE ONLY: compact runtime table for screenshot inspection.\nvar table __vt=table.new(position.top_center,9,17,border_width=1,force_overlay=true)\nif barstate.islast\n    table.clear(__vt,0,0,8,16)\n    color __h=color.rgb(35,35,35)\n    color __b=color.rgb(0,0,0)\n    color __fg=color.white\n    table.cell(__vt,0,0,"N",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,1,0,"QTY",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,2,0,"RISK",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,3,0,"R",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,4,0,"EXIT",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,5,0,"EQ0",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,6,0,"E",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,7,0,"SL",text_color=__fg,bgcolor=__h,text_size=size.small)\n    table.cell(__vt,8,0,"X",text_color=__fg,bgcolor=__h,text_size=size.small)\n    int __cnt=array.size(__vn)\n    if __cnt>0\n        int __shown=math.min(__cnt,14)\n        for __j=0 to __shown-1\n            int __row=__j+1\n            table.cell(__vt,0,__row,str.tostring(array.get(__vn,__j)),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,1,__row,str.tostring(array.get(__vq,__j),"#.###"),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,2,__row,str.tostring(array.get(__vrisk,__j),"#.###"),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,3,__row,str.tostring(array.get(__vR,__j),"#.#####"),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,4,__row,array.get(__vexit,__j),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,5,__row,str.tostring(array.get(__veq,__j),"#.###"),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,6,__row,str.tostring(array.get(__vE,__j),format.mintick),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,7,__row,str.tostring(array.get(__vS,__j),format.mintick),text_color=__fg,bgcolor=__b,text_size=size.small)\n            table.cell(__vt,8,__row,str.tostring(array.get(__vX,__j),format.mintick),text_color=__fg,bgcolor=__b,text_size=size.small)\n    string __m1="tick="+str.tostring(syminfo.mintick)+" minc="+str.tostring(syminfo.mincontract)+" pv="+str.tostring(syminfo.pointvalue)\n    string __m2="canon="+str.tostring(canonicalTrades)+" win="+str.tostring(windowTrades)+" WR="+str.tostring(windowTotalR,"#.#####")+" EQ="+str.tostring(canonicalEquity,"#.###")\n    table.cell(__vt,0,15,__m1,text_color=color.yellow,bgcolor=__h,text_size=size.small)\n    table.merge_cells(__vt,0,15,8,15)\n    table.cell(__vt,0,16,__m2,text_color=color.aqua,bgcolor=__h,text_size=size.small)\n    table.merge_cells(__vt,0,16,8,16)\n'''

src += f'\n// PARITY_VISUAL_NONCE {nonce}\n'
Path('/tmp/wr2513-accounting-visual.pine').write_text(src)
print('ACCOUNTING_VISUAL_SHA256='+hashlib.sha256(src.encode()).hexdigest())
