#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def age_minutes(value, now):
    dt = parse_dt(value)
    if not dt:
        return None
    return round((now - dt).total_seconds() / 60, 1)


def load(path):
    p = Path(path)
    if not p.exists():
        return None, f"missing:{path}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, f"invalid_json:{path}:{exc}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trends", default="trends_vn_latest.json")
    ap.add_argument("--f33", default="voz_f33_latest.json")
    ap.add_argument("--forum", default="forum_signal_latest.json")
    ap.add_argument("--output", default="radar_vn_inputs_latest.json")
    ap.add_argument("--trends-max-age-min", type=float, default=240)
    ap.add_argument("--f33-max-age-min", type=float, default=480)
    ap.add_argument("--forum-max-age-min", type=float, default=360)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    blocking = []

    trends, err = load(args.trends)
    t_age = age_minutes((trends or {}).get("captured_at"), now)
    t_rows = len((trends or {}).get("top10_rows") or [])
    t_ok = bool(
        not err
        and (trends or {}).get("status") == "HEALTHY"
        and t_rows == 10
        and t_age is not None
        and 0 <= t_age <= args.trends_max_age_min
    )
    if not t_ok:
        blocking.append("trends_not_healthy_fresh_top10")

    f33, err = load(args.f33)
    f_age = age_minutes((f33 or {}).get("generated_at"), now)
    f_expected = (f33 or {}).get("expected_pages_total")
    f_fetched = (f33 or {}).get("fetched_pages_total")
    f_ok = bool(
        not err
        and (f33 or {}).get("status") == "HEALTHY"
        and int((f33 or {}).get("artifact_id") or 0) > 0
        and int((f33 or {}).get("missing_pages_total") or 0) == 0
        and int((f33 or {}).get("threads_degraded") or 0) == 0
        and int((f33 or {}).get("threads_failed") or 0) == 0
        and f_expected is not None
        and f_fetched == f_expected
        and f_age is not None
        and 0 <= f_age <= args.f33_max_age_min
    )
    if not f_ok:
        blocking.append("f33_not_full_healthy_fresh")

    forum, err = load(args.forum)
    forum_age = age_minutes((forum or {}).get("generated_at"), now)
    forum_status = (forum or {}).get("status")
    forum_ok = bool(
        not err
        and forum_status in {"HEALTHY", "DEGRADED"}
        and (forum or {}).get("crawl_outcome") == "success"
        and int((forum or {}).get("artifact_id") or 0) > 0
        and forum_age is not None
        and 0 <= forum_age <= args.forum_max_age_min
    )
    if not forum_ok:
        blocking.append("forum_signal_not_usable_fresh")

    render_allowed = t_ok and f_ok and forum_ok
    payload = {
        "generated_at": now.isoformat(),
        "status": "READY" if render_allowed else "BLOCKED",
        "render_allowed": render_allowed,
        "full_quality": bool(render_allowed and forum_status == "HEALTHY"),
        "blocking_reasons": blocking,
        "inputs": {
            "trends": {
                "path": args.trends,
                "ok": t_ok,
                "status": (trends or {}).get("status"),
                "captured_at": (trends or {}).get("captured_at"),
                "age_minutes": t_age,
                "top10_count": t_rows,
            },
            "f33": {
                "path": args.f33,
                "ok": f_ok,
                "status": (f33 or {}).get("status"),
                "generated_at": (f33 or {}).get("generated_at"),
                "age_minutes": f_age,
                "run_id": (f33 or {}).get("run_id"),
                "artifact_id": (f33 or {}).get("artifact_id"),
                "threads_discovered": (f33 or {}).get("threads_discovered"),
                "expected_pages_total": f_expected,
                "fetched_pages_total": f_fetched,
                "missing_pages_total": (f33 or {}).get("missing_pages_total"),
                "posts_total": (f33 or {}).get("posts_total"),
            },
            "forum_signal": {
                "path": args.forum,
                "ok": forum_ok,
                "status": forum_status,
                "generated_at": (forum or {}).get("generated_at"),
                "age_minutes": forum_age,
                "run_id": (forum or {}).get("run_id"),
                "artifact_id": (forum or {}).get("artifact_id"),
                "crawl_outcome": (forum or {}).get("crawl_outcome"),
            },
        },
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(0 if render_allowed else 2)


if __name__ == "__main__":
    main()
