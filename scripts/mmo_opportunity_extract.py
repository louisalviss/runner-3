#!/usr/bin/env python3
import argparse
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

from mmo_forum_fulltext import (
    UA, PREMIUM_MARKERS, audit_thread, detect_max_pages, fetch, thread_id
)

MONEY_RE = re.compile(r"(?i)(?:[$€£]\s?\d[\d,.]*(?:\s?[kmb])?|\b\d[\d,.]*\s?(?:usd|eur|gbp|dollars?|bucks?)\b)")
PERCENT_RE = re.compile(r"(?i)\b\d+(?:\.\d+)?\s?%")

SIGNALS = {
    "money": ["revenue", "profit", "profitable", "income", "mrr", "arr", "roi", "roas", "earned", "made $", "sales", "turnover", "net profit", "gross profit"],
    "buyer": ["client", "customer", "buyer", "paid order", "order", "repeat order", "retainer", "contract", "closed", "close rate", "lead", "inbound", "outbound"],
    "service": ["agency", "freelance", "service", "consulting", "productized", "retainer", "fulfillment", "outsource", "va ", "client work"],
    "acquisition": ["cold email", "cold call", "outreach", "seo", "ppc", "facebook ads", "google ads", "reddit", "youtube", "tiktok", "instagram", "email list", "newsletter", "referral", "organic traffic", "paid traffic", "lead gen", "landing page", "conversion rate"],
    "automation": ["automation", "automate", "api", "n8n", "zapier", "scraper", "bot", "agent", "ai ", "claude", "chatgpt", "codex", "workflow", "self-hosted", "tracking", "attribution"],
    "exit": ["sold the site", "sold my site", "sold for", "exit", "acquisition offer", "valuation", "multiple", "flippa", "empire flippers", "motion invest", "website flipping", "site flipping"],
    "failure": ["failed", "failure", "lost money", "loss", "unprofitable", "didn't work", "did not work", "shut down", "gave up", "stopped", "dead", "banned", "suspended"],
    "durability": ["years", "year later", "months later", "recurring", "repeat", "retention", "renewal", "subscription", "evergreen", "owned audience", "brand"],
}

CLUSTERS = {
    "Services / Agency": ["agency", "freelance", "service", "consulting", "client", "retainer", "fulfillment", "local business"],
    "Lead Gen / Outbound": ["lead gen", "lead generation", "cold email", "cold call", "outreach", "appointment", "prospect", "rank and rent", "rank & rent"],
    "SEO / Content Assets": ["seo", "content site", "authority site", "niche site", "organic traffic", "google traffic", "affiliate site", "content asset"],
    "Affiliate / Paid Traffic": ["affiliate", "media buying", "paid traffic", "facebook ads", "google ads", "native ads", "cpa", "epc", "roas", "roi"],
    "SaaS / Software": ["saas", "software", "micro-saas", "mrr", "arr", "subscription", "app"],
    "AI / Automation Ops": ["automation", "agent", "ai ", "chatgpt", "claude", "codex", "n8n", "zapier", "scraper", "workflow", "attribution", "tracking"],
    "Ecommerce / Product": ["ecommerce", "e-commerce", "shopify", "amazon fba", "dropshipping", "private label", "product", "store"],
    "Email / Newsletter": ["newsletter", "email list", "email marketing", "subscriber", "deliverability"],
    "Social / Creator Distribution": ["youtube", "reddit", "tiktok", "instagram", "twitter", " x ", "creator", "clipping", "shorts"],
    "Digital Asset Flipping / Exit": ["site flipping", "website flipping", "sold the site", "sold my site", "valuation", "multiple", "flippa", "exit"],
    "Tracking / Campaign Ops": ["tracker", "tracking", "attribution", "postback", "capi", "conversion api", "optimizer", "automated rules"],
}

NEGATIVE_PATTERNS = ["what do you think", "anyone tried", "is it possible", "how can i", "how do i", "beginner question"]


def normalize(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def signal_counts(text):
    low = " " + text.lower() + " "
    out = {}
    for name, kws in SIGNALS.items():
        out[name] = sum(low.count(k) for k in kws)
    out["money_amounts"] = len(MONEY_RE.findall(text))
    out["percentages"] = len(PERCENT_RE.findall(text))
    return out


def cluster_scores(title, text):
    low = (title + "\n" + text).lower()
    scores = {}
    for name, kws in CLUSTERS.items():
        scores[name] = sum(low.count(k) for k in kws)
    return scores


def split_units(text):
    text = normalize(text)
    units = re.split(r"(?<=[.!?])\s+|\s*[|•]\s*", text)
    return [u.strip() for u in units if len(u.strip()) >= 25]


def evidence_snippets(text, max_snippets=6):
    units = split_units(text)
    ranked = []
    for unit in units:
        low = unit.lower()
        sig = 0
        sig += 5 * len(MONEY_RE.findall(unit))
        sig += 3 * sum(low.count(k) for k in SIGNALS["money"])
        sig += 2 * sum(low.count(k) for k in SIGNALS["buyer"])
        sig += 2 * sum(low.count(k) for k in SIGNALS["failure"])
        sig += 1 * sum(low.count(k) for k in SIGNALS["acquisition"])
        sig += 1 * sum(low.count(k) for k in SIGNALS["automation"])
        sig += 2 * sum(low.count(k) for k in SIGNALS["exit"])
        if sig:
            clipped = unit[:360]
            ranked.append((sig, clipped))
    ranked.sort(key=lambda x: (-x[0], len(x[1])))
    out, seen = [], set()
    for score, s in ranked:
        key = re.sub(r"\W+", " ", s.lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        out.append({"score": score, "text": s})
        if len(out) >= max_snippets:
            break
    return out


def opportunity_score(title, text, signals, clusters):
    score = 0.0
    score += min(signals["money_amounts"], 8) * 3.0
    score += min(signals["money"], 15) * 1.4
    score += min(signals["buyer"], 18) * 0.8
    score += min(signals["service"], 12) * 0.5
    score += min(signals["acquisition"], 20) * 0.35
    score += min(signals["automation"], 15) * 0.35
    score += min(signals["exit"], 10) * 1.2
    score += min(signals["durability"], 12) * 0.45
    score += min(signals["failure"], 10) * 0.35  # failures are evidence too
    score += min(signals["percentages"], 8) * 0.4
    score += math.log10(max(len(text.split()), 10)) * 1.5
    low_title = title.lower()
    if any(x in low_title for x in ["journey", "case study", "case-study", "results", "profit", "revenue", "mrr", "sold"]):
        score += 5
    if any(x in low_title for x in NEGATIVE_PATTERNS) and signals["money_amounts"] == 0 and signals["money"] < 2:
        score -= 5
    if max(clusters.values() or [0]) == 0:
        score -= 3
    return round(score, 2)


def fetch_full_pass(session, row, source_cfg):
    base = row["url"]
    requested_id = row.get("thread_id") or thread_id(base)
    timeout = int(source_cfg.get("timeout_seconds", 35))
    delay = float(source_cfg.get("delay_seconds", 0.02))
    first = fetch(session, base, timeout)
    final_id = thread_id(first.get("final_url", ""))
    mismatch = bool(requested_id and final_id and requested_id != final_id)
    premium = any(x in first.get("text", "").lower() for x in PREMIUM_MARKERS)
    if not first.get("ok") or mismatch or premium:
        if mismatch:
            qa = "FAIL_CANONICAL_MISMATCH"
        elif premium:
            qa = "PARTIAL_PREMIUM"
        elif first.get("blocked"):
            qa = "FAIL_BLOCKED"
        else:
            qa = "FAIL"
        return qa, "", 0, 1
    max_pages = detect_max_pages(first.get("html", ""), row.get("listed_pages", 1))
    texts = [first.get("text", "")]
    ok_pages = 1
    for p in range(2, max_pages + 1):
        url = base.rstrip("/") + f"/page-{p}/"
        res = fetch(session, url, timeout)
        pid = thread_id(res.get("final_url", ""))
        pmismatch = bool(requested_id and pid and requested_id != pid)
        if not res.get("ok") or pmismatch:
            return "PARTIAL", "\n".join(texts), ok_pages, max_pages
        texts.append(res.get("text", ""))
        ok_pages += 1
        time.sleep(delay)
    return "PASS", "\n".join(texts), ok_pages, max_pages


def extract_shard(config_path, manifest_path, output, source_name, shard_index, shard_total):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    source_cfg = next(x for x in cfg["sources"] if x["name"] == source_name)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows = [x for x in manifest if x["source"] == source_name]
    rows = [row for i, row in enumerate(rows) if i % shard_total == shard_index]
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    records = []
    qa_counts = Counter()
    for i, row in enumerate(rows, 1):
        qa, text, pages_ok, pages_total = fetch_full_pass(session, row, source_cfg)
        qa_counts[qa] += 1
        if qa == "PASS":
            signals = signal_counts(text)
            clusters = cluster_scores(row.get("title", ""), text)
            ranked_clusters = sorted(clusters.items(), key=lambda x: (-x[1], x[0]))
            score = opportunity_score(row.get("title", ""), text, signals, clusters)
            records.append({
                "source": source_name,
                "section": row.get("section", ""),
                "thread_id": row.get("thread_id", ""),
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                "pages": pages_total,
                "words": len(text.split()),
                "opportunity_score": score,
                "signals": signals,
                "clusters": dict(ranked_clusters[:5]),
                "primary_cluster": ranked_clusters[0][0] if ranked_clusters and ranked_clusters[0][1] > 0 else "Unclassified",
                "evidence": evidence_snippets(text),
            })
        print(json.dumps({"source": source_name, "shard": shard_index, "item": i, "total": len(rows), "qa": qa, "candidates": len(records)}, ensure_ascii=False), flush=True)
        time.sleep(float(source_cfg.get("delay_seconds", 0.02)))
    fn = out / f"candidates-{source_name}-{shard_index}.jsonl"
    with fn.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {
        "source": source_name,
        "shard": shard_index,
        "threads_attempted": len(rows),
        "qa": dict(qa_counts),
        "pass_records_extracted": len(records),
    }
    (out / f"summary-{source_name}-{shard_index}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def aggregate(input_dir, output):
    inp = Path(input_dir)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for fp in inp.rglob("candidates-*.jsonl"):
        with fp.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    records.append(json.loads(line))
    records.sort(key=lambda r: (-r.get("opportunity_score", 0), r.get("source", ""), r.get("thread_id", "")))
    cluster = defaultdict(lambda: {"threads": 0, "score_sum": 0.0, "money_threads": 0, "buyer_threads": 0, "failure_threads": 0, "sources": Counter(), "top": []})
    for r in records:
        c = r.get("primary_cluster", "Unclassified")
        d = cluster[c]
        d["threads"] += 1
        d["score_sum"] += r.get("opportunity_score", 0)
        d["money_threads"] += int(r.get("signals", {}).get("money_amounts", 0) > 0 or r.get("signals", {}).get("money", 0) >= 3)
        d["buyer_threads"] += int(r.get("signals", {}).get("buyer", 0) >= 3)
        d["failure_threads"] += int(r.get("signals", {}).get("failure", 0) >= 2)
        d["sources"][r.get("source", "")] += 1
        if len(d["top"]) < 15:
            d["top"].append({k: r.get(k) for k in ["source", "thread_id", "title", "url", "opportunity_score"]})
    clusters = []
    for name, d in cluster.items():
        clusters.append({
            "cluster": name,
            "threads": d["threads"],
            "avg_score": round(d["score_sum"] / max(d["threads"], 1), 2),
            "money_threads": d["money_threads"],
            "buyer_threads": d["buyer_threads"],
            "failure_threads": d["failure_threads"],
            "sources": dict(d["sources"]),
            "top": d["top"],
        })
    clusters.sort(key=lambda x: (-x["money_threads"], -x["avg_score"], -x["threads"]))
    top = records[:400]
    with (out / "top_candidates.jsonl").open("w", encoding="utf-8") as fh:
        for r in top:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "clusters.json").write_text(json.dumps(clusters, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({
        "pass_threads_extracted": len(records),
        "top_candidates_retained": len(top),
        "clusters": len(clusters),
        "source_counts": dict(Counter(r.get("source", "") for r in records)),
        "threads_with_money_signal": sum(1 for r in records if r.get("signals", {}).get("money_amounts", 0) > 0 or r.get("signals", {}).get("money", 0) >= 3),
        "threads_with_buyer_signal": sum(1 for r in records if r.get("signals", {}).get("buyer", 0) >= 3),
        "threads_with_failure_signal": sum(1 for r in records if r.get("signals", {}).get("failure", 0) >= 2),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shard")
    s.add_argument("config")
    s.add_argument("manifest")
    s.add_argument("--output", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--shard-index", type=int, required=True)
    s.add_argument("--shard-total", type=int, required=True)
    a = sub.add_parser("aggregate")
    a.add_argument("input")
    a.add_argument("--output", required=True)
    args = ap.parse_args()
    if args.cmd == "shard":
        extract_shard(args.config, args.manifest, args.output, args.source, args.shard_index, args.shard_total)
    else:
        aggregate(args.input, args.output)

if __name__ == "__main__":
    main()
