#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, random, re, string, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import websocket

START = datetime(2026,7,27,tzinfo=timezone.utc)
END = datetime(2026,8,15,tzinfo=timezone.utc)  # exclusive; through Aug 14
TFS = (3,5,10)
TV='wss://data.tradingview.com/socket.io/websocket?from=chart%2F'
RX=re.compile(r'~m~(\d+)~m~')
TP_R=2.3

# Public, Wave-Rider-independent benchmark basket. Never copy the private
# HAS_TRADE_BEFORE registry into this public runner.
GROUPS={
 'stock_us': [f'BATS:{s}' for s in [
   'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','AMD','NFLX',
   'ORCL','CRM','PLTR','JPM','BAC','WFC','GS','V','MA','WMT','COST','HD','LOW',
   'XOM','CVX','LLY','JNJ','PFE','UNH','PG','KO','CAT','GE','BA','MU','QCOM','INTC']],
 'forex': [f'FX_IDC:{s}' for s in ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','USDCHF','NZDUSD']],
 'metal': ['OANDA:XAUUSD','OANDA:XAGUSD'],
 'index': ['OANDA:NAS100USD','OANDA:SPX500USD','OANDA:US30USD'],
}

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

class Bar:
    __slots__=('ot','ct','o','h','l','c')
    def __init__(self,ot,tf,o,h,l,c):
        self.ot=int(ot*1000); self.ct=self.ot+tf*60000
        self.o=float(o); self.h=float(h); self.l=float(l); self.c=float(c)

def fetch_symbol(fullsym, bars=5000, timeout=18):
    cs=sid('cs_'); ws=websocket.create_connection(TV,timeout=timeout,origin='https://www.tradingview.com',header=['User-Agent: Mozilla/5.0'])
    series={f'ser_{tf}':{} for tf in TFS}; completed=set(); meta={}; errors=[]
    try:
        ws.send(cmd('set_auth_token',['unauthorized_user_token']))
        ws.send(cmd('chart_create_session',[cs,'']))
        spec={'symbol':fullsym,'adjustment':'splits','session':'regular'}
        ws.send(cmd('resolve_symbol',[cs,'sym_0','='+json.dumps(spec,separators=(',',':'))]))
        for tf in TFS:
            k=f'ser_{tf}'; ws.send(cmd('create_series',[cs,k,k,'sym_0',str(tf),bars]))
        end=time.monotonic()+timeout
        while time.monotonic()<end and len(completed)<len(TFS):
            ws.settimeout(max(.5,min(5,end-time.monotonic())))
            try: raw=ws.recv()
            except Exception: break
            if not isinstance(raw,str): continue
            for p in payloads(raw):
                if p.startswith('~h~'): ws.send(frame(p)); continue
                try: msg=json.loads(p)
                except: continue
                m=msg.get('m'); par=msg.get('p',[])
                if m=='symbol_resolved' and len(par)>=3 and isinstance(par[2],dict):
                    x=par[2]
                    for k in ('name','full_name','description','exchange','listed_exchange','timezone','session','minmov','pricescale','pointvalue','type'):
                        if k in x: meta[k]=x[k]
                elif m=='critical_error': errors.append(par)
                elif m=='timescale_update':
                    u=par[1] if len(par)>1 and isinstance(par[1],dict) else {}
                    for sk in series:
                        s=u.get(sk)
                        if isinstance(s,dict):
                            for row in s.get('s',[]):
                                v=row.get('v',[])
                                if len(v)>=5:
                                    try: series[sk][int(float(v[0]))]=v[:5]
                                    except: pass
                elif m=='series_completed' and len(par)>1 and par[1] in series:
                    completed.add(par[1])
        out={}
        for tf in TFS:
            vals=series[f'ser_{tf}']
            out[tf]=[Bar(ts,tf,*vals[ts][1:5]) for ts in sorted(vals)]
        return out,meta,errors,sorted(completed)
    finally:
        try: ws.close()
        except: pass

def ema(v,n):
    a=2/(n+1); out=[]; p=None
    for x in v:
        p=x if p is None else a*x+(1-a)*p; out.append(p)
    return out

def rma(v,n):
    out=[None]*len(v); p=None; seed=[]
    for i,x in enumerate(v):
        if p is None:
            seed.append(x)
            if len(seed)==n: p=sum(seed)/n; out[i]=p
        else:
            p=(p*(n-1)+x)/n; out[i]=p
    return out

def calc_ind(b):
    C=[x.c for x in b]; H=[x.h for x in b]; L=[x.l for x in b]
    E=ema(C,21); tr=[]
    for i,x in enumerate(b):
        pc=C[i-1] if i else C[i]
        tr.append(max(x.h-x.l,abs(x.h-pc),abs(x.l-pc)))
    A10=rma(tr,10); A14=rma(tr,14)
    above=below=0; resistance=support=None; angles=[None]*len(b); out=[]
    for i,x in enumerate(b):
        center=i-11  # pivot 10/10 plus Pine [1] confirmation delay
        if center>=10 and center+10<i:
            wH=H[center-10:center+11]; wL=L[center-10:center+11]
            ph=H[center]; pl=L[center]
            if ph==max(wH) and sum(z==ph for z in wH)==1: resistance=ph
            if pl==min(wL) and sum(z==pl for z in wL)==1: support=pl
        above=above+1 if x.c>E[i] else 0
        below=below+1 if x.c<E[i] else 0
        ema_up=i>=2 and E[i]>=E[i-2]
        an=None
        if i>=4 and A10[i] not in (None,0): an=math.degrees(math.atan((E[i]-E[i-4])/A10[i]/4))
        angles[i]=an
        outside=an is not None and (an>5 or an<-5)
        ag=i>0 and outside and angles[i-1] is not None and an>angles[i-1]
        ar=i>0 and outside and angles[i-1] is not None and an<angles[i-1]
        ch=None
        if i>=13:
            trs=sum(tr[i-13:i+1]); pr=max(H[i-13:i+1])-min(L[i-13:i+1])
            if pr>0 and trs>0: ch=100*math.log10(trs/pr)/math.log10(14)
        sra=None if A14[i] in (None,0) else (x.h-x.l)/A14[i]
        out.append({'ema':E[i],'ema_up':ema_up,'ha':above>=12,'hb':below>=12,
                    'ag':ag,'ar':ar,'chop_ok':ch is not None and ch<50,
                    'sra_ok':sra is not None and sra<=1.5,'res':resistance,'sup':support})
    return out

def hm(v):
    v=v.strip(); return int(v[:2])*60+int(v[2:4])

def regular_close_ms(bar_ot_ms, meta):
    sess=str(meta.get('session','')).split(':')[0].split(';')[0]
    if '-' not in sess: return None
    try: a,b=sess.split('-',1); sm,em=hm(a),hm(b)
    except: return None
    try: tz=ZoneInfo(meta.get('timezone') or 'UTC')
    except: tz=timezone.utc
    dt=datetime.fromtimestamp(bar_ot_ms/1000,tz)
    lm=dt.hour*60+dt.minute
    d=dt.date()
    if sm==em:
        cd=d if lm<em else d+timedelta(days=1)
    elif sm<em:
        cd=d
    else:
        cd=d+timedelta(days=1) if lm>=sm else d
    close=datetime(cd.year,cd.month,cd.day,em//60,em%60,tzinfo=tz)
    return int(close.timestamp()*1000)

def session_flags(x,tf,meta):
    close=regular_close_ms(x.ot,meta)
    if close is None: return True,False
    chart=tf*60000; noentry=close-40*60000; ex=close-15*60000
    allowed=not (x.ct>=noentry or x.ct+chart>=noentry)
    exitnow=(x.ct>=ex and x.ct<=close)
    return allowed,exitnow

def path_points(x):
    return [x.o,x.h,x.l,x.c] if abs(x.o-x.h)<abs(x.o-x.l) else [x.o,x.l,x.h,x.c]

def after_entry_path(x,side,e):
    pts=path_points(x)
    if side==1 and pts[0]>=e: return pts[0],[pts[0]]+pts[1:]
    if side==-1 and pts[0]<=e: return pts[0],[pts[0]]+pts[1:]
    for j,(a,b) in enumerate(zip(pts,pts[1:])):
        if side==1 and a<e<=b: return e,[e,b]+pts[j+2:]
        if side==-1 and a>e>=b: return e,[e,b]+pts[j+2:]
    return None,None

def touches(points,p):
    return any(min(a,b)<=p<=max(a,b) for a,b in zip(points,points[1:])) if points and len(points)>1 else False

def entry_bracket(x,side,e,s,t):
    fill,pts=after_entry_path(x,side,e)
    if fill is None: return None,None,None,False
    sh=touches(pts,s); th=touches(pts,t)
    if sh and th: return fill,'AMBIG->SL',s,True
    if sh: return fill,'SL',s,False
    if th: return fill,'TP',t,False
    return fill,None,None,False

def active_bracket(x,side,s,t):
    sh=x.l<=s if side==1 else x.h>=s
    th=x.h>=t if side==1 else x.l<=t
    if sh and th: return 'AMBIG->SL',s,True
    if sh: return 'SL',s,False
    if th: return 'TP',t,False
    return None,None,False

def run(tf,b,meta,tick):
    if len(b)<50: return []
    ind=calc_ind(b); pending=None; pos=None; trades=[]
    st=int(START.timestamp()*1000); en=int(END.timestamp()*1000)
    for i,x in enumerate(b):
        if x.ct>=en: break
        closed=False
        # Existing position bracket first.
        if pos is not None:
            reason,px,amb=active_bracket(x,pos['d'],pos['s'],pos['t'])
            if reason:
                r=-1.0 if reason!='TP' else TP_R
                trades.append({'tf':tf,'signal':pos['sig'],'entry':pos['ent_t'],'exit':x.ct,'r':r,'reason':reason,'ambiguous':amb})
                pos=None; closed=True
        # Pending stop entry only on immediately following chart candle.
        if pos is None and pending is not None and i==pending['i']+1 and not closed:
            fill,reason,px,amb=entry_bracket(x,pending['d'],pending['e'],pending['s'],pending['t'])
            if fill is not None:
                pos={**pending,'fill':fill,'ent_t':x.ot}; pending=None
                if reason:
                    r=-1.0 if reason!='TP' else TP_R
                    trades.append({'tf':tf,'signal':pos['sig'],'entry':x.ot,'exit':x.ct,'r':r,'reason':reason,'ambiguous':amb})
                    pos=None; closed=True
        if pending is not None and i>=pending['i']+1 and pos is None: pending=None
        allowed,sexit=session_flags(x,tf,meta)
        if pos is not None and not closed:
            z=ind[i]
            le=pos['d']==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']
            se=pos['d']==-1 and x.c>z['ema'] and not z['hb'] and z['ema_up']
            if sexit or le or se:
                r=pos['d']*(x.c-pos['e'])/abs(pos['e']-pos['s'])
                trades.append({'tf':tf,'signal':pos['sig'],'entry':pos['ent_t'],'exit':x.ct,'r':r,'reason':'SESSION' if sexit else 'EMA','ambiguous':False})
                pos=None; closed=True
        if x.ct<st: continue
        if pos is not None or pending is not None or closed: continue
        z=ind[i]
        lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
        sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
        nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
        ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
        if nl or ns:
            d=1 if nl else -1
            e=x.h+tick if d==1 else x.l-tick
            s=x.l-tick if d==1 else x.h+tick
            if abs(e-s)>0:
                t=e+d*TP_R*abs(e-s)
                pending={'d':d,'e':e,'s':s,'t':t,'i':i,'sig':x.ct}
    return trades

def mean(a): return sum(a)/len(a) if a else None
def pf(a):
    gp=sum(x for x in a if x>0); gl=-sum(x for x in a if x<0)
    return gp/gl if gl>0 else None

def qtile(xs,q):
    if not xs: return None
    s=sorted(xs); p=(len(s)-1)*q; lo=int(math.floor(p)); hi=int(math.ceil(p))
    return s[lo] if lo==hi else s[lo]*(hi-p)+s[hi]*(p-lo)
def block_ci(a,reps=2000,seed=2513):
    n=len(a)
    if n<2:return [None,None]
    rng=random.Random(seed); L=max(2,min(n,round(n**(1/3)))); vals=[]
    for _ in range(reps):
        z=[]
        while len(z)<n:
            if n<=L: z.extend(a); break
            st=rng.randrange(0,n-L+1); z.extend(a[st:st+L])
        vals.append(mean(z[:n]))
    return [qtile(vals,.025),qtile(vals,.975)]
def summarize(ts):
    a=[float(t['r']) for t in ts]
    wins=sum(x>0 for x in a)
    curve=peak=dd=0; ls=mx=0
    for r in a:
        curve+=r; peak=max(peak,curve); dd=max(dd,peak-curve); ls=ls+1 if r<0 else 0; mx=max(mx,ls)
    ci=block_ci(a) if len(a)>=5 else [None,None]
    return {'n':len(a),'total_r':sum(a),'avg_r':mean(a),'pf_r':pf(a),'win_rate':100*wins/len(a) if a else None,
            'ci95_avg_r':ci,'max_dd_r':dd,'max_loss_streak':mx,
            'classification':('SCREEN_POSITIVE' if len(a)>=20 and ci[0] is not None and ci[0]>0 else
                              'SCREEN_NEGATIVE' if len(a)>=20 and ci[1] is not None and ci[1]<0 else 'UNPROVEN')}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default='wr_cross_asset_screen.json'); args=ap.parse_args()
    result={'schema':'wr-cross-asset-screen-0.1','strategy':'Wave Rider v2.5.13 core/lifecycle cross-asset replication',
            'window_utc':{'start':START.isoformat(),'end_exclusive':END.isoformat()},
            'status':'SCREENING_ONLY_NOT_OOS_VALIDATION',
            'notes':['TradingView public regular-session bars; no authenticated deep-history entitlement.',
                     'Same fixed calendar window and 3m/5m/10m across groups.',
                     'Gross R only: spread/commission/slippage are not deducted.',
                     'Stock benchmark is public and independent of private HAS_TRADE_BEFORE, but current-basket survivorship remains.',
                     'FX/metals/indices are feed-specific proxies; broker CFD execution can differ.',
                     'Do not promote any winner from this reused short window directly to production.'],
            'groups':{},'errors':[]}
    for g,syms in GROUPS.items():
        cells=[]; alltr=[]
        print(f'GROUP {g} symbols={len(syms)}',flush=True)
        for j,sym in enumerate(syms,1):
            bars=meta=errs=comp=None
            for attempt in range(2):
                try:
                    bars,meta,errs,comp=fetch_symbol(sym)
                    if any(bars[tf] for tf in TFS): break
                except Exception as e:
                    errs=[repr(e)]; time.sleep(1.0+attempt)
            if not bars:
                result['errors'].append({'group':g,'symbol':sym,'error':errs}); continue
            tick=(float(meta.get('minmov',1))/float(meta.get('pricescale',100))) if meta.get('pricescale') else .01
            print(f' {j}/{len(syms)} {sym} type={meta.get("type")} session={meta.get("session")} tick={tick}',flush=True)
            for tf in TFS:
                ts=run(tf,bars[tf],meta,tick); alltr.extend([{**t,'symbol':sym} for t in ts])
                sm=summarize(ts)
                cells.append({'symbol':sym,'tf':tf,'bars_total':len(bars[tf]),'bars_window':sum(int(START.timestamp()*1000)<=x.ct<int(END.timestamp()*1000) for x in bars[tf]),
                              'session':meta.get('session'),'timezone':meta.get('timezone'),'tick':tick,**sm})
            if errs: result['errors'].append({'group':g,'symbol':sym,'warnings':errs})
            time.sleep(.08)
        bytf={}
        for tf in TFS:
            c=[x for x in cells if x['tf']==tf]; n=sum(x['n'] for x in c); tr=[t for t in alltr if t['tf']==tf]
            bytf[str(tf)]={'cells':len(c),'cells_with_trade':sum(x['n']>0 for x in c),'positive_avg_cells':sum(x['n']>0 and x['avg_r']>0 for x in c),
                          'negative_avg_cells':sum(x['n']>0 and x['avg_r']<0 for x in c),'pooled':summarize(tr),
                          'unweighted_mean_cell_avg_r':mean([x['avg_r'] for x in c if x['n']>0])}
        ranked=[x for x in cells if x['n']>=3]
        result['groups'][g]={'symbols_requested':len(syms),'cells':cells,'timeframes':bytf,
                             'top_cells_n_ge_3':sorted(ranked,key=lambda x:x['avg_r'],reverse=True)[:10],
                             'bottom_cells_n_ge_3':sorted(ranked,key=lambda x:x['avg_r'])[:10]}
    with open(args.out,'w') as f: json.dump(result,f,indent=2)
    # concise log summary
    print('\n=== CROSS-ASSET SUMMARY ===')
    for g,x in result['groups'].items():
        print('\n',g)
        for tf,z in x['timeframes'].items():
            p=z['pooled']; print(f" {tf}m trades={p['n']} pooledAvgR={p['avg_r']} PF={p['pf_r']} cells+={z['positive_avg_cells']}/{z['cells_with_trade']} meanCellAvg={z['unweighted_mean_cell_avg_r']}")
        print(' top:',[(c['symbol'],c['tf'],c['n'],round(c['avg_r'],3)) for c in x['top_cells_n_ge_3'][:5]])
        print(' bottom:',[(c['symbol'],c['tf'],c['n'],round(c['avg_r'],3)) for c in x['bottom_cells_n_ge_3'][:5]])
    print('\nerrors',len(result['errors']))
if __name__=='__main__': main()
