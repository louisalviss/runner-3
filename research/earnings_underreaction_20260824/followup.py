from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ROOT / "artifacts/earnings_underreaction_20260824/events.csv"
OUT = ROOT / "artifacts/earnings_followup_20260824"
OUT.mkdir(parents=True, exist_ok=True)
DISC = (pd.Timestamp("2010-01-01"), pd.Timestamp("2016-12-31"))
VAL = (pd.Timestamp("2017-01-01"), pd.Timestamp("2024-12-31"))
H = ("4w","8w","13w")

# New hypotheses fixed before reading their results. Because they are generated after
# the first earnings test, any apparent winner requires fresh 2025-2026 OOS.
# diagnostic trigger: 2026-08-24
SPECS = {
    "BEAT_CONFIRM": {
        "signal": lambda x: (x.surprise_pct >= 10) & (x.reaction_2session >= .03),
        "control": lambda x: (x.surprise_pct >= 10) & (x.reaction_2session.between(-.03,.03)),
        "mechanism": "positive earnings surprise confirmed by immediate price reaction",
    },
    "BEAT_WEAK_PRIOR": {
        "signal": lambda x: (x.surprise_pct >= 10) & (x.pre_mom63 <= 0),
        "control": lambda x: (x.surprise_pct >= 10) & (x.pre_mom63 >= .10),
        "mechanism": "good earnings contradict weak pre-event price expectations",
    },
    "BEAT_CONFIRM_WEAK_PRIOR": {
        "signal": lambda x: (x.surprise_pct >= 10) & (x.reaction_2session >= .03) & (x.pre_mom63 <= 0),
        "control": lambda x: (x.surprise_pct >= 10) & (x.reaction_2session >= .03) & (x.pre_mom63 >= .10),
        "mechanism": "positive surprise + confirming reaction after weak prior trend",
    },
    "BIG_BEAT_CONFIRM": {
        "signal": lambda x: (x.surprise_pct >= 20) & (x.reaction_2session >= .03),
        "control": lambda x: (x.surprise_pct.between(5,10)) & (x.reaction_2session >= .03),
        "mechanism": "large positive surprise with price confirmation",
    },
}


def month_cluster_ci(weeks, excess, reps=3000):
    d=pd.DataFrame({"week":weeks,"ex":excess}).dropna()
    wm=d.groupby("week",observed=True).ex.mean().to_numpy(dtype=float)
    if len(wm)<8: return (np.nan,np.nan)
    rng=np.random.default_rng(20260824); n=len(wm)
    bs=np.array([np.mean(wm[rng.integers(0,n,n)]) for _ in range(reps)])
    return tuple(np.quantile(bs,[.025,.975]))


def nearest(s, pool, spec):
    c=pool[spec["control"](pool)].copy()
    if c.empty: return None
    for days in (28,56,112):
        z=c[(c.event_date-s.event_date).abs().dt.days<=days].copy()
        if z.empty: continue
        scale_sur=max(10.0, float(z.surprise_pct.abs().median()))
        dist=(z.surprise_pct-s.surprise_pct).abs()/scale_sur + (z.pre_dd52-s.pre_dd52).abs()/.15 + (z.pre_mom63-s.pre_mom63).abs()/.25
        return int(dist.idxmin())
    return None


def evaluate(e,a,b,name,spec):
    p=e[e.event_date.between(a,b)].copy(); sig=p[spec["signal"](p)].copy()
    pairs=[]
    for idx,s in sig.iterrows():
        ci=nearest(s,p.drop(index=idx),spec)
        if ci is not None: pairs.append((idx,ci))
    rows=[]
    for h in H:
        col=f"ret_{h}"; sr=[]; ex=[]; weeks=[]
        for si,ci in pairs:
            a1=p.at[si,col]; b1=p.at[ci,col]
            if pd.notna(a1) and pd.notna(b1):
                sr.append(float(a1)); ex.append(float(a1-b1)); weeks.append(pd.Timestamp(p.at[si,"event_date"]).to_period("M").to_timestamp())
        if ex:
            lo,hi=month_cluster_ci(weeks,np.asarray(ex)); arr=np.asarray(sr); exa=np.asarray(ex)
            rows.append({"strategy":name,"mechanism":spec["mechanism"],"horizon":h,"signal_n":len(arr),"matched_n":len(exa),"win_rate":float(np.mean(arr>0)),"median_return":float(np.median(arr)),"median_excess":float(np.median(exa)),"mean_excess":float(np.mean(exa)),"beat_matched":float(np.mean(exa>0)),"ci_lo":float(lo),"ci_hi":float(hi)})
        else:
            rows.append({"strategy":name,"mechanism":spec["mechanism"],"horizon":h,"signal_n":0,"matched_n":0,"win_rate":np.nan,"median_return":np.nan,"median_excess":np.nan,"mean_excess":np.nan,"beat_matched":np.nan,"ci_lo":np.nan,"ci_hi":np.nan})
    return rows


def pct(x): return "NA" if not np.isfinite(x) else f"{x*100:+.2f}%"

def main():
    e=pd.read_csv(EVENTS,parse_dates=["event_date","entry_date"])
    rows=[]
    for split,(a,b) in {"discovery":DISC,"validation":VAL}.items():
        for name,spec in SPECS.items():
            for r in evaluate(e,a,b,name,spec): r["split"]=split; rows.append(r)
    res=pd.DataFrame(rows); res.to_csv(OUT/"results.csv",index=False)
    v=res[(res.split=="validation")&(res.horizon=="13w")].copy()
    v["gate"]=(v.matched_n>=100)&(v.median_excess>0)&(v.beat_matched>=.55)&(v.ci_lo>0)
    v["score"]=v.median_excess.fillna(-9)+.5*(v.beat_matched.fillna(0)-.5)
    best=v.sort_values(["gate","score"],ascending=[False,False]).iloc[0]
    lines=["# Earnings Follow-up — Frozen Development Validation","","These follow-up rules were defined after the first earnings test; any winner requires fresh 2025-2026 OOS.","Primary 13w; signal-month clustered bootstrap.","","| Strategy | N | Win | Median ret | Median excess | Beat control | CI95 | Gate |","|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in v.itertuples(index=False): lines.append(f"| {r.strategy} | {r.signal_n} | {pct(r.win_rate)} | {pct(r.median_return)} | {pct(r.median_excess)} | {pct(r.beat_matched)} | [{pct(r.ci_lo)}, {pct(r.ci_hi)}] | {'PASS' if r.gate else 'FAIL'} |")
    lines += ["",f"Best: {best.strategy}; median excess {pct(best.median_excess)}; beat {pct(best.beat_matched)}; CI [{pct(best.ci_lo)}, {pct(best.ci_hi)}]; gate {'PASS' if best.gate else 'FAIL'}."]
    (OUT/"RESULT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (OUT/"summary.json").write_text(json.dumps({"best":best.to_dict(),"validation13":v.to_dict("records")},indent=2,default=str),encoding="utf-8")
    print("\n".join(lines))

if __name__=="__main__": main()
