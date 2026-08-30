from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
UTC = timezone.utc
RECOVERY_DAYS = 3
F33_AFTER_MIDNIGHT_GRACE_HOURS = 3


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_ts(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def source_ts(kind: str, obj: dict):
    return parse_ts(obj.get("captured_at" if kind == "trends" else "generated_at"))


def local_date(kind: str, obj: dict):
    # F33 may deliberately carry the intended Vietnam target date when a
    # scheduled/late-close crawl is delayed past midnight by GitHub Actions.
    if kind == "f33" and obj.get("vietnam_date"):
        return obj["vietnam_date"]
    ts = source_ts(kind, obj)
    return ts.astimezone(VN_TZ).date().isoformat() if ts else None


def sha256_obj(obj) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def usable_snapshot(kind: str, obj) -> bool:
    if not isinstance(obj, dict):
        return False
    if obj.get("status") == "RUNNING":
        return False
    if kind in {"f33", "forum"} and not int(obj.get("artifact_id") or 0):
        return False
    return source_ts(kind, obj) is not None


def snapshot_belongs_to_day(kind: str, obj, day: str) -> bool:
    if not usable_snapshot(kind, obj) or local_date(kind, obj) != day:
        return False
    if kind != "f33":
        return True

    ts = source_ts(kind, obj)
    local_ts = ts.astimezone(VN_TZ) if ts else None
    if not local_ts:
        return False
    target = date.fromisoformat(day)
    if local_ts.date() == target:
        return True
    # F33 may finish shortly after midnight if GitHub delays a close crawl,
    # but never let an arbitrarily late next-day run rewrite yesterday.
    if local_ts.date() == target + timedelta(days=1):
        return local_ts.hour < F33_AFTER_MIDNIGHT_GRACE_HOURS
    return False


def git_versions_for_day(path: str, day: str):
    """Yield historical versions of a pointer near a Vietnam calendar day.

    History freezing must not depend on a workflow running before midnight.
    GitHub scheduled jobs can be delayed by hours, so recover the latest valid
    pointer version whose semantic Vietnam date matches the requested day.
    """
    target = date.fromisoformat(day)
    start_local = datetime.combine(target, datetime.min.time(), tzinfo=VN_TZ)
    # Include the following day because a delayed scheduled F33 close may finish
    # shortly after midnight while still carrying target_date=day.
    since = (start_local - timedelta(hours=6)).astimezone(UTC).isoformat()
    until = (start_local + timedelta(days=2, hours=6)).astimezone(UTC).isoformat()
    proc = subprocess.run(
        [
            "git", "log", "--format=%H", f"--since={since}", f"--until={until}",
            "--", path,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return
    for commit in (line.strip() for line in proc.stdout.splitlines() if line.strip()):
        shown = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if shown.returncode != 0:
            continue
        try:
            obj = json.loads(shown.stdout)
        except json.JSONDecodeError:
            continue
        yield obj


def archive_latest(kind: str, latest_name: str, history_dir: str):
    obj = load(ROOT / latest_name)
    if not usable_snapshot(kind, obj):
        return None
    day = local_date(kind, obj)
    ts = source_ts(kind, obj)
    if not day or not ts or not snapshot_belongs_to_day(kind, obj, day):
        return None

    out = dict(obj)
    out["vietnam_date"] = day
    dest = ROOT / history_dir / f"{day}.json"
    previous = load(dest)
    if isinstance(previous, dict):
        prev_ts = source_ts(kind, previous)
        if prev_ts and prev_ts > ts:
            return day
    dump(dest, out)
    return day


def recover_best_for_day(kind: str, latest_name: str, history_dir: str, day: str):
    """Freeze the newest usable snapshot semantically belonging to `day`.

    Sources are recovered from both the checked-out current pointer and its git
    history. This is the actual implementation of the manifest selection policy
    `latest_completed_snapshot_whose_local_date_equals_target_date`.
    """
    candidates = []
    current = load(ROOT / latest_name)
    if snapshot_belongs_to_day(kind, current, day):
        candidates.append(current)
    for obj in git_versions_for_day(latest_name, day):
        if snapshot_belongs_to_day(kind, obj, day):
            candidates.append(obj)

    if not candidates:
        return False

    best = max(candidates, key=lambda obj: source_ts(kind, obj))
    dest = ROOT / history_dir / f"{day}.json"
    previous = load(dest)
    prev_ts = source_ts(kind, previous) if isinstance(previous, dict) else None
    best_ts = source_ts(kind, best)
    if prev_ts and best_ts and prev_ts > best_ts and snapshot_belongs_to_day(kind, previous, day):
        return False

    out = dict(best)
    out["vietnam_date"] = day
    if previous == out:
        return False
    dump(dest, out)
    return True


def valid_trends(obj):
    reasons = []
    if not isinstance(obj, dict):
        return False, ["trends_history_missing"]
    if obj.get("status") != "HEALTHY":
        reasons.append("trends_not_healthy")
    if len(obj.get("top10_rows") or []) != 10:
        reasons.append("trends_top10_not_exactly_10")
    return not reasons, reasons


def valid_f33(obj):
    reasons = []
    if not isinstance(obj, dict):
        return False, ["f33_history_missing"]
    if obj.get("status") != "HEALTHY":
        reasons.append("f33_not_healthy")
    expected = obj.get("expected_pages_total")
    fetched = obj.get("fetched_pages_total")
    if not expected or fetched != expected:
        reasons.append("f33_pages_incomplete")
    if obj.get("missing_pages_total") != 0:
        reasons.append("f33_missing_pages")
    if int(obj.get("threads_discovered") or 0) <= 0:
        reasons.append("f33_no_threads")
    if int(obj.get("artifact_id") or 0) <= 0:
        reasons.append("f33_artifact_missing")
    return not reasons, reasons


def valid_forum(obj):
    reasons = []
    if not isinstance(obj, dict):
        return False, ["forum_history_missing"]
    if obj.get("status") not in {"HEALTHY", "DEGRADED"}:
        reasons.append("forum_not_usable")
    if obj.get("crawl_outcome") == "failed":
        reasons.append("forum_crawl_failed")
    if int(obj.get("artifact_id") or 0) <= 0:
        reasons.append("forum_artifact_missing")
    return not reasons, reasons


def local_time(kind: str, obj):
    if not isinstance(obj, dict):
        return None
    ts = source_ts(kind, obj)
    return ts.astimezone(VN_TZ) if ts else None


def f33_close_time_ok(day: str, obj, local_ts) -> bool:
    if not isinstance(obj, dict) or not local_ts or not snapshot_belongs_to_day("f33", obj, day):
        return False
    target = date.fromisoformat(day)
    if local_ts.date() == target:
        return local_ts.hour >= 19
    # A GitHub schedule delayed past midnight can still be the intended close
    # crawl for the previous date. Keep the grace bounded to avoid day bleed.
    if local_ts.date() == target + timedelta(days=1):
        return local_ts.hour < F33_AFTER_MIDNIGHT_GRACE_HOURS
    return False


def build_manifest(day: str):
    trends_path = ROOT / "trends_vn_history" / f"{day}.json"
    f33_path = ROOT / "voz_f33_history" / f"{day}.json"
    forum_path = ROOT / "forum_signal_history" / f"{day}.json"

    trends = load(trends_path)
    f33 = load(f33_path)
    forum = load(forum_path)

    trends_ok, tr = valid_trends(trends)
    f33_ok, fr = valid_f33(f33)
    forum_ok, rr = valid_forum(forum)
    if isinstance(f33, dict) and not snapshot_belongs_to_day("f33", f33, day):
        f33_ok = False
        fr.append("f33_target_date_outside_grace")
    reasons = tr + fr + rr

    t_local = local_time("trends", trends)
    f_local = local_time("f33", f33)
    r_local = local_time("forum", forum)
    close_quality = bool(
        trends_ok and f33_ok and forum_ok
        and t_local and f_local and r_local
        and t_local.date().isoformat() == day
        and r_local.date().isoformat() == day
        and t_local.hour >= 20
        and f33_close_time_ok(day, f33, f_local)
        and r_local.hour >= 20
    )

    def input_rec(path: Path, obj, kind: str):
        if not isinstance(obj, dict):
            return {"path": str(path.relative_to(ROOT)), "present": False}
        rec = {
            "path": str(path.relative_to(ROOT)),
            "present": True,
            "sha256": sha256_obj(obj),
            "status": obj.get("status"),
            "vietnam_date": local_date(kind, obj),
        }
        if kind == "trends":
            rec.update({"captured_at": obj.get("captured_at"), "top10_count": len(obj.get("top10_rows") or [])})
        else:
            rec.update({
                "generated_at": obj.get("generated_at"),
                "run_id": obj.get("run_id"),
                "artifact_id": obj.get("artifact_id"),
            })
        if kind == "f33":
            rec.update({
                "threads_discovered": obj.get("threads_discovered"),
                "expected_pages_total": obj.get("expected_pages_total"),
                "fetched_pages_total": obj.get("fetched_pages_total"),
                "missing_pages_total": obj.get("missing_pages_total"),
                "posts_total": obj.get("posts_total"),
                "target_date_source": obj.get("target_date_source"),
            })
        if kind == "forum":
            rec.update({"posts_total": obj.get("posts_total"), "crawl_outcome": obj.get("crawl_outcome")})
        return rec

    manifest = {
        "schema_version": "1.1",
        "target_date": day,
        "timezone": "Asia/Ho_Chi_Minh",
        "selection_policy": "latest_completed_snapshot_whose_local_date_equals_target_date",
        "recovery_policy": "current_pointer_plus_git_history",
        "close_policy": {
            "trends_min_local_hour": 20,
            "f33_min_local_hour": 19,
            "f33_after_midnight_grace_hours": F33_AFTER_MIDNIGHT_GRACE_HOURS,
            "forum_min_local_hour": 20,
        },
        "status": "READY" if not reasons else "BLOCKED",
        "render_allowed": not reasons,
        "full_quality": not reasons,
        "close_quality": close_quality,
        "blocking_reasons": reasons,
        "inputs": {
            "trends": input_rec(trends_path, trends, "trends"),
            "f33": input_rec(f33_path, f33, "f33"),
            "forum_signal": input_rec(forum_path, forum, "forum"),
        },
    }
    dump(ROOT / "radar_vn_history" / f"{day}.json", manifest)


def main():
    affected = set()
    for kind, latest, hist in (
        ("trends", "trends_vn_latest.json", "trends_vn_history"),
        ("forum", "forum_signal_latest.json", "forum_signal_history"),
        ("f33", "voz_f33_latest.json", "voz_f33_history"),
    ):
        day = archive_latest(kind, latest, hist)
        if day:
            affected.add(day)

    now_vn = datetime.now(UTC).astimezone(VN_TZ)
    recovery_days = {
        (now_vn.date() - timedelta(days=offset)).isoformat()
        for offset in range(RECOVERY_DAYS)
    }
    requested = (os.environ.get("RADAR_VN_BACKFILL_DATE") or "").strip()
    if requested:
        # Fail fast on malformed manual backfill input.
        date.fromisoformat(requested)
        recovery_days.add(requested)

    for day in sorted(recovery_days):
        for kind, latest, hist in (
            ("trends", "trends_vn_latest.json", "trends_vn_history"),
            ("forum", "forum_signal_latest.json", "forum_signal_history"),
            ("f33", "voz_f33_latest.json", "voz_f33_history"),
        ):
            if recover_best_for_day(kind, latest, hist, day):
                affected.add(day)
        affected.add(day)

    for day in sorted(affected):
        build_manifest(day)


if __name__ == "__main__":
    main()
