#!/usr/bin/env python3

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path


F91_SOURCE = "VOZ-F91"
F91_DISCOVERY = [
    "https://voz.vn/f/lap-trinh-cntt.91/",
    "https://voz.vn/f/lap-trinh-cntt.91/page-2",
    "https://voz.vn/f/lap-trinh-cntt.91/page-3",
]
F91_EXTRA_PRIORITY = [
    "vibe code", "vibe coding", "llm", "agent", "agentic", "mcp", "api", "openrouter",
    "github", "backend", "frontend", "fullstack", "data", "data analyst", "data engineer",
    "qa", "tester", "automation test", "semiconductor", "vi mạch", "embedded", "firmware",
    "kubernetes", "docker", "aws", "azure", "gcp", "terraform", "sre", "platform engineer",
    "remote", "outsourcing", "outsource", "career", "offer", "deal lương", "nhảy việc",
    "fresher", "intern", "senior", "staff", "layoff", "sa thải", "thạc sĩ", "xuất ngoại",
]
F91_EXTRA_DEPRIORITIZE = [
    "leetcode mỗi ngày", "kết nối sâu - cộng sinh cùng ai", "nội quy box cntt", "chuyện trò linh tinh",
    "xin code", "bài tập", "nhờ vả", "có lộc cafe", "spam", "waifu", "meme",
]


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
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


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
    cmd = [
        sys.executable,
        "forum_signal_delta.py",
        str(job_path),
        "--output",
        str(output),
        "--state-file",
        str(state_file),
    ]
    subprocess.run(cmd, check=True)


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
    ap = argparse.ArgumentParser(description="Run Forum Signal with expanded VOZ F91 coverage")
    ap.add_argument("job_file")
    ap.add_argument("--output", default="crawl_output")
    ap.add_argument("--state-file", default=".forum-state/state.json")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    job = load_json(args.job_file)
    sources = job.get("sources") or []
    f91_sources = [s for s in sources if str(s.get("name")) == F91_SOURCE]
    if len(f91_sources) != 1:
        raise SystemExit(f"expected exactly one {F91_SOURCE} source, got {len(f91_sources)}")

    f91 = copy.deepcopy(f91_sources[0])
    f91["discovery_urls"] = F91_DISCOVERY
    f91["priority_keywords"] = uniq(list(f91.get("priority_keywords") or []) + F91_EXTRA_PRIORITY)
    f91["deprioritize_keywords"] = uniq(list(f91.get("deprioritize_keywords") or []) + F91_EXTRA_DEPRIORITIZE)

    main_job = copy.deepcopy(job)
    main_job["name"] = f"{job.get('name', 'forum-signal-vn')}-main"
    main_job["sources"] = [s for s in sources if str(s.get("name")) != F91_SOURCE]

    f91_job = copy.deepcopy(job)
    f91_job["name"] = f"{job.get('name', 'forum-signal-vn')}-f91-expanded"
    f91_job["probe_threads_per_source"] = 40
    f91_job["max_threads_per_source"] = 20
    f91_job["max_posts_per_thread"] = 20
    f91_job["min_probe_score"] = min(float(job.get("min_probe_score", 1.2)), 1.0)
    f91_job["min_final_score"] = float(job.get("min_final_score", 1.8))
    f91_job["sources"] = [f91]

    if args.validate_only:
        print(json.dumps({
            "runner": "forum_signal_f91_expand",
            "source": F91_SOURCE,
            "discovery_pages": len(F91_DISCOVERY),
            "probe_threads": f91_job["probe_threads_per_source"],
            "retain_threads": f91_job["max_threads_per_source"],
            "max_posts_per_thread": f91_job["max_posts_per_thread"],
            "validated": True,
        }, ensure_ascii=False))
        return

    out = Path(args.output)
    f91_out = out.parent / f"{out.name}_f91_expanded"
    tmp = out.parent / ".forum-f91-jobs"
    tmp.mkdir(parents=True, exist_ok=True)
    main_job_path = tmp / "main.json"
    f91_job_path = tmp / "f91.json"
    write_json(main_job_path, main_job)
    write_json(f91_job_path, f91_job)

    state_file = Path(args.state_file)
    f91_state = state_file.with_name(f"{state_file.stem}-f91{state_file.suffix}")

    try:
        run_delta(main_job_path, out, state_file)
        run_delta(f91_job_path, f91_out, f91_state)

        main_delta = load_jsonl(out / "forum_signal.jsonl")
        f91_delta = load_jsonl(f91_out / "forum_signal.jsonl")
        main_snapshot = load_jsonl(out / "forum_signal_snapshot.jsonl")
        f91_snapshot = load_jsonl(f91_out / "forum_signal_snapshot.jsonl")
        write_jsonl(out / "forum_signal.jsonl", main_delta + f91_delta)
        write_jsonl(out / "forum_signal_snapshot.jsonl", main_snapshot + f91_snapshot)

        main_manifest = load_json(out / "manifest.json")
        f91_manifest = load_json(f91_out / "manifest.json")
        f91_meta = (f91_manifest.get("sources") or [None])[0]
        if not f91_meta:
            raise RuntimeError("expanded F91 manifest has no source metadata")
        main_manifest["job_name"] = job.get("name", "forum-signal-vn")
        main_manifest["sources"] = list(main_manifest.get("sources") or []) + [f91_meta]
        main_manifest["f91_expanded"] = {
            "enabled": True,
            "discovery_urls": F91_DISCOVERY,
            "probe_threads_per_source": 40,
            "max_threads_per_source": 20,
            "max_posts_per_thread": 20,
            "delta_rows": len(f91_delta),
            "snapshot_rows": len(f91_snapshot),
        }
        recalc_manifest(main_manifest, out)
        write_json(out / "manifest.json", main_manifest)
        write_json(out / "forum_f91_expanded_manifest.json", f91_manifest)

        candidates = f91_out / "forum_candidates.json"
        if candidates.exists():
            shutil.copy2(candidates, out / "forum_candidates_f91_expanded.json")

        print(json.dumps({
            "runner": "forum_signal_f91_expand",
            "main_delta_rows": len(main_delta),
            "f91_delta_rows": len(f91_delta),
            "f91_snapshot_rows": len(f91_snapshot),
            "f91_threads_probed": f91_meta.get("threads_probed"),
            "f91_threads_selected": f91_meta.get("threads_selected"),
            "f91_structured_posts": f91_meta.get("structured_posts"),
            "output": str(out),
        }, ensure_ascii=False))
    finally:
        shutil.rmtree(f91_out, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
