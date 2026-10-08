#!/usr/bin/env python3
"""Fail-closed product-intent query selector for SeoTrends exact-SERP validation."""
from __future__ import annotations
import re

# Each profile identifies a narrow, replicable *product* search intent.
# Generic topical/news/brand keywords must never pass this selector.
PROFILES = (
    ("meeting_assistant",
     re.compile(r"(meeting assistant|meeting (transcrip|notes|minutes|summary)|automatic transcription)", re.I),
     re.compile(r"(meeting.{0,30}(minute|note|transcrib|summari|assistant|software)|transcri.{0,30}(tool|app|software|meeting|voice|audio|live)|voice.to.text|audio.to.text|(?:srt|vtt).{0,25}(convert|edit|generat|subtitle))", re.I)),
    ("customer_support_automation",
     re.compile(r"(customer (service|support|engagement)|whatsapp|chatbots?|chat assistants?)", re.I),
     re.compile(r"(whatsapp.{0,55}(automat|chatbot|api|integration|business tool|support tool)|(?:customer|support).{0,40}(chatbot|automation|ai assistant|chat software|support software)|live chat.{0,35}(software|tool|automation)|chatbot.{0,35}(customer|support|whatsapp))", re.I)),
    ("field_service_cmms",
     re.compile(r"(field service management|cmms|maintenance management|work orders?|technicians?.{0,20}assets)", re.I),
     re.compile(r"(work.order.{0,35}(generat|template|form|software|management|planner|schedul|app)|cmms.{0,30}(software|tool|system|program)|maintenance.{0,35}(software|checklist|planner|work.order)|field.service.{0,30}(software|management))", re.I)),
    ("legislative_intelligence",
     re.compile(r"(congressional (intelligence|witness)|lobbying data|legislative intelligence|government affairs)", re.I),
     re.compile(r"((lobby|lobbyist|lobbying).{0,40}(database|data|list|rank|group|spending|search|tracking|report)|(congressional|legislativ|committee|witness).{0,40}(database|data|search|tracker|history|voting records))", re.I)),
)
# Some broad industry words are not evidence of a *specific* product opportunity.
EXCLUDE = re.compile(r"(?:^|[\s])(news|breaking news|definition of|what is a|meaning of|election results|today's headlines)(?:$|[\s])", re.I)
GENERIC = {"best ai tools", "ai tools", "tools", "software", "analytics", "api", "business", "ai"}
def detect_profile(context: dict | None) -> tuple[str, re.Pattern] | None:
    if not context:
        return None
    text = " ".join(str(context.get(k) or "") for k in ("title", "description"))
    for name, category, query in PROFILES:
        if category.search(text):
            return name, query
    return None

def product_keyword_candidates(domain: str, raw: dict, context: dict | None, maxn: int = 6) -> list[dict]:
    profile = detect_profile(context)
    if not profile:
        return []  # no verified product mapping: fail closed, never topical SERP
    _, allow = profile
    label = domain.split(".")[0].lower().replace("-", "")
    seen, scored = set(), []
    for row in raw.get("rows") or []:
        phrase = str(row.get("phrase") or "").strip()
        norm = " ".join(phrase.lower().split())
        if not norm or norm in seen or norm in GENERIC or EXCLUDE.search(norm):
            continue
        seen.add(norm)
        compact = re.sub(r"[^a-z0-9]", "", norm)
        if label and label in compact:  # brand-led keywords are not transferable
            continue
        if not allow.search(norm):
            continue
        url = str(row.get("url") or "").lower()
        if "/news/" in url or "/press/" in url or "/blog/news/" in url:
            continue
        try:
            volume = int(float(row.get("volume") or 0))
            traffic = float(row.get("traffic") or 0)
            kd = float(row.get("keywordDifficulty") or 100)
        except (ValueError, TypeError):
            continue
        if volume < 30:
            continue
        # Real utility/transaction intent gets priority over high-volume articles.
        action = bool(re.search(r"(software|tool|generator|template|converter|database|lookup|automation|tracker|checklist|management|app|api|list|ranking|transcription)", norm))
        informational = any(part in url for part in ("/blog/", "/glossary/", "/news/"))
        score = (6 if action else 0) + (2 if not informational else 0) + min(volume / 1000, 3) + min(traffic / 15, 3) + max(0, (45-kd)/30)
        scored.append((score, traffic, volume, -kd, norm, phrase, url))
    scored.sort(reverse=True)
    return [
        {"keyword": phrase, "volume": vol, "traffic": traffic, "kd": -nkd, "url": url,
         "profile": profile[0], "product_intent_matched": True}
        for _, traffic, vol, nkd, norm, phrase, url in scored[:maxn]
    ]
