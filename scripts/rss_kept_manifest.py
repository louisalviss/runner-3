#!/usr/bin/env python3
import argparse
import json
import re
import unicodedata
from pathlib import Path

DIRECT_KEYS = {"hoquoctuan", "vnhacker"}
KEEP_DEFAULT = {
    "tinhte", "fulcrum", "noema", "projectsyndicate", "economist",
    "grimlogs", "scientificamerican", "quanta"
}

PROMO_PATTERNS = [
    r"\bsăn sale\b", r"\bdeal\b", r"\bgiảm giá\b", r"\bmã giảm\b", r"\bcoupon\b",
    r"\bbình chọn\b", r"better choice awards", r"\bquà tặng\b", r"\bgiftcode\b",
    r"\bkhuyến mãi\b", r"\bmua .* nhận\b", r"\bưu đãi\b", r"\bmiễn phí\b"
]
GENK_LOW_SIGNAL = [
    r"nữ đại gia", r"nam diễn viên", r"nữ diễn viên", r"hoa hậu", r"hot girl", r"body", r"gây sốt",
    r"mẫu xe tay ga", r"xe tay ga .*giá", r"ra mắt tai nghe", r"thương hiệu được người việt tin dùng",
    r"hàng nhật bãi", r"tửu lượng", r"trò đùa quái gở", r"giá iphone .*chạm đáy", r"danh sách private",
    r"trải nghiệm loạt công nghệ .* cuối tuần", r"esports world cup", r"giành cúp vô địch esports",
    r"mặt xinh", r"khóa môi", r"phim ngắn.*nam diễn viên", r"săn sale"
]
GENK_SIGNAL = [
    r"\bai\b", r"trí tuệ nhân tạo", r"chip", r"semiconductor", r"ram", r"vram", r"ssd", r"cpu", r"gpu",
    r"nvidia", r"amd", r"intel", r"apple", r"iphone", r"mac mini", r"mac studio", r"microsoft", r"windows",
    r"google", r"openai", r"chatgpt", r"deepseek", r"robot", r"quantum", r"lượng tử", r"công nghệ", r"khoa học",
    r"nghiên cứu", r"ung thư", r"bluetooth", r"chrome", r"trình duyệt", r"bảo mật", r"hack", r"mã độc",
    r"dữ liệu", r"vneid", r"bhxh", r"bảo hiểm xã hội", r"quy định", r"nghị định", r"pháp luật", r"cổ phiếu",
    r"bitcoin", r"crypto", r"thị trường", r"kinh tế", r"doanh nghiệp", r"ceo", r"sản xuất", r"công nghiệp",
    r"năng lượng", r"nhiên liệu", r"hạt nhân", r"xe điện", r"ev\b", r"pin", r"máy ảnh", r"hasselblad",
    r"camera", r"smartphone", r"galaxy", r"exynos", r"snapdragon", r"xring", r"xiaomi", r"huawei",
    r"internet", r"viễn thông", r"server", r"máy chủ", r"data center", r"trung quốc", r"nhật bản", r"mỹ"
]
GAMEK_LOW_SIGNAL = [
    r"hot girl", r"cosplay", r"streamer", r"livestream", r"triệu view", r"fan nam", r"nữ diễn viên",
    r"người phụ nữ", r"nữ tài xế", r"mỹ nhân", r"hoa hậu", r"body", r"gia thế", r"hải sapa",
    r"fandom", r"blackpink", r"miễn phí", r"giftcode", r"top \d+", r"sale", r"khuyến mãi",
    r"tip hẳn", r"ảnh nghìn like", r"nhung nhớ", r"em gái", r"hồng hài nhi", r"phim hàn",
    r"\bdrama\b", r"bạn gái", r"bạn trai", r"người yêu", r"đời tư", r"hẹn hò", r"réo tên",
    r"lo sốt vó", r"tình ái", r"chia tay", r"kết hôn", r"lấy chồng", r"lấy vợ", r"quỳnh alee",
    r"lai bâng", r"fan .* lo", r"fan .* nhớ", r"fan .* réo"
]
GAMEK_SIGNAL = [
    r"black myth", r"game science", r"steam", r"playstation", r"xbox", r"nintendo", r"epic games", r"unity",
    r"unreal engine", r"phát hành", r"ra mắt", r"trì hoãn", r"doanh thu", r"studio", r"nhà phát triển",
    r"nhà phát hành", r"thâu tóm", r"acquisition", r"layoff", r"sa thải", r"công nghệ", r"engine", r"gpu",
    r"\bai\b", r"bom tấn", r"where winds meet", r"gta", r"elden ring", r"wukong", r"zhong kui"
]
VHH_SIGNAL = [
    "đầu tư", "chứng khoán", "cổ phiếu", "vic", "vnindex", "vn-index", "yield", "trái phiếu",
    "btc", "bitcoin", "crypto", "vàng", "lãi suất", "quỹ", "dca", "kinh tế", "thị trường",
    "ngân hàng", "fed", "usd", "tỷ giá", "regulation", "công nghệ", "ai"
]
ATLANTIC_EXCLUDE = [r"/press-releases/", r"^the atlantic announces\b", r"/summer-songs-", r"\bsummer songs\b"]
ATLANTIC_KEEP_URL = [
    r"/technology/", r"/science/", r"/health/", r"/ideas/", r"/politics/", r"/national-security/",
    r"/international/", r"/education/", r"/business/", r"/economy/", r"/climate/"
]
ATLANTIC_SIGNAL = [
    r"trump", r"iran", r"khamenei", r"qatar", r"israel", r"china", r"russia", r"ukraine", r"war\b",
    r"politic", r"policy", r"government", r"econom", r"business", r"market", r"college", r"university",
    r"education", r"technology", r"password", r"login", r"\bai\b", r"science", r"health", r"climate",
    r"data center", r"immigration", r"democracy", r"social", r"middle class", r"downwardly mobile",
    r"hitler", r"antisemit", r"jews?"
]

SOURCE_PRIORITY = {
    "economist": 100, "quanta": 98, "scientificamerican": 96, "projectsyndicate": 94,
    "fulcrum": 92, "noema": 90, "nghiencuuquocte": 88, "theatlantic": 86,
    "grimlogs": 82, "vohoanghac": 80, "tinhte": 65, "genk": 60, "gamek": 45,
}

# Patterns are ASCII because explicit_topic_key() normalizes accents before matching.
TOPIC_RULES = [
    ("spacex-louisiana-spaceport", [r"spacex", r"(?:spaceport|starbase|louisiana)"]),
    ("meta-youth-social-harms-settlement", [r"meta", r"(?:under.?18|children|tre em|youth)", r"(?:settle|lawsuit|harm|gioi han|18 billion|\$18|dong y)"]),
    ("dolly-parton-remembrance", [r"dolly parton"]),
    ("apple-mac-mini-m6-launch", [r"mac mini", r"\bm6\b"]),
    ("apple-mac-studio-m5-launch", [r"mac studio", r"m5 (?:max|ultra)|m5 max|m5 ultra"]),
    ("apple-iphone18-sept9-launch", [r"iphone", r"(?:9/9|september 9|9 september|iphone 18|iphone gap|foldable)"]),
    ("hasselblad-mirrorless-10y", [r"hasselblad", r"mirrorless"]),
    ("bhxh-national-id-sept1", [r"(?:bhxh|bao hiem xa hoi)", r"(?:1/9|1-9|september 1|dinh danh|cccd)"]),
    ("xiaomi-xring-o3", [r"xiaomi", r"xring o3"]),
    ("gta6-113gb-malware", [r"gta ?6", r"113 ?gb|ma doc|malware"]),
    ("rog-20th-anniversary", [r"(?:rog|asus)", r"20 nam|20th|edition 20|ky niem 20"]),
]

STOP_TOKENS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "from", "is", "are", "new",
    "va", "cua", "cho", "voi", "tu", "trong", "la", "mot", "co", "da", "dang", "moi", "nay", "nhung",
    "ra", "mat", "se", "duoc", "tai", "tren", "khi", "ve", "sau", "truoc", "nhu", "the"
}


def norm(value):
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def ascii_norm(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return norm(value)


def match_any(text, patterns):
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def load_mirror_map(root, source):
    path = root / "data/rss-reader/sources" / f"{source}.json"
    if not path.exists():
        return {}
    obj = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for item in obj.get("items") or []:
        for identity in (item.get("key"), item.get("canonicalUrl")):
            if identity:
                out[str(identity)] = item
    return out


def enrich(raw, mirror_map):
    source_item = mirror_map.get(str(raw.get("key"))) or mirror_map.get(str(raw.get("canonicalUrl"))) or {}
    out = dict(raw)
    out["description"] = source_item.get("description") or raw.get("description") or ""
    out["itemType"] = out.get("itemType") or source_item.get("itemType")
    return out


def decide(source, item):
    title = norm(item.get("title")); desc = norm(item.get("description")); text = f"{title} {desc}"; url = norm(item.get("canonicalUrl"))
    if not item.get("canonicalUrl") or not item.get("title"):
        return False, "invalid item: missing canonicalUrl/title"
    if source in KEEP_DEFAULT:
        if source == "economist" and match_any(text, [r"^subscribe", r"newsletter sign-up"]):
            return False, "non-article subscription/promo surface"
        return True, "canonical source-policy keep"
    if source == "nghiencuuquocte":
        if re.search(r"^mục lục", title, flags=re.I): return False, "index/non-substantive utility post"
        return True, "valid substantive NCQT item"
    if source == "theatlantic":
        if match_any(url, ATLANTIC_EXCLUDE) or match_any(title, ATLANTIC_EXCLUDE): return False, "press-release/culture-package/non-canonical surface"
        if match_any(url, ATLANTIC_KEEP_URL) or match_any(text, ATLANTIC_SIGNAL): return True, "material tech/science/economy/policy/geopolitics/Ideas/social-analysis signal"
        return False, "culture/profile/lifestyle item without material canonical-lane signal"
    if source == "vohoanghac":
        if item.get("itemType") == "article": return True, "original article"
        if any(keyword in text for keyword in VHH_SIGNAL): return True, "original note with substantive target-domain signal"
        return False, "note lacks substantive investing/markets/economics/tech signal"
    if source == "genk":
        if match_any(text, PROMO_PATTERNS): return False, "commerce/promo/award low-signal"
        if match_any(title, GENK_LOW_SIGNAL): return False, "celebrity/drama/filler/minor-product low-signal"
        if match_any(text, GENK_SIGNAL): return True, "substantive tech/AI/science/economics/markets/business/industry/regulation signal"
        return False, "no strong GenK canonical-lane signal"
    if source == "gamek":
        if match_any(text, PROMO_PATTERNS) or match_any(title, GAMEK_LOW_SIGNAL): return False, "fandom/relationship/streamer/drama/listicle/promo/minor-esports noise"
        if match_any(text, GAMEK_SIGNAL): return True, "substantive game/business/technology signal"
        return False, "no strong GameK canonical-lane signal"
    return True, "default keep"


def compact_item(item, reason):
    compact = {key: item.get(key) for key in ("key", "articleId", "noteId", "itemType", "title", "canonicalUrl", "publishedAt")}
    compact["filterReason"] = reason
    evidence = re.sub(r"\s+", " ", (item.get("description") or "").strip())
    compact["summaryEvidence"] = evidence[:1600]
    compact["summaryEvidenceStatus"] = "rss-description" if evidence else "missing-direct-verify-required"
    return compact


def stable_id(item): return item.get("key") or item.get("canonicalUrl")


def title_tokens(item):
    tokens = re.findall(r"[a-z0-9]+", ascii_norm(item.get("title")))
    return {token for token in tokens if len(token) >= 3 and token not in STOP_TOKENS}


def explicit_topic_key(item):
    text = ascii_norm(f"{item.get('title') or ''} {item.get('summaryEvidence') or ''}")
    for key, required_patterns in TOPIC_RULES:
        if all(re.search(pattern, text, flags=re.I) for pattern in required_patterns): return key
    return None


def similarity_duplicate(a, b):
    ta, tb = title_tokens(a), title_tokens(b)
    if min(len(ta), len(tb)) < 5: return False
    overlap = ta & tb
    if len(overlap) < 5: return False
    return len(overlap) / max(1, len(ta | tb)) >= 0.80


def representative_score(item):
    return (SOURCE_PRIORITY.get(item.get("sourceKey"), 50), min(len(item.get("summaryEvidence") or ""), 1600), item.get("publishedAt") or "")


def topic_dedupe(items):
    if not items: return [], []
    explicit_groups, unmatched = {}, []
    for item in items:
        key = explicit_topic_key(item)
        if key: explicit_groups.setdefault(key, []).append(item)
        else: unmatched.append(item)
    kept, dropped = [], []
    for key, group in explicit_groups.items():
        winner = max(group, key=representative_score); kept.append(winner)
        for item in group:
            if item is not winner: dropped.append((item, winner, f"topic duplicate [{key}] of {winner.get('canonicalUrl')}"))
    clusters = []
    for item in sorted(unmatched, key=representative_score, reverse=True):
        cluster = next((c for c in clusters if similarity_duplicate(item, c[0])), None)
        if cluster is None: clusters.append([item])
        else: cluster.append(item)
    for cluster in clusters:
        winner = max(cluster, key=representative_score); kept.append(winner)
        for item in cluster:
            if item is not winner: dropped.append((item, winner, f"high-confidence title duplicate of {winner.get('canonicalUrl')}"))
    return kept, dropped


def build(root, inventory_path):
    inventory = json.loads(inventory_path.read_text(encoding="utf-8")); problems = list(inventory.get("problems") or [])
    rows, rows_by_source, all_kept, runner_raw = [], {}, [], 0
    for row in inventory.get("sourceRows") or []:
        source = row.get("sourceKey")
        if source in DIRECT_KEYS:
            direct_row = {"sourceKey": source, "mode": row.get("mode"), "status": "requires-direct-verification", "rawCount": None, "keptCount": None, "filteredCount": None, "filterReasonSummary": "direct source must be verified and appended before final 15/15 render", "keptItems": [], "filteredItems": []}
            rows.append(direct_row); rows_by_source[source] = direct_row; continue
        raw_items = row.get("items") or []; raw_count = row.get("rawCount")
        if raw_count != len(raw_items): problems.append(f"{source}: rawCount {raw_count} != items {len(raw_items)}")
        runner_raw += len(raw_items); mirror_map = load_mirror_map(root, source); kept, filtered, reasons = [], [], {}
        for raw in raw_items:
            item = enrich(raw, mirror_map); keep, reason = decide(source, item); compact = compact_item(item, reason)
            if keep: kept.append(compact)
            else: filtered.append(compact); reasons[reason] = reasons.get(reason, 0) + 1
        if len(raw_items) != len(kept) + len(filtered): problems.append(f"{source}: raw != kept + filtered")
        if raw_items and not kept and not reasons: problems.append(f"{source}: raw>0 kept=0 without filter reason")
        all_kept.extend({**item, "sourceKey": source} for item in kept)
        output_row = {"sourceKey": source, "mode": row.get("mode"), "status": row.get("status"), "rawCount": len(raw_items), "keptCount": len(kept), "filteredCount": len(filtered), "filterReasonSummary": reasons, "keptItems": kept, "filteredItems": filtered}
        rows.append(output_row); rows_by_source[source] = output_row

    deduped_kept, topic_drops = topic_dedupe(all_kept)
    for dropped_item, winner, reason in topic_drops:
        source = dropped_item.get("sourceKey"); row = rows_by_source.get(source)
        if not row: problems.append(f"dedupe: missing source row for {source}"); continue
        identity = stable_id(dropped_item); before = len(row["keptItems"])
        row["keptItems"] = [item for item in row["keptItems"] if stable_id(item) != identity]
        if len(row["keptItems"]) == before: problems.append(f"dedupe: could not remove kept item {identity} from {source}"); continue
        filtered_copy = dict(dropped_item); filtered_copy.pop("sourceKey", None); filtered_copy["filterReason"] = reason
        row["filteredItems"].append(filtered_copy); row["filterReasonSummary"][reason] = row["filterReasonSummary"].get(reason, 0) + 1
        row["keptCount"] = len(row["keptItems"]); row["filteredCount"] = len(row["filteredItems"])
    for row in rows:
        if row.get("rawCount") is not None and row["rawCount"] != row["keptCount"] + row["filteredCount"]: problems.append(f"{row['sourceKey']}: post-dedupe raw != kept + filtered")

    seen, manifest = set(), []
    for item in sorted(deduped_kept, key=lambda value: value.get("publishedAt") or "", reverse=True):
        identity = stable_id(item)
        if not identity: problems.append(f"{item.get('sourceKey')}: kept item missing stable identity"); continue
        if identity in seen: problems.append(f"duplicate stable identity after topic dedupe: {identity}"); continue
        seen.add(identity); manifest.append(item)
    runner_kept = sum(row.get("keptCount") or 0 for row in rows if row.get("sourceKey") not in DIRECT_KEYS)
    runner_filtered = sum(row.get("filteredCount") or 0 for row in rows if row.get("sourceKey") not in DIRECT_KEYS)
    if runner_raw != inventory.get("runnerRawItemCount"): problems.append(f"runner raw total {runner_raw} != inventory {inventory.get('runnerRawItemCount')}")
    if runner_raw != runner_kept + runner_filtered: problems.append(f"runner raw total {runner_raw} != kept {runner_kept} + filtered {runner_filtered}")
    if runner_kept != len(manifest): problems.append(f"runner kept total {runner_kept} != unique manifest {len(manifest)}")
    for number, item in enumerate(manifest, 1): item["number"] = number

    missing_evidence = sum(1 for item in manifest if item.get("summaryEvidenceStatus") != "rss-description")
    render_contract = {"version": 2, "itemFormat": "N. [Source] [Title](canonicalUrl) — concise Vietnamese summary", "titleClickableRequired": True, "summaryRequired": True, "summaryMustAddBeyondTitleWhenEvidenceAllows": True, "summaryEvidenceFirst": True, "missingEvidenceAction": "direct-verify canonical URL before writing summary; never silently omit summary and never invent facts", "exactManifestNumberingRequired": True, "allKeptItemsMustRender": True, "sourceAccountingMustReconcileBeforeRender": True, "fandomRelationshipDramaForbidden": True, "sameEventTopicDedupeRequired": True, "sameEventRule": "keep one strongest representative for high-confidence same-event duplicates; preserve distinct thesis when uncertain"}
    return {"version": 5, "scope": "rss-kept-manifest-runner13", "date": inventory.get("date"), "timezone": inventory.get("timezone"), "windowUtc": inventory.get("windowUtc"), "filterPolicyVersion": "2026-08-27-canonical-source-policy-v5-drama-topic-dedupe", "logicalSourceCount": 15, "runnerSourceCount": 13, "directSourceCount": 2, "runnerRawCount": runner_raw, "runnerKeptCount": runner_kept, "runnerFilteredCount": runner_filtered, "runnerManifestCount": len(manifest), "topicDuplicateFilteredCount": len(topic_drops), "summaryEvidenceMissingCount": missing_evidence, "sourceRows": rows, "manifest": manifest, "renderContract": render_contract, "directVerificationPending": ["hoquoctuan", "vnhacker"], "runnerAccountingOk": not problems, "complete15SourceRenderReady": False, "problems": problems, "contract": {"rawEqualsKeptPlusFilteredPerRunnerSource": True, "runnerManifestEqualsSumKept": True, "uniqueStableIdentityRequired": True, "finalRenderRequiresDirectVerification": True, "clickableTitleAndSummaryRequired": True, "fandomRelationshipDramaForbidden": True, "highConfidenceSameEventDedupRequired": True}}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("--inventory", required=True); parser.add_argument("--out", required=True); args = parser.parse_args()
    root = Path(args.root).resolve(); obj = build(root, Path(args.inventory)); output = Path(args.out); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": obj["date"], "runnerRawCount": obj["runnerRawCount"], "runnerKeptCount": obj["runnerKeptCount"], "runnerFilteredCount": obj["runnerFilteredCount"], "runnerManifestCount": obj["runnerManifestCount"], "topicDuplicateFilteredCount": obj["topicDuplicateFilteredCount"], "summaryEvidenceMissingCount": obj["summaryEvidenceMissingCount"], "runnerAccountingOk": obj["runnerAccountingOk"]}, ensure_ascii=False))
    raise SystemExit(0 if obj["runnerAccountingOk"] else 2)


if __name__ == "__main__": main()
