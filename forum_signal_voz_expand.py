#!/usr/bin/env python3

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROFILES = {
    "VOZ-F91": {
        "slug": "f91",
        "discovery_urls": [
            "https://voz.vn/f/lap-trinh-cntt.91/",
            "https://voz.vn/f/lap-trinh-cntt.91/page-2",
            "https://voz.vn/f/lap-trinh-cntt.91/page-3",
        ],
        "probe_threads": 40,
        "retain_threads": 20,
        "max_posts": 20,
        "extra_priority": [
            "vibe code", "vibe coding", "llm", "agent", "agentic", "mcp", "api", "openrouter",
            "github", "backend", "frontend", "fullstack", "data", "data analyst", "data engineer",
            "qa", "tester", "automation test", "semiconductor", "vi mạch", "embedded", "firmware",
            "kubernetes", "docker", "aws", "azure", "gcp", "terraform", "sre", "platform engineer",
            "remote", "outsourcing", "outsource", "career", "offer", "deal lương", "nhảy việc",
            "fresher", "intern", "senior", "staff", "layoff", "sa thải", "thạc sĩ", "xuất ngoại",
        ],
        "extra_deprioritize": [
            "leetcode mỗi ngày", "kết nối sâu - cộng sinh cùng ai", "nội quy box cntt", "chuyện trò linh tinh",
            "xin code", "bài tập", "nhờ vả", "có lộc cafe", "spam", "waifu", "meme",
        ],
    },
    "VOZ-F93-MMO": {
        "slug": "f93",
        "discovery_urls": [
            "https://voz.vn/f/make-money-online.93/",
            "https://voz.vn/f/make-money-online.93/page-2",
            "https://voz.vn/f/make-money-online.93/page-3",
        ],
        "probe_threads": 40,
        "retain_threads": 20,
        "max_posts": 20,
        "extra_priority": [
            "affiliate marketing", "seo", "traffic", "organic", "keyword", "rank", "content",
            "google ads", "facebook ads", "meta ads", "tiktok ads", "adsense", "cpm", "cpc", "cpa", "cpl", "roas",
            "conversion", "landing page", "lead", "offer", "vertical", "domain", "hosting", "email",
            "youtube", "tiktok", "facebook", "x", "shopify", "amazon", "etsy", "kdp",
            "multi account", "nhiều acc", "account", "checkpoint", "limit", "ban", "die acc",
            "paypal", "payoneer", "wise", "stripe", "payment", "payout", "refund", "chargeback",
            "automation", "workflow", "crawler", "scrape", "ai", "agent", "tool", "api",
            "case study", "doanh thu", "revenue", "lợi nhuận", "profit", "chi phí", "cost", "margin",
            "kinh nghiệm", "thực tế", "test", "a/b", "scale", "scaling",
        ],
        "extra_deprioritize": [
            "airdrop", "coin", "token", "ref link", "mã giới thiệu", "official thread", "khóa học", "khoá học",
            "trọn bộ mmo", "telegram", "zalo", "đăng ký ngay", "tham gia nhóm", "giveaway", "voucher",
            "khuyến mãi", "giảm giá", "kèo chắc ăn", "đào free", "spam",
        ],
    },
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def uniq(values):
    seen = set()
    out = []
    for value in values:
        key = str(value).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def run_delta(job_path, output, state_file):
    subprocess.run([
        sys.executable,
        "forum_signal_delta.py",
        str(job_path),
        "--output",
        str(output),
        "--state-file",
        str(state_file),
    ], check=True)


def build_expanded_job(job, source, profile):
    src = copy.deepcopy(source)
    src["discovery_urls"] = profile["discovery_urls"]
    src["priority_keywords"] = uniq(list(src.get("priority_keywords") or []) + profile["extra_priority"])
    src["deprioritize_keywords"] = uniq(list(src.get("deprioritize_keywords") or []) + profile["extra_deprioritize"])

    expanded = copy.deepcopy(job)
    expanded["name"] = f"{job.get('name', 'forum-signal-vn')}-{profile['slug']}-expanded"
    expanded["probe_threads_per_source"] = profile["probe_threads"]
    expanded["max_threads_per_source"] = profile["retain_threads"]
    expanded["max_posts_per_thread"] = profile["max_posts"]
    expanded["min_probe_score"] = min(float(job.get("min_probe_score", 1.2)), 1.0)
    expanded["min_final_score"] = float(job.get("min_final_score", 1.8))
    expanded["sources"] = [src]
    return expanded


def recalc_manifest(manifest, output_dir):
    rows = load_jsonl(Path(output_dir) / "forum_signal.jsonl")
    snapshots = load_jsonl(Path(output_dir) / "forum_signal_snapshot.jsonl")
    sources = manifest.get("sources") or []
    manifest["total_rows"] = len(rows)
    manifest["snapshot_rows"] = len(snapshots)
    manifest["delta_rows"] = len(rows)
    manifest["total_structured_posts"] = sum(int(s.get("structured_posts") or 0) for s in sources)
    manifest["total_fallback_pages"] = sum(int(s.get("fallback_pages") or 0) for s in sources)
    manifest["total_threads_probed"] = sum(int(s.get("threads_probed") or 0) for s in sources)
    manifest["total_threads_selected"] = sum(int(s.get("threads_selected") or 0) for s in sources)
    return manifest


def main():
    ap = argparse.ArgumentParser(description="Run Forum Signal with consolidated expanded VOZ source coverage")
    ap.add_argument("job_file")
    ap.add_argument("--output", default="crawl_output")
    ap.add_argument("--state-file", default=".forum-state/state.json")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    job = load_json(args.job_file)
    sources = job.get("sources") or []
    source_map = {str(s.get("name")): s for s in sources}
    missing = [name for name in PROFILES if name not in source_map]
    if missing:
        raise SystemExit(f"expanded VOZ source(s) missing from job: {missing}")

    expanded_jobs = {
        name: build_expanded_job(job, source_map[name], profile)
        for name, profile in PROFILES.items()
    }

    if args.validate_only:
        print(json.dumps({
            "runner": "forum_signal_voz_expand",
            "profiles": {
                name: {
                    "discovery_pages": len(PROFILES[name]["discovery_urls"]),
                    "probe_threads": PROFILES[name]["probe_threads"],
                    "retain_threads": PROFILES[name]["retain_threads"],
                    "max_posts_per_thread": PROFILES[name]["max_posts"],
                }
                for name in PROFILES
            },
            "validated": True,
        }, ensure_ascii=False))
        return

    out = Path(args.output)
    tmp = out.parent / ".forum-voz-expand-jobs"
    tmp.mkdir(parents=True, exist_ok=True)

    main_job = copy.deepcopy(job)
    main_job["name"] = f"{job.get('name', 'forum-signal-vn')}-main"
    main_job["sources"] = [s for s in sources if str(s.get("name")) not in PROFILES]
    main_job_path = tmp / "main.json"
    write_json(main_job_path, main_job)

    state_file = Path(args.state_file)
    outputs = {}
    try:
        run_delta(main_job_path, out, state_file)

        for name, profile in PROFILES.items():
            slug = profile["slug"]
            special_out = out.parent / f"{out.name}_{slug}_expanded"
            special_job_path = tmp / f"{slug}.json"
            special_state = state_file.with_name(f"{state_file.stem}-{slug}{state_file.suffix}")
            write_json(special_job_path, expanded_jobs[name])
            run_delta(special_job_path, special_out, special_state)
            outputs[name] = special_out

        merged_delta = load_jsonl(out / "forum_signal.jsonl")
        merged_snapshot = load_jsonl(out / "forum_signal_snapshot.jsonl")
        main_manifest = load_json(out / "manifest.json")
        merged_sources = list(main_manifest.get("sources") or [])
        expansion_meta = {}

        for name, special_out in outputs.items():
            profile = PROFILES[name]
            special_delta = load_jsonl(special_out / "forum_signal.jsonl")
            special_snapshot = load_jsonl(special_out / "forum_signal_snapshot.jsonl")
            special_manifest = load_json(special_out / "manifest.json")
            source_meta = (special_manifest.get("sources") or [None])[0]
            if not source_meta:
                raise RuntimeError(f"expanded {name} manifest has no source metadata")

            merged_delta.extend(special_delta)
            merged_snapshot.extend(special_snapshot)
            merged_sources.append(source_meta)
            expansion_meta[profile["slug"]] = {
                "enabled": True,
                "source": name,
                "discovery_urls": profile["discovery_urls"],
                "probe_threads_per_source": profile["probe_threads"],
                "max_threads_per_source": profile["retain_threads"],
                "max_posts_per_thread": profile["max_posts"],
                "delta_rows": len(special_delta),
                "snapshot_rows": len(special_snapshot),
            }
            write_json(out / f"forum_{profile['slug']}_expanded_manifest.json", special_manifest)
            candidates = special_out / "forum_candidates.json"
            if candidates.exists():
                shutil.copy2(candidates, out / f"forum_candidates_{profile['slug']}_expanded.json")

        write_jsonl(out / "forum_signal.jsonl", merged_delta)
        write_jsonl(out / "forum_signal_snapshot.jsonl", merged_snapshot)

        main_manifest["job_name"] = job.get("name", "forum-signal-vn")
        main_manifest["sources"] = merged_sources
        for slug, meta in expansion_meta.items():
            main_manifest[f"{slug}_expanded"] = meta
        recalc_manifest(main_manifest, out)
        write_json(out / "manifest.json", main_manifest)

        print(json.dumps({
            "runner": "forum_signal_voz_expand",
            "expanded": {
                name: {
                    "snapshot_rows": expansion_meta[PROFILES[name]["slug"]]["snapshot_rows"],
                    "delta_rows": expansion_meta[PROFILES[name]["slug"]]["delta_rows"],
                    "threads_probed": next((s.get("threads_probed") for s in merged_sources if s.get("source") == name), None),
                    "threads_selected": next((s.get("threads_selected") for s in merged_sources if s.get("source") == name), None),
                    "structured_posts": next((s.get("structured_posts") for s in merged_sources if s.get("source") == name), None),
                }
                for name in PROFILES
            },
            "output": str(out),
        }, ensure_ascii=False))
    finally:
        for special_out in outputs.values():
            shutil.rmtree(special_out, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
