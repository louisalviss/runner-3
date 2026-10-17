#!/usr/bin/env python3
"""Read-only SEO upside advisory for *verified-domain* acquisition listings.

Never discovers listings, calls Semrush, treats rank headroom as a backlink
signal, or promotes BUY/BUILD verdicts. Historical SeoTrends domains are not
purchase candidates.
"""
from __future__ import annotations

import json
import pathlib
import re
from collections import Counter, defaultdict
from urllib.parse import urlsplit

SCHEMA = "seo-upside-shadow-v1"
_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_POSITIONS = range(4, 16)
_COMMERCIAL = re.compile(
    r"(?:^|/)(?:products?|services?|solutions?|tools?|calculators?|"
    r"converters?|generators?|software|pricing|features|integrations?|"
    r"downloads?|shop|store|buy|sale|category|collections?)(?:/|$|-)"
    r"|(?:calculator|converter|generator|software|for-sale|download)(?:/|$|-)",
    re.I,
)
_NON_COMMERCIAL = ("/blog/", "/articles/", "/news/", "/glossary/", "/forum/",
                   "/wiki/", "/press/", "/guides/", "/learn/", "/resources/")
_VALID_ISSUES = {"intent_mismatch", "missing_contextual_link", "material_content_gap",
                 "broken_canonical", "indexability_error"}
_MAX_EXPORT_BYTES = 32 * 1024 * 1024
_MAX_ROWS = 30000


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if 0 <= n < 1_000_000_000 and n == n else None
    except (TypeError, ValueError, OverflowError):
        return None


def _page(url: object, domain: str) -> str | None:
    try:
        p = urlsplit(str(url))
        host = (p.hostname or "").lower()
        if p.scheme not in ("http", "https") or host not in (domain, "www." + domain):
            return None
        path = p.path.rstrip("/") or "/"
        if any(x in (path + "/").lower() for x in _NON_COMMERCIAL):
            return None
        if not _COMMERCIAL.search(path):
            return None
        return "https://" + domain + path
    except (TypeError, ValueError):
        return None


def _brand_keyword(word: str, domain: str) -> bool:
    brand = re.sub(r"[^a-z0-9]", "", domain.split(".")[0].lower())
    text = re.sub(r"[^a-z0-9]", "", word.lower())
    return len(brand) >= 5 and brand in text


def rank_headroom(domain: str, rows: list) -> dict:
    """Conservative keyword/page *hypotheses*; not a traffic or revenue forecast."""
    pages: dict[str, dict] = defaultdict(dict)
    for row in rows[:_MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        page = _page(row.get("url"), domain)
        kw = str(row.get("phrase") or "").lower().strip()
        pos = _number(row.get("position"))
        vol = _number(row.get("volume"))
        kd = _number(row.get("keywordDifficulty"))
        cpc = _number(row.get("cpc"))
        if not page or not kw or _brand_keyword(kw, domain):
            continue
        if pos is None or pos not in _POSITIONS or vol is None or vol < 100:
            continue
        if kd is None or kd > 50 or cpc is None or cpc < 0.5:
            continue
        old = pages[page].get(kw)
        if old is None or pos < old["position"]:
            pages[page][kw] = {
                "keyword": kw, "position": int(pos), "volume": int(vol),
                "cpc": round(cpc, 2), "kd": round(kd, 1),
            }
    result = []
    for page, keyed in pages.items():
        kws = list(keyed.values())
        if len(kws) < 2:
            continue
        kws.sort(key=lambda k: (-k["volume"] * k["cpc"] / (k["kd"] + 20), k["keyword"]))
        value = sum(
            min(k["volume"], 10000) * min(k["cpc"], 20) / (k["kd"] + 20)
            * (16 - k["position"]) / 12
            for k in kws[:8]
        )
        result.append({"url": page, "keyword_count": len(kws),
                       "ranking_opportunity_index": round(value, 2),
                       "keywords": kws[:5]})
    result.sort(key=lambda p: (-p["ranking_opportunity_index"], p["url"]))
    return {"candidate_page_count": len(result), "pages": result[:5],
            "index_definition": "Heuristic search visibility index; NOT traffic/revenue/ROI"}


def evaluate(domain: str, export: dict | None, independent: dict | None = None) -> dict:
    """Authority and fixable gaps require separate independent evidence."""
    domain = str(domain or "").lower().strip()
    out = {"schema": SCHEMA, "domain": domain, "mode": "SHADOW",
           "can_promote_buy": False, "can_override_source_verdict": False,
           "authority_verified": False, "fixable_gap_verified": False}
    if not _DOMAIN.fullmatch(domain):
        return {**out, "status": "BLOCKED_INVALID_DOMAIN"}
    if not isinstance(export, dict) or export.get("domain", "").lower() != domain or not isinstance(export.get("rows"), list):
        return {**out, "status": "BLOCKED_EXPORT_MISMATCH"}
    if len(export["rows"]) > _MAX_ROWS:
        return {**out, "status": "BLOCKED_EXPORT_TOO_LARGE"}
    out["source"] = "Semrush cached export, independent buyer DD"
    out["export_truncated"] = bool(export.get("truncated"))
    out["headroom"] = rank_headroom(domain, export["rows"])
    out["modeled_not_first_party"] = True
    if out["headroom"]["candidate_page_count"] == 0:
        return {**out, "status": "NO_RANKING_HEADROOM_SIGNAL",
                "next_gate": "No SEO-upside ranking promotion; retain existing acquisition DD"}
    independent = independent if isinstance(independent, dict) else {}
    proof = independent.get("backlinks") or {}
    # A declared source is not independent evidence by itself; the operator
    # must supply a dated verified audit and referring-domain count.
    if (isinstance(proof, dict) and proof.get("verified") is True
            and proof.get("source") in {"Ahrefs", "Semrush", "Majestic", "manual_verified"}
            and isinstance(proof.get("checked_at"), str)
            and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", proof["checked_at"])
            and (_number(proof.get("referring_domains")) or 0) >= 20):
        out["authority_verified"] = True
        out["referring_domains"] = int(proof["referring_domains"])
    issues = independent.get("issues") or []
    if isinstance(issues, list):
        verified_issues = [
            {"type": issue["type"], "url": issue["url"]}
            for issue in issues[:100] if isinstance(issue, dict)
            and issue.get("verified") is True and issue.get("type") in _VALID_ISSUES
            and isinstance(issue.get("url"), str)
            and _page(issue["url"], domain) is not None
            and issue["url"].split("?", 1)[0].rstrip("/") in
            {p["url"] for p in out["headroom"]["pages"]}
        ]
    else:
        verified_issues = []
    out["fixable_gap_verified"] = bool(verified_issues)
    out["verified_issues"] = verified_issues[:10]
    if not out["authority_verified"]:
        out["status"] = "NEEDS_AUTHORITY_PROOF"
        out["next_gate"] = "Verify real referring domains, topical relevance and transferability"
    elif not out["fixable_gap_verified"]:
        out["status"] = "NEEDS_PAGE_AUDIT"
        out["next_gate"] = "Crawl/rank-intent audit: prove a specific fixable gap, not just rank 4-15"
    else:
        out["status"] = "SUPPORTED_UPSIDE_HYPOTHESIS"
        out["next_gate"] = "Seller GSC/GA, backlink ownership, cost/time and controlled upside DD"
    return out


def read_export(path: pathlib.Path, domain: str) -> dict | None:
    """No external calls, bounded source artifact, fail closed."""
    path = pathlib.Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_EXPORT_BYTES:
            return None
        with path.open(encoding="utf-8") as f:
            value = json.load(f)
        if isinstance(value, dict) and str(value.get("domain") or "").lower() == domain:
            return value
    except (OSError, ValueError, UnicodeError):
        pass
    return None


def attach(value: dict, root: pathlib.Path, independent_dir: pathlib.Path | None = None) -> dict:
    """Annotate Flippa DD records only; never change existing decisions."""
    day = str(value.get("date_vn") or "")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
        raise ValueError("Invalid run date")
    root = pathlib.Path(root)
    records = {
        x.get("listing_identity"): x for x in
        (value.get("flippa_semrush") or {}).get("items", [])
        if isinstance(x, dict) and x.get("listing_identity")
    }
    statuses = Counter()
    for candidate in (value.get("qualification") or {}).get("candidates", []):
        if candidate.get("source") != "FLIPPA":
            continue
        identity = str(candidate.get("identity") or "")
        item = records.get(identity)
        if item is None:
            result = {"schema": SCHEMA, "status": "NO_VERIFIED_LISTING_DOMAIN", "mode": "SHADOW",
                      "can_promote_buy": False}
        elif item.get("status") != "PASS":
            result = {"schema": SCHEMA, "status": "BLOCKED_SOURCE", "mode": "SHADOW",
                      "can_promote_buy": False}
        else:
            domain = str(item.get("domain") or "").lower()
            if not _DOMAIN.fullmatch(domain):
                result = {"schema": SCHEMA, "status": "BLOCKED_INVALID_DOMAIN", "mode": "SHADOW",
                          "can_promote_buy": False}
            else:
                path = root / ("flippa-sem-" + day.replace("-", "")) / (domain + ".json")
                independent = None
                if independent_dir is not None and re.fullmatch(r"flippa:\d+", identity):
                    audit_path = pathlib.Path(independent_dir) / (identity.split(":", 1)[1] + ".json")
                    try:
                        if audit_path.is_file() and not audit_path.is_symlink() and audit_path.stat().st_size <= 100_000:
                            independent = json.loads(audit_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError, UnicodeError):
                        pass
                result = evaluate(domain, read_export(path, domain), independent)
                result["export_path"] = str(path)
        candidate.setdefault("evidence", {})["seo_upside"] = result
        statuses[result["status"]] += 1
    summary = {"schema": SCHEMA, "status": "SHADOW",
               "evaluated_flippa": sum(statuses.values()),
               "status_counts": dict(statuses),
               "no_buy_build_verdict_changes": True,
               "no_new_provider_calls": True}
    value["seo_upside"] = summary
    return summary
