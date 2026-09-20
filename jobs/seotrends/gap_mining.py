#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

MODIFIERS = {
    "exact_size": [r"\b\d+(?:\.\d+)?\s?(?:kb|mb|gb|px|dpi|cm|mm|inch|inches|%)\b", r"\b\d{2,5}\s?[x×]\s?\d{2,5}\b"],
    "document_form": [r"\bpassport\b", r"\bvisa\b", r"\bsignature\b", r"\bexam\b", r"\bapplication\b", r"\bform\b", r"\bssc\b", r"\bupsc\b", r"\bibps\b", r"\bdv lottery\b"],
    "device_display": [r"\boled\b", r"\bamoled\b", r"\bmonitor\b", r"\bscreen\b", r"\bdisplay\b", r"\btv\b", r"\blaptop\b", r"\bphone\b", r"\bpixel\b", r"\brefresh rate\b", r"\bghosting\b", r"\bburn[- ]?in\b", r"\buniformity\b", r"\bbacklight\b", r"\bbanding\b"],
    "file_type": [r"\bjpg\b", r"\bjpeg\b", r"\bpng\b", r"\bwebp\b", r"\bheic\b", r"\bpdf\b", r"\bgif\b", r"\bsvg\b"],
    "platform": [r"\binstagram\b", r"\byoutube\b", r"\bfacebook\b", r"\blinkedin\b", r"\btiktok\b", r"\bwhatsapp\b", r"\bshopify\b", r"\bamazon\b", r"\betsy\b"],
    "task": [r"\bresize\b", r"\bcompress\b", r"\bconvert\b", r"\bchecker\b", r"\bcheck\b", r"\btest\b", r"\bviewer\b", r"\bcalculator\b", r"\bcompare\b", r"\bremove\b", r"\bcrop\b", r"\bfix\b", r"\bvalidator\b", r"\blookup\b"],
}

HEAD_TERMS = {
    "black screen", "image resizer", "resize image", "screen test", "monitor test",
    "image compressor", "photo resizer", "dead pixel test",
}


def as_float(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def as_int(v, default=0):
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def norm_phrase(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%+×x.-]+", " ", (s or "").lower())).strip()


def modifier_groups(phrase: str) -> list[str]:
    p = phrase.lower()
    out = []
    for group, patterns in MODIFIERS.items():
        if any(re.search(pattern, p, flags=re.I) for pattern in patterns):
            out.append(group)
    return out


def is_brand(phrase: str, brands: list[str]) -> bool:
    p = " " + norm_phrase(phrase) + " "
    for brand in brands:
        b = norm_phrase(brand)
        if b and f" {b} " in p:
            return True
    return False


def load_rows(path: Path) -> tuple[str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError(f"invalid Semrush export: {path}")
    return str(payload.get("domain") or path.stem), payload["rows"]


def score_row(row: dict, groups: list[str], tokens: int) -> float:
    volume = max(0, as_int(row.get("volume")))
    kd = max(0.0, min(100.0, as_float(row.get("keywordDifficulty"), 100.0)))
    cpc = max(0.0, as_float(row.get("cpc")))
    position = max(1, as_int(row.get("position"), 100))

    demand = math.log1p(volume)
    weakness = max(0.10, 1.0 - kd / 100.0)
    specificity = 1.0 + 0.18 * max(0, tokens - 2) + 0.22 * len(groups)
    value = 1.0 + min(cpc, 5.0) / 10.0
    observed = 1.0 + (0.10 if position <= 20 else 0.0)
    return round(demand * weakness * specificity * value * observed, 4)


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine narrow long-tail opportunities from Semrush organic-position exports.")
    ap.add_argument("--input", action="append", required=True, help="Semrush DPA JSON export; repeatable")
    ap.add_argument("--brand", action="append", default=[], help="Brand term to exclude; repeatable")
    ap.add_argument("--min-volume", type=int, default=20)
    ap.add_argument("--max-kd", type=float, default=49.0)
    ap.add_argument("--min-tokens", type=int, default=3)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    candidates = []
    source_stats = []
    inferred_brands = list(args.brand)

    loaded = []
    for raw in args.input:
        domain, rows = load_rows(Path(raw))
        loaded.append((domain, rows))
        inferred_brands.append(domain.split(".")[0])

    for domain, rows in loaded:
        kept = 0
        for row in rows:
            phrase = str(row.get("phrase") or "").strip()
            if not phrase:
                continue
            norm = norm_phrase(phrase)
            tokens = len(norm.split())
            volume = as_int(row.get("volume"))
            kd = as_float(row.get("keywordDifficulty"), 100.0)
            if tokens < args.min_tokens or volume < args.min_volume or kd > args.max_kd:
                continue
            if is_brand(phrase, inferred_brands):
                continue
            groups = modifier_groups(phrase)
            if not groups:
                continue
            if norm in HEAD_TERMS and len(groups) < 2:
                continue
            rec = {
                "source_domain": domain,
                "keyword": phrase,
                "position": as_int(row.get("position"), 0),
                "volume": volume,
                "kd": round(kd, 2),
                "cpc": round(as_float(row.get("cpc")), 4),
                "traffic": as_float(row.get("traffic")),
                "traffic_percent": as_float(row.get("trafficPercent")),
                "ranking_url": row.get("url") or "",
                "groups": groups,
                "tokens": tokens,
            }
            rec["gap_score"] = score_row(row, groups, tokens)
            candidates.append(rec)
            kept += 1
        source_stats.append({"domain": domain, "rows": len(rows), "candidates": kept})

    # Deduplicate same keyword across multiple seed competitors, retaining strongest evidence.
    dedup = {}
    for rec in candidates:
        key = norm_phrase(rec["keyword"])
        cur = dedup.get(key)
        if cur is None or rec["gap_score"] > cur["gap_score"]:
            dedup[key] = rec
    ranked = sorted(dedup.values(), key=lambda r: (r["gap_score"], r["volume"], -r["kd"]), reverse=True)[: max(1, args.top)]

    cluster_counts = Counter(g for r in ranked for g in r["groups"])
    cluster_volume = defaultdict(int)
    for r in ranked:
        for g in r["groups"]:
            cluster_volume[g] += r["volume"]

    payload = {
        "status": "PASS",
        "method": "crowded-but-proven adjacent keyword gap mining",
        "filters": {"min_volume": args.min_volume, "max_kd": args.max_kd, "min_tokens": args.min_tokens},
        "sources": source_stats,
        "count": len(ranked),
        "clusters": [
            {"group": g, "keywords": cluster_counts[g], "summed_volume_non_dedup_metric": cluster_volume[g]}
            for g in sorted(cluster_counts, key=lambda x: (cluster_counts[x], cluster_volume[x]), reverse=True)
        ],
        "items": ranked,
        "note": "gap_score is a triage heuristic, not final opportunity proof; exact SERP DD remains required.",
    }

    (outdir / "gap-mining.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["keyword", "source_domain", "gap_score", "volume", "kd", "cpc", "position", "tokens", "groups", "ranking_url"]
    with (outdir / "gap-mining.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ranked:
            x = dict(r)
            x["groups"] = "|".join(r["groups"])
            w.writerow({k: x.get(k, "") for k in fields})

    lines = [
        "# Crowded-but-proven Gap Mining",
        "",
        f"- sources: {', '.join(s['domain'] for s in source_stats) or '-'}",
        f"- candidates after filters/dedupe: {len(ranked)}",
        f"- min volume: {args.min_volume}",
        f"- max KD: {args.max_kd}",
        "- gap_score is triage only; exact SERP DD is mandatory before BUILD.",
        "",
        "## Clusters",
    ]
    for c in payload["clusters"]:
        lines.append(f"- {c['group']}: {c['keywords']} keywords; summed volume={c['summed_volume_non_dedup_metric']}")
    lines += ["", "## Top keyword gaps"]
    for i, r in enumerate(ranked, 1):
        lines += [
            f"### {i}. {r['keyword']}",
            f"- source: {r['source_domain']} | pos {r['position']}",
            f"- volume: {r['volume']} | KD: {r['kd']} | CPC: ${r['cpc']} | heuristic: {r['gap_score']}",
            f"- groups: {', '.join(r['groups'])}",
            f"- ranking URL: {r['ranking_url'] or '-'}",
            "",
        ]
    (outdir / "gap-mining.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"status": "PASS", "sources": len(source_stats), "candidates": len(ranked), "output_dir": str(outdir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
