#!/usr/bin/env python3
"""Canonical QA/repair/finalize worker for Dungeon Crawler Carl VI-v3.

Runner-3 native. Source and final artifacts live in R2. This worker never
translates or editorially rewrites books. It may make conservative EPUB
package/language repairs and the one explicitly approved Book 7 text repair.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

MANIFEST = Path(__file__).with_name("books") / "dcc-v3.json"
CONTAINER = "META-INF/container.xml"
MIMETYPE = b"application/epub+zip"
XML_EXT = {".xhtml", ".html", ".htm", ".xml", ".opf", ".ncx", ".svg"}
TEXT_EXT = {".xhtml", ".html", ".htm"}
LANG_ATTR = "{http://www.w3.org/XML/1998/namespace}lang"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def die(code: str, detail: str, extra=None):
    payload = {"ok": False, "code": code, "detail": detail}
    if extra is not None:
        payload["extra"] = extra
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(2)


def env_first(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None


def s3_client():
    try:
        import boto3
        from botocore.config import Config
    except Exception as exc:
        die("BOTO3_MISSING", str(exc))
    account = env_first("R2_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID")
    endpoint = env_first("R2_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3")
    if not endpoint and account:
        endpoint = f"https://{account}.r2.cloudflarestorage.com"
    key = env_first("R2_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
    secret = env_first("R2_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
    if not endpoint or not key or not secret:
        die("R2_CREDENTIALS_MISSING", "Need R2_ENDPOINT_URL (or R2_ACCOUNT_ID), access key and secret key")
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=key,
        aws_secret_access_key=secret, region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def norm(s: str) -> str:
    s = s.lower().replace("_", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def discover_source(s3, bucket: str, book: dict, prefixes: list[str]) -> str:
    explicit = book.get("source_key")
    override = os.getenv(f"DCC_BOOK_{book['book']}_SOURCE_KEY")
    if override:
        return override
    if explicit:
        return explicit
    terms = [norm(x) for x in book.get("source_match", [])]
    candidates = []
    for prefix in prefixes:
        token = None
        while True:
            kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kw["ContinuationToken"] = token
            try:
                page = s3.list_objects_v2(**kw)
            except Exception as exc:
                die("R2_LIST_FAILED", f"{type(exc).__name__}: {exc}")
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.lower().endswith(".epub"):
                    continue
                nk = norm(key)
                score = sum(1 for t in terms if t and t in nk)
                # Strong preference for VI-v2/fixed/candidate and avoid already-final v3.
                if "v3" in nk or "/final/" in key.lower():
                    score -= 4
                if "v2" in nk:
                    score += 2
                if book["book"] == 7 and any(x in nk for x in ("fixed", "candidate", "repair")):
                    score += 2
                if score > 0:
                    candidates.append((score, obj.get("LastModified"), key, obj.get("Size", 0)))
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
    candidates.sort(key=lambda x: (x[0], x[1] or ""), reverse=True)
    if not candidates:
        die("SOURCE_R2_KEY_MISSING", f"No EPUB candidate found for Book {book['book']}", {"prefixes": prefixes, "terms": terms})
    best = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == best[0]:
        die("SOURCE_R2_AMBIGUOUS", f"Multiple equally-ranked sources for Book {book['book']}", [x[2] for x in candidates[:10]])
    print(f"SOURCE_KEY={best[2]}")
    return best[2]


def unzip_epub(src: Path, root: Path):
    try:
        with zipfile.ZipFile(src) as z:
            bad = z.testzip()
            if bad:
                die("EPUB_CRC_FAIL", bad)
            names = z.namelist()
            if not names or names[0] != "mimetype":
                print("REPAIR_NEEDED=mimetype-not-first")
            if "mimetype" not in names or z.read("mimetype") != MIMETYPE:
                die("EPUB_MIMETYPE_INVALID", "Missing or invalid mimetype")
            z.extractall(root)
    except zipfile.BadZipFile as exc:
        die("EPUB_ZIP_INVALID", str(exc))


def parse_xml(path: Path):
    try:
        return ET.parse(path)
    except Exception as exc:
        die("XML_INVALID", f"{path}: {exc}")


def resolve_opf(root: Path) -> Path:
    c = root / CONTAINER
    if not c.exists():
        die("CONTAINER_MISSING", CONTAINER)
    tree = parse_xml(c)
    el = tree.find(".//{*}rootfile")
    if el is None or not el.attrib.get("full-path"):
        die("CONTAINER_INVALID", "rootfile full-path missing")
    opf = root / PurePosixPath(el.attrib["full-path"])
    if not opf.exists():
        die("OPF_MISSING", str(opf.relative_to(root)))
    return opf


def validate_and_repair(root: Path, book: dict) -> dict:
    report = {"xml_files": 0, "text_files": 0, "duplicate_ids": [], "broken_refs": [], "repairs": [], "adjacent_repeat_candidates": []}
    opf = resolve_opf(root)

    # Parse all XML-family resources.
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in XML_EXT:
            parse_xml(p)
            report["xml_files"] += 1

    # Conservative metadata repair: dc:language and document lang/xml:lang.
    opft = parse_xml(opf)
    opfr = opft.getroot()
    changed = False
    langs = opfr.findall(".//{http://purl.org/dc/elements/1.1/}language")
    if not langs:
        metadata = opfr.find(".//{*}metadata")
        if metadata is None:
            die("OPF_METADATA_MISSING", str(opf))
        lang = ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}language")
        lang.text = "vi"
        changed = True
    else:
        for lang in langs:
            if (lang.text or "").strip().lower() != "vi":
                lang.text = "vi"
                changed = True
    if changed:
        opft.write(opf, encoding="utf-8", xml_declaration=True)
        report["repairs"].append("opf-dc-language=vi")

    # Manifest/spine targets and references.
    opft = parse_xml(opf)
    base = opf.parent
    manifest = {}
    for item in opft.getroot().findall(".//{*}manifest/{*}item"):
        iid, href = item.attrib.get("id"), item.attrib.get("href")
        if iid and href:
            manifest[iid] = href
            target = (base / PurePosixPath(href.split("#", 1)[0])).resolve()
            if not target.exists():
                report["broken_refs"].append(f"manifest:{href}")
    for itemref in opft.getroot().findall(".//{*}spine/{*}itemref"):
        rid = itemref.attrib.get("idref")
        if rid and rid not in manifest:
            report["broken_refs"].append(f"spine:{rid}")

    repeat_re = re.compile(r"\b([\wÀ-ỹ]+)\s+\1\b", re.I)
    for p in root.rglob("*"):
        if not (p.is_file() and p.suffix.lower() in TEXT_EXT):
            continue
        report["text_files"] += 1
        tree = parse_xml(p)
        r = tree.getroot()
        doc_changed = False
        if r.attrib.get("lang") != "vi":
            r.set("lang", "vi"); doc_changed = True
        if r.attrib.get(LANG_ATTR) != "vi":
            r.set(LANG_ATTR, "vi"); doc_changed = True
        seen = set()
        for el in r.iter():
            eid = el.attrib.get("id")
            if eid:
                if eid in seen:
                    report["duplicate_ids"].append(f"{p.relative_to(root)}#{eid}")
                seen.add(eid)
            for attr in ("href", "src"):
                val = el.attrib.get(attr)
                if not val or val.startswith(("http:", "https:", "mailto:", "data:", "#")):
                    continue
                rel = val.split("#", 1)[0]
                if rel and not (p.parent / PurePosixPath(rel)).resolve().exists():
                    report["broken_refs"].append(f"{p.relative_to(root)}:{val}")
            for slot in ("text", "tail"):
                txt = getattr(el, slot)
                if not txt:
                    continue
                # Only approved prose mutation: Book 7 exact known defect.
                if book["book"] == 7 and "anh ấy ấy" in txt:
                    setattr(el, slot, txt.replace("anh ấy ấy", "anh ấy"))
                    txt = getattr(el, slot)
                    doc_changed = True
                    report["repairs"].append(f"book7-known-defect:{p.relative_to(root)}")
                for m in repeat_re.finditer(txt):
                    token = m.group(1)
                    if len(token) > 1:
                        report["adjacent_repeat_candidates"].append({"file": str(p.relative_to(root)), "token": token})
        if doc_changed:
            tree.write(p, encoding="utf-8", xml_declaration=True)
            if "xhtml-lang=vi" not in report["repairs"]:
                report["repairs"].append("xhtml-lang=vi")

    # Zero-byte assets are always invalid.
    zeros = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.stat().st_size == 0]
    if zeros:
        die("ZERO_BYTE_ASSET", "Zero-byte EPUB resources", zeros[:50])
    if report["duplicate_ids"] or report["broken_refs"]:
        die("EPUB_STRUCTURAL_QA_FAIL", "Duplicate IDs or broken references", report)
    return report


def pack_epub(root: Path, dst: Path):
    with zipfile.ZipFile(dst, "w") as z:
        z.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.relative_to(root).as_posix() == "mimetype":
                continue
            z.write(p, p.relative_to(root).as_posix(), compress_type=zipfile.ZIP_DEFLATED)


def exact_final_qa(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            die("FINAL_CRC_FAIL", bad)
        infos = z.infolist()
        if not infos or infos[0].filename != "mimetype" or infos[0].compress_type != zipfile.ZIP_STORED:
            die("FINAL_MIMETYPE_ORDER_FAIL", "mimetype must be first and STORED")
        if z.read("mimetype") != MIMETYPE:
            die("FINAL_MIMETYPE_FAIL", "invalid mimetype")
    with tempfile.TemporaryDirectory(prefix="dcc-final-qa-") as td:
        root = Path(td)
        unzip_epub(path, root)
        opf = resolve_opf(root)
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in XML_EXT:
                parse_xml(p)
        lang_values = [(x.text or "").strip().lower() for x in parse_xml(opf).getroot().findall(".//{http://purl.org/dc/elements/1.1/}language")]
        if "vi" not in lang_values:
            die("FINAL_LANGUAGE_FAIL", f"dc:language={lang_values}")
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size, "zip_crc": "PASS", "mimetype": "PASS", "xml": "PASS", "language": "vi"}


def checkpoint(stage: str, payload: dict):
    url = env_first("RUNNER3_CORE_URL", "CORE_API_URL")
    token = env_first("RUNNER3_CORE_TOKEN", "CORE_API_TOKEN")
    required = os.getenv("DCC_REQUIRE_DURABLE_CHECKPOINT", "1") != "0"
    if not url:
        if required:
            die("D1_CHECKPOINT_CONFIG_MISSING", "RUNNER3_CORE_URL/CORE_API_URL is required for DURABLE_COMPLETE")
        return None
    body = json.dumps({"project": "ebook", "scope": payload["scope"], "stage": stage, "data": payload}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/checkpoints", data=body, method="POST", headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        die("D1_CHECKPOINT_HTTP_FAIL", f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except Exception as exc:
        die("D1_CHECKPOINT_FAIL", str(exc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True, choices=range(1, 9))
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--result", default="artifacts/dcc-v3-result.json")
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    book = next(x for x in manifest["books"] if x["book"] == args.book)
    bucket = os.getenv(manifest["artifact_store"]["bucket_env"], manifest["artifact_store"]["default_bucket"])
    s3 = s3_client()
    source_key = discover_source(s3, bucket, book, manifest["artifact_store"]["source_prefixes"])

    with tempfile.TemporaryDirectory(prefix=f"dcc-b{args.book}-") as td:
        td = Path(td); src = td / "source.epub"; root = td / "root"; root.mkdir(); final = td / "final.epub"
        try:
            s3.download_file(bucket, source_key, str(src))
        except Exception as exc:
            die("SOURCE_DOWNLOAD_FAIL", f"{source_key}: {exc}")
        source_sha, source_bytes = sha256_file(src), src.stat().st_size
        checkpoint("SOURCE_VERIFIED", {"scope": f"dcc-book-{args.book:02d}", "book": args.book, "source_key": source_key, "source_sha256": source_sha, "source_bytes": source_bytes})
        unzip_epub(src, root)
        qa = validate_and_repair(root, book)
        # Always canonical-repack, then QA the exact candidate bytes. Any repair happened before this point.
        pack_epub(root, final)
        final_qa = exact_final_qa(final)
        scope = f"dcc-book-{args.book:02d}"
        checkpoint("FINAL_FILE_QA_PASS", {"scope": scope, "book": args.book, "qa": final_qa, "repairs": qa["repairs"]})
        checkpoint("FINAL_BYTES_FROZEN", {"scope": scope, "book": args.book, **final_qa})
        stem = re.sub(r"(?i)(?:[-_. ]?(?:vi[-_. ]?)?v\d+)$", "", Path(source_key).stem).strip(" ._-") or f"Dungeon_Crawler_Carl_Book_{args.book}"
        final_name = f"{stem}.VI-v3.epub"
        final_key = f"{manifest['artifact_store']['final_prefix']}/book-{args.book:02d}/final/{final_name}"
        try:
            s3.upload_file(str(final), bucket, final_key, ExtraArgs={"ContentType": "application/epub+zip"})
            rb = td / "readback.epub"; s3.download_file(bucket, final_key, str(rb))
        except Exception as exc:
            die("FINAL_R2_IO_FAIL", f"{type(exc).__name__}: {exc}")
        rb_sha, rb_bytes = sha256_file(rb), rb.stat().st_size
        if rb_sha != final_qa["sha256"] or rb_bytes != final_qa["bytes"]:
            die("FINAL_R2_READBACK_MISMATCH", "R2 bytes differ from frozen final", {"local": final_qa, "readback_sha256": rb_sha, "readback_bytes": rb_bytes})
        result = {
            "ok": True, "status": "DURABLE_COMPLETE", "series": manifest["series_id"], "book": args.book,
            "scope": scope, "mode": manifest["mode"], "source_r2_key": source_key,
            "source_sha256": source_sha, "source_bytes": source_bytes,
            "repairs": qa["repairs"], "adjacent_repeat_candidates": qa["adjacent_repeat_candidates"][:100],
            "final_file_qa": "PASS", "final_bytes_frozen": True,
            "final_r2_key": final_key, "final_sha256": final_qa["sha256"], "final_bytes": final_qa["bytes"],
            "r2_readback_verified": True,
        }
        checkpoint("DURABLE_COMPLETE", result)
        out = Path(args.result); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
