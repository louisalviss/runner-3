from pathlib import Path
import hashlib,re

p=Path('/tmp/wr2513.pine').read_text()
def rep(old,new,n=1):
    global p
    c=p.count(old)
    if c<n: raise SystemExit(f'PINE_PATCH_MISSING count={c}: {old[:120]}')
    p=p.replace(old,new,n)

rep('strategy("Wave Rider Strategy v2.5.13 WINDOW REPORT", shorttitle="WR 2.5.13 WIN"',
    'strategy("Wave Rider Strategy v2.5.15 DETERMINISTIC", shorttitle="WR 2.5.15 DET"')
rep('// Wave Rider 2.5.13 WINDOW REPORT', '''// Wave Rider 2.5.15 DETERMINISTIC
// v2.5.15 = v2.5.13 Window Report + deterministic state anchor.
// v2.5.14 notional cap is intentionally NOT carried forward.
// State Start gates deterministic indicator/state initialization; Window Start/End remain report-only.''')
rep('''groupWindow="10. Window Report"
startTime=input.time(1785171600000,"Start (VN)",group=groupWindow)
endTime=input.time(1786813200000,"End (VN, exclusive)",group=groupWindow)
validWindow=endTime>startTime
signalInReportWindow=validWindow and time_close>=startTime and time_close<endTime''',
    '''groupWindow="10. Deterministic Window"
stateStartTime=input.time(1785171600000,"State Start (VN, exact bar required)",group=groupWindow)
startTime=input.time(1785862800000,"Start (VN)",group=groupWindow)
endTime=input.time(1786294800000,"End (VN, exclusive)",group=groupWindow)
var bool stateAnchorSeen=false
if time==stateStartTime
    stateAnchorSeen:=true
stateActive=stateAnchorSeen
validWindow=endTime>startTime
signalInReportWindow=stateActive and validWindow and time_close>=startTime and time_close<endTime
detClose=stateActive?close:na
detHigh=stateActive?high:na
detLow=stateActive?low:na
detTR=stateActive?(na(detClose[1])?high-low:math.max(high-low,math.abs(high-detClose[1]),math.abs(low-detClose[1]))):na''')
rep('ema21=ta.ema(close,emaLength)','ema21=ta.ema(detClose,emaLength)')
rep('ph=ta.pivothigh(high,leftBars,rightBars)[1]','ph=ta.pivothigh(detHigh,leftBars,rightBars)[1]')
rep('pl=ta.pivotlow(low,leftBars,rightBars)[1]','pl=ta.pivotlow(detLow,leftBars,rightBars)[1]')
rep('belowCount:=close<ema21?nz(belowCount[1])+1:0','belowCount:=stateActive and not na(ema21) and close<ema21?nz(belowCount[1])+1:0')
rep('aboveCount:=close>ema21?nz(aboveCount[1])+1:0','aboveCount:=stateActive and not na(ema21) and close>ema21?nz(aboveCount[1])+1:0')
rep('atrAngle=ta.atr(atrPeriod)','atrAngle=ta.rma(detTR,atrPeriod)')
rep('trSum=math.sum(ta.atr(1),chopLength)','trSum=math.sum(detTR,chopLength)')
rep('priceRange=ta.highest(high,chopLength)-ta.lowest(low,chopLength)','priceRange=ta.highest(detHigh,chopLength)-ta.lowest(detLow,chopLength)')
rep('signalATR=ta.atr(signalAtrLength)','signalATR=ta.rma(detTR,signalAtrLength)')
rep('bool engineOK=canonOutcomeOK and canonExitOK and skippedNativeToCanon==0 and tpLockOK',
    'bool engineOK=stateAnchorSeen and canonOutcomeOK and canonExitOK and skippedNativeToCanon==0 and tpLockOK')
rep('string engineText=engineOK?"✓ CLEAN":"! CHECK"',
    'string engineText=not stateAnchorSeen?"! ANCHOR":engineOK?"✓ CLEAN":"! CHECK"')
assert 'signalRangePass=not na(signalRangeATR) and signalRangeATR<=maxSignalRangeATR' in p
assert 'Max Notional / Equity' not in p and 'notionalCap' not in p
Path('/tmp/wr2515.pine').write_text(p)
Path('/tmp/Wave Rider Strategy v2.5.15 DETERMINISTIC.md').write_text('```pine\n'+p+'```\n')
print('WR2515_NOCAP_SHA256='+hashlib.sha256(p.encode()).hexdigest())

v=Path('/tmp/reference_verify.py').read_text()
v=v.replace('# Wave Rider 2.5.13 defaults','# Wave Rider 2.5.15 deterministic defaults',1)
v=v.replace("END=os.getenv('WR_END','2026-08-14')", "END=os.getenv('WR_END','2026-08-10')\nREPORT_START=os.getenv('WR_REPORT_START','2026-08-05T00:00:00+07:00')\nREPORT_END=os.getenv('WR_REPORT_END','2026-08-10T00:00:00+07:00')\nSTATE_START=os.getenv('WR_STATE_START','2026-07-28T00:00:00+07:00')",1)
v=v.replace('TFS=(3,5,10)',"TFS=(int(os.getenv('WR_TF','5')),)",1)
v=v.replace('TP_R=2.3; RISK_PCT=1.0; INIT=100000.0','TP_R=2.3; RISK_PCT=1.0; INIT=100000.0\nQTY_STEP=float(os.getenv("WR_QTY_STEP","1.0"))',1)
old='''        if v[c]==ext:\n            if sum(x==ext for x in w)==1: base[conf]=v[c]\n            else: ties+=1\n'''
new='''        if v[c]==ext:\n            # Pine ta.pivothigh/low parity: left/older equal is allowed; right/newer equal rejects.\n            if all(x!=ext for x in v[c+1:c+right+1]): base[conf]=v[c]\n            else: ties+=1\n'''
if v.count(old)!=1: raise SystemExit('VERIFIER_PIVOT_PATCH_MISSING')
v=v.replace(old,new,1)
v=v.replace('a=datetime.fromisoformat(START).replace(tzinfo=timezone.utc)-timedelta(days=WARMUP_DAYS)\n    b=datetime.fromisoformat(END).replace(tzinfo=timezone.utc)',
            'a=datetime.fromisoformat(STATE_START).astimezone(timezone.utc)\n    b=datetime.fromisoformat(REPORT_END).astimezone(timezone.utc)+timedelta(days=2)',1)
v=v.replace('def run(tf,bars,tick,start_ms,end_ms):\n    ind,pht,plt=calc_ind(bars); chart_ms=tf*60000; eq=INIT; peak=INIT',
            'def run(tf,bars,tick,start_ms,end_ms):\n    state_ms=int(datetime.fromisoformat(STATE_START).timestamp()*1000)\n    bars=[x for x in bars if x.ot>=state_ms]\n    ind,pht,plt=calc_ind(bars); chart_ms=tf*60000; eq=INIT; peak=INIT',1)
v,nsub=re.subn(r'if start_ms<=bars\[i\]\.ct<=?end_ms:\n\s+trades\.append\(Trade',
               'if start_ms<=active.sig_t<end_ms:\n            trades.append(Trade',v,count=1)
if nsub!=1: raise SystemExit('VERIFIER_REPORT_MEMBERSHIP_PATCH_MISSING')
v=v.replace('        if x.ct>end_ms: break\n','',1)
v=v.replace('        # Warmup bars compute indicators only; no orders until evaluation window.\n        if x.ct<start_ms or x.ct>end_ms: continue\n','',1)
v=v.replace('raw=(eq*RISK_PCT/100)/abs(e-s); q=math.floor(raw); risk=abs(e-s)*q\n                if q>0 and risk>0:',
            'raw=(eq*RISK_PCT/100)/abs(e-s); q=math.floor(raw/QTY_STEP)*QTY_STEP; risk=abs(e-s)*q\n                if q>0 and risk>0:',1)
pos=v.index('def main():')
v=v[:pos]+'''def main():
    OUT.mkdir(parents=True,exist_ok=True)
    one,tick,missing=fetch_1m(); sm=[]
    st=int(datetime.fromisoformat(REPORT_START).timestamp()*1000)
    en=int(datetime.fromisoformat(REPORT_END).timestamp()*1000)
    for tf in TFS:
        tr,s=run(tf,agg(one,tf),tick,st,en); sm.append(s)
        p=OUT/f'{SYMBOL}_{tf}m_trades.csv'
        with p.open('w',newline='') as f:
            fields=list(Trade.__dataclass_fields__); w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            for x in tr: w.writerow(asdict(x))
    payload={'symbol':SYMBOL,'state_start':STATE_START,'report_start':REPORT_START,'report_end':REPORT_END,'tick':tick,'missing_days':missing,'summary':sm}
    print(json.dumps(payload,indent=2))
    (OUT/f'{SYMBOL}_summary.json').write_text(json.dumps(payload,indent=2))

if __name__=='__main__': main()
'''
Path('/tmp/reference_verify_v2.5.15.py').write_text(v)
print('VER2515_NOCAP_SHA256='+hashlib.sha256(v.encode()).hexdigest())
