#!/usr/bin/env python3
"""Evidence-gated BUILD vs BUY comparison over source-owned SeoTrends and Flippa.

This layer only interprets existing source artifacts. It never drives browsers,
calls providers, writes to source scanners, bids, buys, or creates a website.
"""
from __future__ import annotations

import json
import pathlib
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

SEO_SCAN_ROOT = pathlib.Path("/var/lib/seotrends-public/scans")
ACTIVE_BUY_LIMIT_USD = 10000

def read_semantic(day: str, root: pathlib.Path = SEO_SCAN_ROOT) -> dict:
    path = pathlib.Path(root) / (day + "-semantic-business-dd.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"status": "MISSING", "by_domain": {}, "file": str(path)}
    if value.get("date") != day or value.get("status") != "PASS_SOURCE_PLUS_SEMANTIC_SCREEN":
        return {"status": "INVALID_OR_STALE", "by_domain": {}, "file": str(path)}
    if value.get("approved_build") != 0:
        # This reader does not trust approvals from a downstream note.
        return {"status": "INVALID_APPROVAL_CLAIM", "by_domain": {}, "file": str(path)}
    items = value.get("items") or []
    if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
        return {"status": "INVALID_ITEMS", "by_domain": {}, "file": str(path)}
    by_domain = {}
    for item in items:
        name = str(item.get("domain") or "").lower()
        if name and name not in by_domain:
            by_domain[name] = item
    return {"status": "PASS", "by_domain": by_domain, "file": str(path)}

def positive_number(x):
    if isinstance(x, bool):
        return None
    try:
        n = float(x)
        if 0 <= n < 100_000_000 and n != float("inf"):
            return n
    except (ValueError, TypeError, OverflowError):
        pass
    return None

def seo_qualification(row: dict, semantic: dict, provider_ok: bool) -> dict:
    domain = str(row.get("domain") or "").lower()
    semantic_verdict = str(semantic.get("semantic_verdict") or "")
    terminal = str(semantic.get("terminal_verdict") or row.get("terminal_verdict") or "")
    raw = str(row.get("verdict") or "")
    product_intent = (semantic.get("product_intent_checked") is True if semantic else row.get("product_intent_checked") is True)
    if raw == "BLOCKED_PROVIDER" or not provider_ok:
        build, why = "BLOCKED", "Semrush/terminal data unavailable, never infer zero demand"
    elif raw == "DROP" or terminal == "DROP" or semantic_verdict == "DROP_THIS_CYCLE":
        build, why = "DROP", str(semantic.get("business_reason") or row.get("reason") or "Terminal rejection")[:300]
    elif semantic_verdict == "WATCH_NARROW_GAP" and product_intent and terminal == "WATCH":
        build, why = "WATCH_GAP", str(semantic.get("business_reason") or "Gap not yet validated")[:300]
    elif semantic_verdict == "DEFER_UNMATCHED_INTENT" or not product_intent:
        build, why = "DEFER", "No independently matched commercially useful product-intent keyword"
    elif not semantic_verdict and product_intent and raw in ("WATCH_DD", "SEO_BUILD_TEST"):
        build, why = "DD_PENDING", "Exact SERP was checked but semantic business review, unmet need and monetization remain unverified"
    else:
        build, why = "DD_PENDING", "Validate unmet user need, exact SERP, differentiation, monetization and conversion before BUILD"
    metric = row.get("metrics") or {}
    traffic = positive_number(semantic.get("us_organic_estimate")) if semantic else positive_number(metric.get("traffic"))
    return {
        "identity": domain, "source": "SEOTRENDS", "title": row.get("title") or domain,
        "reference": domain, "category": "BUILD_DD" if build == "DD_PENDING" else build,
        "buy": {"state": "NOT_LISTED", "why": "Discovery is not evidence that this asset is for sale"},
        "build": {"state": build, "why": why},
        "evidence": {
            "semrush_status": "PASS" if provider_ok else "BLOCKED",
            "source_organic_us_monthly_estimate": traffic,
            "source_traffic_is_transferable": False,
            "product_intent_exact_serp_checked": product_intent,
            "terminal_gate": terminal or raw,
            "semantic_gate": semantic_verdict or "NOT_AVAILABLE", "semantic_review_completed": bool(semantic_verdict),
            "revenue_verified": False,
            "differentiated_solution_verified": False,
        },
        "missing": ([] if build in ("DROP", "BLOCKED") else
                    ["demonstrated unmet need", "replicable search gap", "credible monetization/conversion"]),
    }

def flippa_qualification(row: dict, max_buy_usd: int) -> dict:
    is_detail = row.get("verified_detail") is True
    profit_card = positive_number(row.get("profit_card"))
    views = positive_number(row.get("pageviews_verified"))
    reserve = positive_number(row.get("reserve_verified"))
    buy_it_now = positive_number(row.get("bin_verified"))
    asking = positive_number(row.get("asking_verified"))
    # All three are observed price fields; none alone verifies a successful transfer.
    price = buy_it_now if buy_it_now is not None else reserve if reserve is not None else asking
    price_type = "bin" if buy_it_now is not None else "reserve" if reserve is not None else "asking" if asking is not None else None
    under_cap = price is not None and price <= max_buy_usd
    verdict = str(row.get("verdict") or "")
    if verdict.startswith("DROP_") or verdict == "DROP":
        buy, why = "DROP", "Source verdict excludes this listing"
    elif not is_detail:
        buy, why = "DEFER", "Direct listing unverified or CAPTCHA/source unavailable"
    elif price is None:
        buy, why = "DEFER", "No direct observed asking/reserve/BIN price"
    elif not under_cap:
        buy, why = "DROP", "Observed price above buy cap; all-in transaction costs still require DD"
    elif profit_card is None or profit_card < 250:
        buy, why = "DEFER", "No credible material recurring earnings evidenced; card profit alone is insufficient"
    elif views is None or views < 200:
        buy, why = "DEFER", "No useful independent traffic verification"
    else:
        buy, why = "DD_PENDING", "Price and card earnings justify DD only; processor, GSC, cohorts, ownership and reserve still unverified"
    if verdict == "BUILD_REFERENCE":
        build = "REFERENCE_ONLY"
        reason = "Reusable utility concept, but no independently verified commercial SERP gap or conversions"
    elif verdict.startswith("DROP_"):
        build = "DROP"
        reason = "Low-quality source candidate; do not infer build viability from listing"
    elif verdict in ("SEO_BUY_DD", "BUY_DD"):
        build = "DD_PENDING"
        reason = "Benchmark keywords and competing tools independently; avoid cloning unverified seller thesis"
    else:
        build = "DEFER"
        reason = "No independent organic opportunity or differentiation test"
    # A listing can be in one research lane and only serve as reference for another.
    if buy == "DD_PENDING" and build == "DD_PENDING":
        category = "DUAL_DD"
    elif buy == "DD_PENDING":
        category = "BUY_DD"
    elif build == "DD_PENDING":
        category = "BUILD_DD"
    elif build == "REFERENCE_ONLY":
        category = "REFERENCE_ONLY"
    elif buy == "DROP" and build == "DROP":
        category = "DROP"
    else:
        category = "DEFER"
    return {
        "identity":row.get("identity"), "source":"FLIPPA", "title":row.get("title"),
        "reference":row.get("url") or "", "category":category,
        "buy":{"state":buy,"why":why},
        "build":{"state":build,"why":reason},
        "evidence":{
            "verified_direct_listing":is_detail, "price_observed_usd":price,
            "price_type":price_type, "price_within_cap":under_cap,
            "profit_card_usd_per_month":profit_card, "profit_independently_verified":False,
            "pageviews_claim_month":views, "ga_gsc_independently_verified":False,
            "buyer_transferability_verified":False, "build_serp_gap_verified":False,
        },
        "missing":([] if category == "DROP" else ["seller accounting/processor proofs","GSC/GA source access","attainable all-in price","independent product/SERP gap","migration and ownership proof"]),
    }

def qualify(day: str, seo: dict, flippa: dict, root: pathlib.Path = SEO_SCAN_ROOT, max_buy_usd: int = ACTIVE_BUY_LIMIT_USD) -> dict:
    semantic = read_semantic(day, root)
    provider_ok = seo.get("provider_status") == "PASS" and seo.get("terminal_status") == "PASS" and seo.get("source_complete") is True
    rows = []
    by_domain = semantic["by_domain"]
    for item in seo.get("items") or []:
        if not isinstance(item, dict) or not item.get("domain"):
            continue
        rows.append(seo_qualification(item, by_domain.get(str(item["domain"]).lower(), {}), provider_ok))
    for item in flippa.get("new") or []:
        if isinstance(item, dict) and item.get("identity"):
            rows.append(flippa_qualification(item, max_buy_usd))
    distinct = {}
    for row in rows:
        if row["identity"] not in distinct:
            distinct[row["identity"]] = row
    rows = list(distinct.values())
    counts = Counter(x["category"] for x in rows)
    priority = {"DUAL_DD":0,"BUY_DD":1,"BUILD_DD":2,"WATCH_GAP":3,"REFERENCE_ONLY":4,"DD_PENDING":5,"DEFER":6,"BLOCKED":7,"DROP":8}
    rows.sort(key=lambda x:(priority.get(x["category"],9), x["identity"]))
    # The scraper has no first-party earnings/access rights; upgrades to READY are forbidden.
    actionable = [x for x in rows if x["category"] in ("DUAL_DD","BUY_DD","BUILD_DD")]
    study = [x for x in rows if x["category"] in ("WATCH_GAP","REFERENCE_ONLY")]
    can_proceed = provider_ok and flippa.get("status") == "PASS"
    return {
        "schema":"build-buy-qualification-v1", "date":day,
        "status":"PASS" if can_proceed else "PARTIAL_BLOCKED",
        "semantic_dd_status":semantic["status"],"source_semantic_path":semantic["file"],
        "evaluated":len(rows), "by_source":dict(Counter(x["source"] for x in rows)),
        "counts":dict(counts),
        "approved_buy":0,"approved_build":0,
        "actionable_dd":actionable[:10], "study_queue":study[:10],
        "candidates":rows, "policy":{
            "max_buy_usd":max_buy_usd,
            "no_auto_bid_or_buy":True, "no_auto_build":True,
            "unknown_is_not_zero":True,"source_traffic_not_transferable":True,
            "listing_claims_not_verified_financials":True,
            "reference_only_cannot_be_promoted":True,
            "source_scanners_unchanged":True,
        },
    }
