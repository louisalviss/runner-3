#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

STOPWORDS = {
    "a","an","and","are","as","at","be","best","by","can","for","free","from","how","i","in",
    "is","it","me","my","near","of","on","online","or","the","to","what","where","which","with",
}
HIGH_INTENT = {
    "lookup","check","checker","calculator","estimate","estimator","compare","comparison","convert",
    "converter","generator","validator","verify","verification","search","find","finder","audit","cost",
    "price","pricing","quote","requirements","permit","license","title","serial","vin","compliance",
}


def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_journal(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def norm_phrase(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+%.-]+", " ", (s or "").lower())).strip()


def tokens(s: str) -> list[str]:
    return [t for t in norm_phrase(s).split() if len(t) > 1 and t not in STOPWORDS]


def as_float(v: Any, default: float | None = 0.0) -> float | None:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def as_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def parse_idea(project: str, seed: str, row: dict[str, Any]) -> dict[str, Any] | None:
    phrase = str(row.get("phrase") or row.get("keyword") or "").strip()
    if not phrase:
        return None
    volume = as_int(row.get("volume"))
    kd = as_float(row.get("difficulty", row.get("keywordDifficulty")), None)
    cpc = as_float(row.get("cpc"), 0.0) or 0.0
    intent = row.get("intent", row.get("intents"))
    toks = tokens(phrase)
    return {
        "project": project,
        "seed": seed,
        "keyword": phrase,
        "norm": norm_phrase(phrase),
        "volume": max(0, volume),
        "kd": kd,
        "cpc": max(0.0, cpc),
        "intent": intent,
        "token_count": len(norm_phrase(phrase).split()),
        "tokens": toks,
        "high_intent": bool(set(toks) & HIGH_INTENT),
    }


def load_universe(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []

    projects = payload.get("projects") if isinstance(payload, dict) else None
    if isinstance(projects, dict):
        for project, pval in projects.items():
            if not isinstance(pval, dict):
                continue
            seeds = pval.get("seeds") or {}
            if not isinstance(seeds, dict):
                continue
            for seed, sval in seeds.items():
                if not isinstance(sval, dict):
                    continue
                ideas = sval.get("ideas") or []
                if not isinstance(ideas, list):
                    continue
                for row in ideas:
                    if isinstance(row, dict):
                        rec = parse_idea(str(project), str(seed), row)
                        if rec:
                            out.append(rec)
        return out

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            us = row.get("us")
            if isinstance(us, dict):
                flat = dict(us)
                flat["phrase"] = row.get("keyword") or us.get("phrase")
                rec = parse_idea(str(row.get("group") or "default"), str(row.get("keyword") or ""), flat)
            else:
                rec = parse_idea(str(row.get("group") or "default"), str(row.get("seed") or ""), row)
            if rec:
                out.append(rec)
        return out

    raise ValueError("Unsupported Semrush universe JSON shape")


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["project"], r["norm"])
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = r
            continue
        cur_kd = cur["kd"] if cur["kd"] is not None else 999.0
        new_kd = r["kd"] if r["kd"] is not None else 999.0
        if (r["volume"], -new_kd, r["cpc"]) > (cur["volume"], -cur_kd, cur["cpc"]):
            by_key[key] = r
    return list(by_key.values())


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def project_metrics(rows: list[dict[str, Any]], max_kd: float, longtail_tokens: int) -> dict[str, Any]:
    non_null = [r for r in rows if r["kd"] is not None]
    low = [r for r in non_null if r["kd"] <= max_kd]
    lt_low = [r for r in low if r["token_count"] >= longtail_tokens]
    total_volume = sum(r["volume"] for r in rows)
    low_volume = sum(r["volume"] for r in low)
    lt_low_volume = sum(r["volume"] for r in lt_low)
    head_volume = max((r["volume"] for r in rows), default=0)
    cpc_den = sum(r["volume"] for r in rows)
    high_intent_volume = sum(r["volume"] for r in rows if r["high_intent"])
    return {
        "keyword_count": len(rows),
        "metric_keyword_count": len(non_null),
        "total_volume": total_volume,
        "low_kd_keyword_count": len(low),
        "low_kd_volume": low_volume,
        "longtail_low_kd_count": len(lt_low),
        "longtail_low_kd_volume": lt_low_volume,
        "median_kd": median([float(r["kd"]) for r in non_null]),
        "head_share": round(head_volume / total_volume, 4) if total_volume else 1.0,
        "weighted_cpc": round(sum(r["cpc"] * r["volume"] for r in rows) / cpc_den, 4) if cpc_den else 0.0,
        "high_intent_volume_share": round(high_intent_volume / total_volume, 4) if total_volume else 0.0,
    }


def scale_band(total_volume: int) -> str:
    if total_volume < 10000:
        return "REJECT_SCALE_LT10K"
    if total_volume < 50000:
        return "CONDITIONAL_10K_50K"
    if total_volume < 200000:
        return "VALID_TEST_50K_200K"
    return "PRIORITY_200K_PLUS"


def gate(metrics: dict[str, Any], cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metrics["total_volume"] < cfg["min_total_volume"]:
        reasons.append("total_volume")
    if metrics["low_kd_volume"] < cfg["min_low_kd_volume"]:
        reasons.append("low_kd_volume")
    if metrics["keyword_count"] < cfg["min_keyword_count"]:
        reasons.append("keyword_count")
    if metrics["longtail_low_kd_count"] < cfg["min_longtail_count"]:
        reasons.append("longtail_count")
    if metrics["median_kd"] is None or metrics["median_kd"] > cfg["max_median_kd"]:
        reasons.append("median_kd")
    if metrics["head_share"] > cfg["max_head_share"]:
        reasons.append("head_concentration")
    return not reasons, reasons


class DSU:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))
        self.sz = [1] * n

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.sz[ra] < self.sz[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        self.sz[ra] += self.sz[rb]


def similar(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    if inter < 2:
        return False
    union = len(a | b)
    return inter / union >= 0.50 or (inter / min(len(a), len(b)) >= 0.75 and abs(len(a) - len(b)) <= 2)


def cluster_project(rows: list[dict[str, Any]], max_kd: float, min_volume: int, min_tokens: int) -> list[list[dict[str, Any]]]:
    candidates = [
        r for r in rows
        if r["kd"] is not None
        and r["kd"] <= max_kd
        and r["volume"] >= min_volume
        and r["token_count"] >= min_tokens
        and len(r["tokens"]) >= 2
    ]
    if not candidates:
        return []
    dsu = DSU(len(candidates))
    inv: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(candidates):
        for t in set(r["tokens"]):
            inv[t].append(i)

    checked: set[tuple[int, int]] = set()
    for bucket in inv.values():
        if len(bucket) > 500:
            bucket = bucket[:500]
        for pos, i in enumerate(bucket):
            ai = set(candidates[i]["tokens"])
            for j in bucket[pos + 1:]:
                pair = (i, j) if i < j else (j, i)
                if pair in checked:
                    continue
                checked.add(pair)
                if similar(ai, set(candidates[j]["tokens"])):
                    dsu.union(i, j)

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, r in enumerate(candidates):
        groups[dsu.find(i)].append(r)
    return sorted(groups.values(), key=lambda g: sum(x["volume"] for x in g), reverse=True)


def cluster_summary(project: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(r["volume"] for r in rows)
    token_freq: dict[str, int] = defaultdict(int)
    for r in rows:
        for t in set(r["tokens"]):
            token_freq[t] += 1
    label_tokens = [t for t, _ in sorted(token_freq.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)[:4]]
    top = sorted(rows, key=lambda r: (r["volume"], -(r["kd"] or 999)), reverse=True)[:8]
    return {
        "project": project,
        "label": " ".join(label_tokens) or project,
        "keyword_count": len(rows),
        "total_volume": total,
        "median_kd": median([float(r["kd"]) for r in rows if r["kd"] is not None]),
        "weighted_cpc": round(sum(r["cpc"] * r["volume"] for r in rows) / total, 4) if total else 0.0,
        "head_share": round(max((r["volume"] for r in rows), default=0) / total, 4) if total else 1.0,
        "top_keywords": [{"keyword": r["keyword"], "volume": r["volume"], "kd": r["kd"], "cpc": r["cpc"]} for r in top],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["project","seed","keyword","volume","kd","cpc","token_count","high_intent"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> int:
    ap = argparse.ArgumentParser(description="Independent Semrush demand-first niche discovery lane.")
    ap.add_argument("--input", required=True, help="Semrush universe JSON/RPC export")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-kd", type=float, default=29.0)
    ap.add_argument("--min-keyword-volume", type=int, default=20)
    ap.add_argument("--min-total-volume", type=int, default=10000)
    ap.add_argument("--min-low-kd-volume", type=int, default=2000)
    ap.add_argument("--min-keyword-count", type=int, default=20)
    ap.add_argument("--min-longtail-count", type=int, default=10)
    ap.add_argument("--longtail-tokens", type=int, default=4)
    ap.add_argument("--max-median-kd", type=float, default=30.0)
    ap.add_argument("--max-head-share", type=float, default=0.60)
    ap.add_argument("--cluster-min-tokens", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    src = Path(args.input)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    state_path = outdir / "state.json"
    journal_path = outdir / "main-points.jsonl"
    source_sha = sha256_file(src)

    cfg = {
        "max_kd": args.max_kd,
        "min_keyword_volume": args.min_keyword_volume,
        "min_total_volume": args.min_total_volume,
        "min_low_kd_volume": args.min_low_kd_volume,
        "min_keyword_count": args.min_keyword_count,
        "min_longtail_count": args.min_longtail_count,
        "longtail_tokens": args.longtail_tokens,
        "max_median_kd": args.max_median_kd,
        "max_head_share": args.max_head_share,
        "cluster_min_tokens": args.cluster_min_tokens,
    }

    if state_path.exists() and not args.force:
        prev = json.loads(state_path.read_text(encoding="utf-8"))
        if prev.get("source_sha256") == source_sha and prev.get("config") == cfg and prev.get("stage") == "SERP_DD_PENDING":
            print(json.dumps({
                "status": "RESUME_NO_BACKTRACK",
                "stage": prev["stage"],
                "source_sha256": source_sha,
                "passed_projects": prev.get("passed_projects", []),
                "output_dir": str(outdir),
            }, ensure_ascii=False))
            return 0

    state = {
        "lane": "semrush-demand-first",
        "version": 1,
        "stage": "INIT",
        "updated_at": now_ts(),
        "source": str(src),
        "source_sha256": source_sha,
        "config": cfg,
    }
    atomic_json(state_path, state)
    append_journal(journal_path, {"ts": now_ts(), "stage": "INIT", "source_sha256": source_sha, "config": cfg})

    raw_rows = load_universe(src)
    state.update(stage="UNIVERSE_LOADED", updated_at=now_ts(), raw_keyword_rows=len(raw_rows))
    atomic_json(state_path, state)
    append_journal(journal_path, {"ts": now_ts(), "stage": "UNIVERSE_LOADED", "raw_keyword_rows": len(raw_rows)})

    rows = dedupe_rows(raw_rows)
    state.update(stage="NORMALIZED", updated_at=now_ts(), dedup_keyword_rows=len(rows))
    atomic_json(state_path, state)
    append_journal(journal_path, {"ts": now_ts(), "stage": "NORMALIZED", "dedup_keyword_rows": len(rows)})

    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_project[r["project"]].append(r)

    project_report = []
    passed_projects = []
    for project, prows in sorted(by_project.items()):
        metrics = project_metrics(prows, args.max_kd, args.longtail_tokens)
        ok, fail_reasons = gate(metrics, cfg)
        project_report.append({"project": project, "pass": ok, "fail_reasons": fail_reasons, "scale_band": scale_band(metrics["total_volume"]), **metrics})
        if ok:
            passed_projects.append(project)

    atomic_json(outdir / "project-gates.json", {
        "lane": "semrush-demand-first",
        "source_sha256": source_sha,
        "config": cfg,
        "projects": project_report,
    })
    state.update(stage="DEMAND_GATE_COMPLETE", updated_at=now_ts(), project_count=len(project_report), passed_projects=passed_projects)
    atomic_json(state_path, state)
    append_journal(journal_path, {"ts": now_ts(), "stage": "DEMAND_GATE_COMPLETE", "project_count": len(project_report), "passed_projects": passed_projects})

    clusters = []
    for project in passed_projects:
        groups = cluster_project(by_project[project], args.max_kd, args.min_keyword_volume, args.cluster_min_tokens)
        for idx, group in enumerate(groups, 1):
            if len(group) < 2:
                continue
            rec = cluster_summary(project, group)
            rec["cluster_id"] = f"{norm_phrase(project).replace(' ', '-')[:40]}-{idx:03d}"
            clusters.append(rec)

    clusters.sort(key=lambda x: (x["total_volume"], x["keyword_count"]), reverse=True)
    atomic_json(outdir / "clusters.json", {"lane": "semrush-demand-first", "source_sha256": source_sha, "clusters": clusters})
    write_csv(outdir / "keywords-normalized.csv", rows)

    state.update(stage="CLUSTERED", updated_at=now_ts(), cluster_count=len(clusters))
    atomic_json(state_path, state)
    append_journal(journal_path, {"ts": now_ts(), "stage": "CLUSTERED", "cluster_count": len(clusters)})

    queue = [{
        "project": r["project"],
        "cluster_id": r["cluster_id"],
        "label": r["label"],
        "total_volume": r["total_volume"],
        "median_kd": r["median_kd"],
        "weighted_cpc": r["weighted_cpc"],
        "head_share": r["head_share"],
        "top_keywords": r["top_keywords"],
        "next": "exact SERP DD + exact-product competitor gate + monetization/WTP validation",
    } for r in clusters]
    atomic_json(outdir / "serp-dd-queue.json", {
        "status": "PENDING",
        "lane": "semrush-demand-first",
        "source_sha256": source_sha,
        "passed_projects": passed_projects,
        "queue": queue,
    })

    lines = [
        "# Semrush Demand-First — checkpoint",
        "",
        f"- source SHA256: `{source_sha}`",
        f"- input rows: {len(raw_rows)}",
        f"- dedup rows: {len(rows)}",
        f"- projects: {len(project_report)}",
        f"- demand-gate PASS: {len(passed_projects)}",
        f"- clusters queued for SERP DD: {len(queue)}",
        "",
        "## Demand-gate PASS",
    ]
    if passed_projects:
        for p in project_report:
            if p["pass"]:
                lines.append(
                    f"- {p['project']}: band={p['scale_band']}; volume={p['total_volume']}; lowKD={p['low_kd_volume']}; medianKD={p['median_kd']}; "
                    f"longtailLowKD={p['longtail_low_kd_count']}; headShare={p['head_share']}"
                )
    else:
        lines.append("- none")
    lines += [
        "",
        "## Resume contract",
        "- `state.json` is the exact stage pointer.",
        "- `main-points.jsonl` is append-only stage history.",
        "- same input SHA + same config + `SERP_DD_PENDING` => do not restart discovery; resume from `serp-dd-queue.json`.",
        "- no BUILD verdict is allowed from volume/KD alone.",
    ]
    (outdir / "checkpoint.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    state.update(stage="SERP_DD_PENDING", updated_at=now_ts(), queue_count=len(queue))
    atomic_json(state_path, state)
    append_journal(journal_path, {"ts": now_ts(), "stage": "SERP_DD_PENDING", "queue_count": len(queue), "passed_projects": passed_projects})

    print(json.dumps({
        "status": "PASS",
        "stage": "SERP_DD_PENDING",
        "source_sha256": source_sha,
        "projects": len(project_report),
        "passed_projects": passed_projects,
        "queue_count": len(queue),
        "output_dir": str(outdir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
