#!/usr/bin/env python3
"""Production-oriented strict AutoContent entrypoint.

Draft with gpt-oss-20b for latency, audit with gpt-oss-120b, then enforce
machine-verifiable grounding before WordPress. Numeric facts must exist in the
raw crawled source text; common paired-unit conversions are sanity-checked;
ancillary social/video facts may not escape the final article/claim ledger.
"""
import os
import re

import autocontent_quality_runner as quality

engine = quality.engine
_original_balanced_pick = engine.balanced_pick
_original_issues = quality._deterministic_issues
_base_draft_call = quality._original_call_model
_CURRENT_ITEMS = []

BROAD_SYNTHESIS_PATTERNS = [
    r"\bincreasingly dominate\b",
    r"\btechnology (?:is|are) (?:advancing|evolving) (?:quickly|rapidly)\b",
    r"\bmanufacturers are overcoming\b",
    r"\bas more (?:makers|manufacturers|automakers)\b",
    r"\b(?:gap|difference)\b[^.!?]{0,80}\bcontinues? to narrow\b",
    r"\bgiving buyers a broader range\b",
]


def strict_balanced_pick(items, limit=12):
    return _original_balanced_pick(items, limit=min(int(limit), 6))


def fast_draft_call(items, focus, final_model):
    global _CURRENT_ITEMS
    _CURRENT_ITEMS = list(items)
    draft_model = os.environ.get("AUTOCONTENT_DRAFT_MODEL", "@cf/openai/gpt-oss-20b")
    return _base_draft_call(items, focus, draft_model)


def _clean_unit_pairs(text):
    text = str(text or "")

    def speed(match):
        mph = float(match.group(1))
        kmh = float(match.group(2))
        expected = mph * 1.609344
        if abs(kmh - expected) / max(expected, 1) > 0.04:
            return f"{match.group(1)} mph"
        return match.group(0)

    def distance(match):
        km = float(match.group(1))
        miles = float(match.group(2))
        expected = km * 0.621371
        if abs(miles - expected) / max(expected, 1) > 0.04:
            return f"{match.group(1)} km"
        return match.group(0)

    def torque(match):
        lbft = float(match.group(1))
        nm = float(match.group(2))
        expected = lbft * 1.355818
        if abs(nm - expected) / max(expected, 1) > 0.04:
            return f"{match.group(1)} lb-ft"
        return match.group(0)

    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*mph\s*\(\s*(\d+(?:\.\d+)?)\s*km/h\s*\)",
        speed,
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*km\s*\(\s*(\d+(?:\.\d+)?)\s*(?:mi|miles?)\s*\)",
        distance,
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*lb[- ]?ft\s*\(\s*(\d+(?:\.\d+)?)\s*nm\s*\)",
        torque,
        text,
        flags=re.I,
    )
    return text


def _sanitize_bad_unit_pairs(result):
    for field in ("title", "excerpt", "article_html"):
        if field in result:
            result[field] = _clean_unit_pairs(result.get(field))

    seo = result.setdefault("seo", {})
    if "meta_description" in seo:
        seo["meta_description"] = _clean_unit_pairs(seo.get("meta_description"))

    social = result.setdefault("social", {})
    for field in ("x", "linkedin", "instagram"):
        if field in social:
            social[field] = _clean_unit_pairs(social.get(field))

    video = result.setdefault("video", {})
    for field in ("hook", "script"):
        if field in video:
            video[field] = _clean_unit_pairs(video.get(field))
    if isinstance(video.get("shots"), list):
        video["shots"] = [_clean_unit_pairs(x) for x in video["shots"]]

    for check in result.get("claim_checks") or []:
        if isinstance(check, dict) and "claim" in check:
            check["claim"] = _clean_unit_pairs(check.get("claim"))
    return result


def _grounded_numeric_sentence(sentence, grounded_text):
    for token in quality._numeric_tokens(sentence):
        if quality._norm_text(token) not in grounded_text:
            return False
    return True


def _filter_text(text, grounded_text):
    text = str(text or "").strip()
    if not text:
        return ""
    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if part.strip()
    ]
    kept = [part for part in parts if _grounded_numeric_sentence(part, grounded_text)]
    return " ".join(kept).strip()


def _strip_speculative_sections(html):
    heading = r"(?:implications?|looking ahead|conclusion|the bigger picture|what (?:this|it) means)"
    pattern = rf"<h[23]>\s*{heading}[^<]*</h[23]>.*?(?=<h[23]>|$)"
    return re.sub(pattern, "", str(html or ""), flags=re.I | re.S).strip()


def _safe_meta(result):
    seo = result.setdefault("seo", {})
    base = re.sub(r"\s+", " ", str(result.get("excerpt") or seo.get("meta_description") or "")).strip()
    for marker in (" highlighting ", " showing ", " signaling ", " underscoring "):
        idx = base.lower().find(marker)
        if idx >= 60:
            base = base[:idx].rstrip(" ,;:-")
            break
    if len(base) > 155:
        title = re.sub(r"\s+", " ", str(result.get("title") or "")).strip()
        base = title if 25 <= len(title) <= 150 else base[:150].rsplit(" ", 1)[0]
    base = base.rstrip(" .,:;-")
    if not base:
        base = "Sourced automotive analysis based on the latest verified reporting"
    seo["meta_description"] = base[:154].rstrip(" ,;:-") + "."


def _sanitize_ancillary(result):
    result["article_html"] = _strip_speculative_sections(result.get("article_html"))
    _safe_meta(result)

    html = str(result.get("article_html") or "")
    claims = " ".join(
        str(check.get("claim") or "")
        for check in (result.get("claim_checks") or [])
        if isinstance(check, dict)
    )
    grounded = quality._norm_text(html + " " + claims)

    social = result.setdefault("social", {})
    for field in ("x", "linkedin", "instagram"):
        cleaned = _filter_text(social.get(field), grounded)
        substantive = re.sub(r"(?:^|\s)#[A-Za-z0-9_]+", "", cleaned).strip()
        if len(substantive) < 40:
            fallback = f"{result.get('title', 'Automotive update')} — sourced breakdown in the full article."
            cleaned = _filter_text(fallback, grounded)
        social[field] = cleaned or "Read the full sourced automotive analysis."

    video = result.setdefault("video", {})
    video["hook"] = _filter_text(video.get("hook"), grounded) or "What matters in this automotive story?"
    video["script"] = _filter_text(video.get("script"), grounded) or (
        "This short video summarizes the verified points in the accompanying article without adding new factual claims."
    )

    shots = video.get("shots") or []
    if isinstance(shots, list):
        cleaned_shots = [
            str(shot).strip()
            for shot in shots
            if str(shot).strip() and _grounded_numeric_sentence(str(shot), grounded)
        ]
        video["shots"] = cleaned_shots or [
            "Opening visual for the automotive story.",
            "Supporting vehicle or charging context.",
            "Closing frame pointing to the full sourced article.",
        ]
    return result


def _numeric_surface(text):
    text = str(text or "").lower().replace("\u202f", " ").replace("\u00a0", " ")
    text = text.replace(",", "")
    return re.sub(r"[^a-z0-9%£$€./+-]+", "", text)


def _source_numeric_issues(result):
    used = set(result.get("used_source_urls") or [])
    source_parts = []
    for item in _CURRENT_ITEMS:
        if item.get("url") in used:
            source_parts.extend(
                [
                    item.get("title", ""),
                    item.get("description", ""),
                    item.get("article_text", ""),
                ]
            )
    source_surface = _numeric_surface(" ".join(source_parts))
    if not source_surface:
        return ["Machine source-grounding has no raw text for the selected source URLs."]

    checks = " ".join(
        str(c.get("claim") or "")
        for c in (result.get("claim_checks") or [])
        if isinstance(c, dict)
    )
    social = result.get("social") or {}
    video = result.get("video") or {}
    factual_output = " ".join(
        [
            str(result.get("title") or ""),
            str(result.get("excerpt") or ""),
            str((result.get("seo") or {}).get("meta_description") or ""),
            str(result.get("article_html") or ""),
            checks,
            str(social.get("x") or ""),
            str(social.get("linkedin") or ""),
            str(social.get("instagram") or ""),
            str(video.get("hook") or ""),
            str(video.get("script") or ""),
            " ".join(str(x) for x in (video.get("shots") or [])),
        ]
    )

    issues = []
    for token in sorted(quality._numeric_tokens(factual_output)):
        surface = _numeric_surface(token)
        if surface and surface not in source_surface:
            issues.append(f"Numeric token is absent from raw selected source text: {token}")
    return issues


def _unit_consistency_issues(result):
    text = re.sub(r"<[^>]+>", " ", str(result.get("article_html") or ""))
    issues = []

    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*mph\s*\(\s*(\d+(?:\.\d+)?)\s*km/h\s*\)", text, re.I):
        mph, kmh = map(float, m.groups())
        expected = mph * 1.609344
        if abs(kmh - expected) / max(expected, 1) > 0.04:
            issues.append(f"Inconsistent speed conversion: {mph:g} mph vs {kmh:g} km/h")

    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*km\s*\(\s*(\d+(?:\.\d+)?)\s*(?:mi|miles?)\s*\)", text, re.I):
        km, miles = map(float, m.groups())
        expected = km * 0.621371
        if abs(miles - expected) / max(expected, 1) > 0.04:
            issues.append(f"Inconsistent distance conversion: {km:g} km vs {miles:g} mi")

    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*lb[- ]?ft\s*\(\s*(\d+(?:\.\d+)?)\s*nm\s*\)", text, re.I):
        lbft, nm = map(float, m.groups())
        expected = lbft * 1.355818
        if abs(nm - expected) / max(expected, 1) > 0.04:
            issues.append(f"Inconsistent torque conversion: {lbft:g} lb-ft vs {nm:g} Nm")

    return issues


def strict_issues(result):
    _sanitize_bad_unit_pairs(result)
    _sanitize_ancillary(result)
    issues = _original_issues(result)

    combined = " ".join(
        [
            str(result.get("article_html") or ""),
            str(result.get("excerpt") or ""),
            str((result.get("seo") or {}).get("meta_description") or ""),
        ]
    )
    for pattern in BROAD_SYNTHESIS_PATTERNS:
        if re.search(pattern, combined, re.I | re.S):
            issues.append(f"Broad unsupported synthesis remains: {pattern}")

    issues.extend(_source_numeric_issues(result))
    issues.extend(_unit_consistency_issues(result))
    return list(dict.fromkeys(issues))


engine.balanced_pick = strict_balanced_pick
quality._original_call_model = fast_draft_call
quality._deterministic_issues = strict_issues


if __name__ == "__main__":
    engine.main()
