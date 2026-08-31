#!/usr/bin/env python3
"""Client for Runner3 Content Intelligence API.

Generic structured path for RSS/X/Facebook/Reddit/web/YouTube items, features,
append-only user events, thin explicit-interest ingest, and derived profile reads.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

DEFAULT_CORE_URL = "https://runner3-core.ducduy2411.workers.dev"
DEFAULT_PERSONAL_MODEL = "personal-v2"

FEATURE_RULES: dict[str, tuple[str, ...]] = {
    "macro_finance": ("bond", "yield", "treasury", "fed", "deficit", "debt", "recession", "capital market", "thị trường vốn", "lợi suất", "trái phiếu"),
    "ai_economics": ("ai ", "artificial intelligence", "robot", "humanoid", "nvidia", "model", "chip", "automation"),
    "regulation_policy": ("regulation", "policy", "sanction", "privacy", "data protection", "vaccine", "fda", "vneid", "quy định", "xử phạt", "bảo vệ dữ liệu"),
    "vietnam_sea": ("vietnam", "việt nam", "southeast asia", "asean", "indonesia", "malaysia", "thailand", "singapore"),
    "political_institutions": ("political", "succession", "institution", "trump", "china", "chinese", "trung quốc", "chu dung cơ", "khamenei", "kim "),
    "security_auth_ux": ("password", "login", "authentication", "passkey", "security", "hack", "malware", "bảo mật", "đăng nhập"),
    "explanatory_science": ("scientist", "science", "cancer", "evolution", "brain", "memory", "biology", "octopus", "wildfire", "eclipse", "ung thư", "tiến hóa"),
    "structural_business": ("industrial", "supply chain", "business", "market structure", "enterprise", "factory", "trade", "thương mại", "doanh nghiệp"),
}

MECHANISM_RULES: dict[str, tuple[str, ...]] = {
    "causal_mechanism": ("why", "how", "vì sao", "tại sao", "mechanism", "cơ chế"),
    "system_design": ("system", "architecture", "authentication", "infrastructure", "framework", "thiết kế", "hệ thống"),
    "second_order_effect": ("implication", "impact", "effect", "risk", "trade-off", "tác động", "rủi ro", "hệ quả"),
    "economics_unit": ("cost", "profit", "yield", "valuation", "price", "economics", "chi phí", "lợi nhuận", "định giá"),
}


def request_json(method: str, path: str, payload: dict[str, Any] | None = None, *, core_url: str | None = None) -> dict[str, Any]:
    base = (core_url or os.environ.get("RUNNER3_CORE_URL") or DEFAULT_CORE_URL).rstrip("/")
    headers = {"Accept": "application/json", "User-Agent": "runner3-content-intelligence/1.3"}
    token = os.environ.get("RUNNER3_CORE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def batches(rows: list[dict[str, Any]], n: int = 100):
    for i in range(0, len(rows), n):
        yield rows[i:i+n]


def stable_id(item: dict[str, Any]) -> str:
    return str(item.get("stableIdentity") or item.get("itemId") or item.get("canonicalUrl") or "").strip()


def infer_features(item: dict[str, Any]) -> list[dict[str, Any]]:
    item_id = stable_id(item)
    text = " ".join(str(item.get(k) or "") for k in ("title", "summaryEvidence", "sourceName", "sourceKey")).lower()
    text = re.sub(r"\s+", " ", text)
    out: list[dict[str, Any]] = []
    for key, needles in FEATURE_RULES.items():
        hits = sum(1 for needle in needles if needle in text)
        if hits:
            out.append({"item_id": item_id, "feature_type": "topic", "feature_key": key, "weight": min(2.0, 0.75 + 0.25 * hits), "confidence": min(1.0, 0.65 + 0.1 * hits), "model_version": "rules-v1"})
    for key, needles in MECHANISM_RULES.items():
        hits = sum(1 for needle in needles if needle in text)
        if hits:
            out.append({"item_id": item_id, "feature_type": "mechanism", "feature_key": key, "weight": min(2.0, 0.8 + 0.3 * hits), "confidence": min(1.0, 0.7 + 0.1 * hits), "model_version": "rules-v1"})
    source_key = str(item.get("sourceKey") or "").strip().lower()
    if source_key:
        out.append({"item_id": item_id, "feature_type": "source", "feature_key": source_key, "weight": 0.35, "confidence": 1.0, "model_version": "rules-v1"})
    return out


def manifest_rows(obj: dict[str, Any], source_type: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    items = obj.get("manifest") or []
    content_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    shown_rows: list[dict[str, Any]] = []
    render_id = obj.get("renderId") or obj.get("date") or obj.get("windowDate") or "rss-manifest"
    for item in items:
        iid = stable_id(item)
        url = item.get("canonicalUrl")
        if not iid or not url:
            continue
        content_rows.append({
            "item_id": iid,
            "canonical_url": url,
            "source_type": source_type,
            "source_name": item.get("sourceName") or item.get("sourceKey"),
            "source_key": item.get("sourceKey"),
            "title": item.get("title"),
            "published_at": item.get("publishedAt"),
            "language": item.get("language"),
            "raw_ref": item.get("rawRef"),
            "metadata": {"render_number": item.get("number"), "summary_evidence_status": item.get("summaryEvidenceStatus")},
        })
        feature_rows.extend(infer_features(item))
        shown_rows.append({"item_id": iid, "event_type": "shown", "render_id": str(render_id), "context": {"source_type": source_type, "number": item.get("number")}})
    return content_rows, feature_rows, shown_rows


def post_batches(path: str, rows: list[dict[str, Any]], core_url: str | None) -> int:
    applied = 0
    for batch in batches(rows):
        if not batch:
            continue
        result = request_json("POST", path, {"rows": batch}, core_url=core_url)
        applied += int(result.get("applied") or 0)
    return applied


def cmd_ingest_manifest(args: argparse.Namespace) -> int:
    obj = load_json(args.manifest)
    content_rows, feature_rows, shown_rows = manifest_rows(obj, args.source_type)
    items_applied = post_batches("/content-intelligence/items", content_rows, args.core_url)
    features_applied = post_batches("/content-intelligence/features", feature_rows, args.core_url)
    shown_applied = 0 if args.no_shown else post_batches("/content-intelligence/events/batch", shown_rows, args.core_url)
    result = {"ok": True, "items": items_applied, "features": features_applied, "shown_events": shown_applied}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_event(args: argparse.Namespace) -> int:
    payload = {"item_id": args.item_id, "event_type": args.event_type, "render_id": args.render_id, "assistant_recommended": args.assistant_recommended, "assistant_rank": args.assistant_rank, "explicit_feedback": args.explicit_feedback, "context": json.loads(args.context_json) if args.context_json else None}
    result = request_json("POST", "/content-intelligence/events", payload, core_url=args.core_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_event_batch(args: argparse.Namespace) -> int:
    obj = load_json(args.file)
    rows = obj.get("events") if isinstance(obj, dict) else obj
    if not isinstance(rows, list):
        raise SystemExit("event batch must be a list or {events:[...]}")
    applied = 0
    missing_or_duplicate = 0
    durable = True
    for batch in batches(rows):
        if not batch:
            continue
        result = request_json("POST", "/content-intelligence/events/batch", {"rows": batch}, core_url=args.core_url)
        if result.get("ok") is not True:
            raise RuntimeError(result)
        applied += int(result.get("applied") or 0)
        missing_or_duplicate += int(result.get("missing_or_duplicate") or 0)
        durable = durable and result.get("durable") is True
    print(json.dumps({"ok": True, "durable": durable, "applied": applied, "requested": len(rows), "missing_or_duplicate": missing_or_duplicate}, sort_keys=True))
    return 0


def cmd_interest_save(args: argparse.Namespace) -> int:
    payload = load_json(args.file)
    if not isinstance(payload, dict):
        raise SystemExit("interest save payload must be an object")
    result = request_json("POST", "/content-intelligence/interests/save", payload, core_url=args.core_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_interest_ingest(args: argparse.Namespace) -> int:
    payload = load_json(args.file)
    if not isinstance(payload, dict):
        raise SystemExit("interest ingest payload must be an object")
    result = request_json("POST", "/content-intelligence/interests/ingest", payload, core_url=args.core_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_recompute(args: argparse.Namespace) -> int:
    profile = request_json("POST", "/content-intelligence/profile/recompute", {"model_version": args.model_version}, core_url=args.core_url)
    scores = request_json("POST", "/content-intelligence/scores/recompute", {"model_version": args.model_version}, core_url=args.core_url)
    print(json.dumps({"ok": True, "profile": profile, "scores": scores}, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    result = request_json("GET", f"/content-intelligence/profile?limit={args.limit}", core_url=args.core_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core-url")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("ingest-manifest")
    m.add_argument("--manifest", required=True)
    m.add_argument("--source-type", default="rss")
    m.add_argument("--no-shown", action="store_true")
    m.set_defaults(func=cmd_ingest_manifest)
    e = sub.add_parser("event")
    e.add_argument("--item-id", required=True)
    e.add_argument("--event-type", required=True, choices=["shown", "selected", "deep_read", "liked", "disliked", "saved", "interest_saved"])
    e.add_argument("--render-id")
    e.add_argument("--assistant-recommended", action="store_true")
    e.add_argument("--assistant-rank", type=int)
    e.add_argument("--explicit-feedback")
    e.add_argument("--context-json")
    e.set_defaults(func=cmd_event)
    b = sub.add_parser("event-batch")
    b.add_argument("--file", required=True)
    b.set_defaults(func=cmd_event_batch)
    i = sub.add_parser("interest-save")
    i.add_argument("--file", required=True, help="Legacy eager payload accepted by /content-intelligence/interests/save")
    i.set_defaults(func=cmd_interest_save)
    ii = sub.add_parser("interest-ingest")
    ii.add_argument("--file", required=True, help="Thin durable payload accepted by /content-intelligence/interests/ingest")
    ii.set_defaults(func=cmd_interest_ingest)
    r = sub.add_parser("recompute")
    r.add_argument("--model-version", default=DEFAULT_PERSONAL_MODEL)
    r.set_defaults(func=cmd_recompute)
    g = sub.add_parser("profile")
    g.add_argument("--limit", type=int, default=100)
    g.set_defaults(func=cmd_profile)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
