from pathlib import Path

# Research diagnostic only.
# Reuse the frozen v2.5.15 10m engine exactly, changing ONE execution rule:
# baseline next-bar intrabar trigger -> next-bar CLOSE confirmation, entry at that close.
# All signal logic, S/R, EMA, angle, CHOP, signal-range gate, TP=2.3R,
# stop anchor and lifecycle remain unchanged.

p = Path('wave-rider-verify/wr2515_tf_phase1.py')
src = p.read_text()
old = """        if active is None and pending is not None and i==pending.sig_i+1 and not closed:\n            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))\n            if fill:\n                gap=(pending.d==1 and round(x.o/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.o/tick)<=round(pending.e/tick))\n                active=pending; pending=None; r,px=nextb(active,x,None if gap else active.e)\n                if r:closed=close(i,r,px)\n"""
new = """        if active is None and pending is not None and i==pending.sig_i+1 and not closed:\n            # Close-confirm diagnostic: the next bar must CLOSE through the original\n            # breakout trigger. Entry is the confirming close, so there is no\n            # look-ahead fill at the earlier trigger price. Bracket becomes active\n            # from the following bar.\n            confirm=(pending.d==1 and round(x.c/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.c/tick)<=round(pending.e/tick))\n            if confirm:\n                d=pending.d; s=pending.s; e=x.c\n                valid=(d==1 and e>s) or (d==-1 and e<s)\n                if valid:\n                    t=e+TP*(e-s) if d==1 else e-TP*(s-e)\n                    q=math.floor((eq*RP/100)/abs(e-s)); risk=abs(e-s)*q\n                    if q>0 and risk>0:\n                        active=Plan(d,e,s,t,risk,q,pending.sig_i,pending.sig_t,pending.sig_h,pending.sig_l)\n                pending=None\n"""
if src.count(old) != 1:
    raise RuntimeError(f'close-confirm patch anchor count={src.count(old)} expected=1')
src = src.replace(old, new, 1)
# Tag stdout only; output schema stays identical for direct comparison.
src = src.replace("runner3-wr2515-phase1-{TF}m/1.0", "runner3-wr-close-confirm-{TF}m/1.0")
exec(compile(src, 'wr_close_confirm_core_diag_exec.py', 'exec'), {'__name__':'__main__'})
