#!/usr/bin/env python3
"""Fail-closed product-intent query selector for SeoTrends exact-SERP validation."""
from __future__ import annotations
import re

# Each profile identifies a narrow, replicable *product* search intent.
# Generic topical/news/brand keywords must never pass this selector.
PROFILES = (
    ("meeting_assistant",
     re.compile(r"(meeting assistant|meeting (transcrip|notes|minutes|summary)|automatic transcription)", re.I),
     re.compile(r"(meeting.{0,30}(minute|note|transcrib|summari|assistant)|transcri.{0,30}(tool|app|software|meeting|voice|audio|live)|voice.to.text|audio.to.text|(?:srt|vtt).{0,25}(convert|edit|generat|subtitle))", re.I)),
    ("customer_support_automation",
     re.compile(r"(customer (service|support|engagement)|whatsapp|chatbots?|chat assistants?)", re.I),
     re.compile(r"(whatsapp.{0,55}(automat\w*|chatbot|\bapi\b|integration|\btools?\b)|(?:customer service|customer support|support team).{0,40}(chatbot|automation|ai assistant|chat software|support software)|live chat.{0,35}(software|tool|automation)|chatbot.{0,35}(customer service|customer support|whatsapp))", re.I)),
    ("field_service_cmms",
     re.compile(r"(field service management|cmms|maintenance management|work orders?|technicians?.{0,20}assets)", re.I),
     re.compile(r"(work.order.{0,35}(generat|template|form|software|management|planner|schedul|app)|cmms.{0,30}(software|tool|system|program)|maintenance.{0,35}(software|checklist|planner|work.order)|field.service.{0,30}(software|management))", re.I)),
    ("legislative_intelligence",
     re.compile(r"(congressional (intelligence|witness)|lobbying data|legislative intelligence|government affairs)", re.I),
     re.compile(r"((lobby|lobbyist|lobbying).{0,40}(database|data|list|rank|spending|search|tracking|report|platform)|(?:list|ranking|biggest|top).{0,30}(?:lobby|lobbyist|lobbying).{0,15}groups?|(congressional|legislativ|committee|witness).{0,40}(database|data|search|tracker|history|voting records))", re.I)),
)
# Some broad industry words are not evidence of a *specific* product opportunity.
EXCLUDE = re.compile(r"(?:^|[\s])(news|breaking news|definition of|what is a|meaning of|election results|today's headlines)(?:$|[\s])", re.I)

GENERIC_SITE_PRODUCT = re.compile(
    r"\b(software|saas|api|calculator|converter|generator|checker|estimator|planner|lookup|tracker|validator|viewer|editor|compressor|analytics|automation|tools?|platform|application|web app)\b", re.I)
PHYSICAL_ONLY = re.compile(
    r"\b(fpga|embedded boards?|hardware vendor|surveillance cameras?|physical devices?|portable saunas?|sauna tents?|airport|airline|manufacturer of|shop outdoor)\b", re.I)
GENERIC_QUERY_ACTION = re.compile(
    r"\b(software|api|calculator|converter|generator|checker|estimator|planner|lookup|tracker|validator|viewer|editor|compressor|analytics|automation|tools?|platform|apps?|templates?|schedul(?:er|ing)|dashboard)\b", re.I)
GENERIC_STOP = {
    "the","and","for","with","your","from","into","are","you","best","powerful",
    "business","solutions","solution","services","service","customers","customer",
    "software","saas","platform","tool","tools","app","apps","online","website",
    "management","support","modern","smart","digital","product","products","market",
    "cloud","system","systems","using","automatically","automated","teams","team",
    "simple","easy","data","technology","technical","businesses","free","company",
    "intelligent","fast","make","create","build","leading","welcome","home","join",
    "more","today","all","and","new","this","that","what","about","artificial",
    "intelligence","users","people","benefits","features","solutions","solutions"
}
def generic_product_profile(context: dict | None, domain: str = "") -> tuple[str,re.Pattern] | None:
    if not context: return None
    title=str(context.get('title') or '').lower()
    desc=str(context.get('description') or '').lower()
    combined=title+" "+desc
    if not GENERIC_SITE_PRODUCT.search(combined): return None
    # A hardware/ecommerce site mentioning automation isn't automatically a utility.
    if PHYSICAL_ONLY.search(combined) and not re.search(r"\b(software|saas|api|web app)\b",combined):
        return None
    label=domain.lower().split('.')[0].replace('-','')
    title_tokens=re.findall(r"[a-z][a-z0-9]{2,}", title)
    desc_tokens=re.findall(r"[a-z][a-z0-9]{2,}", desc)
    title_anchors=[x for x in title_tokens if x not in GENERIC_STOP and x!=label]
    desc_anchors=[x for x in desc_tokens if x not in GENERIC_STOP and x!=label]
    anchors=list(dict.fromkeys(title_anchors+desc_anchors))[:28]
    if not anchors: return None
    return "generic_product", re.compile(r"\b(?:"+"|".join(re.escape(x) for x in anchors)+r")\b",re.I)

GENERIC = {"best ai tools", "ai tools", "tools", "software", "analytics", "api", "business", "ai"}
def detect_profile(context: dict | None, domain: str = "") -> tuple[str, re.Pattern] | None:
    if not context:
        return None
    text = " ".join(str(context.get(k) or "") for k in ("title", "description"))
    for name, category, query in PROFILES:
        if category.search(text):
            return name, query
    return generic_product_profile(context, domain)

def product_keyword_candidates(domain: str, raw: dict, context: dict | None, maxn: int = 6) -> list[dict]:
    profile = detect_profile(context, domain)
    if not profile:
        return []  # no verified product mapping: fail closed, never topical SERP
    _, allow = profile
    label = domain.split(".")[0].lower().replace("-", "")
    seen, scored = set(), []
    for row in raw.get("rows") or []:
        phrase = str(row.get("phrase") or "").strip()
        norm = " ".join(phrase.lower().split())
        if not norm or len(norm.split()) > 12 or norm in seen or norm in GENERIC or EXCLUDE.search(norm):
            continue
        seen.add(norm)
        compact = re.sub(r"[^a-z0-9]", "", norm)
        if label and label in compact:  # brand-led keywords are not transferable
            continue
        if not allow.search(norm):
            continue
        if profile[0]=='generic_product' and not GENERIC_QUERY_ACTION.search(norm):
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
        action = bool(re.search(r"\b(software|tools?|generator|templates?|converter|database|lookup|automation|tracker|checklist|management|app|api|list|ranking|transcription)\b", norm))
        informational = any(part in url for part in ("/blog/", "/glossary/", "/news/"))
        direct = bool(re.search(r"\b(generator|software|automation|converter|database|tracker|platform|templates?|tools?|lookup|management)\b", norm))
        direct_bonus = (7 if re.search(r"\b(generator|software|automation|database|platform)\b", norm) else (5 if direct else 0))
        informational_phrase = bool(re.search(r"\b(benefits of|guide|meaning|explained|how to|challenges|what is|is .+ a)\b", norm))
        score = direct_bonus + (2 if not informational else 0) + min(volume / 1000, 3) + min(traffic / 15, 3) + max(0, (45-kd)/30) - max(0,len(norm.split())-7)*0.7 - (5 if informational_phrase else 0)
        if profile[0] == 'field_service_cmms':
            if 'work order generator' in norm: score += 9
            elif 'generator' in norm: score -= 9  # electrical generator is not software
        if profile[0] == 'legislative_intelligence' and re.search(r"\b(platform|database|lookup|research tool|tracker)\b",norm):score+=5
        if profile[0] == 'meeting_assistant' and 'meeting minutes software' in norm: score += 5
        scored.append((score, traffic, volume, -kd, norm, phrase, url))
    scored.sort(reverse=True)
    out, used_urls = [], set()
    for _, traffic, vol, nkd, norm, phrase, url in scored:
        # Two paraphrases on one landing page do not justify two provider queries.
        canonical_url=url.split("?")[0].rstrip("/")
        if canonical_url and canonical_url in used_urls: continue
        if canonical_url: used_urls.add(canonical_url)
        out.append({"keyword": phrase, "volume": vol, "traffic": traffic, "kd": -nkd, "url": url,
                    "profile": profile[0], "product_intent_matched": True})
        if len(out)>=maxn:break
    return out
