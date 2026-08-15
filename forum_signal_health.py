#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return {} if default is None else default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Health gate for forum signal crawl")
    ap.add_argument("--manifest", default="crawl_output/manifest.json")
    ap.add_argument("--job", default="forum-jobs/forum-signal-vn.json")
    ap.add_argument("--state", default=".forum-state/health-baseline.json")
    ap.add_argument("--output", default="crawl_output/forum_health.json")
    ap.add_argument("--summary", default="crawl_output/forum_health.md")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    job = load_json(args.job)
    sources_cfg = job.get("sources") or []
    if not sources_cfg:
        raise SystemExit("job has no sources")
    expected_discovery = {
        str(s.get("name")): max(1, len(s.get("discovery_urls") or []))
        for s in sources_cfg
        if s.get("name")
    }
    if args.validate_only:
        print(json.dumps({"health_gate": "forum-signal-health-v1", "sources": len(expected_discovery), "validated": True}))
        return

    manifest = load_json(args.manifest)
    rows = manifest.get("sources") or []
    previous = load_json(args.state, default={})
    prev_sources = previous.get("sources") or {}

    source_health = []
    failed = 0
    degraded = 0
    total_structured = 0

    for row in rows:
        name = str(row.get("source") or "unknown")
        expected = expected_discovery.get(name, 1)
        discovery_ok = int(row.get("discovery_ok") or 0)
        links = int(row.get("discovered_thread_links") or 0)
        probed = int(row.get("threads_probed") or 0)
        selected = int(row.get("threads_selected") or 0)
        structured = int(row.get("structured_posts") or 0)
        fallback = int(row.get("fallback_pages") or 0)
        errors = row.get("errors") or []
        total_structured += structured

        status = "HEALTHY"
        reasons = []

        if discovery_ok <= 0 or probed <= 0:
            status = "FAILED"
            reasons.append("discovery_or_probe_failed")
        elif discovery_ok < expected:
            status = "DEGRADED"
            reasons.append(f"partial_discovery:{discovery_ok}/{expected}")

        if links < 3:
            if status == "HEALTHY":
                status = "DEGRADED"
            reasons.append(f"low_discovery_links:{links}")

        if selected > 0 and structured < max(2, selected * 2):
            if structured == 0:
                status = "FAILED"
            elif status == "HEALTHY":
                status = "DEGRADED"
            reasons.append(f"low_structured_posts:{structured}")

        if fallback > 0 and fallback >= max(2, structured):
            if status == "HEALTHY":
                status = "DEGRADED"
            reasons.append(f"fallback_dominant:{fallback}")

        prev = prev_sources.get(name) or {}
        prev_structured = int(prev.get("structured_posts") or 0)
        if prev_structured >= 8 and structured < max(2, int(prev_structured * 0.25)):
            if structured == 0:
                status = "FAILED"
            elif status == "HEALTHY":
                status = "DEGRADED"
            reasons.append(f"sudden_structured_drop:{structured}/{prev_structured}")

        if errors:
            if status == "HEALTHY":
                status = "DEGRADED"
            reasons.append(f"errors:{len(errors)}")

        if status == "FAILED":
            failed += 1
        elif status == "DEGRADED":
            degraded += 1

        source_health.append({
            "source": name,
            "status": status,
            "reasons": reasons,
            "expected_discovery": expected,
            "discovery_ok": discovery_ok,
            "discovered_thread_links": links,
            "threads_probed": probed,
            "threads_selected": selected,
            "structured_posts": structured,
            "fallback_pages": fallback,
            "errors": errors,
            "previous_structured_posts": prev_structured if prev_structured else None,
        })

    configured = len(expected_discovery)
    observed_names = {x["source"] for x in source_health}
    missing = sorted(set(expected_discovery) - observed_names)
    for name in missing:
        failed += 1
        source_health.append({
            "source": name,
            "status": "FAILED",
            "reasons": ["missing_from_manifest"],
            "expected_discovery": expected_discovery[name],
            "discovery_ok": 0,
            "discovered_thread_links": 0,
            "threads_probed": 0,
            "threads_selected": 0,
            "structured_posts": 0,
            "fallback_pages": 0,
            "errors": [],
            "previous_structured_posts": (prev_sources.get(name) or {}).get("structured_posts"),
        })

    fail_threshold = max(2, (configured + 1) // 2)
    if failed >= fail_threshold or total_structured < 20:
        overall = "FAILED"
    elif failed > 0 or degraded > 0:
        overall = "DEGRADED"
    else:
        overall = "HEALTHY"

    result = {
        "health_gate": "forum-signal-health-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "configured_sources": configured,
        "failed_sources": failed,
        "degraded_sources": degraded,
        "total_structured_posts": total_structured,
        "sources": source_health,
    }
    write_json(args.output, result)

    # Keep last known usable baseline per source; failed observations do not erase it.
    next_baseline = {"updated_at": result["checked_at"], "sources": dict(prev_sources)}
    for s in source_health:
        if s["status"] != "FAILED" and s["structured_posts"] > 0:
            next_baseline["sources"][s["source"]] = {
                "structured_posts": s["structured_posts"],
                "discovered_thread_links": s["discovered_thread_links"],
            }
    write_json(args.state, next_baseline)

    md = [
        "# Forum Signal Health",
        "",
        f"Overall: **{overall}**",
        f"Sources: {configured} | failed: {failed} | degraded: {degraded}",
        f"Structured posts: {total_structured}",
        "",
    ]
    for s in source_health:
        reason = ", ".join(s["reasons"]) if s["reasons"] else "ok"
        md.append(f"- **{s['source']}** — {s['status']} — structured={s['structured_posts']} discovery={s['discovery_ok']}/{s['expected_discovery']} — {reason}")
    Path(args.summary).write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "health_gate": "forum-signal-health-v1",
        "overall_status": overall,
        "failed_sources": failed,
        "degraded_sources": degraded,
        "total_structured_posts": total_structured,
        "output": args.output,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
