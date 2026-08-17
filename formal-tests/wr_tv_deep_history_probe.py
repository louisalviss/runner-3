#!/usr/bin/env python3
import json,time,random,re,string
from datetime import datetime,timezone
import websocket
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

def fetch(sym,tf,target='2026-01-01T00:00:00+00:00'):
    target_ts=int(datetime.fromisoformat(target).timestamp())
    cs=sid('cs_'); sk='ser_0'; vals={}; meta={}; errs=[]
    ws=websocket.create_connection(TV,timeout=20,origin='https://www.tradingview.com',header=['User-Agent: Mozilla/5.0'])
    try:
        ws.send(cmd('set_auth_token',['unauthorized_user_token'])); ws.send(cmd('chart_create_session',[cs,'']))
        spec={'symbol':sym,'adjustment':'splits','session':'regular'}
        ws.send(cmd('resolve_symbol',[cs,'sym_0','='+json.dumps(spec,separators=(',',':'))]))
        ws.send(cmd('create_series',[cs,sk,sk,'sym_0',str(tf),5000]))
        rounds=0; completed=0; deadline=time.monotonic()+150; last_oldest=None; stagnant=0
        while time.monotonic()<deadline:
            ws.settimeout(max(.5,min(8,deadline-time.monotonic())))
            try: raw=ws.recv()
            except Exception: break
            if not isinstance(raw,str): continue
            for p in payloads(raw):
                if p.startswith('~h~'): ws.send(frame(p)); continue
                try: msg=json.loads(p)
                except: continue
                m=msg.get('m'); par=msg.get('p',[])
                if m=='symbol_resolved' and len(par)>=3 and isinstance(par[2],dict): meta=par[2]
                elif m=='critical_error': errs.append(par)
                elif m=='timescale_update':
                    u=par[1] if len(par)>1 and isinstance(par[1],dict) else {}; s=u.get(sk)
                    if isinstance(s,dict):
                        for row in s.get('s',[]):
                            v=row.get('v',[])
                            if len(v)>=5:
                                try: vals[int(float(v[0]))]=v[:5]
                                except: pass
                elif m=='series_completed' and len(par)>1 and par[1]==sk:
                    completed+=1
                    if not vals: break
                    oldest=min(vals); newest=max(vals)
                    print(sym,tf,'round',rounds,'bars',len(vals),'oldest',datetime.fromtimestamp(oldest,timezone.utc).isoformat(),flush=True)
                    if oldest<=target_ts: return {'symbol':sym,'tf':tf,'bars':len(vals),'rounds':rounds,'oldest':oldest,'newest':newest,'reached_target':True,'errors':errs}
                    if oldest==last_oldest: stagnant+=1
                    else: stagnant=0
                    last_oldest=oldest
                    if stagnant>=2 or rounds>=30: return {'symbol':sym,'tf':tf,'bars':len(vals),'rounds':rounds,'oldest':oldest,'newest':newest,'reached_target':False,'stagnant':stagnant,'errors':errs}
                    rounds+=1; ws.send(cmd('request_more_data',[cs,sk,5000]))
        return {'symbol':sym,'tf':tf,'bars':len(vals),'rounds':rounds,'oldest':min(vals) if vals else None,'newest':max(vals) if vals else None,'reached_target':False,'timeout':True,'errors':errs}
    finally:
        try: ws.close()
        except: pass

out=[]
for sym,tf in [('BATS:AAPL',5),('FX_IDC:EURUSD',5),('OANDA:XAUUSD',5),('OANDA:NAS100USD',5),('BATS:AAPL',3)]:
    try: out.append(fetch(sym,tf))
    except Exception as e: out.append({'symbol':sym,'tf':tf,'error':repr(e)})
open('wr_tv_deep_history_probe.json','w').write(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
