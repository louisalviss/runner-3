#!/usr/bin/env python3
"""Conservative curation layer for cross-niche Reddit opportunity candidates."""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BUILD_LANES = {"software-workflow", "ecosystem", "professional-workflow", "developer", "commerce"}
BUY_LANES = {"purchase-intent"}
PROMO = (
    "this week's top", "news stories", "i spent ", "i built ", "i made ",
    "launching", "launched", "tested ", "ranked by", "free workflow",
    "sharing in case", "case study", "my app", "my saas",
)
DISTRESS = (
    "financial hole", "eidl loan", "cc debt", "burnt out", "burned out",
    "chronic illness", "always sleepy", "litigation", "laws broken",
)
LOW_VALUE = ("[ removed by moderator ]", "giveaway", "meme")


def has_any(text, needles):
    low = text.lower()
    return any(x in low for x in needles)


def confirmation(row):
    ev = row.get("comment_evidence") or {}
    return int(ev.get("matching_comments") or 0)

def classify(row):
    title = str(row.get("title") or "")
    body = str(row.get("body") or "")
    text = title + "\n" + body[:2500]
    lanes = set(row.get("lanes") or [])
    d = row.get("dimensions") or {}
    pain = float(d.get("pain_specificity") or 0)
    money = float(d.get("money_intent") or 0)
    workaround = float(d.get("workaround_complexity") or 0)
    repeat = float(d.get("repeat_frequency") or 0)
    replacement = float(d.get("replacement_intent") or 0)

    if has_any(title, LOW_VALUE) or has_any(text, DISTRESS):
        return "IGNORE", 0.0, ["low-value-or-distress"]
    if has_any(title, PROMO):
        return "IGNORE", 0.0, ["supply-side-promo"]

    reasons = []
    base = float(row.get("opportunity_score") or 0)
    confirmed = confirmation(row)
    structural = workaround >= 7 or repeat >= 4 or replacement >= 4
    demand = pain >= 8 or money >= 6
    if lanes & BUILD_LANES and structural and demand:
        reasons.append("build-demand")
        if workaround >= 10:
            reasons.append("strong-workaround")
        if repeat >= 4:
            reasons.append("recurring")
        if replacement >= 4:
            reasons.append("replacement")
        score = base + min(8.0, confirmed / 5.0)
        return "BUILD", round(min(100.0, score), 2), reasons

    if lanes & BUY_LANES and (money >= 6 or replacement >= 4) and (pain >= 4 or replacement >= 4):
        reasons.append("purchase-intent")
        score = base + min(5.0, confirmed / 8.0)
        return "BUY", round(min(100.0, score), 2), reasons

    if pain >= 10 and structural and base >= 35:
        reasons.append("pain-discovery")
        return "DISCOVERY", round(base, 2), reasons

    return "IGNORE", 0.0, ["insufficient-actionability"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    kept = []
    counts = Counter()
    by_lane = Counter()
    for row in rows:
        kind, score, reasons = classify(row)
        counts[kind] += 1
        if kind == "IGNORE":
            continue
        item = dict(row)
        item["decision_class"] = kind
        item["curated_score"] = score
        item["curation_reasons"] = reasons
        kept.append(item)
        for lane in item.get("lanes") or []:
            by_lane[lane] += 1
    kept.sort(key=lambda x: (-x["curated_score"], -x.get("num_comments", 0)))

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "actionable.jsonl").open("w", encoding="utf-8") as fh:
        for row in kept:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "top_actionable.json").write_text(
        json.dumps(kept[:100], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        "input_rows": len(rows),
        "kept": len(kept),
        "classes": dict(counts),
        "actionable_by_lane": dict(by_lane),
        "top_subreddits": dict(Counter(x["subreddit"] for x in kept).most_common(20)),
        "top_build": [{"score":x["curated_score"],"subreddit":x["subreddit"],"title":x["title"],"url":x["url"]} for x in kept if x["decision_class"]=="BUILD"][:30],
        "top_buy": [{"score":x["curated_score"],"subreddit":x["subreddit"],"title":x["title"],"url":x["url"]} for x in kept if x["decision_class"]=="BUY"][:20],
    }
    (out / "curation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
