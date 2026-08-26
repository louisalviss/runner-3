#!/usr/bin/env python3

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


FIRSTHAND = [
    "mình mua", "tôi mua", "đã mua", "đang dùng", "đã dùng", "mình dùng", "tôi dùng",
    "đang xài", "đã xài", "xe tôi", "xe của tôi", "nhà tôi", "máy tôi", "của tôi",
    "lái thử", "đi thử", "gặp lỗi", "bị lỗi", "xe lỗi", "đã cài", "đang cài",
    "đã chơi", "đang chơi", "đang thuê", "đã thuê", "đang cho thuê", "đã bán",
    "đã sạc", "đang sạc", "vẫn hài lòng với", "hotline", "bảo hành",
]
REASONING = [
    "vì", "do đó", "nên", "nếu", "thì", "nhưng", "tuy nhiên", "theo mình", "theo tôi", "có thể",
    "khả năng", "nguyên nhân", "so với", "thành ra", "dẫn đến", "nghĩ là", "cho rằng", "hợp lý",
    "không hợp lý", "lý do", "kết quả là",
]
CURRENT = [
    "hôm nay", "vừa", "mới", "hiện tại", "bây giờ", "tới giờ", "patch", "update", "beta", "leak",
    "rumor", "tin đồn", "banner", "meta", "fix", "nerf", "buff", "ra mắt", "trailer", "release",
    "phiên bản",
]
EVIDENCE = [
    "ảnh", "video", "screenshot", "benchmark", "test", "log", "km", "kwh", "mah", "fps", "%",
    "triệu", "tỷ", "usd", "vnd", "gb", "hz", "km/h", "rc3", "rc6", "np",
]
NEWSISH = [
    "theo báo", "báo viết", "nguồn tin", "reuters", "bloomberg", "cnn", "bbc", "vnexpress", "tuổi trẻ",
    "dantri", "cafef", "cafebiz", "zing", "link báo", "bài báo",
]
TINHTE_PRODUCT = [
    "apple", "mac", "iphone", "ipad", "android", "windows", "laptop", "pc", "màn hình", "camera",
    "pin", "sạc", "ram", "ssd", "chip", "cpu", "gpu", "router", "nas", "wifi", "tai nghe", "loa",
    "đồng hồ", "watch", "app", "ứng dụng", "firmware", "xe điện", "ev", "máy lạnh", "máy lọc",
]
TINHTE_PROMO = [
    "ví trả sau", "đăng ký trả góp", "mã giảm giá", "mã khuyến mãi", "affiliate", "mua ngay", "đặt hàng",
]
NOISE_PATTERNS = [
    re.compile(r"^(\+1|up|ké|hóng|chấm|lol|vl|vãi|ok|oke|thanks|thank|=\)+|:v|haha+)[.!? ]*$", re.I),
    re.compile(r"^(ngon|hay|đẹp|xấu|ảo|ghê|kinh|chịu|thôi|đúng|sai)[.!? ]*$", re.I),
]
NUMERIC_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|km|km/h|kwh|wh|mah|gb|tb|fps|hz|triệu|tỷ|tr|usd|vnd|đồng)?\b", re.I)
URL_FULL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)


def norm(text):
    return " ".join(str(text or "").lower().split())


def hits(text, markers):
    return sorted({m for m in markers if m in text})


def parse_dt(value):
    value = str(value or "").strip()
    if not value:
        return None
    candidates = [value, value.replace("Z", "+00:00")]
    for item in candidates:
        try:
            dt = datetime.fromisoformat(item)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def age_hours(row):
    post_dt = parse_dt(row.get("timestamp"))
    fetched_dt = parse_dt(row.get("fetched_at")) or datetime.now(timezone.utc)
    if not post_dt:
        return None
    return (fetched_dt.astimezone(timezone.utc) - post_dt.astimezone(timezone.utc)).total_seconds() / 3600.0


def score_row(row, max_age_hours):
    raw = str(row.get("text") or "").strip()
    urls = URL_FULL_RE.findall(raw)
    plain_raw = URL_FULL_RE.sub(" ", raw)
    text = norm(plain_raw)
    title = norm(row.get("thread_title") or "")
    n = len(plain_raw)
    link_ratio = sum(len(u) for u in urls) / max(1, len(raw))

    firsthand = hits(text, FIRSTHAND)
    reasoning = hits(text, REASONING)
    current = hits(text, CURRENT)
    evidence = hits(text, EVIDENCE)
    newsish = hits(text, NEWSISH)
    numbers = NUMERIC_RE.findall(text)
    age = age_hours(row)

    score = 0.55
    reasons = []

    if age is not None:
        if age < -6:
            return {
                "score": 0.0, "signal_type": "timestamp_error", "reasons": ["future_timestamp"],
                "firsthand_hits": firsthand[:8], "reasoning_hits": reasoning[:8], "current_hits": current[:8],
                "evidence_hits": evidence[:8], "numeric_count": len(numbers), "needs_verification": True,
                "age_hours": round(age, 2), "fresh": False,
            }
        if age > max_age_hours:
            return {
                "score": 0.0, "signal_type": "stale", "reasons": ["stale_timestamp"],
                "firsthand_hits": firsthand[:8], "reasoning_hits": reasoning[:8], "current_hits": current[:8],
                "evidence_hits": evidence[:8], "numeric_count": len(numbers), "needs_verification": False,
                "age_hours": round(age, 2), "fresh": False,
            }

    if n >= 120:
        score += 0.4
        reasons.append("substantive_text")
    if n >= 250:
        score += 0.4
    if n >= 500:
        score += 0.3

    if firsthand:
        score += min(1.7, 0.55 * len(firsthand))
        reasons.append("firsthand")
    if reasoning:
        score += min(1.15, 0.23 * len(reasoning))
        reasons.append("reasoning")
    if current:
        score += min(0.9, 0.24 * len(current))
        reasons.append("current_signal")
    if evidence:
        score += min(0.8, 0.2 * len(evidence))
        reasons.append("evidence_marker")
    if numbers:
        score += min(1.0, 0.16 * len(numbers))
        reasons.append("numeric_detail")

    if n < 45:
        score -= 1.15
        reasons.append("too_short")
    if any(p.match(text) for p in NOISE_PATTERNS):
        score -= 1.5
        reasons.append("reaction_noise")
    if urls and (n < 180 or link_ratio > 0.25):
        score -= 1.0
        reasons.append("link_heavy")

    source_article = (
        title.startswith("[dịch]")
        or title.startswith("[dich]")
        or any(src in norm(plain_raw[:180]) for src in ("[bloomberg", "[reuters", "[bbc", "[cnn", "theo bloomberg", "theo reuters"))
    )
    if source_article:
        score -= 2.6
        reasons.append("source_article_repost")
    elif newsish and not firsthand and len(reasoning) < 2:
        score -= 1.0
        reasons.append("news_repost_risk")

    if row.get("extraction") == "page_fallback":
        score -= 1.2
        reasons.append("page_fallback")

    # Tinhte's useful signal is often terse product ownership/price evidence rather than long-form reasoning.
    # Only boost structured comments from the latest active-thread slice, and require substantive evidence.
    tinhte_proxy = (
        str(row.get("source") or "") == "Tinhte"
        and str(row.get("extraction") or "") == "structured_post"
        and str(row.get("timestamp_recovery_source") or "") == "tinhte_active_thread_fetch"
    )
    tinhte_product_hits = hits(f"{title} {text}", TINHTE_PRODUCT) if tinhte_proxy else []
    tinhte_promo_hits = hits(text, TINHTE_PROMO) if tinhte_proxy else []
    if tinhte_proxy and n >= 90 and tinhte_product_hits and (firsthand or reasoning or len(numbers) >= 2):
        score += 0.75
        reasons.append("tinhte_active_product_signal")
        if firsthand or len(numbers) >= 3:
            score += 0.55
            reasons.append("tinhte_firsthand_or_numeric_depth")
        if tinhte_promo_hits:
            score -= 1.2
            reasons.append("tinhte_promo_risk")

    # A candidate must contain at least one core community signal. Numbers/links alone are not insight,
    # except the guarded Tinhte active-product case above where fresh numeric ownership evidence is intentional.
    if not firsthand and not reasoning and not current and score >= 3.0 and not (
        tinhte_proxy and tinhte_product_hits and len(numbers) >= 2 and not tinhte_promo_hits
    ):
        score = 2.85
        reasons.append("no_core_signal")

    score = round(max(0.0, min(5.0, score)), 2)

    if firsthand and len(numbers) >= 2:
        signal_type = "empirical_data"
    elif firsthand:
        signal_type = "firsthand_experience"
    elif len(reasoning) >= 2 and current:
        signal_type = "current_reasoning"
    elif len(reasoning) >= 2:
        signal_type = "reasoning_theory"
    elif current:
        signal_type = "current_claim"
    elif tinhte_proxy and len(numbers) >= 2:
        signal_type = "consumer_product_signal"
    else:
        signal_type = "unusual_signal"

    needs_verification = signal_type in {"current_claim", "current_reasoning"} or bool(newsish) or any(
        k in text for k in ("leak", "rumor", "tin đồn", "confirm", "xác nhận")
    )

    return {
        "score": score,
        "signal_type": signal_type,
        "reasons": reasons,
        "firsthand_hits": firsthand[:8],
        "reasoning_hits": reasoning[:8],
        "current_hits": current[:8],
        "evidence_hits": evidence[:8],
        "numeric_count": len(numbers),
        "needs_verification": needs_verification,
        "age_hours": round(age, 2) if age is not None else None,
        "fresh": age is None or age <= max_age_hours,
        "freshness_proxy": bool(tinhte_proxy),
        "freshness_basis": "active_thread_fetch" if tinhte_proxy else "post_timestamp",
        "url_count": len(urls),
        "link_ratio": round(link_ratio, 3),
    }


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Score fresh forum delta rows into signal candidates")
    parser.add_argument("--input", default="crawl_output/forum_signal.jsonl")
    parser.add_argument("--output", default="crawl_output/forum_insight_candidates.jsonl")
    parser.add_argument("--summary", default="crawl_output/forum_insights.md")
    parser.add_argument("--min-score", type=float, default=3.0)
    parser.add_argument("--max-age-hours", type=float, default=72.0)
    args = parser.parse_args()

    if not 0 <= args.min_score <= 5:
        raise SystemExit("min-score must be 0..5")
    if not 1 <= args.max_age_hours <= 720:
        raise SystemExit("max-age-hours must be 1..720")

    rows = load_jsonl(Path(args.input))
    scored = []
    thread_counts = Counter(str(r.get("thread_key") or "") for r in rows)

    for row in rows:
        meta = score_row(row, args.max_age_hours)
        item = dict(row)
        item.update(meta)
        item["scorer"] = "forum-signal-heuristic-v3"
        item["thread_delta_posts"] = thread_counts[str(row.get("thread_key") or "")]
        scored.append(item)

    kept = [r for r in scored if r["score"] >= args.min_score and r.get("fresh", True)]
    kept.sort(key=lambda r: (-r["score"], r.get("source", ""), r.get("thread_title", "")))
    kept_counts = Counter(str(r.get("thread_key") or "") for r in kept)
    for item in kept:
        item["consensus_candidate"] = kept_counts[str(item.get("thread_key") or "")] >= 3

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_source = defaultdict(int)
    by_type = defaultdict(int)
    for row in kept:
        by_source[row.get("source", "unknown")] += 1
        by_type[row.get("signal_type", "unknown")] += 1

    stale_count = sum(1 for r in scored if r.get("signal_type") == "stale")
    md = [
        "# Forum Signal Candidates",
        "",
        f"Unseen delta rows: {len(rows)}",
        f"Stale unseen rows excluded (> {args.max_age_hours:g}h): {stale_count}",
        f"Fresh candidates score >= {args.min_score:g}: {len(kept)}",
        "Scorer: forum-signal-heuristic-v3 (deterministic prefilter; not an LLM)",
        "",
    ]
    for row in kept[:50]:
        text = " ".join(str(row.get("text") or "").split())
        if len(text) > 360:
            text = text[:357] + "..."
        md.extend([
            f"## [{row['score']}/5] {row.get('source','')} — {row.get('thread_title','')}",
            f"Type: `{row.get('signal_type')}` | age_h: `{row.get('age_hours')}` | verify: `{row.get('needs_verification')}` | author: `{row.get('author','')}`",
            "",
            text,
            "",
        ])

    Path(args.summary).write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({
        "scorer": "forum-signal-heuristic-v3",
        "unseen_delta_rows": len(rows),
        "stale_excluded": stale_count,
        "candidates": len(kept),
        "min_score": args.min_score,
        "max_age_hours": args.max_age_hours,
        "by_source": dict(by_source),
        "by_type": dict(by_type),
        "output": str(out_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
