#!/usr/bin/env python3
import json, math, random, re, string, time
from datetime import datetime
from zoneinfo import ZoneInfo
import websocket

NY=ZoneInfo('America/New_York')
SESSION='2026-08-14'
SYMBOLS=[('NASDAQ','AMAT'),('NASDAQ','AMZN'),('NYSE','ANET'),('NASDAQ','APLD'),('NASDAQ','APP'),('NASDAQ','AVGO')]
TV='wss://data.tradingview.com/socket.io/websocket?from=chart%2F'
RX=re.compile(r'~m~(\d+)~m~')

def frame(s): return f'~m~{len(s)}~m~{s}'
def cmd(m,p): return frame(json.dumps({'m':m,'p':p},separators=(',',':')))
def sid(p): return p+''.join(random.choice(string.ascii_lowercase) for _ in range(12))
def payloads(raw):
    pos=0
    while pos<len(raw):
        m=RX.match(raw,pos)
        if not m: break
        n=int(m.group(1)); a=m.end(); b=a+n
        if b>len(raw): break
        yield raw[a:b]; pos=b

def fetch(exchange,symbol,bars=700,timeout=20):
    cs=sid('cs_'); ws=websocket.create_connection(TV,timeout=timeout,origin='https://www.tradingview.com',header=['User-Agent: Mozilla/5.0'])
    try:
        ws.send(cmd('set_auth_token',['unauthorized_user_token'])); ws.send(cmd('chart_create_session',[cs,'']))
        spec={'symbol':f'{exchange}:{symbol}','adjustment':'splits','session':'regular'}
        ws.send(cmd('resolve_symbol',[cs,'sym_0','='+json.dumps(spec,separators=(',',':'))]))
        ws.send(cmd('create_series',[cs,'ser_0','ser_0','sym_0','3',bars]))
        out=[]; end=time.monotonic()+timeout
        while time.monotonic()<end:
            ws.settimeout(max(.5,end-time.monotonic()))
            try: raw=ws.recv()
            except Exception: break
            if not isinstance(raw,str): continue
            for p in payloads(raw):
                if p.startswith('~h~'): ws.send(frame(p)); continue
                try: msg=json.loads(p)
                except: continue
                if msg.get('m')=='timescale_update':
                    u=msg.get('p',[None,{}])[1]
                    s=u.get('ser_0') if isinstance(u,dict) else None
                    if isinstance(s,dict):
                        vals=[]
                        for x in s.get('s',[]):
                            v=x.get('v',[])
                            if len(v)>=6:
                                try: vals.append(tuple(map(float,v[:6])))
                                except: pass
                        if vals: out=sorted(vals)
                if msg.get('m')=='series_completed': return out
        return out
    finally:
        try: ws.close()
        except: pass

def rma(vals,n):
    out=[None]*len(vals); buf=[]; prev=None
    for i,v in enumerate(vals):
        if v is None: continue
        if prev is None:
            buf.append(v)
            if len(buf)==n: prev=sum(buf)/n; out[i]=prev
        else:
            prev=(prev*(n-1)+v)/n; out[i]=prev
    return out

def ema(vals,n):
    a=2/(n+1); out=[]; e=None
    for v in vals:
        e=v if e is None else a*v+(1-a)*e; out.append(e)
    return out

def path_points(o,h,l,c):
    return [o,h,l,c] if abs(o-h)<abs(o-l) else [o,l,h,c]

def cross(a,b,x): return min(a,b)<=x<=max(a,b)

def intrabar_entry(bar,side,entry):
    o,h,l,c=bar[1],bar[2],bar[3],bar[4]
    if side==1 and o>=entry: return o
    if side==-1 and o<=entry: return o
    pts=path_points(o,h,l,c)
    for a,b in zip(pts,pts[1:]):
        if cross(a,b,entry):
            if side==1 and b>=a: return entry
            if side==-1 and b<=a: return entry
    return None

def bracket(bar,side,stop,target):
    h,l=bar[2],bar[3]
    stop_hit=l<=stop if side==1 else h>=stop
    tp_hit=h>=target if side==1 else l<=target
    if stop_hit and tp_hit: return ('AMBIG→SL',stop,-1.0,True)
    if stop_hit: return ('SL',stop,-1.0,False)
    if tp_hit: return ('TP',target,2.3,False)
    return None

def run(symbol,bars):
    b=[x for x in bars if datetime.fromtimestamp(x[0],NY).date().isoformat()==SESSION and 570<=datetime.fromtimestamp(x[0],NY).hour*60+datetime.fromtimestamp(x[0],NY).minute<960]
    if len(b)<100: return [], {'status':'INSUFFICIENT','bars':len(b)}
    # prepend warmup from earlier sessions
    allb=bars
    O=[x[1] for x in allb]; H=[x[2] for x in allb]; L=[x[3] for x in allb]; C=[x[4] for x in allb]
    E=ema(C,21)
    tr=[]
    for i,x in enumerate(allb):
        pc=C[i-1] if i else C[i]
        tr.append(max(H[i]-L[i],abs(H[i]-pc),abs(L[i]-pc)))
    A10=rma(tr,10); A14=rma(tr,14)
    above=below=0; resistance=support=None; pending=None; pos=None; eq=100000.0; trades=[]
    start_idx=next((i for i,x in enumerate(allb) if datetime.fromtimestamp(x[0],NY).date().isoformat()==SESSION),len(allb))
    for i,x in enumerate(allb):
        if i<1: continue
        dt=datetime.fromtimestamp(x[0],NY); mins=dt.hour*60+dt.minute; in_target=(dt.date().isoformat()==SESSION and 570<=mins<960)
        above=above+1 if C[i]>E[i] else 0; below=below+1 if C[i]<E[i] else 0
        center=i-11
        if center>=10 and center+10<i:
            ph=H[center]
            if ph>=max(H[center-10:center+11]): resistance=ph
            pl=L[center]
            if pl<=min(L[center-10:center+11]): support=pl
        if not in_target: continue
        closed_this_bar=False
        # pending stop entry lives only on the immediately following candle
        if pending and pending['signal_i']==i-1 and pos is None:
            fill=intrabar_entry(x,pending['side'],pending['entry'])
            if fill is not None:
                side=pending['side']; qty=pending['qty']; risk=pending['risk']
                pos={**pending,'actual_entry':fill,'entry_i':i}; pending=None
                bh=bracket(x,side,pos['stop'],pos['target'])
                if bh:
                    reason,px,r,amb=bh; eq+=r*risk
                    trades.append({'symbol':symbol,'side':'L' if side==1 else 'S','signal_et':datetime.fromtimestamp(pos['signal_ts'],NY).isoformat(),'entry_et':dt.isoformat(),'exit_et':dt.isoformat(),'planned_entry':round(pos['entry'],4),'actual_entry':round(fill,4),'stop':round(pos['stop'],4),'target':round(pos['target'],4),'exit':round(px,4),'reason':reason,'r':round(r,4),'ambiguous':amb})
                    pos=None; closed_this_bar=True
        if pending and pending['signal_i']<=i-1 and pos is None: pending=None
        # active bracket then managed exits
        if pos is not None and not closed_this_bar:
            bh=bracket(x,pos['side'],pos['stop'],pos['target'])
            if bh:
                reason,px,r,amb=bh; eq+=r*pos['risk']
                trades.append({'symbol':symbol,'side':'L' if pos['side']==1 else 'S','signal_et':datetime.fromtimestamp(pos['signal_ts'],NY).isoformat(),'entry_et':datetime.fromtimestamp(allb[pos['entry_i']][0],NY).isoformat(),'exit_et':dt.isoformat(),'planned_entry':round(pos['entry'],4),'actual_entry':round(pos['actual_entry'],4),'stop':round(pos['stop'],4),'target':round(pos['target'],4),'exit':round(px,4),'reason':reason,'r':round(r,4),'ambiguous':amb})
                pos=None; closed_this_bar=True
            else:
                time_close=mins+3
                session_exit=time_close>=945
                ema_up=E[i]>=E[max(0,i-2)]
                long_exit=pos['side']==1 and C[i]<E[i] and above<12 and not ema_up
                short_exit=pos['side']==-1 and C[i]>E[i] and below<12 and ema_up
                if session_exit or long_exit or short_exit:
                    reason='SESSION' if session_exit else 'EMA'; side=pos['side']; risk=pos['risk']; px=C[i]
                    r=side*(px-pos['entry'])*pos['qty']/risk
                    eq+=r*risk
                    trades.append({'symbol':symbol,'side':'L' if side==1 else 'S','signal_et':datetime.fromtimestamp(pos['signal_ts'],NY).isoformat(),'entry_et':datetime.fromtimestamp(allb[pos['entry_i']][0],NY).isoformat(),'exit_et':dt.isoformat(),'planned_entry':round(pos['entry'],4),'actual_entry':round(pos['actual_entry'],4),'stop':round(pos['stop'],4),'target':round(pos['target'],4),'exit':round(px,4),'reason':reason,'r':round(r,4),'ambiguous':False})
                    pos=None; closed_this_bar=True
        if pos is not None or pending is not None or closed_this_bar: continue
        if i<30 or A10[i] is None or A14[i] is None or resistance is None or support is None: continue
        angle=180/math.pi*math.atan((E[i]-E[i-4])/A10[i]/4) if A10[i] else 0
        prev_angle=180/math.pi*math.atan((E[i-1]-E[i-5])/A10[i-1]/4) if A10[i-1] else 0
        outside=abs(angle)>5
        ag=outside and angle>prev_angle; ar=outside and angle<prev_angle
        trs=sum(tr[i-13:i+1]); pr=max(H[i-13:i+1])-min(L[i-13:i+1]); chop=100*math.log10(trs/pr)/math.log10(14) if pr>0 else 100
        range_pass=(H[i]-L[i])/A14[i]<=1.5
        time_close=mins+3
        no_entry=time_close>=920 or time_close+3>=920
        if no_entry: continue
        long_ready=above>=12 and C[i]>E[i] and ag and chop<50
        short_ready=below>=12 and C[i]<E[i] and ar and chop<50
        side=0
        if range_pass and C[i]>O[i] and long_ready and C[i]>resistance and L[i]<=resistance: side=1
        if range_pass and C[i]<O[i] and short_ready and C[i]<support and H[i]>=support: side=-1
        if side:
            entry=(H[i]+.01) if side==1 else (L[i]-.01); stop=(L[i]-.01) if side==1 else (H[i]+.01)
            target=entry+side*2.3*abs(entry-stop); raw=(eq*.01)/abs(entry-stop); qty=math.floor(raw); risk=abs(entry-stop)*qty
            if qty>0 and risk>0: pending={'side':side,'signal_i':i,'signal_ts':x[0],'entry':entry,'stop':stop,'target':target,'qty':qty,'risk':risk}
    return trades, {'status':'COMPLETE','bars':len(b),'trades':len(trades)}

def summary(ts):
    rs=[t['r'] for t in ts]; wins=[r for r in rs if r>0]; losses=[r for r in rs if r<0]
    peak=cur=dd=0; streak=mx=0
    for r in rs:
        cur+=r; peak=max(peak,cur); dd=max(dd,peak-cur); streak=streak+1 if r<0 else 0; mx=max(mx,streak)
    return {'total_trades':len(rs),'total_r':round(sum(rs),4),'win_rate':round(100*len(wins)/len(rs),2) if rs else 0,'avg_r':round(sum(rs)/len(rs),4) if rs else 0,'profit_factor_r':round(sum(wins)/(-sum(losses)),4) if losses else None,'max_drawdown_r':round(dd,4),'max_losing_streak':mx}

def main():
    alltr=[]; per=[]
    for ex,s in SYMBOLS:
        bars=[]; err=None
        for delay in (0,1.5,4):
            if delay: time.sleep(delay)
            try: bars=fetch(ex,s)
            except Exception as e: err=str(e)
            if bars: break
        if not bars: per.append({'symbol':s,'status':'NO_BARS','error':err}); continue
        ts,st=run(s,bars); alltr+=ts; per.append({'symbol':s,**st})
    p={'schema':'wave-stage2-smoke-0.1','mode':'same-session-audit','parity_status':'SMOKE_APPROX_UNVERIFIED','source_session':SESSION,'candidate_count':len(SYMBOLS),'summary':summary(alltr),'per_symbol':per,'trades':alltr}
    print(json.dumps(p,ensure_ascii=False,indent=2))
    open('data/wave_stage2_smoke.json','w').write(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__': main()
