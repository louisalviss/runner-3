#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import html
import json
import random
import re
import time
import unicodedata
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://metruyenchuvn.org"
STORY_PATH = "/vuong-bai-tien-hoa"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 runner-3-vbth/2.0"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_line(s):
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def get(url, timeout=30, retries=5):
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            return r
        except Exception as e:
            last = e
            time.sleep(min(4.0, 0.45 * (2 ** attempt)) + random.random() * 0.35)
    raise RuntimeError(f"GET failed {url}: {last}")


def parse_story_index():
    story_url = urljoin(BASE, STORY_PATH)
    r = get(story_url)
    text = r.text
    m = re.search(r'name=["\']bid["\']\s+value=["\'](\d+)["\']', text, re.I)
    if not m:
        raise RuntimeError("cannot find MeTruyen book id")
    book_id = int(m.group(1))
    pages = [int(x) for x in re.findall(rf"page\({book_id},\s*(\d+)\)", text)]
    last_page = max(pages) if pages else 1

    ordered = []
    seen = set()
    for page in range(1, last_page + 1):
        api = f"{BASE}/get/listchap/{book_id}?page={page}"
        jr = get(api)
        try:
            payload = jr.json()
        except Exception as e:
            raise RuntimeError(f"invalid chapter-list JSON page {page}: {e}")
        fragment = payload.get("data") or ""
        soup = BeautifulSoup(fragment, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            label = normalize_line(a.get_text(" ", strip=True))
            if not href.startswith(STORY_PATH + "/chuong-"):
                continue
            full = urljoin(BASE, href)
            if full in seen:
                continue
            seen.add(full)
            ordered.append({"url": full, "site_title": label, "list_page": page})
    if len(ordered) < 1000:
        raise RuntimeError(f"chapter index suspiciously short: {len(ordered)}")

    # Infer volume boundaries when chapter numbering resets.
    volume = 1
    previous_no = None
    for seq, rec in enumerate(ordered, start=1):
        m = re.search(r"Chương\s*0*(\d+)", rec["site_title"], re.I)
        site_no = int(m.group(1)) if m else None
        if site_no is not None and previous_no is not None and site_no < previous_no and site_no <= 5:
            volume += 1
        rec.update({"seq": seq, "volume": volume, "site_no": site_no})
        if site_no is not None:
            previous_no = site_no
    return {
        "book_id": book_id,
        "last_page": last_page,
        "story_url": r.url,
        "chapters": ordered,
        "volume_count": volume,
    }


def visible_lines(soup):
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    out = []
    for raw in soup.get_text("\n").splitlines():
        s = normalize_line(raw)
        if s:
            out.append(s)
    return out


def isolate_body(page_html, site_title):
    soup = BeautifulSoup(page_html or "", "html.parser")
    lines = visible_lines(soup)

    # Primary marker on MeTruyen reader: Tải Ebook -> repeated chapter heading -> prose.
    start = None
    for i, line in enumerate(lines):
        if line == "Tải Ebook":
            for j in range(i + 1, min(len(lines), i + 8)):
                if lines[j].lower().startswith("chương"):
                    start = j + 1
                    break
            if start is not None:
                break

    # Fallback: use the last exact/near-exact chapter title before reader navigation.
    if start is None:
        candidates = []
        norm_title = normalize_line(site_title).lower()
        for i, line in enumerate(lines):
            low = line.lower()
            if low == norm_title or (low.startswith("chương") and norm_title and norm_title in low):
                candidates.append(i)
        if candidates:
            start = candidates[-1] + 1

    if start is None:
        raise ValueError("reader body start marker not found")

    end = len(lines)
    end_markers = (
        "《 chương trước",
        "bạn có thể dùng phím",
        "báo lỗi",
        "truyện hot mới",
        "danh sách chương",
    )
    for i in range(start, len(lines)):
        low = lines[i].lower()
        if any(low.startswith(x) for x in end_markers):
            end = i
            break

    body_lines = lines[start:end]
    # Remove exact navigation remnants that occasionally leak into the reader body.
    garbage = {
        "Chương tiếp 》", "《 Chương trước", "Tải Ebook", "Báo lỗi", "Bình luận",
        "Mê Truyện Chữ", "MeTruyenChu",
    }
    body_lines = [x for x in body_lines if x not in garbage]
    body = "\n\n".join(body_lines).strip()
    if len(body) < 500:
        raise ValueError(f"body too short: {len(body)}")
    return body


def normalize_entities(text, bible):
    pairs = []
    for ent in bible.get("entities", []):
        canonical = normalize_line(ent.get("canonical", ""))
        for alias in ent.get("aliases", []):
            alias = normalize_line(alias)
            if canonical and alias and canonical != alias:
                pairs.append((alias, canonical))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    for alias, canonical in pairs:
        text = text.replace(alias, canonical)
    return text


def editorial_clean(text, bible):
    text = unicodedata.normalize("NFC", text)
    text = normalize_entities(text, bible)

    # Conservative source-wide cleanup. Do not invent information or rewrite plot.
    replacements = {
        "part-time": "làm thêm",
        "Part-time": "Làm thêm",
        " . . . . ": "…",
        ". . . .": "…",
        ". . .": "…",
        "……": "…",
        "---------": "——",
        "--------": "——",
        "-------": "——",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Typography and whitespace.
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=[A-Za-zÀ-ỹĐđ])", r"\1 ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize paired quote spacing without changing wording.
    text = text.replace('" ', '"').replace(' "', ' "')
    return text.strip()


def fetch_chapter(rec, bible):
    r = get(rec["url"], timeout=30, retries=5)
    body = isolate_body(r.text, rec["site_title"])
    body = editorial_clean(body, bible)
    out = dict(rec)
    out.update({
        "final_url": r.url,
        "body": body,
        "chars": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "ok": True,
    })
    return out


def chapter_label(rec):
    base = rec.get("site_title") or f"Chương {rec['seq']}"
    return f"Quyển {rec['volume']} · {base}"


def xhtml_doc(title, body):
    pars = []
    for para in body.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if re.fullmatch(r"[-—–_=*·•]{3,}", para):
            pars.append("<hr/>")
        else:
            pars.append(f"<p>{html.escape(para)}</p>")
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="vi" xml:lang="vi">'
        f'<head><meta charset="utf-8"/><title>{html.escape(title)}</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
        f'<body><h1>{html.escape(title)}</h1>{"".join(pars)}</body></html>'
    )


def build_epub(records, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    uid = str(uuid.uuid4())
    style = (
        'body{font-family:serif;line-height:1.58;margin:5%;}'
        'h1{font-size:1.25em;text-align:center;line-height:1.35;margin:1.4em 0 1.8em;}'
        'p{text-align:justify;text-indent:1.2em;margin:.38em 0;}'
        'hr{border:0;border-top:1px solid #999;margin:1.5em 22%;}'
    )

    manifest = []
    spine = []
    nav_items = []
    ncx_items = []
    volume_groups = []
    current_volume = None
    current_links = []

    for rec in records:
        seq = rec["seq"]
        fn = f"ch{seq:04d}.xhtml"
        iid = f"ch{seq:04d}"
        label = chapter_label(rec)
        manifest.append(f'<item id="{iid}" href="{fn}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{iid}"/>')
        current = rec["volume"]
        if current_volume is None:
            current_volume = current
        if current != current_volume:
            volume_groups.append((current_volume, current_links))
            current_volume = current
            current_links = []
        current_links.append(f'<li><a href="{fn}">{html.escape(rec["site_title"])}</a></li>')
        ncx_items.append(
            f'<navPoint id="nav{seq}" playOrder="{seq}"><navLabel><text>{html.escape(label)}</text></navLabel>'
            f'<content src="{fn}"/></navPoint>'
        )
    if current_links:
        volume_groups.append((current_volume, current_links))

    for vol, links in volume_groups:
        nav_items.append(f'<li><span>Quyển {vol}</span><ol>{"".join(links)}</ol></li>')

    cover_svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1800" viewBox="0 0 1200 1800">
<rect width="1200" height="1800" fill="#111"/><text x="600" y="760" fill="#fff" font-size="84" text-anchor="middle" font-family="serif">VƯƠNG BÀI</text><text x="600" y="875" fill="#fff" font-size="84" text-anchor="middle" font-family="serif">TIẾN HÓA</text><text x="600" y="1010" fill="#bbb" font-size="42" text-anchor="middle" font-family="serif">Quyển Thổ</text></svg>'''
    cover_xhtml = '''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" lang="vi"><head><title>Bìa</title><style>html,body{margin:0;padding:0;text-align:center}img{max-width:100%;height:auto}</style></head><body><img src="cover.svg" alt="Vương Bài Tiến Hóa"/></body></html>'''
    nav_doc = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi">'
        '<head><title>Mục lục</title></head><body><nav epub:type="toc" id="toc"><h1>Mục lục</h1>'
        f'<ol>{"".join(nav_items)}</ol></nav></body></html>'
    )
    ncx_doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f'<head><meta name="dtb:uid" content="urn:uuid:{uid}"/></head>'
        '<docTitle><text>Vương Bài Tiến Hóa</text></docTitle>'
        f'<navMap>{"".join(ncx_items)}</navMap></ncx>'
    )
    modified = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">urn:uuid:{uid}</dc:identifier>'
        '<dc:title>Vương Bài Tiến Hóa</dc:title><dc:creator>Quyển Thổ</dc:creator><dc:language>vi</dc:language>'
        '<dc:description>Bản tiếng Việt từ nguồn MeTruyen, đã làm sạch và chuẩn hóa thuật ngữ theo Story Bible.</dc:description>'
        f'<meta property="dcterms:modified">{modified}</meta>'
        '</metadata><manifest>'
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        '<item id="css" href="style.css" media-type="text/css"/>'
        '<item id="cover-svg" href="cover.svg" media-type="image/svg+xml" properties="cover-image"/>'
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
        f'{"".join(manifest)}</manifest><spine toc="ncx"><itemref idref="cover"/>{"".join(spine)}</spine></package>'
    )
    container = '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'

    with zipfile.ZipFile(output, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/style.css", style)
        z.writestr("OEBPS/cover.svg", cover_svg)
        z.writestr("OEBPS/cover.xhtml", cover_xhtml)
        z.writestr("OEBPS/nav.xhtml", nav_doc)
        z.writestr("OEBPS/toc.ncx", ncx_doc)
        z.writestr("OEBPS/content.opf", opf)
        for rec in records:
            z.writestr(
                f"OEBPS/ch{rec['seq']:04d}.xhtml",
                xhtml_doc(chapter_label(rec), rec["body"]),
                compress_type=zipfile.ZIP_DEFLATED,
            )
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bible", default="story_pipeline/config/story_bible.json")
    ap.add_argument("--out", default="vbth_metruyen_full")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0, help="test only: cap chapter count")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bible = read_json(args.bible)
    index = parse_story_index()
    records = index["chapters"]
    if args.limit:
        records = records[:args.limit]

    results = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_chapter, rec, bible): rec for rec in records}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            rec = futs[fut]
            done += 1
            try:
                result = fut.result()
                results.append(result)
            except Exception as e:
                failures.append({"seq": rec["seq"], "url": rec["url"], "error": f"{type(e).__name__}: {e}"})
            if done % 100 == 0 or failures and done % 25 == 0:
                print(json.dumps({"done": done, "total": len(records), "failures": len(failures)}, ensure_ascii=False), flush=True)

    # One conservative sequential recovery pass for failures.
    if failures:
        by_seq = {r["seq"]: r for r in results}
        retry_failures = []
        for old in failures:
            rec = next(x for x in records if x["seq"] == old["seq"])
            try:
                by_seq[rec["seq"]] = fetch_chapter(rec, bible)
            except Exception as e:
                retry_failures.append({"seq": rec["seq"], "url": rec["url"], "error": f"{type(e).__name__}: {e}"})
        failures = retry_failures
        results = list(by_seq.values())

    results.sort(key=lambda x: x["seq"])
    expected = len(records)
    manifest = {
        "story": "Vương Bài Tiến Hóa",
        "author": "Quyển Thổ",
        "source": "MeTruyen",
        "story_url": index["story_url"],
        "book_id": index["book_id"],
        "list_pages": index["last_page"],
        "index_chapters": len(index["chapters"]),
        "requested": expected,
        "ok": len(results),
        "failed": len(failures),
        "failed_items": failures,
        "volumes_inferred": index["volume_count"],
        "story_bible_version": bible.get("version"),
        "total_chars": sum(r["chars"] for r in results),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures or len(results) != expected:
        print(json.dumps(manifest, ensure_ascii=False), flush=True)
        raise SystemExit(2)

    issues = []
    seen_sha = {}
    for r in results:
        if r["chars"] < 500:
            issues.append({"seq": r["seq"], "type": "short", "chars": r["chars"]})
        for marker in ["Tải Ebook", "Truyện Hot Mới", "Bạn có thể dùng phím", "《 Chương trước"]:
            if marker in r["body"]:
                issues.append({"seq": r["seq"], "type": "boilerplate", "value": marker})
        if r["sha256"] in seen_sha:
            issues.append({"seq": r["seq"], "type": "duplicate_body", "same_as": seen_sha[r["sha256"]]})
        else:
            seen_sha[r["sha256"]] = r["seq"]

    qa = {
        "checked": len(results),
        "issue_count": len(issues),
        "issues": issues,
        "min_chars": min(r["chars"] for r in results),
        "max_chars": max(r["chars"] for r in results),
        "avg_chars": round(sum(r["chars"] for r in results) / len(results), 1),
    }
    (out / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata = [{k: r.get(k) for k in ("seq", "volume", "site_no", "site_title", "url", "final_url", "chars", "sha256")} for r in results]
    (out / "chapters.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    # Human-readable samples from beginning / middle / end for spot review.
    picks = sorted(set([1, 2, 3, max(1, len(results)//2), max(1, len(results)//2 + 1), len(results)-1, len(results)]))
    sample_parts = []
    by_seq = {r["seq"]: r for r in results}
    for seq in picks:
        r = by_seq.get(seq)
        if not r:
            continue
        sample_parts.append(f"{'='*72}\n{chapter_label(r)}\n{'='*72}\n\n{r['body']}")
    (out / "sample_spread.txt").write_text("\n\n".join(sample_parts), encoding="utf-8")

    epub = build_epub(results, out / "Vuong_Bai_Tien_Hoa_MeTruyen_BienTap.epub")
    print(json.dumps({"epub": str(epub), "epub_bytes": epub.stat().st_size, "qa_issues": len(issues), **manifest}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
