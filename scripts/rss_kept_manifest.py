#!/usr/bin/env python3
import argparse
import json
import re
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
    r"tip hẳn", r"ảnh nghìn like", r"nhung nhớ", r"em gái", r"hồng hài nhi", r"phim hàn"
]
GAMEK_SIGNAL = [
    r"black myth", r"game science", r"steam", r"playstation", r"xbox", r"nintendo", r"epic games", r"unity",
    r"unreal engine", r"phát hành", r"ra mắt", r"trì hoãn", r"doanh thu", r"studio", r"nhà phát triển",
    r"nhà phát hành", r"thâu tóm", r"acquisition", r"layoff", r"sa thải", r"công nghệ", r"engine", r"gpu",
    r"ai\b", r"bom tấn", r"where winds meet", r"gta", r"elden ring", r"wukong", r"zhong kui"
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
    r"education", r"technology", r"password", r"login", r"ai\b", r"science", r"health", r"climate",
    r"data center", r"immigration", r"democracy", r"social", r"middle class", r"downwardly mobile",
    r"hitler", r"antisemit", r"jews?"
]


def norm(value):
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


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
    title = norm(item.get("title"))
    desc = norm(item.get("description"))
    text = f"{title} {desc}"
    url = norm(item.get("canonicalUrl"))

    if not item.get("canonicalUrl") or not item.get("title"):
        return False, "invalid item: missing canonicalUrl/title"
    if source in KEEP_DEFAULT:
        if source == "economist" and match_any(text, [r"^subscribe", r"newsletter sign-up"]):
            return False, "non-article subscription/promo surface"
        return True, "canonical source-policy keep"
    if source == "nghiencuuquocte":
        if re.search(r"^mục lục", title, flags=re.I):
            return False, "index/non-substantive utility post"
        return True, "valid substantive NCQT item"
    if source == "theatlantic":
        if match_any(url, ATLANTIC_EXCLUDE) or match_any(title, ATLANTIC_EXCLUDE):
            return False, "press-release/culture-package/non-canonical surface"
        if match_any(url, ATLANTIC_KEEP_URL) or match_any(text, ATLANTIC_SIGNAL):
            return True, "material tech/science/economy/policy/geopolitics/Ideas/social-analysis signal"
        return False, "culture/profile/lifestyle item without material canonical-lane signal"
    if source == "vohoanghac":
        if item.get("itemType") == "article":
            return True, "original article"
        if any(keyword in text for keyword in VHH_SIGNAL):
            return True, "original note with substantive target-domain signal"
        return False, "note lacks substantive investing/markets/economics/tech signal"
    if source == "genk":
        if match_any(text, PROMO_PATTERNS):
            return False, "commerce/promo/award low-signal"
        if match_any(title, GENK_LOW_SIGNAL):
            return False, "celebrity/drama/filler/minor-product low-signal"
        if match_any(text, GENK_SIGNAL):
            return True, "substantive tech/AI/science/economics/markets/business/industry/regulation signal"
        return False, "no strong GenK canonical-lane signal"
    if source == "gamek":
        if match_any(text, PROMO_PATTERNS) or match_any(title, GAMEK_LOW_SIGNAL):
            return False, "fandom/streamer/drama/listicle/promo/minor-esports noise"
        if match_any(text, GAMEK_SIGNAL):
            return True, "substantive game/business/technology signal"
        return False, "no strong GameK canonical-lane signal"
    return True, "default keep"


def compact_item(item, reason):
    compact = {key: item.get(key) for key in (
        "key", "articleId", "noteId", "itemType", "title", "canonicalUrl", "publishedAt"
    )}
    compact["filterReason"] = reason
    evidence = re.sub(r"\s+", " ", (item.get("description") or "").strip())
    compact["summaryEvidence"] = evidence[:1600]
    compact["summaryEvidenceStatus"] = "rss-description" if evidence else "missing-direct-verify-required"
    return compact


def stable_id(item):
    return item.get("key") or item.get("canonicalUrl")


def build(root, inventory_path):
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    problems = list(inventory.get("problems") or [])
    rows = []
    all_kept = []
    runner_raw = 0
    runner_kept = 0

    for row in inventory.get("sourceRows") or []:
        source = row.get("sourceKey")
        if source in DIRECT_KEYS:
            rows.append({
                "sourceKey": source,
                "mode": row.get("mode"),
                "status": "requires-direct-verification",
                "rawCount": None,
                "keptCount": None,
                "filteredCount": None,
                "filterReasonSummary": "direct source must be verified and appended before final 15/15 render",
                "keptItems": [],
                "filteredItems": []
            })
            continue

        raw_items = row.get("items") or []
        raw_count = row.get("rawCount")
        if raw_count != len(raw_items):
            problems.append(f"{source}: rawCount {raw_count} != items {len(raw_items)}")
        runner_raw += len(raw_items)
        mirror_map = load_mirror_map(root, source)
        kept = []
        filtered = []
        reasons = {}

        for raw in raw_items:
            item = enrich(raw, mirror_map)
            keep, reason = decide(source, item)
            compact = compact_item(item, reason)
            if keep:
                kept.append(compact)
            else:
                filtered.append(compact)
                reasons[reason] = reasons.get(reason, 0) + 1

        if len(raw_items) != len(kept) + len(filtered):
            problems.append(f"{source}: raw != kept + filtered")
        if raw_items and not kept and not reasons:
            problems.append(f"{source}: raw>0 kept=0 without filter reason")

        runner_kept += len(kept)
        all_kept.extend({**item, "sourceKey": source} for item in kept)
        rows.append({
            "sourceKey": source,
            "mode": row.get("mode"),
            "status": row.get("status"),
            "rawCount": len(raw_items),
            "keptCount": len(kept),
            "filteredCount": len(filtered),
            "filterReasonSummary": reasons,
            "keptItems": kept,
            "filteredItems": filtered
        })

    seen = set()
    manifest = []
    for item in sorted(all_kept, key=lambda value: value.get("publishedAt") or "", reverse=True):
        identity = stable_id(item)
        if not identity:
            problems.append(f"{item.get('sourceKey')}: kept item missing stable identity")
            continue
        if identity in seen:
            problems.append(f"duplicate stable identity: {identity}")
            continue
        seen.add(identity)
        manifest.append(item)

    if runner_raw != inventory.get("runnerRawItemCount"):
        problems.append(f"runner raw total {runner_raw} != inventory {inventory.get('runnerRawItemCount')}")
    if runner_kept != len(manifest):
        problems.append(f"runner kept total {runner_kept} != unique manifest {len(manifest)}")

    for number, item in enumerate(manifest, 1):
        item["number"] = number

    missing_evidence = sum(1 for item in manifest if item.get("summaryEvidenceStatus") != "rss-description")
    render_contract = {
        "version": 1,
        "itemFormat": "N. [Source] [Title](canonicalUrl) — concise Vietnamese summary",
        "titleClickableRequired": True,
        "summaryRequired": True,
        "summaryMustAddBeyondTitleWhenEvidenceAllows": True,
        "summaryEvidenceFirst": True,
        "missingEvidenceAction": "direct-verify canonical URL before writing summary; never silently omit summary and never invent facts",
        "exactManifestNumberingRequired": True,
        "allKeptItemsMustRender": True,
        "sourceAccountingMustReconcileBeforeRender": True
    }

    return {
        "version": 4,
        "scope": "rss-kept-manifest-runner13",
        "date": inventory.get("date"),
        "timezone": inventory.get("timezone"),
        "windowUtc": inventory.get("windowUtc"),
        "filterPolicyVersion": "2026-08-25-canonical-source-policy-v4-summary-contract",
        "logicalSourceCount": 15,
        "runnerSourceCount": 13,
        "directSourceCount": 2,
        "runnerRawCount": runner_raw,
        "runnerKeptCount": runner_kept,
        "runnerFilteredCount": runner_raw - runner_kept,
        "runnerManifestCount": len(manifest),
        "summaryEvidenceMissingCount": missing_evidence,
        "sourceRows": rows,
        "manifest": manifest,
        "renderContract": render_contract,
        "directVerificationPending": ["hoquoctuan", "vnhacker"],
        "runnerAccountingOk": not problems,
        "complete15SourceRenderReady": False,
        "problems": problems,
        "contract": {
            "rawEqualsKeptPlusFilteredPerRunnerSource": True,
            "runnerManifestEqualsSumKept": True,
            "uniqueStableIdentityRequired": True,
            "finalRenderRequiresDirectVerification": True,
            "clickableTitleAndSummaryRequired": True
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    obj = build(root, Path(args.inventory))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "date": obj["date"],
        "runnerRawCount": obj["runnerRawCount"],
        "runnerKeptCount": obj["runnerKeptCount"],
        "runnerFilteredCount": obj["runnerFilteredCount"],
        "runnerManifestCount": obj["runnerManifestCount"],
        "summaryEvidenceMissingCount": obj["summaryEvidenceMissingCount"],
        "runnerAccountingOk": obj["runnerAccountingOk"]
    }, ensure_ascii=False))
    raise SystemExit(0 if obj["runnerAccountingOk"] else 2)


if __name__ == "__main__":
    main()
