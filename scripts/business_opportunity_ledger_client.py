#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "business-opportunity-ledger-client-v1"
DEFAULT_CORE_URL = "https://runner3-core.ducduy2411.workers.dev"
DEFAULT_ENV_PATH = Path("/etc/vps-control/runner3-core.env")
ALLOWED_ENV_KEYS = {"RUNNER3_CORE_TOKEN_B64", "RUNNER3_CORE_URL", "RUNNER3_SOURCE"}
ALLOWED_AUTHORITIES = {
    "BUSINESS_OPPORTUNITY_RADAR",
    "PROJECT_AUTHORITY",
    "MARKET_VALIDATION",
    "MANUAL_RECONCILIATION",
}
ALLOWED_STATUS = {
    "DISCOVERED", "RESEARCHING", "WATCH", "VALIDATED_CANDIDATE",
    "INVESTIGATE", "TEST", "PROJECT", "WTP", "PILOT", "EXECUTE",
    "HOLD", "DROP", "KILL",
}
ALLOWED_DIRECTION = {"SUPPORT", "COUNTER", "NEUTRAL"}
KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
FORBIDDEN_EVIDENCE_FIELDS = {
    "raw", "raw_text", "full_text", "content", "html", "body", "page_html", "transcript"
}


class LedgerError(RuntimeError):
    pass


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value: Any, name: str, max_len: int, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise LedgerError(f"{name}_required")
        return None
    out = str(value).strip()
    if not out:
        if required:
            raise LedgerError(f"{name}_required")
        return None
    if len(out) > max_len:
        raise LedgerError(f"{name}_too_large")
    return out


def _key(value: Any, name: str) -> str:
    out = _text(value, name, 200, required=True)
    assert out is not None
    if not KEY_RE.fullmatch(out):
        raise LedgerError(f"{name}_invalid")
    return out


def _load_env_file(path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_ENV_KEYS:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if value:
            values[key] = value
    return values


def _runtime_config(env_path: Path = DEFAULT_ENV_PATH) -> tuple[str, str, str]:
    file_env = _load_env_file(env_path)
    core_url = (
        os.environ.get("RUNNER3_CORE_URL")
        or file_env.get("RUNNER3_CORE_URL")
        or DEFAULT_CORE_URL
    ).rstrip("/")
    source = (
        os.environ.get("RUNNER3_SOURCE")
        or file_env.get("RUNNER3_SOURCE")
        or "business-opportunity-ledger-client"
    ).strip()
    token = os.environ.get("RUNNER3_CORE_TOKEN", "").strip()
    if not token:
        encoded = (
            os.environ.get("RUNNER3_CORE_TOKEN_B64")
            or file_env.get("RUNNER3_CORE_TOKEN_B64")
            or ""
        ).strip()
        if encoded:
            try:
                token = base64.b64decode(encoded, validate=True).decode("utf-8").strip()
            except Exception as exc:
                raise LedgerError("RUNNER3_CORE_TOKEN_B64_INVALID") from exc
    if not token:
        raise LedgerError("RUNNER3_CORE_TOKEN_REQUIRED")
    return core_url, token, source


def _request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
    env_path: Path = DEFAULT_ENV_PATH,
) -> tuple[int, dict[str, Any]]:
    core_url, token, source = _runtime_config(env_path)
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": f"{VERSION}/{source}",
        "Cache-Control": "no-cache",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(core_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"ok": False, "error": raw[:500]}
        return exc.code, body


def _require_ok(status: int, body: dict[str, Any], context: str) -> dict[str, Any]:
    if status < 200 or status >= 300 or body.get("ok") is not True:
        raise LedgerError(f"{context}_failed:http={status}:body={json.dumps(body, ensure_ascii=False)[:800]}")
    return body


def _candidate_payload(candidate: dict[str, Any], expected_version: int) -> dict[str, Any]:
    status = _text(candidate.get("status"), "status", 40, required=True)
    assert status is not None
    if status not in ALLOWED_STATUS:
        raise LedgerError("status_invalid")
    score = candidate.get("score")
    if score is not None:
        try:
            score = float(score)
        except Exception as exc:
            raise LedgerError("score_invalid") from exc
        if score < 0 or score > 10:
            raise LedgerError("score_invalid")

    return {
        "expected_version": expected_version,
        "normalized_problem": _text(candidate.get("normalized_problem"), "normalized_problem", 2000, required=True),
        "thesis_version": _text(candidate.get("thesis_version"), "thesis_version", 300),
        "project_id": _text(candidate.get("project_id"), "project_id", 300),
        "status": status,
        "score": score,
        "next_gate": _text(candidate.get("next_gate"), "next_gate", 4000),
        "decision_reason": _text(candidate.get("decision_reason"), "decision_reason", 4000),
        "source_lane": _text(candidate.get("source_lane"), "source_lane", 200, required=True),
        "research_terminal": bool(candidate.get("research_terminal", False)),
        "research_terminal_at": _text(candidate.get("research_terminal_at"), "research_terminal_at", 100),
        "last_material_delta_at": _text(candidate.get("last_material_delta_at"), "last_material_delta_at", 100),
        "transition_reason": _text(candidate.get("transition_reason"), "transition_reason", 4000),
        "evidence_snapshot_hash": _text(candidate.get("evidence_snapshot_hash"), "evidence_snapshot_hash", 128),
    }


def _validate_identity(item: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise LedgerError("identity_not_object")
    return {
        "candidate_id": candidate_id,
        "identity_type": _text(item.get("identity_type"), "identity_type", 60, required=True),
        "identity_value": _text(item.get("identity_value"), "identity_value", 2000, required=True),
        "source_lane": _text(item.get("source_lane"), "identity_source_lane", 200),
    }


def _validate_evidence(item: dict[str, Any], candidate_id: str) -> tuple[str, dict[str, Any]]:
    if not isinstance(item, dict):
        raise LedgerError("evidence_not_object")
    forbidden = sorted(FORBIDDEN_EVIDENCE_FIELDS.intersection(item))
    if forbidden:
        raise LedgerError("evidence_raw_payload_forbidden:" + ",".join(forbidden))
    source_lane = _text(item.get("source_lane"), "evidence_source_lane", 200, required=True)
    evidence_type = _text(item.get("evidence_type"), "evidence_type", 200, required=True)
    direction = (_text(item.get("direction"), "direction", 20) or "NEUTRAL").upper()
    if direction not in ALLOWED_DIRECTION:
        raise LedgerError("direction_invalid")
    observed_at = _text(item.get("observed_at"), "observed_at", 100, required=True)
    source_ref = _text(item.get("source_ref"), "source_ref", 2000)
    evidence_hash = _text(item.get("evidence_hash"), "evidence_hash", 128)
    note = _text(item.get("note"), "note", 500)
    independence_group = _text(item.get("independence_group"), "independence_group", 300)
    hard_signal = bool(item.get("hard_signal", False))
    if not source_ref and not evidence_hash:
        raise LedgerError("evidence_source_ref_or_hash_required")
    if not evidence_hash:
        evidence_hash = _sha(json.dumps({
            "candidate_id": candidate_id,
            "source_lane": source_lane,
            "source_ref": source_ref,
            "evidence_type": evidence_type,
            "independence_group": independence_group,
            "hard_signal": hard_signal,
            "direction": direction,
            "observed_at": observed_at,
            "note": note,
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    evidence_id = item.get("evidence_id")
    if evidence_id:
        evidence_id = _key(evidence_id, "evidence_id")
    else:
        evidence_id = "ev-" + _sha(f"{candidate_id}:{evidence_hash}")[:32]
    return evidence_id, {
        "candidate_id": candidate_id,
        "source_lane": source_lane,
        "source_ref": source_ref,
        "evidence_type": evidence_type,
        "independence_group": independence_group,
        "hard_signal": hard_signal,
        "direction": direction,
        "observed_at": observed_at,
        "evidence_hash": evidence_hash,
        "note": note,
    }


def validate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise LedgerError("packet_not_object")
    if packet.get("schema_version") != 1:
        raise LedgerError("schema_version_invalid")
    if packet.get("semantic_synthesis") is not True:
        raise LedgerError("semantic_synthesis_required")
    authority = _text(packet.get("synthesis_authority"), "synthesis_authority", 80, required=True)
    assert authority is not None
    if authority not in ALLOWED_AUTHORITIES:
        raise LedgerError("synthesis_authority_invalid")
    candidate = packet.get("candidate")
    if not isinstance(candidate, dict):
        raise LedgerError("candidate_required")
    candidate_id = _key(candidate.get("candidate_id"), "candidate_id")
    candidate_payload = _candidate_payload(candidate, 0)

    identities = [_validate_identity(x, candidate_id) for x in (packet.get("identities") or [])]
    if not identities:
        raise LedgerError("at_least_one_identity_required")
    evidence = [_validate_evidence(x, candidate_id) for x in (packet.get("evidence") or [])]

    return {
        "schema_version": 1,
        "semantic_synthesis": True,
        "synthesis_authority": authority,
        "candidate_id": candidate_id,
        "candidate": candidate_payload,
        "identities": identities,
        "evidence": evidence,
        "reconcile_after": packet.get("reconcile_after", True) is not False,
    }


def _get_candidate(candidate_id: str, env_path: Path) -> dict[str, Any] | None:
    status, body = _request(
        "GET",
        "/business-opportunity/candidates/" + urllib.parse.quote(candidate_id, safe=""),
        env_path=env_path,
    )
    if status == 404:
        return None
    _require_ok(status, body, "candidate_get")
    return body.get("candidate")


def apply_packet(packet: dict[str, Any], *, env_path: Path = DEFAULT_ENV_PATH) -> dict[str, Any]:
    normalized = validate_packet(packet)
    candidate_id = normalized["candidate_id"]

    saved = None
    for attempt in range(3):
        current = _get_candidate(candidate_id, env_path)
        payload = dict(normalized["candidate"])
        payload["expected_version"] = int((current or {}).get("version") or 0)
        status, body = _request(
            "PUT",
            "/business-opportunity/candidates/" + urllib.parse.quote(candidate_id, safe=""),
            payload=payload,
            env_path=env_path,
        )
        if status == 409 and attempt < 2:
            continue
        saved = _require_ok(status, body, "candidate_put")
        break
    if saved is None:
        raise LedgerError("candidate_put_retry_exhausted")

    identity_results = []
    for identity in normalized["identities"]:
        status, body = _request(
            "POST",
            "/business-opportunity/identities",
            payload=identity,
            env_path=env_path,
        )
        identity_results.append(_require_ok(status, body, "identity_put"))

    evidence_results = []
    for evidence_id, evidence in normalized["evidence"]:
        status, body = _request(
            "PUT",
            "/business-opportunity/evidence/" + urllib.parse.quote(evidence_id, safe=""),
            payload=evidence,
            env_path=env_path,
        )
        evidence_results.append(_require_ok(status, body, "evidence_put"))

    reconcile_result = None
    if normalized["reconcile_after"]:
        status, body = _request(
            "POST",
            "/business-opportunity/reconcile",
            payload={
                "candidate_id": candidate_id,
                "thesis_version": normalized["candidate"].get("thesis_version"),
            },
            env_path=env_path,
        )
        reconcile_result = _require_ok(status, body, "reconcile")

    return {
        "ok": True,
        "client_version": VERSION,
        "candidate_id": candidate_id,
        "candidate": saved.get("current"),
        "candidate_changed": bool(saved.get("changed")),
        "identity_writes": len(identity_results),
        "evidence_writes": len(evidence_results),
        "reconcile": reconcile_result,
    }


def command_health(args: argparse.Namespace) -> dict[str, Any]:
    status, body = _request("GET", "/business-opportunity/health", env_path=args.env_path)
    return _require_ok(status, body, "health")


def command_get(args: argparse.Namespace) -> dict[str, Any]:
    candidate_id = _key(args.candidate_id, "candidate_id")
    status, body = _request(
        "GET",
        "/business-opportunity/candidates/" + urllib.parse.quote(candidate_id, safe=""),
        env_path=args.env_path,
    )
    return _require_ok(status, body, "candidate_get")


def command_reconcile(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.candidate_id:
        payload["candidate_id"] = _key(args.candidate_id, "candidate_id")
    elif args.identity_type and args.identity_value:
        payload["identity_type"] = args.identity_type
        payload["identity_value"] = args.identity_value
    else:
        raise LedgerError("candidate_or_identity_required")
    if args.thesis_version:
        payload["thesis_version"] = args.thesis_version
    status, body = _request(
        "POST",
        "/business-opportunity/reconcile",
        payload=payload,
        env_path=args.env_path,
    )
    return _require_ok(status, body, "reconcile")


def command_apply(args: argparse.Namespace) -> dict[str, Any]:
    raw = sys.stdin.read() if args.packet == "-" else Path(args.packet).read_text(encoding="utf-8")
    packet = json.loads(raw)
    normalized = validate_packet(packet)
    if args.dry_run:
        return {"ok": True, "dry_run": True, "normalized": normalized}
    return apply_packet(packet, env_path=args.env_path)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Semantic write-through client for the Business Opportunity D1 ledger.")
    ap.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    sub = ap.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health")
    health.set_defaults(func=command_health)

    get = sub.add_parser("get")
    get.add_argument("candidate_id")
    get.set_defaults(func=command_get)

    reconcile = sub.add_parser("reconcile")
    group = reconcile.add_mutually_exclusive_group(required=True)
    group.add_argument("--candidate-id")
    group.add_argument("--identity-type")
    reconcile.add_argument("--identity-value")
    reconcile.add_argument("--thesis-version")
    reconcile.set_defaults(func=command_reconcile)

    apply = sub.add_parser("apply")
    apply.add_argument("packet", help="JSON packet path or - for stdin")
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(func=command_apply)
    return ap


def main() -> int:
    args = parser().parse_args()
    try:
        result = args.func(args)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (LedgerError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
