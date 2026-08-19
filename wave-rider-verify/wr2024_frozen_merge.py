import glob,json,os,random
from collections import defaultdict
from datetime import datetime,timezone
os.makedirs('/tmp/final',exist_ok=True)
S=[];E=[];T=[]
for p in glob.glob('/tmp/all/summary-*.json'): S+=json.load(open(p))
for p in glob.glob('/tmp/all/errors-*.json'): E+=json.load(open(p))
for p in glob.glob('/tmp/all/trades-*.jsonl'):
    for line in open(p):
        if line.strip(): T.append(json.loads(line))
T.sort(key=lambda a:(a['signal_time'],a['symbol']))
def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def net(a,bps): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def stat(xs):
    z={'n':len(xs),'gross_r':sum(a['R'] for a in xs)}
    for b in (4,6,8,10,12,15,20): z[f'net_r_{b}bps']=sum(net(a,b) for a in xs)
    z['avg_net6_r']=z['net_r_6bps']/z['n'] if z['n'] else None
    return z
by_month=defaultdict(list)
for a in T: by_month[(dt(a).year,dt(a).month)].append(a)
selected=[]; monthly={}; selector={}
for m in range(1,13):
    y=2024; yy,mm=y,m; train_months=[]
    for _ in range(3):
        mm-=1
        if mm==0: yy-=1; mm=12
        train_months.append((yy,mm))
    train=[]
    for k in train_months: train.extend(by_month.get(k,[]))
    sy=defaultdict(list)
    for a in train: sy[a['symbol']].append(a)
    keep={s for s,xs in sy.items() if len(xs)>=5 and sum(net(a,6) for a in xs)>0}
    test=[a for a in by_month.get((y,m),[]) if a['symbol'] in keep]
    selected.extend(test)
    key=f'{y}-{m:02d}'; monthly[key]=stat(test)
    selector[key]={'n_symbols':len(keep),'symbols':sorted(keep),'train_months':[f'{a}-{b:02d}' for a,b in reversed(train_months)]}
eq=peak=0.0; maxdd=0.0
for a in selected:
    eq+=net(a,6); peak=max(peak,eq); maxdd=min(maxdd,eq-peak)
loo={}
for k in monthly:
    xs=[a for a in selected if f'{dt(a).year}-{dt(a).month:02d}'!=k]
    loo[k]=stat(xs)['net_r_6bps']
vals=[net(a,6) for a in selected]; random.seed(2515); boots=[]
if vals:
    n=len(vals)
    for _ in range(10000): boots.append(sum(vals[random.randrange(n)] for __ in range(n))/n)
    boots.sort(); ci=[boots[int(.025*len(boots))],boots[int(.975*len(boots))-1]]
else: ci=[None,None]
report={'status':'WR_2024_FROZEN_ROLLING_OOS_COMPLETE','engine':'WR v2.5.15 deterministic exact Zone C 10m; frozen source commits','rule':'Previous 3 calendar months; include symbol iff train n>=5 and train net6>0; frozen before 2024 test','test_period':'2024-01-01 through 2024-12-31','train_seed_period':'2023-10-01 through 2023-12-31','warmup_from':'2023-09-01','total':stat(selected),'monthly':monthly,'positive_months_net6':sum(v['net_r_6bps']>0 for v in monthly.values()),'months_with_trades':sum(v['n']>0 for v in monthly.values()),'max_drawdown_net6_r':maxdd,'leave_one_month_out_net6':loo,'bootstrap_iid_mean_net6_95ci':ci,'selector':selector,'all_zonec_trades_period':stat([a for a in T if dt(a).year==2024]),'seed_trades_2023q4':stat([a for a in T if dt(a).year==2023 and dt(a).month>=10]),'symbols_completed':len(S),'errors':E}
json.dump(report,open('/tmp/final/report.json','w'),indent=2)
with open('/tmp/final/selected_trades.jsonl','w') as f:
    for a in selected:f.write(json.dumps(a,separators=(',',':'))+'\n')
with open('/tmp/final/all_trades.jsonl','w') as f:
    for a in T:f.write(json.dumps(a,separators=(',',':'))+'\n')
print(json.dumps(report,indent=2))
