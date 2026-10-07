#!/usr/bin/env python3
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, re

DEFAULT_CANDIDATE_DROPBOX = "/Apps/remotely-save/AI/AI-MEMORY/FLOWS/SEO/Semrush Candidate Registry.md"
DEFAULT_TESTED_DROPBOX = "/Apps/remotely-save/AI/AI-MEMORY/FLOWS/SEO/Semrush Tested Registry.json"

def load_env(path):
    p=pathlib.Path(path)
    if not p.exists(): return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1); k=k.strip(); v=v.strip()
        if len(v)>=2 and v[0]==v[-1] and v[0] in "'\"": v=v[1:-1]
        if k and k not in os.environ: os.environ[k]=v

def atomic_text(path,text):
    p=pathlib.Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp"); tmp.write_text(text,encoding="utf-8"); tmp.replace(p)

def derived(project,rows,overrides):
    if project in overrides: return str((overrides.get(project) or {}).get("verdict") or "OVERRIDE")
    gates=[str(r.get("serp_gate") or "") for r in rows]
    if any(g=="SERP_DD_PASS" for g in gates): return "SERP_PASS_NEEDS_DD"
    if any(g=="WATCH_COMPETITION" for g in gates): return "WATCH_SERP_ONLY"
    if gates and all(g=="DROP_SERP_SATURATED" for g in gates): return "DROP_SERP_SATURATED"
    if any(g=="BLOCKED_INCOMPLETE_SERP" for g in gates): return "BLOCKED_INCOMPLETE_SERP"
    return "UNCLASSIFIED"

def infer_round(reg):
    rounds=[]
    for rec in reg.get("records") or []:
        src=str(rec.get("source_results") or "")
        for m in re.finditer(r"(?:^|[-_/])r(\d+)(?:[-_/]|$)",src,re.I):
            try: rounds.append(int(m.group(1)))
            except: pass
    return max(rounds) if rounds else None

def render(reg,lifecycle,tested_sha,terminal_round=None,catalog_exhausted=False):
    recs=reg.get("records") or []; overrides=lifecycle.get("overrides") or {}
    inferred_round=infer_round(reg)
    rounds=[x for x in [inferred_round,terminal_round] if x is not None]
    max_round=max(rounds) if rounds else None
    next_round=(max_round+1) if max_round is not None else None
    by=collections.defaultdict(list)
    for rec in recs: by[str(rec.get("project") or "(unscoped)")].append(rec)
    gc=collections.Counter(str(r.get("serp_gate") or "UNKNOWN") for r in recs)
    lines=[
      "# Semrush Candidate Registry","",
      "STATUS: CANONICAL CANDIDATE LIFECYCLE REGISTRY",
      "UPDATED: "+str(reg.get("updated_at") or lifecycle.get("updated_at") or "")[:10],"",
      "## Authority model","",
      "- Scanner / flow / current run state: `Semrush Research.md`.",
      "- Exact-SERP anti-repeat machine authority: `/var/lib/semrush-research/config/discovery-tested-v1.json`.",
      "- Dropbox machine recovery mirror: `Semrush Tested Registry.json`.",
      "- Human candidate lifecycle authority: this file.",
      "- Project authority exists only after promotion to `BUILD_TEST / ACTIVE VALIDATION / EXECUTION`.",
      "- `SERP_DD_PASS` is evidence only. It is NOT equivalent to `PASS_CANDIDATE` or project promotion.",
      "" ]
    gh=lifecycle.get("github_recovery_baseline")
    if gh: lines.append("- GitHub recovery baseline: `"+str(gh)+"`.")
    lines += ["","## Anti-repeat checkpoint","",
      "- exact-SERP tested records: **%d**"%len(recs),
      "- unique project identities represented: **%d**"%len(by),
      "- machine registry updated_at: `%s`"%reg.get("updated_at"),
      "- machine registry SHA256: `%s`"%tested_sha,
      "- `DROP_SERP_SATURATED`: **%d**"%gc.get("DROP_SERP_SATURATED",0),
      "- `WATCH_COMPETITION`: **%d**"%gc.get("WATCH_COMPETITION",0),
      "- `SERP_DD_PASS`: **%d**"%gc.get("SERP_DD_PASS",0),
      "- `BLOCKED_INCOMPLETE_SERP`: **%d**"%gc.get("BLOCKED_INCOMPLETE_SERP",0),"",
      "Hard rule: never exact-SERP-test an already registered fingerprint unless the thesis/source materially changes. Project-level similarity alone must not suppress a genuinely broader/new market thesis; the machine fingerprint registry remains the exact anti-repeat authority.","",
      "## Lifecycle","",
      "`DISCOVERED -> TESTED -> DROP | WATCH | WATCH_STRONG | PASS -> BUILD_TEST -> PROJECTS/<name>/`","",
      "Promotion rule:",
      "- `DROP`: terminal; no routine rescan.",
      "- `WATCH`: stays in this registry; only recheck on material evidence/cadence defined by flow.",
      "- `WATCH_STRONG`: ranked candidate; still not a project.",
      "- `PASS`: candidate passed research, but remains here until build/business gate.",
      "- `BUILD_TEST+`: create `PROJECTS/<name>/PROJECT.md` and add to `Projects Map.md`.","",
      "## Current ranked candidates","",
      "| Rank | Candidate | Lifecycle verdict | Project? | Next gate |",
      "|---:|---|---|---|---|" ]
    for item in lifecycle.get("current_ranked") or []:
        rank=item.get("rank"); rank_text=str(rank) if rank is not None else "—"
        project="Yes" if item.get("project") else "No"
        lines.append("| %s | %s | `%s` | %s | %s |"%(rank_text,item.get("candidate",""),item.get("verdict",""),project,item.get("next_gate","")))
    conclusion=lifecycle.get("scanner_conclusion")
    if conclusion:
        lines += ["",f"Scanner conclusion: \`{conclusion}\`."]
    strongest=lifecycle.get("strongest_watch")
    if strongest:
        lines.append(f"Strongest remaining search watch: {strongest}.")
    lines += ["","## Curated lifecycle overrides","","| Candidate identity | Final lifecycle verdict | Note |","|---|---|---|"]
    for key in sorted(overrides):
        item=overrides.get(key) or {}; note=str(item.get("note") or "").replace("|","/")
        lines.append("| `%s` | `%s` | %s |"%(key,item.get("verdict",""),note))
    lines += ["","## Full tested project index","",
      "This section is a human projection of the machine registry. `Derived class` never overrides an explicit curated lifecycle verdict above.","",
      "| Project | Records | SERP gates | Derived class | Example tested query | NO_RECHECK |",
      "|---|---:|---|---|---|---|" ]
    for project in sorted(by):
        rows=by[project]; g=collections.Counter(str(r.get("serp_gate") or "UNKNOWN") for r in rows)
        gates=", ".join("%s:%s"%(k,v) for k,v in sorted(g.items())); q=""
        for rec in rows:
            kws=rec.get("top_keywords") or []
            if kws: q=str(kws[0]).replace("|","/"); break
        lines.append("| `%s` | %d | %s | `%s` | %s | YES* |"%(project,len(rows),gates,derived(project,rows,overrides),q[:90]))
    lines += ["","`YES*` means: do not rerun the already-tested exact SERP fingerprint. It does not prohibit testing a materially different/broader thesis.","",
      "## Legacy terminal portfolio decisions",""]
    for item in lifecycle.get("legacy_terminal") or []: lines.append("- "+str(item)+".")
    lines += ["","## Storage rule","",
      "- Do not create one file/folder per candidate.",
      "- Keep candidate lifecycle here.",
      "- Keep scanner implementation/history in `Semrush Research.md`.",
      "- Keep the exact tested machine registry mirrored in Dropbox for disaster recovery.",
      "- Create `PROJECTS/<name>/` only when candidate crosses into `BUILD_TEST / ACTIVE VALIDATION / EXECUTION`.","",
      "## Resume","",
      "- Candidate ranking authority: this registry + newer explicit canonical override in `Semrush Research.md`.",
      "- Exact anti-repeat authority: `discovery-tested-v1.json` plus its Dropbox machine mirror." ]
    if max_round is not None:
        lines.append(f"- Terminal discovery currently extends through R{max_round}.")
        if catalog_exhausted:
            lines.append("- Modifier catalog exhausted; no next discovery run until the catalog is expanded.")
        else:
            lines.append(f"- Next new discovery run: R{next_round}+.")
    lines.append("")
    return "\n".join(lines)

def sync_existing(svc,path,text,backup):
    current,_=svc.download_text(path)
    if current==text: return {"ok":True,"path":path,"unchanged":True}
    return svc.write_text_verified(path,text,backup=backup)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--tested-registry",required=True)
    ap.add_argument("--lifecycle",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--dropbox-path",default=DEFAULT_CANDIDATE_DROPBOX)
    ap.add_argument("--dropbox-tested-path",default=DEFAULT_TESTED_DROPBOX)
    ap.add_argument("--dropbox-env-file",default="/etc/vps-control/dropbox.env")
    ap.add_argument("--terminal-round",type=int)
    ap.add_argument("--catalog-exhausted",action="store_true")
    ap.add_argument("--no-dropbox",action="store_true")
    a=ap.parse_args()
    tested=pathlib.Path(a.tested_registry); raw=tested.read_bytes(); reg=json.loads(raw)
    lifecycle=json.loads(pathlib.Path(a.lifecycle).read_text(encoding="utf-8"))
    sha=hashlib.sha256(raw).hexdigest(); md=render(reg,lifecycle,sha,a.terminal_round,a.catalog_exhausted)
    atomic_text(a.output,md)
    result={"status":"PASS","records":len(reg.get("records") or []),"tested_sha256":sha,"output":a.output,"dropbox_synced":False}
    if not a.no_dropbox:
        load_env(a.dropbox_env_file)
        import sys; sys.path.insert(0,"/opt/ai-vps-unified-gateway/stack")
        import vps_dropbox
        svc=vps_dropbox.DropboxService()
        result["candidate_dropbox"]=sync_existing(svc,a.dropbox_path,md,backup=True)
        result["tested_dropbox"]=sync_existing(svc,a.dropbox_tested_path,raw.decode("utf-8"),backup=False)
        result["dropbox_synced"]=True
    print(json.dumps(result,ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())