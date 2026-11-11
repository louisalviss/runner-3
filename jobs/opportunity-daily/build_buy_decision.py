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
from urllib.parse import urlsplit
from ai_substitution_gate import review_for_candidate
from reviewed_cutover import reviewed_processed_ids, is_reviewed_prior_listing

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

def _is_public_https(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        p = urlsplit(url)
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def local_search_intent_review(semantic: dict, product_intent: bool) -> dict:
    """Source-linked *review queue*, not proof of demand or permission to BUILD.

    Native-language keyword comparisons are considered only for already
    product-intent-matched candidates. This function never calls Semrush/SERP.
    """
    raw = semantic.get("local_search_intent")
    if not isinstance(raw, dict) or not isinstance(raw.get("markets"), list):
        return {"status": "NOT_REVIEWED", "review_priority": "UNCHANGED", "markets_review_ready": 0}
    if not product_intent:
        return {"status": "UPSTREAM_INTENT_UNVERIFIED", "review_priority": "UNCHANGED",
                "markets_review_ready": 0}
    ready = []
    for m in raw["markets"][:8]:  # bounded, human-auditable review
        if not isinstance(m, dict):
            continue
        country = str(m.get("country") or "").upper()
        language = str(m.get("language") or "").strip().lower()
        native = str(m.get("native_keyword") or "").strip()
        literal = str(m.get("literal_translation_keyword") or "").strip()
        if len(country) != 2 or not country.isalpha() or not (2 <= len(language) <= 12):
            continue
        if not native or not literal or native.casefold() == literal.casefold():
            continue
        native_volume = positive_number(m.get("native_volume"))
        translated_volume = positive_number(m.get("literal_translation_volume"))
        if native_volume is None or translated_volume is None or native_volume <= translated_volume:
            continue
        if m.get("matches_product_intent") is not True:
            continue
        if len(str(m.get("unmet_need") or "").strip()) < 20:
            continue
        if not str(m.get("keyword_source_ref") or "").strip() or not str(m.get("serp_source_ref") or "").strip():
            continue
        urls = m.get("serp_result_urls")
        if not isinstance(urls, list):
            continue
        valid_urls = {u.strip() for u in urls if _is_public_https(u)}
        if len(valid_urls) < 5:
            continue
        try:
            observed = datetime.strptime(str(m.get("serp_checked_at") or ""), "%Y-%m-%d").date()
            if observed > datetime.now(ZoneInfo("UTC")).date():
                continue
        except ValueError:
            continue
        ready.append({"country": country, "language": language, "native_keyword": native,
                      "native_volume": native_volume, "literal_translation_volume": translated_volume,
                      "serp_checked_at": observed.isoformat()})
    return {"status": "REVIEW_READY" if ready else "EVIDENCE_INCOMPLETE",
            "review_priority": "EVIDENCE_REVIEW_ONLY" if ready else "UNCHANGED",
            "markets_review_ready": len(ready), "markets": ready,
            "independently_validated": False}


def verified_site_product_review(semantic: dict, domain: str, user_job: str) -> bool:
    """Only a source-linked website/product examination can unlock business DD.

    The reviewer must separately inspect the cited pages; structured claims
    alone do not prove market demand or product performance.
    """
    review = semantic.get("site_product_review")
    if not isinstance(review, dict) or review.get("status") != "REVIEWED":
        return False
    if str(review.get("domain") or "").casefold() != domain.casefold():
        return False
    if str(review.get("user_job") or "").strip().casefold() != user_job.strip().casefold():
        return False
    for field in ("buyer", "product_type", "actual_workflow", "actual_output",
                  "monetization", "replication_risk", "proposed_small_utility"):
        if len(str(review.get(field) or "").strip()) < 15:
            return False
    if review.get("small_utility_feasibility") != "SUPPORTED":
        return False
    pages = review.get("pages")
    if not isinstance(pages, list) or not 3 <= len(pages) <= 6:
        return False
    types = set()
    urls = set()
    for page in pages:
        if not isinstance(page, dict):
            return False
        url = page.get("url")
        if not _is_public_https(url):
            return False
        host = (urlsplit(url).hostname or "").casefold()
        if host != domain.casefold() and not host.endswith("." + domain.casefold()):
            return False
        if url in urls:
            return False
        urls.add(url)
        kind = page.get("kind")
        if kind not in ("home", "product", "pricing", "demo"):
            return False
        types.add(kind)
        if len(str(page.get("finding") or "").strip()) < 20:
            return False
        if len(str(page.get("source_ref") or "").strip()) < 12:
            return False
    if not {"home", "product"}.issubset(types) or not types.intersection({"pricing", "demo"}):
        return False
    return True


def verified_candidate_wedge(semantic: dict, domain: str = "") -> bool:
    """Fail-closed DD admission: the same bounded user task must have four sourced proofs.

    This is eligibility for manual business DD, never BUILD approval. Merely
    checking Exact SERP, counting competitor traffic, or setting a verdict is
    insufficient. No external calls are performed here.
    """
    wedge = semantic.get("candidate_wedge")
    if not isinstance(wedge, dict):
        return False
    if len(str(wedge.get("user_job") or "").strip()) < 12:
        return False
    if not str(wedge.get("query_cluster") or "").strip() or not str(wedge.get("target_market") or "").strip():
        return False
    for key in ("commercial_demand", "underserved_exact_serp", "bounded_build_scope", "credible_monetization"):
        evidence = wedge.get(key)
        if not isinstance(evidence, dict) or evidence.get("verified") is not True:
            return False
        if len(str(evidence.get("evidence_ref") or "").strip()) < 12:
            return False
        if len(str(evidence.get("finding") or "").strip()) < 16:
            return False
    return verified_site_product_review(semantic, domain, str(wedge["user_job"]))


def seo_qualification(row: dict, semantic: dict, provider_ok: bool, as_of: str | None = None) -> dict:
    domain = str(row.get("domain") or "").lower()
    semantic_verdict = str(semantic.get("semantic_verdict") or "")
    # Preserve the source scanner's terminal verdict even if a separate
    # semantic note disagrees. Legacy source-less fixtures still read the note.
    source_terminal = str(row.get("terminal_verdict") or "")
    semantic_terminal = str(semantic.get("terminal_verdict") or "")
    terminal = source_terminal or semantic_terminal
    raw = str(row.get("verdict") or "")
    # Only the scanner may establish product intent. Semantic DD corroborates it.
    product_intent = row.get("product_intent_checked") is True
    semantic_product_intent = semantic.get("product_intent_checked") is True
    if raw in ("BLOCKED_PROVIDER", "BLOCKED_SERP") or terminal == "BLOCKED" or not provider_ok:
        build, why = "BLOCKED", "Semrush or exact-SERP evidence incomplete; never infer zero demand"
    elif raw == "DROP" or terminal == "DROP" or semantic_verdict == "DROP_THIS_CYCLE":
        build, why = "DROP", str(semantic.get("business_reason") or row.get("reason") or "Terminal rejection")[:300]
    elif (semantic_verdict == "WATCH_NARROW_GAP" and product_intent
          and semantic_product_intent and terminal == "WATCH"):
        build, why = "WATCH_GAP", str(semantic.get("business_reason") or "Gap not yet validated")[:300]
    elif semantic_verdict == "DEFER_UNMATCHED_INTENT" or not product_intent:
        build, why = "DEFER", "No independently matched commercially useful product-intent keyword"
    elif (semantic_verdict == "QUALIFIED_DD" and product_intent
          and source_terminal == semantic_terminal == "WATCH"
          and row.get("product_intent_checked") is True
          and semantic.get("product_intent_checked") is True
          and raw in ("WATCH_DD", "SEO_BUILD_TEST")
          and row.get("serp_gate") in ("SERP_DD_PASS", "WATCH_COMPETITION")
          and verified_candidate_wedge(semantic, domain)):
        build, why = "DD_PENDING", "Four sourced business-case gates passed; manual DD still required, no BUILD approval"
    else:
        build, why = "DEFER", "Source traffic or Exact SERP alone is not a business opportunity; verify demand, underserved task, bounded build scope and monetization"
    ai_review = review_for_candidate(domain, semantic.get("ai_substitution_review"), as_of)
    if build not in ("DROP", "BLOCKED"):
        if ai_review["status"] == "HIGH":
            build, why = "DROP", "Reviewed answer-only AI substitution: do not BUILD a click-dependent response site"
        elif build == "DD_PENDING" and ai_review["status"] != "RESILIENT":
            build, why = "DEFER", "AI-substitution risk has not been independently reviewed; no manual BUILD DD promotion"
    local_intent = local_search_intent_review(semantic, product_intent)
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
            "semantic_product_intent_corroborated": semantic_product_intent,
            "terminal_gate": terminal or raw,
            "semantic_gate": semantic_verdict or "NOT_AVAILABLE", "semantic_review_completed": bool(semantic_verdict),
            "ai_substitution_status": ai_review["status"],
            "ai_substitution_reviewed": ai_review["reviewed"],
            "ai_substitution_source_refs": ai_review["source_refs"],
            "revenue_verified": False,
            "differentiated_solution_verified": False,
            "candidate_wedge_evidence_complete": verified_candidate_wedge(semantic, domain),
            "site_product_review_complete": verified_site_product_review(semantic, domain,
                str((semantic.get("candidate_wedge") or {}).get("user_job") or "")),
            "next_gate": ("AI_SUBSTITUTION_REJECTED" if ai_review["status"] == "HIGH" else
                          "AI_SUBSTITUTION_REVIEW" if build == "DEFER"
                              and verified_candidate_wedge(semantic, domain) else
                          "FOUR_PART_CANDIDATE_WEDGE_DD" if build == "DEFER" else
                          "MANUAL_BUSINESS_DD"),
            "local_search_intent": local_intent,
        },
        "missing": ([] if build in ("DROP", "BLOCKED") else
                    ["demonstrated unmet need", "replicable search gap", "credible monetization/conversion"]
                    + ([] if local_intent["status"] == "REVIEW_READY" else
                       ["native-language keyword and country-specific SERP evidence"])
            + ([] if ai_review["status"] in ("HIGH", "RESILIENT") else
                       ["AI substitution and independent non-answer workflow review"])),
    }


def verified_flippa_site_review(row: dict) -> bool:
    """Bounded asset/website inspection for a specific Flippa listing.

    This only checks a source-linked evidence packet's shape. Reviewers must
    independently open the referenced pages and validate seller transferability.
    A similar-looking domain in the title never establishes asset identity.
    """
    review = row.get("site_product_review")
    listed = str(row.get("id") or str(row.get("identity") or "").removeprefix("flippa:"))
    domain = str(row.get("verified_asset_domain") or "").strip().lower().removeprefix("www.")
    if not (str(row.get("identity") or "") == "flippa:" + listed
            and listed.isdecimal() and row.get("verified_detail") is True
            and row.get("asset_domain_verified") is True
            and row.get("asset_domain_source_kind") in ("AUTHENTICATED_LIVE", "DIRECT_LISTING_CURRENT")
            and len(str(row.get("asset_domain_source_ref") or "").strip()) >= 12):
        return False
    if not domain or any(ch in domain for ch in ("/", "@", ":", "?", "#")) or "." not in domain:
        return False
    if not isinstance(review, dict) or review.get("status") != "REVIEWED":
        return False
    if str(review.get("listing_id") or "") != listed:
        return False
    if str(review.get("asset_domain") or "").strip().lower().removeprefix("www.") != domain:
        return False
    if review.get("asset_type") not in ("saas", "content_site", "utility", "ecommerce", "directory", "app"):
        return False
    for field in ("buyer", "asset_offer", "actual_workflow", "observed_conversion_path",
                  "monetization_mechanism", "operator_dependencies", "transfer_risks"):
        if len(str(review.get(field) or "").strip()) < 15:
            return False
    pages = review.get("pages")
    if not isinstance(pages, list) or not 2 <= len(pages) <= 6:
        return False
    kinds, urls = set(), set()
    for page in pages:
        if not isinstance(page, dict) or not _is_public_https(page.get("url")):
            return False
        url = page["url"]
        hostname = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        if hostname != domain and not hostname.endswith("." + domain):
            return False
        if url in urls or page.get("kind") not in (
                "home", "product", "content", "offer", "monetization", "pricing", "demo"):
            return False
        if len(str(page.get("finding") or "").strip()) < 20:
            return False
        if len(str(page.get("source_ref") or "").strip()) < 12:
            return False
        urls.add(url)
        kinds.add(page["kind"])
    return "home" in kinds and bool(kinds.intersection(
        ("product", "content", "offer", "monetization", "pricing", "demo")))


def verified_flippa_build_gap(row: dict, site_ok: bool) -> bool:
    """A seller's website is only a reference; BUILD needs independent whitespace."""
    gap = row.get("independent_build_gap")
    if not site_ok or not isinstance(gap, dict):
        return False
    if len(str(gap.get("user_job") or "").strip()) < 12:
        return False
    for part in ("matched_keyword", "exact_serp_gap", "small_utility_scope", "revenue_path"):
        item = gap.get(part)
        if not isinstance(item, dict) or item.get("verified") is not True:
            return False
        if len(str(item.get("source_ref") or "").strip()) < 12:
            return False
        if len(str(item.get("finding") or "").strip()) < 20:
            return False
    return True

def flippa_qualification(row: dict, max_buy_usd: int, as_of: str | None = None) -> dict:
    is_detail = row.get("verified_detail") is True
    site_ok = verified_flippa_site_review(row)
    build_gap_ok = verified_flippa_build_gap(row, site_ok)
    domain_proved = bool(row.get("asset_domain_verified") is True
        and row.get("asset_domain_source_kind") in ("AUTHENTICATED_LIVE", "DIRECT_LISTING_CURRENT")
        and row.get("verified_asset_domain"))
    public_review = row.get("site_product_review") if isinstance(row.get("site_product_review"), dict) else {}
    capture_state = str(public_review.get("status") or "NOT_CAPTURED")
    page_count = len(public_review.get("pages") or []) if isinstance(public_review.get("pages"), list) else 0
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
    elif not site_ok:
        buy = "SITE_REVIEW_PENDING"
        why = ("Verify the exact Flippa listing-to-asset domain first"
               if not domain_proved else
               "Public pages captured; product, revenue path and transfer risks need semantic review"
               if capture_state == "CAPTURED_PUBLIC_PENDING_REVIEW" else
               "Verified asset domain; public website capture or material is incomplete")
    else:
        buy, why = "DD_PENDING", "Asset website reviewed; price, processor earnings, GSC, cohorts, ownership and transferability still require independent DD"
    if verdict == "BUILD_REFERENCE":
        build = "REFERENCE_ONLY"
        reason = "Reusable utility concept, but no independently verified commercial SERP gap or conversions"
    elif verdict.startswith("DROP_"):
        build = "DROP"
        reason = "Low-quality source candidate; do not infer build viability from listing"
    elif verdict in ("SEO_BUY_DD", "BUY_DD"):
        if build_gap_ok:
            build = "DD_PENDING"
            reason = "Independent product/keyword/SERP gap supports manual BUILD DD only"
        elif not site_ok:
            build = "SITE_REVIEW_PENDING"
            reason = ("Review captured public website material and exact independent product gap"
                      if capture_state == "CAPTURED_PUBLIC_PENDING_REVIEW" else
                      "Inspect exact verified asset; seller claims are not a replicable opportunity")
        else:
            build = "DEFER"
            reason = "Website understood but independent keyword gap, scope and monetization not established"
    else:
        build = "DEFER"
        reason = "No independent organic opportunity or differentiation test"
    ai_review = review_for_candidate(str(row.get("identity") or ""),
                                     row.get("ai_substitution_review"), as_of)
    if ai_review["status"] == "HIGH":
        buy, why = "DROP", "Reviewed answer-only site dependent on visits AI may replace; reject BUY"
        build, reason = "DROP", "AI can answer the user job; no verified durable workflow moat for BUILD"
    elif ai_review["status"] != "RESILIENT":
        if buy == "DD_PENDING":
            buy, why = "SITE_REVIEW_PENDING", "AI substitution review required before BUY DD"
        if build == "DD_PENDING":
            build, reason = "SITE_REVIEW_PENDING", "AI substitution review required before BUILD DD"
    # A listing can be in one research lane and only serve as reference for another.
    if buy == "DD_PENDING" and build == "DD_PENDING":
        category = "DUAL_DD"
    elif buy == "DD_PENDING":
        category = "BUY_DD"
    elif build == "DD_PENDING":
        category = "BUILD_DD"
    elif build == "REFERENCE_ONLY":
        category = "REFERENCE_ONLY"
    elif buy == "SITE_REVIEW_PENDING" or build == "SITE_REVIEW_PENDING":
        category = "SITE_DD_PENDING"
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
            "buyer_transferability_verified":False,
            "ai_substitution_status":ai_review["status"],
            "ai_substitution_reviewed":ai_review["reviewed"],
            "ai_substitution_source_refs":ai_review["source_refs"],
            "asset_site_review_complete":site_ok, "build_serp_gap_verified":build_gap_ok,
            "asset_domain_identity_verified": domain_proved,
            "verified_asset_domain": str(row.get("verified_asset_domain") or "") if domain_proved else "",
            "site_capture_status": capture_state if domain_proved else "DOMAIN_UNVERIFIED",
            "site_pages_captured": page_count if domain_proved else 0,
        },
        "missing":([] if category == "DROP" else
            ([] if domain_proved else ["source-linked listing-to-asset domain"])
            + ([] if capture_state == "CAPTURED_PUBLIC_PENDING_REVIEW" or site_ok else ["public website/material capture"])
            + ([] if site_ok else ["independent semantic product/monetization/operational DD"])
            + ["seller accounting/processor proofs", "GSC/GA source access",
               "attainable all-in price", "independent product/SERP gap",
               "migration and ownership proof"]
            + ([] if ai_review["status"] in ("HIGH", "RESILIENT") else
               ["AI substitution and independent non-answer workflow review"])),
    }

def qualify(day: str, seo: dict, flippa: dict, root: pathlib.Path = SEO_SCAN_ROOT, max_buy_usd: int = ACTIVE_BUY_LIMIT_USD) -> dict:
    semantic = read_semantic(day, root)
    provider_ok = seo.get("provider_status") == "PASS" and seo.get("terminal_status") == "PASS" and seo.get("source_complete") is True
    rows = []
    by_domain = semantic["by_domain"]
    for item in seo.get("items") or []:
        if not isinstance(item, dict) or not item.get("domain"):
            continue
        rows.append(seo_qualification(item, by_domain.get(str(item["domain"]).lower(), {}), provider_ok, as_of=day))
    archived_ids=reviewed_processed_ids(day)
    archived_suppressed=0
    for item in flippa.get("new") or []:
        if isinstance(item, dict) and item.get("identity"):
            listing_identity=str(item.get("identity") or "")
            if is_reviewed_prior_listing(listing_identity, day):
                archived_suppressed+=1
                continue
            rows.append(flippa_qualification(item, max_buy_usd, as_of=day))
    distinct = {}
    for row in rows:
        if row["identity"] not in distinct:
            distinct[row["identity"]] = row
    rows = list(distinct.values())
    counts = Counter(x["category"] for x in rows)
    priority = {"DUAL_DD":0,"BUY_DD":1,"BUILD_DD":2,"SITE_DD_PENDING":3,"WATCH_GAP":4,"REFERENCE_ONLY":5,"DD_PENDING":6,"DEFER":7,"BLOCKED":8,"DROP":9}
    rows.sort(key=lambda x:(priority.get(x["category"],9), x["identity"]))
    # The scraper has no first-party earnings/access rights; upgrades to READY are forbidden.
    actionable = [x for x in rows if x["category"] in ("DUAL_DD","BUY_DD","BUILD_DD")]
    study = [x for x in rows if x["category"] in ("SITE_DD_PENDING", "WATCH_GAP", "REFERENCE_ONLY")]
    can_proceed = provider_ok and flippa.get("status") == "PASS"
    return {
        "schema":"build-buy-qualification-v1", "date":day,
        "status":"PASS" if can_proceed else "PARTIAL_BLOCKED",
        "semantic_dd_status":semantic["status"],"source_semantic_path":semantic["file"],
        "evaluated":len(rows), "by_source":dict(Counter(x["source"] for x in rows)),
        "archived_reviewed_suppressed":archived_suppressed,
        "reviewed_prior_cohort_size":len(archived_ids),
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
            "ai_substitution_review_required_before_actionable_dd":True,
            "ai_review_is_not_financial_proof":True,
            "reviewed_cohort_not_reintroduced_as_new_buy_build":True,
        },
    }
