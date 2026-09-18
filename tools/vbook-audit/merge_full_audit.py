#!/usr/bin/env python3
import argparse, json
from collections import Counter
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--meta",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()

    meta=json.loads(Path(a.meta).read_text(encoding="utf-8"))
    files=sorted(Path(a.input).glob("vbook-e2e-shard-*/out/e2e-benchmark.json"))
    if not files:
        raise SystemExit("no shard result files found")

    rows=[]
    for f in files:
        part=json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(part,list):
            raise SystemExit(f"invalid shard payload: {f}")
        rows.extend(part)

    by={}
    dup=[]
    for r in rows:
        i=int(r["i"])
        if i in by:
            dup.append(i)
        by[i]=r

    expected=set(range(len(meta)))
    got=set(by)
    missing=sorted(expected-got)
    extra=sorted(got-expected)
    if dup or missing or extra:
        raise SystemExit(json.dumps({"duplicates":dup,"missing":missing,"extra":extra},ensure_ascii=False))

    ordered=[by[i] for i in range(len(meta))]
    classes=Counter(r.get("class","UNKNOWN") for r in ordered)
    passes=[r for r in ordered if r.get("class")=="PASS_E2E"]

    # Attach stable registry metadata so the result can be used without re-querying upstream repos.
    pass_entries=[]
    for r in passes:
        m=meta[int(r["i"])]
        pass_entries.append({
            "i":int(r["i"]),
            "name":m.get("name"),
            "author":m.get("author"),
            "type":m.get("type"),
            "source":m.get("source"),
            "version":m.get("version"),
            "path":m.get("path"),
            "repo":m.get("repo"),
            "registry":m.get("registry"),
            "e2e":r,
        })

    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    (out/"vbook-e2e-full.json").write_text(json.dumps(ordered,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"vbook-e2e-pass.json").write_text(json.dumps(pass_entries,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={
        "total":len(ordered),
        "pass_e2e":len(passes),
        "classes":dict(sorted(classes.items())),
        "pass_names":[r.get("name") for r in passes],
        "coverage":{"expected":len(meta),"received":len(ordered),"missing":0,"duplicates":0},
    }
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
