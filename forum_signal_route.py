#!/usr/bin/env python3

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def has_any(text, keywords):
    return any(k in text for k in keywords)


ALIGNMENT = {
    "VOZ-F91": [
        "ai", "claude", "codex", "cursor", "lập trình", "developer", "devops", "linux",
        "cloud", "server", "database", "security", "bug", "performance", "benchmark",
        "công ty", "lương", "phỏng vấn", "automotive", "bosch", "outsour", "task", "resource",
    ],
    "VOZ-F92": [
        "chứng khoán", "cổ phiếu", "phái sinh", "đầu tư", "thị trường", "vnindex", "vn100",
        "vàng", "ngân hàng", "lãi suất", "thẻ tín dụng", "tài sản", "bất động sản", "nhà",
        "thuê", "thuế", "luật", "bảo hiểm", "vnd", "usd", "tỷ giá", "thanh khoản", "khối ngoại",
    ],
    "VOZ-F38": [
        "xe", "ô tô", "hộp số", "bảo dưỡng", "động cơ", "dầu", "lốp", "sạc", "pin", "ev",
        "bev", "phev", "honda", "toyota", "vios", "city", "vinfast", "đăng kiểm", "cao tốc",
    ],
    "VOZ-F10": [
        "máy", "điều hòa", "máy lạnh", "máy giặt", "máy sấy", "máy rửa", "robot", "hút bụi",
        "quạt", "điện", "bo mạch", "bảo hành", "bosch", "roborock", "ecovacs", "tineco", "dock",
    ],
}

GAMEVN_NOISE_TITLES = [
    "trà chanh chém gió", "chat topic", "chém gió", "tán gẫu", "offtopic", "off-topic",
]

F95_LISTING_MARKERS = [
    "headhunt", "tuyển dụng nhân sự", "update liên tục", "chân dung ứng viên phù hợp",
    "sharecv", "mức treo thưởng", "gởi jd", "gửi jd", "yêu cầu ứng viên", "job description",
]

MMO_PROMO_MARKERS = [
    "ref link", "mã giới thiệu", "telegram", "zalo", "đào free", "kèo chắc ăn", "airdrop",
]

CRYPTO_PROMO_MARKERS = [
    "thưởng người dùng mới", "airdrop", "đào free", "kèo chắc ăn", "mã giới thiệu", "ref link",
    "thưởng 3200", "bottrade", "tín hiệu trade", "signal vip",
]


def route_for(source):
    s = str(source or "").upper()
    if "F93" in s or s.endswith("-MMO"):
        return "mmo"
    if "F94" in s or "CRYPTO" in s:
        return "crypto"
    return "general"


def rejection_reason(row):
    source = str(row.get("source") or "")
    title = norm(row.get("thread_title"))
    text = norm(row.get("text"))
    joined = f"{title} {text}"
    route = route_for(source)

    # Final promotion requires a parseable recent post timestamp. Unknown age is audit-only.
    if row.get("age_hours") is None:
        return "freshness_unknown"
    if row.get("extraction") == "page_fallback":
        return "page_fallback"

    if source == "VOZ-F95" and has_any(joined, F95_LISTING_MARKERS):
        return "job_listing_not_discussion"

    if source in ALIGNMENT and not has_any(text, ALIGNMENT[source]):
        return "topic_drift"

    if source == "GameVN" and has_any(title, GAMEVN_NOISE_TITLES):
        return "general_chat_thread"

    if route == "mmo" and has_any(joined, MMO_PROMO_MARKERS):
        return "mmo_promo_risk"

    if route == "crypto" and has_any(joined, CRYPTO_PROMO_MARKERS):
        return "crypto_promo_risk"

    return None


def load_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(path, title, rows):
    lines = [f"# {title}", "", f"Candidates: {len(rows)}", ""]
    for row in rows[:60]:
        text = " ".join(str(row.get("text") or "").split())
        if len(text) > 420:
            text = text[:417] + "..."
        lines.extend([
            f"## [{row.get('score')}/5] {row.get('source','')} — {row.get('thread_title','')}",
            f"Route: `{row.get('route')}` | Type: `{row.get('signal_type')}` | age_h: `{row.get('age_hours')}` | verify: `{row.get('needs_verification')}`",
            "",
            text,
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Route and final-postfilter forum signal candidates")
    parser.add_argument("--input", default="crawl_output/forum_insight_candidates.jsonl")
    parser.add_argument("--output-dir", default="crawl_output")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output_dir)
    rows = load_jsonl(in_path)

    kept = []
    rejected = []
    for row in rows:
        item = dict(row)
        item["route"] = route_for(item.get("source"))
        reason = rejection_reason(item)
        if reason:
            item["route_filter_rejection"] = reason
            rejected.append(item)
        else:
            item["route_filter"] = "pass"
            kept.append(item)

    kept.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("source") or "")))
    general = [r for r in kept if r["route"] == "general"]
    mmo = [r for r in kept if r["route"] == "mmo"]
    crypto = [r for r in kept if r["route"] == "crypto"]

    # Keep the canonical filename GENERAL-only so the 21:00 Vietnam Radar cannot consume MMO/crypto by accident.
    write_jsonl(in_path, general)
    write_jsonl(out_dir / "forum_insight_candidates_all_routes.jsonl", kept)
    write_jsonl(out_dir / "forum_insight_candidates_mmo.jsonl", mmo)
    write_jsonl(out_dir / "forum_insight_candidates_crypto.jsonl", crypto)
    write_jsonl(out_dir / "forum_candidate_rejections.jsonl", rejected)

    write_summary(out_dir / "forum_insights.md", "Forum Signal Candidates — General", general)
    write_summary(out_dir / "forum_insights_mmo.md", "Forum Signal Candidates — MMO", mmo)
    write_summary(out_dir / "forum_insights_crypto.md", "Forum Signal Candidates — Crypto", crypto)

    reject_counts = Counter(r.get("route_filter_rejection") for r in rejected)
    print(json.dumps({
        "router": "forum-signal-route-v1",
        "input_candidates": len(rows),
        "kept_all_routes": len(kept),
        "general": len(general),
        "mmo": len(mmo),
        "crypto": len(crypto),
        "rejected": len(rejected),
        "reject_reasons": dict(reject_counts),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
