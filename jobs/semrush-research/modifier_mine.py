#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, pathlib, re, statistics
from collections import defaultdict

GENERIC = {
 "calculator","calculation","calculate","calculating","tool","tools","lookup","finder","find","checker","check",
 "estimator","estimate","selector","selection","sizing","size","cost","price","pricing","serial","number","numbers",
 "model","address","compatibility","compatible","capacity","load","value","values","fitment","cross","reference",
 "spec","specs","specification","specifications","material","materials","configuration","requirements","requirement",
 "quantity","replacement","replace","equivalent","part","parts","by","for","free","online","chart","guide","search"
}
QUESTION = {"how","what","where","why","when","who","does","do","can","is","are"}
STOP = {"a","an","and","in","on","to","of","the","with","using","my","your","at","from"}
NOISE = {"word","excel","google","sheets","photoshop"}
BANNED = {"gun","guns","firearm","firearms","weapon","weapons","bullet","ammo","ammunition","colt","ruger","winchester","remington","prostate","dosage","dose","medication","insulin","pregnancy","medical","health","body","blood","heart","kidney"}
RETAIL_NOISE = {"bazic","desktop","pocket","digit"}
AI_WEAK = {"definition","meaning","formula","explain","explained","tutorial","example","examples","incidence","best"}

def norm(s):
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9+%.-]+"," ",str(s or "").lower())).strip()

def tokens(s):
    return [x for x in norm(s).split() if x]

def asnum(x, default=0.0):
    try:return float(x)
    except:return default

def subject_key(kw):
    ts=tokens(kw)
    if not ts:return ""
    if ts[0] in QUESTION:return ""
    core=[t for t in ts if len(t)>=2 and t not in GENERIC and t not in QUESTION and t not in STOP]
    if not core or set(core) & BANNED:return ""
    if set(core) & RETAIL_NOISE:return ""
    # Preserve compact nouns/brands while avoiding excessively specific tails.
    return " ".join(core[:3])

def descriptor_tokens(s):
    return {t for t in tokens(s) if t not in GENERIC and t not in QUESTION and t not in STOP}

def load_seen(config_dir):
    seen=[]
    if not config_dir:
        return seen
    for p in pathlib.Path(config_dir).glob("*.json"):
        try:data=json.loads(p.read_text(encoding="utf-8"))
        except Exception:continue
        for theme in data.get("themes",[]):
            descriptors=[theme.get("theme_id",""),theme.get("label","")]+list(theme.get("seeds") or [])
            for d in descriptors:
                st=descriptor_tokens(d)
                if st:seen.append(st)
    return seen

def already_seen(subject, seen):
    st=set(tokens(subject))
    if not st:return True
    for d in seen:
        if len(st)==1:
            if st==d or (st <= d and len(d)<=4):return True
        elif st <= d:
            return True
    return False

def load_rows(paths):
    out=[]
    for p in paths:
        data=json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        projects=data.get("projects") or {}
        for project,pv in projects.items():
            for seed,sv in (pv.get("seeds") or {}).items():
                for x in sv.get("ideas") or []:
                    kw=norm(x.get("phrase") or x.get("keyword"))
                    if not kw:continue
                    kd=x.get("difficulty",x.get("keywordDifficulty"))
                    out.append({
                        "project":project,"seed":seed,"keyword":kw,
                        "volume":int(asnum(x.get("volume"),0)),
                        "kd":None if kd is None else asnum(kd,None),
                        "cpc":asnum(x.get("cpc"),0.0),
                    })
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",nargs="+",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--min-volume",type=int,default=100)
    ap.add_argument("--max-kd",type=float,default=29)
    ap.add_argument("--min-cluster-volume",type=int,default=500)
    ap.add_argument("--top",type=int,default=100)
    ap.add_argument("--config-dir")
    a=ap.parse_args()

    seen=load_seen(a.config_dir)
    rows=load_rows(a.input)
    best={}
    for r in rows:
        if r["volume"]<a.min_volume or r["kd"] is None or r["kd"]>a.max_kd:continue
        if len(tokens(r["keyword"]))<3:continue
        key=subject_key(r["keyword"])
        if not key:continue
        if set(tokens(key)) <= NOISE:continue
        if set(tokens(r["keyword"])) & AI_WEAK:continue
        if already_seen(key,seen):continue
        r={**r,"subject":key}
        k=(key,r["keyword"])
        if k not in best or r["volume"]>best[k]["volume"]:best[k]=r

    groups=defaultdict(list)
    for r in best.values():groups[r["subject"]].append(r)

    clusters=[]
    for subject,rs in groups.items():
        total=sum(r["volume"] for r in rs)
        if total<a.min_cluster_volume:continue
        kds=[r["kd"] for r in rs if r["kd"] is not None]
        cpc_den=sum(r["volume"] for r in rs)
        weighted_cpc=sum(r["cpc"]*r["volume"] for r in rs)/cpc_den if cpc_den else 0
        head=max((r["volume"] for r in rs),default=0)
        top=sorted(rs,key=lambda r:(-r["volume"],r["kd"]))[:10]
        # Reward scale, low KD and breadth; penalize single-keyword clusters.
        breadth=min(2.0, 0.7 + math.log10(len(rs)+1))
        score=round(math.log10(total+1)*breadth*(1-(statistics.median(kds) if kds else 100)/100),4)
        clusters.append({
            "subject":subject,
            "total_volume":total,
            "keyword_count":len(rs),
            "median_kd":round(statistics.median(kds),2) if kds else None,
            "head_share":round(head/total,4) if total else 1,
            "weighted_cpc":round(weighted_cpc,4),
            "score":score,
            "top_keywords":top,
        })

    clusters.sort(key=lambda x:(-x["score"],-x["total_volume"],x["median_kd"] or 999))
    payload={
      "version":1,
      "inputs":a.input,
      "filters":{"min_volume":a.min_volume,"max_kd":a.max_kd,"min_cluster_volume":a.min_cluster_volume},
      "raw_rows":len(rows),
      "qualified_rows":len(best),
      "cluster_count":len(clusters),
      "clusters":clusters[:a.top],
    }
    out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","raw_rows":len(rows),"qualified_rows":len(best),"clusters":len(clusters),"output":str(out)},ensure_ascii=False))
    for c in clusters[:20]:
        print(json.dumps({k:c[k] for k in ["subject","total_volume","keyword_count","median_kd","head_share","weighted_cpc","score"]},ensure_ascii=False))
if __name__=="__main__":
    main()
