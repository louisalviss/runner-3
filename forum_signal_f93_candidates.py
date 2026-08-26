#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import forum_signal_score as base


SOURCE = "VOZ-F93-MMO"
DOMAIN = [
    "affiliate", "affiliate marketing", "seo", "traffic", "organic", "keyword", "rank", "content",
    "adsense", "google ads", "facebook ads", "meta ads", "tiktok ads", "cpm", "cpc", "cpa", "cpl", "roas",
    "conversion", "landing page", "lead", "offer", "vertical", "domain", "hosting", "email",
    "youtube", "tiktok", "facebook", "shopify", "amazon", "etsy", "kdp",
    "account", "nhiều acc", "multi account", "checkpoint", "limit", "ban", "die acc",
    "paypal", "payoneer", "wise", "stripe", "payment", "payout", "refund", "chargeback",
    "automation", "workflow", "crawler", "scrape", "api", "ai", "agent", "tool",
    "case study", "doanh thu", "revenue", "lợi nhuận", "profit", "chi phí", "cost", "margin",
    "kinh nghiệm", "thực tế", "test", "scale", "scaling",
]
ECON = [
    "cpm", "cpc", "cpa", "cpl", "roas", "conversion", "doanh thu", "revenue", "lợi nhuận", "profit",
    "chi phí", "cost", "margin", "payout", "refund", "chargeback", "traffic", "lead", "scale", "scaling",
]
TITLE_PROMO = [
    "official thread", "trọn bộ mmo", "khóa học", "khoá học", "tổng hợp khóa học", "tổng hợp khoá học",
    "share khóa học", "share khoá học", "airdrop", "giveaway",
]
CTA_PROMO = [
    "ref link", "link ref", "mã giới thiệu", "đăng ký qua", "đăng kí qua", "đăng ký ngay", "đăng kí ngay",
    "liên hệ telegram", "liên hệ zalo", "ib mình", "inbox mình", "tham gia nhóm", "join group",
    "mua khóa học", "mua khoá học", "bán khóa học", "bán khoá học", "giá chỉ", "voucher", "khuyến mãi",
]


def norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_jsonl(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def row_key(row):
    fp = str(row.get("fingerprint") or "").strip()
    if fp:
        return fp
    raw = "|".join([
        str(row.get("source") or ""),
        str(row.get("thread_key") or ""),
        str(row.get("post_id") or ""),
        norm(row.get("text")),
    ])
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def marker_hits(text, markers):
    return sorted({m for m in markers if m in text})


def promo_reason(row, meta=None):
    title = norm(row.get("thread_title"))
    text = norm(row.get("text"))
    title_hits = marker_hits(title, TITLE_PROMO)
    cta_hits = marker_hits(text, CTA_PROMO)
    if title_hits:
        return "promotional_thread"
    reasoning = (meta or {}).get("reasoning_hits") or []
    firsthand = (meta or {}).get("firsthand_hits") or []
    if len(cta_hits) >= 2 and not reasoning and not firsthand:
        return "promotional_cta"
    if ("ref link" in text or "link ref" in text or "mã giới thiệu" in text) and int((meta or {}).get("url_count") or 0) > 0:
        return "referral_link"
    return None


def main():
    ap = argparse.ArgumentParser(description="Promote F93 operator/economics insights and reject promotional noise")
    ap.add_argument("--raw", default="crawl_output/forum_signal_snapshot.jsonl")
    ap.add_argument("--candidates", default="crawl_output/forum_insight_candidates.jsonl")
    ap.add_argument("--audit", default="crawl_output/forum_f93_candidate_boost.json")
    ap.add_argument("--min-score", type=float, default=3.0)
    ap.add_argument("--max-age-hours", type=float, default=72.0)
    args = ap.parse_args()

    existing = load_jsonl(args.candidates)
    raw = [r for r in load_jsonl(args.raw) if str(r.get("source") or "") == SOURCE]
    thread_counts = Counter(str(r.get("thread_key") or "") for r in raw)

    cleaned_existing = []
    existing_promo_rejected = 0
    for row in existing:
        if str(row.get("source") or "") != SOURCE:
            cleaned_existing.append(row)
            continue
        meta = row if "reasoning_hits" in row else base.score_row(row, args.max_age_hours)
        if promo_reason(row, meta):
            existing_promo_rejected += 1
            continue
        cleaned_existing.append(row)

    boosted = []
    promo_rejected = 0
    thin_rejected = 0
    for row in raw:
        text = norm(row.get("text"))
        title = norm(row.get("thread_title"))
        joined = f"{title} {text}"
        domain = marker_hits(joined, DOMAIN)
        if not domain:
            continue

        meta = base.score_row(row, args.max_age_hours)
        if not meta.get("fresh", True) or meta.get("signal_type") in {"stale", "timestamp_error"}:
            continue
        if promo_reason(row, meta):
            promo_rejected += 1
            continue

        n = len(str(row.get("text") or "").strip())
        reasoning = meta.get("reasoning_hits") or []
        firsthand = meta.get("firsthand_hits") or []
        numeric = int(meta.get("numeric_count") or 0)
        econ = marker_hits(joined, ECON)

        # F93 value should come from operator detail, economics, failure/workaround or an actual experiment.
        if n < 90 and not firsthand and not reasoning:
            thin_rejected += 1
            continue
        if len(domain) < 2 and n < 160 and not firsthand and not econ:
            thin_rejected += 1
            continue

        bonus = min(0.9, 0.14 * len(domain))
        bonus += min(0.7, 0.18 * len(econ))
        if n >= 140:
            bonus += 0.25
        if n >= 300:
            bonus += 0.2
        if reasoning:
            bonus += min(0.45, 0.14 * len(reasoning))
        if firsthand:
            bonus += min(0.55, 0.2 * len(firsthand))
        if numeric:
            bonus += min(0.4, 0.08 * numeric)

        item = dict(row)
        item.update(meta)
        item["score"] = round(min(5.0, float(meta.get("score") or 0) + bonus), 2)
        if item["score"] < args.min_score:
            continue
        item["scorer"] = "forum-signal-f93-operator-v1"
        item["f93_domain_hits"] = domain[:18]
        item["f93_econ_hits"] = econ[:12]
        item["thread_delta_posts"] = thread_counts[str(row.get("thread_key") or "")]
        item["consensus_candidate"] = False
        boosted.append(item)

    merged = {}
    for row in cleaned_existing + boosted:
        key = row_key(row)
        current = merged.get(key)
        if current is None or float(row.get("score") or 0) > float(current.get("score") or 0):
            merged[key] = row
    rows = list(merged.values())
    rows.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("source") or ""), str(r.get("thread_title") or "")))

    kept_counts = Counter(str(r.get("thread_key") or "") for r in rows if str(r.get("source") or "") == SOURCE)
    for row in rows:
        if str(row.get("source") or "") == SOURCE:
            row["consensus_candidate"] = kept_counts[str(row.get("thread_key") or "")] >= 3

    write_jsonl(args.candidates, rows)
    audit = {
        "scorer": "forum-signal-f93-operator-v1",
        "raw_f93_rows": len(raw),
        "existing_candidates": len(existing),
        "existing_promo_rejected": existing_promo_rejected,
        "snapshot_promo_rejected": promo_rejected,
        "thin_rejected": thin_rejected,
        "boosted_candidates": len(boosted),
        "merged_candidates": len(rows),
        "f93_candidates_after_merge": sum(1 for r in rows if str(r.get("source") or "") == SOURCE),
        "f93_threads_after_merge": len({str(r.get("thread_key") or "") for r in rows if str(r.get("source") or "") == SOURCE}),
        "min_score": args.min_score,
        "max_age_hours": args.max_age_hours,
    }
    Path(args.audit).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
