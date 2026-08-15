#!/usr/bin/env python3

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


FIRSTHAND = [
    "tôi", "mình", "nhà tôi", "xe tôi", "máy tôi", "đang dùng", "đã dùng", "đang xài", "đã xài",
    "mua", "bán", "thuê", "cho thuê", "đang ở", "đã ở", "đi thử", "test", "thử", "trải nghiệm",
    "gặp lỗi", "bị lỗi", "sạc", "chạy được", "đi được", "đã cài", "đang cài", "đã chơi", "đang chơi",
]
REASONING = [
    "vì", "do đó", "nên", "nếu", "thì", "nhưng", "tuy nhiên", "theo mình", "theo tôi", "có thể",
    "khả năng", "nguyên nhân", "so với", "thành ra", "dẫn đến", "nghĩ là", "cho rằng", "hợp lý",
    "không hợp lý", "lý do", "kết quả là",
]
CURRENT = [
    "hôm nay", "vừa", "mới", "hiện tại", "bây giờ", "patch", "update", "beta", "leak", "rumor",
    "banner", "meta", "giá", "lãi suất", "thuê", "rao", "bán", "lỗi", "fix", "nerf", "buff",
    "ra mắt", "trailer", "release", "phiên bản", "3.8", "1.18",
]
EVIDENCE = [
    "ảnh", "video", "screenshot", "benchmark", "đo", "test", "log", "km", "kwh", "mah", "fps", "%",
    "triệu", "tỷ", "usd", "vnd", "gb", "hz", "km/h", "rc3", "rc6", "np",
]
NEWSISH = [
    "theo báo", "báo viết", "nguồn tin", "reuters", "cnn", "bbc", "vnexpress", "tuổi trẻ", "dantri",
    "cafef", "cafebiz", "zing", "link báo", "bài báo",
]
NOISE_PATTERNS = [
    re.compile(r"^(\+1|up|ké|hóng|chấm|lol|vl|vãi|ok|oke|thanks|thank|=\)+|:v|haha+)[.!? ]*$", re.I),
    re.compile(r"^(ngon|hay|đẹp|xấu|ảo|ghê|kinh|chịu|thôi|đúng|sai)[.!? ]*$", re.I),
]
NUMERIC_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|km|km/h|kwh|wh|mah|gb|tb|fps|hz|triệu|tỷ|tr|usd|vnd|đồng)?\b", re.I)
URL_RE = re.compile(r"https?://|www\.", re.I)


def norm(text):
    return " ".join(str(text or "").lower().split())


def hits(text, markers):
    return sorted({m for m in markers if m in text})


def score_row(row):
    raw = str(row.get("text") or "").strip()
    text = norm(raw)
    n = len(raw)

    firsthand = hits(text, FIRSTHAND)
    reasoning = hits(text, REASONING)
    current = hits(text, CURRENT)
    evidence = hits(text, EVIDENCE)
    newsish = hits(text, NEWSISH)
    numbers = NUMERIC_RE.findall(text)

    score = 0.55
    reasons = []

    if n >= 120:
        score += 0.4
        reasons.append("substantive_text")
    if n >= 250:
        score += 0.4
    if n >= 500:
        score += 0.3

    if firsthand:
        add = min(1.55, 0.45 * len(firsthand))
        score += add
        reasons.append("firsthand")
    if reasoning:
        add = min(1.15, 0.23 * len(reasoning))
        score += add
        reasons.append("reasoning")
    if current:
        add = min(0.9, 0.24 * len(current))
        score += add
        reasons.append("current_signal")
    if evidence:
        add = min(0.8, 0.2 * len(evidence))
        score += add
        reasons.append("evidence_marker")
    if numbers:
        add = min(1.0, 0.16 * len(numbers))
        score += add
        reasons.append("numeric_detail")

    if n < 45:
        score -= 1.15
        reasons.append("too_short")
    if any(p.match(text) for p in NOISE_PATTERNS):
        score -= 1.5
        reasons.append("reaction_noise")
    if URL_RE.search(raw) and n < 180:
        score -= 0.55
        reasons.append("link_heavy")
    if newsish and not firsthand and len(reasoning) < 2:
        score -= 0.8
        reasons.append("news_repost_risk")
    if row.get("extraction") == "page_fallback":
        score -= 1.2
        reasons.append("page_fallback")

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
    }


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Score forum delta rows into signal candidates")
    parser.add_argument("--input", default="crawl_output/forum_signal.jsonl")
    parser.add_argument("--output", default="crawl_output/forum_insight_candidates.jsonl")
    parser.add_argument("--summary", default="crawl_output/forum_insights.md")
    parser.add_argument("--min-score", type=float, default=3.0)
    args = parser.parse_args()

    if not 0 <= args.min_score <= 5:
        raise SystemExit("min-score must be 0..5")

    rows = load_jsonl(Path(args.input))
    scored = []
    thread_counts = Counter(str(r.get("thread_key") or "") for r in rows)

    for row in rows:
        meta = score_row(row)
        item = dict(row)
        item.update(meta)
        item["scorer"] = "forum-signal-heuristic-v1"
        item["thread_delta_posts"] = thread_counts[str(row.get("thread_key") or "")]
        if item["thread_delta_posts"] >= 3 and item["score"] >= args.min_score:
            item["consensus_candidate"] = True
        else:
            item["consensus_candidate"] = False
        scored.append(item)

    kept = [r for r in scored if r["score"] >= args.min_score]
    kept.sort(key=lambda r: (-r["score"], r.get("source", ""), r.get("thread_title", "")))

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

    md = [
        "# Forum Signal Candidates",
        "",
        f"Delta rows: {len(rows)}",
        f"Candidates score >= {args.min_score:g}: {len(kept)}",
        f"Scorer: forum-signal-heuristic-v1 (deterministic prefilter; not an LLM)",
        "",
    ]
    for row in kept[:50]:
        text = " ".join(str(row.get("text") or "").split())
        if len(text) > 360:
            text = text[:357] + "..."
        md.extend([
            f"## [{row['score']}/5] {row.get('source','')} — {row.get('thread_title','')}",
            f"Type: `{row.get('signal_type')}` | verify: `{row.get('needs_verification')}` | author: `{row.get('author','')}`",
            "",
            text,
            "",
        ])

    Path(args.summary).write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({
        "scorer": "forum-signal-heuristic-v1",
        "delta_rows": len(rows),
        "candidates": len(kept),
        "min_score": args.min_score,
        "by_source": dict(by_source),
        "by_type": dict(by_type),
        "output": str(out_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
