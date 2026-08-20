import glob, json, statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VN=ZoneInfo('Asia/Ho_Chi_Minh')
OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)

def load_jsonl(paths):
    out=[]
    for p in paths:
        with open(p) as f:
            for line in f:
                if line.strip(): out.append(json.loads(line))
    return out

def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def zonec(a):
    z=dt(a).astimezone(VN); m=z.hour*60+z.minute
    return m>=1380 or m<60

def net(a,bps=6):
    return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000

def trade_metrics(xs,bps=6):
    vals=[net(a,bps) for a in xs]
    return {
      'n':len(xs),'gross_r':sum(a['R'] for a in xs),'net_r':sum(vals),
      'avg_net_r':statistics.mean(vals) if vals else None,
      'positive_trade_pct':100*sum(v>0 for v in vals)/len(vals) if vals else None,
      'long':{'n':sum(str(a.get('side','')).upper()=='LONG' for a in xs),'net_r':sum(net(a,bps) for a in xs if str(a.get('side','')).upper()=='LONG')},
      'short':{'n':sum(str(a.get('side','')).upper()=='SHORT' for a in xs),'net_r':sum(net(a,bps) for a in xs if str(a.get('side','')).upper()=='SHORT')},
      'exit_reasons':dict(Counter(a.get('exit_reason','?') for a in xs))
    }

def batch_metrics(xs,bps=6):
    g=defaultdict(list)
    for a in xs:g[a['signal_time']].append(a)
    batches=[]
    for t,z in sorted(g.items()):
        raw=sum(net(a,bps) for a in z)
        # Portfolio-normalized: one total 1R risk budget per synchronized signal batch,
        # split equally across all signals in that batch.
        pr=raw/len(z)
        batches.append({'signal_time':t,'n':len(z),'raw_net_r':raw,'portfolio_r':pr})
    def bucket(n):
        if n==1:return '1'
        if n==2:return '2'
        if n<=4:return '3-4'
        if n<=9:return '5-9'
        return '10+'
    bg=defaultdict(list)
    for b in batches:bg[bucket(b['n'])].append(b)
    return {
      'batches':len(batches),
      'portfolio_net_r':sum(b['portfolio_r'] for b in batches),
      'avg_portfolio_r_per_batch':statistics.mean(b['portfolio_r'] for b in batches) if batches else None,
      'positive_batch_pct':100*sum(b['portfolio_r']>0 for b in batches)/len(batches) if batches else None,
      'max_signals_same_timestamp':max((b['n'] for b in batches),default=0),
      'buckets':{k:{'batches':len(v),'trades':sum(x['n'] for x in v),'raw_net_r':sum(x['raw_net_r'] for x in v),'portfolio_net_r':sum(x['portfolio_r'] for x in v),'avg_portfolio_r':statistics.mean(x['portfolio_r'] for x in v) if v else None} for k,v in sorted(bg.items())},
      'top_batches':sorted(batches,key=lambda x:x['raw_net_r'],reverse=True)[:10]
    }

def summary(xs):
    z=[a for a in xs if zonec(a)]
    return {
      'zonec_trade':trade_metrics(z,6),
      'zonec_costs':{str(b):trade_metrics(z,b) for b in (4,6,8,10,12)},
      'zonec_by_year':{str(y):{'trade':trade_metrics([a for a in z if dt(a).year==y],6),'batch':batch_metrics([a for a in z if dt(a).year==y],6)} for y in (2025,2026)},
      'zonec_batch':batch_metrics(z,6)
    }

base=load_jsonl(['/tmp/base10/trades.jsonl'])
close=load_jsonl(sorted(glob.glob('/tmp/all/trades-*.jsonl')))
report={
 'status':'WR_CLOSE_CONFIRM_CORE_DIAG_COMPLETE',
 'warning':'Research diagnostic only. One execution change: next-bar close confirmation with entry at confirming close. No Stage1 reconstruction is applied in this run.',
 'definition':{
   'baseline':'Frozen v2.5.15 10m engine: next-bar intrabar trigger can fill.',
   'close_confirm':'Same signal/lifecycle; next bar must close through original trigger; entry at next-bar close; bracket starts following bar.',
   'portfolio_normalization':'For signals sharing exact signal_time, total risk budget = 1R and is split equally across that batch.'
 },
 'baseline':summary(base),
 'close_confirm':summary(close)
}
# Compact deltas @6bps exact Zone C.
b=report['baseline']['zonec_trade']; c=report['close_confirm']['zonec_trade']
bp=report['baseline']['zonec_batch']; cp=report['close_confirm']['zonec_batch']
report['delta']={
 'trades':c['n']-b['n'],
 'net6_r':c['net_r']-b['net_r'],
 'avg_net6_r':(c['avg_net_r']-b['avg_net_r']) if c['avg_net_r'] is not None and b['avg_net_r'] is not None else None,
 'portfolio_net6_r':cp['portfolio_net_r']-bp['portfolio_net_r'],
 'portfolio_avg_batch_r':cp['avg_portfolio_r_per_batch']-bp['avg_portfolio_r_per_batch']
}
json.dump(report,open(OUT/'wr_close_confirm_compare.json','w'),indent=2)
print(json.dumps({
 'status':report['status'],
 'baseline_zonec':b,
 'close_zonec':c,
 'baseline_portfolio':bp,
 'close_portfolio':cp,
 'delta':report['delta']
},indent=2))
