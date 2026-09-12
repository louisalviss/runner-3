#!/usr/bin/env python3
"""Cross-niche Reddit opportunity scan using Runner-3's resilient acquisition layer."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import reddit_common as reddit

MONEY_RE = re.compile(r"(?i)(?:[$€£]\s?\d[\d,.]*(?:\s?[kmb])?|\b\d[\d,.]*\s?(?:usd|eur|gbp|dollars?|bucks?)\b)")
PATTERNS = {
    "pain": ("doesn't work", "does not work", "can't ", "cannot ", "frustrat", "annoy", "hate ", "problem", "pain", "struggl", "tedious", "time consuming", "takes forever", "manual", "broken", "missing feature", "wish ", "need a way"),
    "money": ("pricing", "paid ", "pay for", "budget", "expensive", "cheaper", "subscription", "revenue", "client", "customer", "cost ", "worth ", "buy ", "purchase"),
    "workaround": ("workaround", "manually", "spreadsheet", "excel", "script", "custom tool", "copy paste", "copy-paste", "multiple tools", "zapier", "n8n", "automate", "automation", "macro", "template"),
    "replacement": ("alternative to", "alternative for", "replace ", "replacement", "switch from", "switched from", "moved from", "looking for", "recommend", "similar to", "instead of", "what do you use"),
    "repeat": ("daily", "weekly", "every day", "every week", "every time", "repeatedly", "recurring", "always ", "each time", "for every", "clients", "customers", "orders"),
}
NOISE = ("giveaway", "meme", "roast me", "rate my", "look what i", "first time", "beginner question", "how to start", "what is the best")

def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def phrase_hits(text, key):
    low = " " + (text or "").lower() + " "
    return sum(low.count(term) for term in PATTERNS[key])


def raw_signals(post):
    title = str(post.get("title") or "")
    body = str(post.get("selftext") or "")
    text = title + "\n" + body
    hits = {k: phrase_hits(text, k) for k in PATTERNS}
    hits["money_amounts"] = len(MONEY_RE.findall(text))
    hits["body_words"] = len(body.split())
    return hits


def dim_scores(post):
    s = raw_signals(post)
    pain = min(25.0, s["pain"] * 4.0 + min(s["body_words"], 500) / 100.0)
    money = min(20.0, s["money"] * 2.3 + s["money_amounts"] * 4.0)
    workaround = min(18.0, s["workaround"] * 3.5)
    repeat = min(12.0, s["repeat"] * 2.4)
    replacement = min(10.0, s["replacement"] * 3.3)
    engagement = min(5.0, math.log1p(max(int(post.get("num_comments") or 0), 0)) * 1.15 + math.log1p(max(int(post.get("score") or 0), 0)) * 0.35)
    return s, {"pain_specificity":round(pain,2), "money_intent":round(money,2), "workaround_complexity":round(workaround,2), "repeat_frequency":round(repeat,2), "replacement_intent":round(replacement,2), "engagement":round(engagement,2)}

def base_score(post, weight):
    signals, dims = dim_scores(post)
    score = sum(dims.values())
    text = (str(post.get("title") or "") + "\n" + str(post.get("selftext") or "")).lower()
    if any(x in text for x in NOISE) and dims["pain_specificity"] < 8 and dims["money_intent"] < 5:
        score -= 8
    if signals["pain"] == 0 and signals["money"] == 0 and signals["workaround"] == 0 and signals["replacement"] == 0:
        score -= 10
    score = max(0.0, min(90.0, score * float(weight)))
    return round(score, 2), signals, dims


def listing_request(subreddit, label, limit):
    endpoint, period = ("top", "week") if label == "top-week" else (label, None)
    query = {"limit": limit, "raw_json": 1}
    if period:
        query["t"] = period
    payload, meta = reddit.resilient_request_json(f"/r/{subreddit}/{endpoint}.json", query)
    children = (((payload or {}).get("data") or {}).get("children") or [])
    posts = []
    for child in children:
        row = (child or {}).get("data") if isinstance(child, dict) else None
        if isinstance(row, dict) and row.get("id"):
            posts.append(reddit.normalize_post(row, subreddit))
    if str(meta.get("via") or "") == "arctic-shift":
        if label == "top-week":
            posts.sort(key=lambda p: (int(p.get("score") or 0), int(p.get("num_comments") or 0)), reverse=True)
        elif label == "hot":
            now = dt.datetime.now(dt.timezone.utc).timestamp()
            def hot_rank(p):
                age_h = max(0.0, (now - int(p.get("created_utc") or 0)) / 3600.0)
                return math.log1p(max(int(p.get("score") or 0), 0)) + 1.15 * math.log1p(max(int(p.get("num_comments") or 0), 0)) - age_h / 36.0
            posts.sort(key=hot_rank, reverse=True)
        else:
            posts.sort(key=lambda p: int(p.get("created_utc") or 0), reverse=True)
    return posts[:limit], meta


def confirm_comments(post_id):
    payload, meta = reddit.resilient_request_json(
        f"/comments/{post_id}.json", {"limit": 300, "depth": 6, "sort": "top", "raw_json": 1}
    )
    _post, comments = reddit.normalize_thread_payload(payload, post_id)
    matches = 0
    dimensions = Counter()
    for row in comments:
        text = str(row.get("body") or "")
        local = {k: phrase_hits(text, k) for k in ("pain", "money", "workaround", "replacement", "repeat")}
        active = [k for k, v in local.items() if v]
        if active:
            matches += 1
            dimensions.update(active)
    bonus = min(10.0, 2.6 * math.log1p(matches) + min(len(dimensions), 4) * 0.6)
    return round(bonus, 2), len(comments), matches, dict(dimensions), meta

def signal_tags(dims):
    out = []
    thresholds = {
        "pain_specificity": 8, "money_intent": 6, "workaround_complexity": 5,
        "repeat_frequency": 4, "replacement_intent": 4,
    }
    for key, threshold in thresholds.items():
        if float(dims.get(key, 0)) >= threshold:
            out.append(key.replace("_", "-"))
    return out or ["weak-signal"]


def canonical_url(post):
    return "https://www.reddit.com" + str(post.get("permalink") or f"/comments/{post.get('id','')}/")


def scan(config, output_dir, max_subs, per_listing, confirmations, delay):
    started = utc_now()
    listings = list(config.get("listings") or ["new", "hot", "top-week"])
    subs = list(config.get("subreddits") or [])
    if max_subs:
        subs = subs[:max_subs]
    records = {}
    errors = []
    acquisition = Counter()

    for index, spec in enumerate(subs, 1):
        name = str(spec["name"])
        for label in listings:
            try:
                posts, meta = listing_request(name, label, per_listing)
                acquisition[str(meta.get("via") or "unknown")] += 1
                for post in posts:
                    pid = str(post["id"])
                    score, signals, dims = base_score(post, spec.get("weight", 1.0))
                    row = records.get(pid)
                    if row is None:
                        row = {
                            "post_id": pid, "subreddit": name, "lanes": list(spec.get("lanes") or []),
                            "title": post.get("title") or "", "body": post.get("selftext") or "",
                            "score": int(post.get("score") or 0), "num_comments": int(post.get("num_comments") or 0),
                            "created_utc": int(post.get("created_utc") or 0), "url": canonical_url(post),
                            "source_listings": [], "signals": signals, "dimensions": dims,
                            "base_score": score, "comment_confirmation": 0.0, "opportunity_score": score,
                        }
                        records[pid] = row
                    if label not in row["source_listings"]:
                        row["source_listings"].append(label)
                time.sleep(delay)
            except Exception as exc:
                errors.append({"subreddit": name, "listing": label, "error": f"{type(exc).__name__}:{str(exc)[:400]}"})
        print(json.dumps({"subreddit": name, "index": index, "total": len(subs), "unique_posts": len(records), "errors": len(errors)}), flush=True)

    ranked = sorted(records.values(), key=lambda r: (-r["base_score"], -r["num_comments"], -r["score"]))
    for row in ranked[:max(0, confirmations)]:
        try:
            bonus, total, matches, dimensions, meta = confirm_comments(row["post_id"])
            row["comment_confirmation"] = bonus
            row["comment_evidence"] = {"comments_seen": total, "matching_comments": matches, "matching_dimensions": dimensions}
            row["opportunity_score"] = round(min(100.0, row["base_score"] + bonus), 2)
            acquisition[str(meta.get("via") or "unknown")] += 1
            time.sleep(delay)
        except Exception as exc:
            row["comment_evidence"] = {"error": f"{type(exc).__name__}:{str(exc)[:400]}"}

    ranked = sorted(records.values(), key=lambda r: (-r["opportunity_score"], -r["num_comments"], -r["score"]))
    lane_stats = defaultdict(lambda: {"posts": 0, "qualified": 0, "score_sum": 0.0})
    clusters = defaultdict(list)
    for row in ranked:
        tags = signal_tags(row["dimensions"])
        row["signal_tags"] = tags
        for lane in row["lanes"]:
            stat = lane_stats[lane]
            stat["posts"] += 1
            stat["qualified"] += int(row["opportunity_score"] >= 35)
            stat["score_sum"] += row["opportunity_score"]
            clusters[(lane, "+".join(tags[:3]))].append(row)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "candidates.jsonl").open("w", encoding="utf-8") as fh:
        for row in ranked:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "top_candidates.json").write_text(json.dumps(ranked[:100], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cluster_rows = []
    for (lane, signature), rows in clusters.items():
        if len(rows) < 2:
            continue
        cluster_rows.append({
            "lane": lane, "signature": signature, "posts": len(rows),
            "avg_score": round(sum(r["opportunity_score"] for r in rows) / len(rows), 2),
            "subreddits": dict(Counter(r["subreddit"] for r in rows).most_common()),
            "top": [{"title": r["title"], "subreddit": r["subreddit"], "score": r["opportunity_score"], "url": r["url"]} for r in rows[:8]],
        })
    cluster_rows.sort(key=lambda x: (-x["avg_score"], -x["posts"]))
    (out / "clusters.json").write_text(json.dumps(cluster_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lane_summary = {}
    for lane, stat in lane_stats.items():
        lane_summary[lane] = {
            "posts": stat["posts"], "qualified_ge_35": stat["qualified"],
            "avg_score": round(stat["score_sum"] / max(stat["posts"], 1), 2),
        }
    summary = {
        "ok": bool(records), "started_at": started, "finished_at": utc_now(),
        "subreddits_requested": len(subs), "listings_per_subreddit": listings,
        "unique_posts": len(records), "comment_confirmations_requested": confirmations,
        "comment_confirmations_completed": sum(1 for r in ranked if "comment_evidence" in r and "error" not in r["comment_evidence"]),
        "qualified_ge_35": sum(1 for r in ranked if r["opportunity_score"] >= 35),
        "strong_ge_50": sum(1 for r in ranked if r["opportunity_score"] >= 50),
        "errors": errors, "acquisition": dict(acquisition), "lanes": lane_summary,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if records else 2

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/reddit-opportunity-universe.json")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-subs", type=int, default=0)
    ap.add_argument("--per-listing", type=int, default=30)
    ap.add_argument("--confirmations", type=int, default=60)
    ap.add_argument("--delay", type=float, default=0.05)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    raise SystemExit(scan(cfg, args.output_dir, args.max_subs, args.per_listing, args.confirmations, args.delay))


if __name__ == "__main__":
    main()
