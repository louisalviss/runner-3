#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path

import crawler as base
from crawler_aiua import AI_UA_PROFILES, MIN_USABLE_TEXT_CHARS


def summarize(profile, rec):
    html = rec.get("html") or ""
    text = rec.get("text") or ""
    return {
        "profile": profile,
        "status": rec.get("status"),
        "final_url": rec.get("final_url"),
        "title": rec.get("title"),
        "content_type": rec.get("content_type"),
        "text_chars": len(text),
        "html_bytes": len(html.encode("utf-8", errors="ignore")),
        "text_sha256": hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest(),
        "html_sha256": hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest(),
        "blocked_or_challenge": base.looks_blocked(
            rec.get("status"), html, text
        ),
        "too_thin": len(text) < MIN_USABLE_TEXT_CHARS,
        "elapsed_seconds": rec.get("elapsed_seconds"),
        "text_head": text[:800],
    }


def fetch_profile(url, timeout, profile, ua):
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    return base.http_fetch(url, timeout, headers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_file")
    ap.add_argument("--output", default="ai_ua_matrix.json")
    args = ap.parse_args()

    job = json.loads(Path(args.job_file).read_text(encoding="utf-8"))
    base.validate_job(job)
    timeout = int(job.get("timeout_seconds", 25))
    normal_ua = str(job.get("user_agent", base.DEFAULT_UA))
    profiles = [("normal", normal_ua), *AI_UA_PROFILES]

    rows = []
    for url in job["urls"]:
        item = {"url": url, "profiles": []}
        for profile, ua in profiles:
            try:
                rec = fetch_profile(url, timeout, profile, ua)
                item["profiles"].append(summarize(profile, rec))
            except Exception as exc:
                item["profiles"].append({
                    "profile": profile,
                    "error": f"{type(exc).__name__}: {exc}",
                })
        rows.append(item)

    out = {
        "job_name": job.get("name") or Path(args.job_file).stem,
        "purpose": "compare identical public URLs across normal and AI/search crawler User-Agent profiles",
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"urls": len(rows), "profiles_per_url": len(profiles)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
