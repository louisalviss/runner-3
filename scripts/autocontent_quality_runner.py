#!/usr/bin/env python3
"""Strict multi-pass editorial gate for the real AutoContent pipeline.

The generator is allowed to draft broadly. The QA stage must narrow the story,
ground every numeric claim, and pass deterministic checks before WordPress is
ever called. A failed gate produces no post.
"""
import json
import re

import autocontent_cloudflare_runner as proxy_runner

engine = proxy_runner.engine
_original_call_model = engine.call_model

NUM_RE = re.compile(
    r"(?<![\w])\$?\d+(?:[.,]\d+)*(?:\s*(?:%|kWh|kW|V|km|miles?|years?|minutes?|seconds?))?",
    re.I,
)
FORBIDDEN_PATTERNS = [
    r"<h[23]>\s*looking ahead\s*</h[23]>",
    r"\bwill likely\b",
    r"\blikely accelerate\b",
    r"\bwill continue to\b",
    r"\bwill only widen\b",
    r"\bgap .* widen .* electric\b",
    r"\baggressive scrappage incentives?\b",
    r"\bcase for .* incentives?\b",
    r"\bconsumers? who act now\b",
    r"\bbuyers? should\b",
    r"\bmessage is clear\b",
    r"\bfuture developments\b",
    r"\btotal cost(?:-per-mile| per mile)? .* lower than .* gasoline\b",
]


def _source_pack(items, max_chars=4300):
    blocks = []
    for i, item in enumerate(items, 1):
        body = item.get("article_text") or item.get("description") or ""
        blocks.append(
            f"SOURCE {i}\n"
            f"Publisher: {item['source']}\n"
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Published: {item.get('published', '')}\n"
            f"Text:\n{body[:max_chars]}\n"
        )
    return "\n".join(blocks)


def _parse_json_content(content):
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _smart_trim(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "."


def _norm_text(text):
    text = str(text or "").replace("\u202f", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def _numeric_tokens(text):
    return {re.sub(r"\s+", " ", x).strip().lower() for x in NUM_RE.findall(str(text or ""))}


def _normalize(result, items):
    by_num = {str(i): item for i, item in enumerate(items, 1)}
    allowed = {item["url"] for item in items}
    used = [u for u in result.get("used_source_urls", []) if u in allowed]

    html = str(result.get("article_html") or "")

    def repl(match):
        item = by_num.get(match.group(1))
        if not item:
            return ""
        if item["url"] not in used:
            used.append(item["url"])
        return f"({item['source']})"

    html = re.sub(r"\(\s*source\s+(\d+)\s*\)", repl, html, flags=re.I)
    html = re.sub(r"\[\s*source\s+(\d+)\s*\]", repl, html, flags=re.I)
    html = re.sub(r"\*([^*<>]{1,120})\*", r"\1", html)

    checks = []
    for check in result.get("claim_checks", []) or []:
        urls = [u for u in check.get("source_urls", []) if u in allowed]
        claim = str(check.get("claim") or "").strip()
        if not urls or not claim:
            continue
        for u in urls:
            if u not in used:
                used.append(u)
        checks.append({"claim": claim, "source_urls": urls})

    result["article_html"] = html
    result["used_source_urls"] = used
    result["claim_checks"] = checks
    result.setdefault("seo", {})
    result["seo"]["meta_description"] = _smart_trim(
        result["seo"].get("meta_description"), 155
    )
    result["excerpt"] = _smart_trim(result.get("excerpt"), 210)
    return result


def _deterministic_issues(result):
    issues = []
    used = result.get("used_source_urls") or []
    html = str(result.get("article_html") or "")
    checks = result.get("claim_checks") or []
    claim_text = " ".join(str(c.get("claim") or "") for c in checks)
    combined = " ".join(
        [
            html,
            str((result.get("social") or {}).get("x") or ""),
            str((result.get("social") or {}).get("linkedin") or ""),
            str((result.get("social") or {}).get("instagram") or ""),
            str((result.get("video") or {}).get("hook") or ""),
            str((result.get("video") or {}).get("script") or ""),
        ]
    )

    if not used:
        issues.append("No grounded source URL is used.")
    if len(used) > 2:
        issues.append(f"Story uses {len(used)} sources; strict mode allows at most 2 coherent sources.")
    if re.search(r"(?:\(|\[)\s*source\s+\d+", combined, re.I):
        issues.append("Internal source-number markers remain in output.")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, combined, re.I | re.S):
            issues.append(f"Unsupported/speculative pattern remains: {pattern}")

    if re.search(r"(?:cheaper|less|lower)[^.!?]{0,70}\bthan\s+(?:charging\s+)?at\s+home\b", combined, re.I):
        issues.append("Output claims public charging is cheaper than home charging; remove unless explicitly sourced and directionally consistent.")

    article_numbers = _numeric_tokens(html)
    claim_norm = _norm_text(claim_text)
    for token in sorted(article_numbers):
        if _norm_text(token) not in claim_norm:
            issues.append(f"Numeric token appears in article without a matching claim_check: {token}")

    article_and_claims = _norm_text(html + " " + claim_text)
    derived_numbers = _numeric_tokens(
        " ".join(
            [
                str((result.get("social") or {}).get("x") or ""),
                str((result.get("social") or {}).get("linkedin") or ""),
                str((result.get("social") or {}).get("instagram") or ""),
                str((result.get("video") or {}).get("hook") or ""),
                str((result.get("video") or {}).get("script") or ""),
            ]
        )
    )
    for token in sorted(derived_numbers):
        if _norm_text(token) not in article_and_claims:
            issues.append(f"Social/video introduces a numeric token not grounded in article/claim_checks: {token}")

    allowed_tags = {"p", "h2", "h3", "ul", "li", "strong"}
    tags = {m.group(1).lower() for m in re.finditer(r"</?([a-z0-9]+)\b", html, re.I)}
    bad_tags = sorted(tags - allowed_tags)
    if bad_tags:
        issues.append("Disallowed HTML tags in article: " + ", ".join(bad_tags))

    if len(str((result.get("seo") or {}).get("meta_description") or "")) > 155:
        issues.append("Meta description exceeds 155 characters.")
    if result.get("qa", {}).get("unsupported_numeric_claims", 0) != 0:
        issues.append("QA reports unsupported numeric claims.")
    return issues


def _audit_once(draft, items, model, prior_issues=None):
    allowed_urls = [item["url"] for item in items]
    issue_block = ""
    if prior_issues:
        issue_block = "\nTHE PREVIOUS QA ATTEMPT FAILED THESE MACHINE CHECKS:\n- " + "\n- ".join(prior_issues) + "\nFix every item.\n"

    prompt = f"""
You are the FINAL factual and editorial QA gate for an automotive publisher.
Rewrite the draft package against the supplied sources. Return JSON only with the SAME top-level schema.
{issue_block}
STRICT RULES:
1. Use ONLY facts explicitly supported by the supplied source text. No outside knowledge.
2. Choose ONE narrow news angle. Use at most 2 genuinely related source URLs. Do not combine battery tech, charger pricing, vehicle pricing and climate policy into one omnibus story.
3. Every numeric fact that remains in article_html must appear verbatim or equivalently in claim_checks with its exact supporting source URL.
4. Do not calculate new prices, savings, percentages, ranges or cost comparisons from separate numbers unless the source itself states that result.
5. Remove predictions, forecasts, policy advocacy, calls to action, unsupported trend language and broad claims about total cost of ownership.
6. Do not create a 'Looking ahead' section. Do not say outcomes 'will likely', 'will continue', or that a gap 'will widen'.
7. No '(source 7)' or similar internal markers. Mention a publisher naturally when attribution helps.
8. article_html may use ONLY p,h2,h3,ul,li,strong. No Markdown and no links; the engine adds a Sources section itself.
9. meta_description must be one complete natural sentence <=155 characters.
10. Social and video must use only facts already present and sourced in the corrected article. They may not introduce new comparisons.
11. Specifically check directional comparisons. Never say public fast charging is cheaper than home charging if the source says the opposite.
12. Avoid AI clichés: no 'message is clear', 'future is here', inflated conclusion, or generic prediction paragraph.
13. Keep 650-950 words. A focused, accurate single-source story is preferable to a forced multi-source story.
14. qa.unsupported_numeric_claims must be 0 only when all numeric facts are source-backed.

ALLOWED SOURCE URLS:
{json.dumps(allowed_urls, ensure_ascii=False)}

SOURCE TEXTS:
{_source_pack(items)}

PACKAGE TO FIX:
{json.dumps(draft, ensure_ascii=False)}
"""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a skeptical senior automotive editor and fact checker. Accuracy and internal consistency override breadth. Output valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.05,
        "max_tokens": 5000,
    }
    response = engine.requests.post(
        "https://models.github.ai/inference/chat/completions",
        json=payload,
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(f"Editorial QA failed {response.status_code}: {response.text[:1000]}")
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return _normalize(_parse_json_content(content), items)


def quality_call_model(items, focus, model):
    draft = _original_call_model(items, focus, model)
    corrected = _audit_once(draft, items, model)
    issues = _deterministic_issues(corrected)
    if issues:
        corrected = _audit_once(corrected, items, model, prior_issues=issues)
        issues = _deterministic_issues(corrected)
    if issues:
        raise RuntimeError("Strict editorial gate failed: " + " | ".join(issues[:20]))
    return corrected


engine.call_model = quality_call_model


if __name__ == "__main__":
    engine.main()
