#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup
from story_pipeline import metruyen_full as core

# Two terminal entries are public reader shells with no prose. They account exactly
# for the 1214-vs-1212 index difference observed against the TTV master count.
KNOWN_EMPTY_TERMINAL = {
    "https://metruyenchuvn.org/vuong-bai-tien-hoa/chuong-91-2DOVcFGWwY42",
    "https://metruyenchuvn.org/vuong-bai-tien-hoa/chuong-92-WvhIANo1oBKG",
}


def isolate_body_v2(page_html, site_title):
    """Prefer MeTruyen's direct prose container, then fall back to the old reader parser."""
    soup = BeautifulSoup(page_html or "", "html.parser")
    node = soup.select_one("div.truyen")
    if node is not None:
        for tag in node(["script", "style", "noscript", "svg", "template"]):
            tag.decompose()
        lines = []
        for raw in node.get_text("\n").splitlines():
            s = core.normalize_line(raw)
            if s:
                lines.append(s)
        body = "\n\n".join(lines).strip()
        if len(body) >= 500:
            return body
    return core.isolate_body(page_html, site_title)


def fetch_v2(rec, bible):
    r = core.get(rec["url"], timeout=30, retries=5)
    body = isolate_body_v2(r.text, rec["site_title"])
    body = core.editorial_clean(body, bible)
    out = dict(rec)
    out.update({
        "final_url": r.url,
        "body": body,
        "chars": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "ok": True,
    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bible", default="story_pipeline/config/story_bible.json")
    ap.add_argument("--out", default="vbth_metruyen_full")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bible = core.read_json(args.bible)
    index = core.parse_story_index()
    records = index["chapters"]

    results = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_v2, rec, bible): rec for rec in records}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            rec = futs[fut]
            done += 1
            try:
                results.append(fut.result())
            except Exception as e:
                failures.append({
                    "seq": rec["seq"], "url": rec["url"],
                    "error": f"{type(e).__name__}: {e}",
                })
            if done % 100 == 0:
                print(json.dumps({"done": done, "total": len(records), "failures": len(failures)}, ensure_ascii=False), flush=True)

    # Sequential recovery for any transient misses.
    if failures:
        by_seq = {r["seq"]: r for r in results}
        retry_failures = []
        rec_by_seq = {r["seq"]: r for r in records}
        for old in failures:
            rec = rec_by_seq[old["seq"]]
            try:
                by_seq[rec["seq"]] = fetch_v2(rec, bible)
            except Exception as e:
                retry_failures.append({
                    "seq": rec["seq"], "url": rec["url"],
                    "error": f"{type(e).__name__}: {e}",
                })
        results = list(by_seq.values())
        failures = retry_failures

    # The only allowed non-prose entries are the two verified terminal reader shells.
    failure_urls = {x["url"] for x in failures}
    if failure_urls and failure_urls != KNOWN_EMPTY_TERMINAL:
        manifest = {
            "story": "Vương Bài Tiến Hóa", "source": "MeTruyen",
            "index_chapters": len(records), "ok": len(results),
            "failed": len(failures), "failed_items": failures,
        }
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False), flush=True)
        raise SystemExit(2)

    # Require the exact 1212 real-content count; do not silently accept a partial book.
    results.sort(key=lambda x: x["seq"])
    if len(results) != 1212:
        raise SystemExit(f"expected 1212 content chapters, got {len(results)}; failures={failures}")

    manifest = {
        "story": "Vương Bài Tiến Hóa",
        "author": "Quyển Thổ",
        "source": "MeTruyen",
        "source_role": "execution master; TTV count/reference master",
        "story_url": index["story_url"],
        "book_id": index["book_id"],
        "list_pages": index["last_page"],
        "raw_index_entries": len(records),
        "content_chapters": len(results),
        "ignored_empty_terminal_shells": sorted(failure_urls),
        "volumes_inferred": index["volume_count"],
        "story_bible_version": bible.get("version"),
        "total_chars": sum(r["chars"] for r in results),
        "failed": 0,
        "ok": len(results),
        "requested": len(results),
        "index_chapters": len(results),
    }

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
        "checked": len(results), "issue_count": len(issues), "issues": issues,
        "min_chars": min(r["chars"] for r in results),
        "max_chars": max(r["chars"] for r in results),
        "avg_chars": round(sum(r["chars"] for r in results) / len(results), 1),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata = [{k: r.get(k) for k in ("seq", "volume", "site_no", "site_title", "url", "final_url", "chars", "sha256")} for r in results]
    (out / "chapters.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    by_seq = {r["seq"]: r for r in results}
    seqs = [r["seq"] for r in results]
    picks = sorted(set([seqs[0], seqs[1], seqs[2], seqs[len(seqs)//2], seqs[-3], seqs[-2], seqs[-1]]))
    samples = []
    for seq in picks:
        r = by_seq[seq]
        samples.append(f"{'='*72}\n{core.chapter_label(r)}\n{'='*72}\n\n{r['body']}")
    (out / "sample_spread.txt").write_text("\n\n".join(samples), encoding="utf-8")

    epub = core.build_epub(results, out / "Vuong_Bai_Tien_Hoa_MeTruyen_BienTap.epub")
    print(json.dumps({"epub": str(epub), "epub_bytes": epub.stat().st_size, "qa_issues": len(issues), **manifest}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
