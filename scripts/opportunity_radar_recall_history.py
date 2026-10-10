#!/usr/bin/env python3
"""Point-in-time archived MARKET_PRICING recall diagnostic (read-only).

Uses git-committed prefilter + health + signals. A historical COMPLETE label
alone is insufficient: require SHA, matching sessions and every symbol's
actual completed US price date. Strictly no backdated discovery, orders,
portfolio/D1/Sheet writes, or inference about out-of-universe securities.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import Counter
from pathlib import Path

PREFILTER = "data/opportunity-radar/market-prefilter.json"
HEALTH = "data/opportunity-radar/market-health.json"
SIGNALS = "data/opportunity-radar/market-signals.json"
OUT = Path("data/opportunity-radar/market-recall-cross-session-diagnostic.json")
QUOTAS = {"PUMP": 28, "SHOCK": 28, "SECTOR": 16, "EARLY": 8}
MAX_PACKET = 80
PROTECTED_PUMP_BUDGET = 24


def git(*args: str) -> bytes:
    p = subprocess.run(["git", *args], capture_output=True, timeout=45)
    if p.returncode:
        raise RuntimeError(f"git {args[0]} failed: {p.stderr[-160:].decode(errors='replace')}")
    return p.stdout


def read_packet(sha: str) -> tuple[dict, dict, dict, bytes]:
    health = json.loads(git("show", f"{sha}:{HEALTH}"))
    raw_prefilter = git("show", f"{sha}:{PREFILTER}")
    prefilter = json.loads(raw_prefilter)
    signals = json.loads(git("show", f"{sha}:{SIGNALS}"))
    return health, prefilter, signals, raw_prefilter


def number(v) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def triggers(r: dict) -> list[str]:
    if r.get("corporate_action_suspected") or r.get("corporate_action_unverified"):
        return []
    d1, d5 = number(r.get("ret_1d_pct")), number(r.get("ret_5d_pct"))
    t = []
    if d1 is not None and d1 >= 7: t.append("1D_PUMP")
    if d5 is not None and d5 >= 15: t.append("5D_PUMP")
    if d1 is not None and d1 <= -7: t.append("1D_SHOCK")
    if d5 is not None and d5 <= -15: t.append("5D_SHOCK")
    return t


def group(r: dict, t: list[str]) -> str | None:
    if r.get("corporate_action_suspected") or r.get("corporate_action_unverified"):
        return None
    up, down = any(x.endswith("PUMP") for x in t), any(x.endswith("SHOCK") for x in t)
    if up and down: return "PUMP" if (number(r.get("ret_1d_pct")) or 0) >= 0 else "SHOCK"
    if up: return "PUMP"
    if down: return "SHOCK"
    rel = number(r.get("sector_relative_5d_pct"))
    if rel is not None and rel <= -10: return "SECTOR"
    d1, vr = number(r.get("ret_1d_pct")), number(r.get("volume_ratio"))
    if d1 is not None and abs(d1) >= 3 and vr is not None and vr >= 2: return "EARLY"
    return None


def priority(r: dict, cls: str):
    a = abs(number(r.get("ret_1d_pct")) or 0)
    b = abs(number(r.get("ret_5d_pct")) or 0)
    v = number(r.get("volume_ratio")) or 0
    dv = number(r.get("avg_dollar_volume_20d")) or 0
    severity = abs(number(r.get("sector_relative_5d_pct")) or 0) / 10 if cls == "SECTOR" else max(a / 7, b / 15)
    return (severity, min(v, 10), math.log10(max(dv, 1)), str(r.get("symbol")))


def verify(h: dict, p: dict, s: dict, raw: bytes) -> list[str]:
    errs = []
    date = h.get("source_session_date")
    rows, sigs = p.get("records") or [], s.get("signals") or []
    if any(x.get("status") != "COMPLETE" or x.get("complete") is not True for x in (h, p, s)):
        errs.append("NOT_COMPLETE")
    if not date or any(x.get("source_session_date") != date for x in (p, s)):
        errs.append("SESSION_MISMATCH")
    if h.get("prefilter_sha256") != hashlib.sha256(raw).hexdigest():
        errs.append("PREFILTER_SHA_MISMATCH")
    if h.get("prefilter_count") != len(rows) or h.get("signal_count") != len(sigs):
        errs.append("PACKET_COUNT_MISMATCH")
    if h.get("history_requested") and len(rows) / h["history_requested"] < 0.8:
        errs.append("INSUFFICIENT_FRESH_COVERAGE")
    if any(r.get("last_date") != date for r in rows):
        errs.append("PREFILTER_SYMBOL_SESSION_STALE")
    if any((q.get("source") or {}).get("last_date") != date for q in sigs):
        errs.append("SIGNAL_SYMBOL_SESSION_STALE")
    syms = [str(r.get("symbol") or "") for r in rows]
    sel = [str(q.get("affected_assets") or "") for q in sigs]
    if len(syms) != len(set(syms)) or len(sel) != len(set(sel)) or not set(sel).issubset(set(syms)):
        errs.append("SYMBOL_IDENTITY_MISMATCH")
    return errs


def assess(h: dict, p: dict, s: dict, commit: str) -> dict:
    rows = p["records"]
    sigs = s["signals"]
    by = {r["symbol"]: r for r in rows}
    baseline_list = [q["affected_assets"] for q in sigs]
    baseline = set(baseline_list)
    old_early = {
        q["affected_assets"] for q in sigs
        if (q.get("source") or {}).get("discovery_state") == "EARLY_WATCH"
    }
    rt = {k: triggers(r) for k, r in by.items()}
    classes = {k: group(by[k], v) for k, v in rt.items()}
    groups = {k: [] for k in QUOTAS}
    for symbol, cls in classes.items():
        if cls: groups[cls].append(symbol)
    for cls in groups:
        groups[cls].sort(key=lambda k: priority(by[k], cls), reverse=True)

    fixed = {symbol for cls, quota in QUOTAS.items() for symbol in groups[cls][:quota]}

    # Preserve all existing shock and EARLY_WATCH emissions. Add pump ideas
    # only by competing for other slots, never silently removing those guards.
    protected = [
        k for k in baseline_list
        if k in old_early or "1D_SHOCK" in rt[k] or "5D_SHOCK" in rt[k]
    ]
    safe_list = list(protected)
    for k in groups["PUMP"]:
        if len(safe_list) >= MAX_PACKET or sum(x not in baseline for x in safe_list) >= PROTECTED_PUMP_BUDGET:
            break
        if k not in safe_list:
            safe_list.append(k)
    for k in baseline_list:
        if len(safe_list) == MAX_PACKET:
            break
        if k not in safe_list:
            safe_list.append(k)
    safe = set(safe_list)
    assert len(safe_list) == len(safe) and len(safe_list) <= MAX_PACKET
    assert baseline.intersection(old_early).issubset(safe)
    assert all(
        symbol in safe for symbol in baseline
        if "1D_SHOCK" in rt[symbol] or "5D_SHOCK" in rt[symbol]
    )

    triggers4 = ("1D_PUMP", "5D_PUMP", "1D_SHOCK", "5D_SHOCK")
    denom = {t: sum(t in rt[sym] for sym in rt) for t in triggers4}
    counts = {
        key: {t: sum(t in rt[sym] for sym in syms) for t in triggers4}
        for key, syms in (("baseline", baseline), ("fixed_quota", fixed), ("protected_shock_early", safe))
    }
    for t in ("1D_SHOCK", "5D_SHOCK"):
        assert counts["protected_shock_early"][t] >= counts["baseline"][t]

    original_by_symbol = {q["affected_assets"]: q for q in sigs}
    replaced = [x for x in baseline_list if x not in safe]
    added = [x for x in safe_list if x not in baseline]
    replaced_causes = Counter()
    for symbol in replaced:
        source = original_by_symbol[symbol].get("source") or {}
        raw = source.get("raw_triggers") or by[symbol].get("raw_triggers") or []
        if source.get("discovery_state") == "EARLY_WATCH":
            replaced_causes["EARLY_WATCH"] += 1
        elif any(t in raw for t in ("1D_SHOCK", "5D_SHOCK")):
            replaced_causes["SHOCK"] += 1
        elif raw == ["SECTOR_UNDERPERFORM"]:
            replaced_causes["SECTOR_ONLY"] += 1
        elif raw:
            replaced_causes["OTHER_RAW_ANOMALY"] += 1
        else:
            replaced_causes["UNCLASSIFIED"] += 1

    def describe(symbol: str) -> dict:
        rec = by[symbol]
        base_source = (original_by_symbol.get(symbol) or {}).get("source") or {}
        return {
            "symbol": symbol,
            "baseline_selected": symbol in baseline,
            "baseline_state": base_source.get("discovery_state"),
            "baseline_raw_triggers": base_source.get("raw_triggers"),
            "shadow_group": classes[symbol],
            "shadow_triggers": rt[symbol],
            "ret_1d_pct": number(rec.get("ret_1d_pct")),
            "ret_5d_pct": number(rec.get("ret_5d_pct")),
            "volume_ratio": number(rec.get("volume_ratio")),
            "raw_priority": number(rec.get("raw_priority")),
            "sector_relative_5d_pct": number(rec.get("sector_relative_5d_pct")),
            "corporate_action_guard": bool(rec.get("corporate_action_suspected") or rec.get("corporate_action_unverified")),
        }

    return {
        "source_session_date": h["source_session_date"], "source_commit": commit,
        "generated_at": h.get("generated_at"), "fresh_symbols": len(rows),
        "baseline_n": len(baseline), "fixed_n": len(fixed),
        "protected_n": len(safe),
        "denominator": denom, "emitted": counts,
        "fixed_additions": len(fixed - baseline),
        "fixed_removed": len(baseline - fixed),
        "protected_additions": len(safe - baseline),
        "protected_removed": len(baseline - safe),
        "protected_displacement_reasons": dict(sorted(replaced_causes.items())),
        "protected_displaced_baseline": [describe(x) for x in replaced],
        "protected_added_pumps": [describe(x) for x in added],
        "baseline_early": len(old_early),
        "protected_preserved_early": len(old_early & safe),
    }


def replay(max_commits: int = 60) -> dict:
    lines = git("log", "--format=%H|%cI", "--", PREFILTER).decode().splitlines()[:max_commits]
    observations: list[dict] = []
    accepted: dict[str, dict] = {}
    rejected = Counter()
    for line in reversed(lines):  # earliest actual git snapshot first
        sha, commit_time = line.split("|", 1)
        try:
            h, p, s, raw = read_packet(sha)
            errors = verify(h, p, s, raw)
            date = h.get("source_session_date")
            if errors:
                for reason in errors: rejected[reason] += 1
                observations.append({"sha":sha[:12],"committed_at":commit_time,"source_session_date":date,"errors":errors})
                continue
            if date in accepted:
                observations.append({"sha":sha[:12],"committed_at":commit_time,"source_session_date":date,"duplicate":True})
                continue
            item = assess(h, p, s, sha)
            item["git_committed_at"] = commit_time
            accepted[date] = item
            observations.append({"sha":sha[:12],"committed_at":commit_time,"source_session_date":date,"accepted":True})
        except Exception as exc:
            rejected["FETCH_OR_PARSE_FAILED"] += 1
            observations.append({"sha":sha[:12], "committed_at":commit_time, "errors":["FETCH_OR_PARSE_FAILED"],"error_type":type(exc).__name__})

    sessions = [accepted[k] for k in sorted(accepted)]
    trigger_keys = ("1D_PUMP", "5D_PUMP", "1D_SHOCK", "5D_SHOCK")
    aggregate = {
        "denominator": {t: sum(x["denominator"][t] for x in sessions) for t in trigger_keys},
        "emitted": {
            policy: {t: sum(x["emitted"][policy][t] for x in sessions) for t in trigger_keys}
            for policy in ("baseline", "fixed_quota", "protected_shock_early")
        },
        "fixed_additions": sum(x["fixed_additions"] for x in sessions),
        "fixed_removed": sum(x["fixed_removed"] for x in sessions),
        "protected_additions": sum(x["protected_additions"] for x in sessions),
        "protected_removed": sum(x["protected_removed"] for x in sessions),
        "baseline_early": sum(x["baseline_early"] for x in sessions),
        "protected_preserved_early": sum(x["protected_preserved_early"] for x in sessions),
        "protected_displacement_reasons": dict(sorted(
            sum((Counter(x["protected_displacement_reasons"]) for x in sessions), Counter()).items()
        )),
    }
    return {
        "schema": "opportunity-radar-multi-session-recall-diagnostic-v1",
        "status": "ARCHIVED_SESSION_REPLAY_DIAGNOSTIC_ONLY",
        "no_hindsight_discovery": True,
        "not_promotion_grade": True,
        "warning": (
            "Only source-session-valid git-archived packets are counted. "
            "The policies are retrospective comparisons on archived snapshots; "
            "not prospectively independent, not predictive alpha, and not the "
            "Rule_Experiments promotion-grade World-State bundle."
        ),
        "max_packet": MAX_PACKET, "fixed_quota": QUOTAS,
        "protected_pump_budget": PROTECTED_PUMP_BUDGET,
        "git_snapshot_commits_considered": len(lines),
        "accepted_independent_sessions": len(sessions),
        "rejected_reason_counts": dict(rejected),
        "aggregate": aggregate,
        "sessions": sessions,
        "audit_log": observations,
    }


def main() -> None:
    data = replay()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status":data["status"], "accepted":data["accepted_independent_sessions"],
        "rejected":data["rejected_reason_counts"],
        "aggregate":data["aggregate"],
        "accepted_dates":[x["source_session_date"] for x in data["sessions"]],
    }, ensure_ascii=False))
    if not data["accepted_independent_sessions"]:
        raise SystemExit("no verified archived complete sessions; diagnostic-only, no promotion")


if __name__ == "__main__":
    main()
