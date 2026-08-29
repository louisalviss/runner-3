from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


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
    if kind == "f33" and obj.get("vietnam_date"):
        return obj["vietnam_date"]
    ts = source_ts(kind, obj)
    return ts.astimezone(VN_TZ).date().isoformat() if ts else None


def sha256_obj(obj) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def archive_latest(kind: str, latest_name: str, history_dir: str):
    obj = load(ROOT / latest_name)
    if not isinstance(obj, dict):
        return None
    if obj.get("status") == "RUNNING":
        return None
    if kind in {"f33", "forum"} and not int(obj.get("artifact_id") or 0):
        return None
    day = local_date(kind, obj)
    ts = source_ts(kind, obj)
    if not day or not ts:
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
    reasons = tr + fr + rr

    t_local = local_time("trends", trends)
    f_local = local_time("f33", f33)
    r_local = local_time("forum", forum)
    close_quality = bool(
        trends_ok and f33_ok and forum_ok
        and t_local and f_local and r_local
        and t_local.date().isoformat() == day
        and f_local.date().isoformat() == day
        and r_local.date().isoformat() == day
        and t_local.hour >= 20
        and f_local.hour >= 19
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
            })
        if kind == "forum":
            rec.update({"posts_total": obj.get("posts_total"), "crawl_outcome": obj.get("crawl_outcome")})
        return rec

    manifest = {
        "schema_version": "1.0",
        "target_date": day,
        "timezone": "Asia/Ho_Chi_Minh",
        "selection_policy": "latest_completed_snapshot_whose_local_date_equals_target_date",
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

    now_vn = datetime.now(timezone.utc).astimezone(VN_TZ)
    affected.add(now_vn.date().isoformat())
    affected.add((now_vn.date() - timedelta(days=1)).isoformat())

    for day in sorted(affected):
        build_manifest(day)


if __name__ == "__main__":
    main()
