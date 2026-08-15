#!/usr/bin/env python3

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CHAPTER_RE = re.compile(r"^Chương\s+(\d+)\.\s*(.+?)\s*$", re.I)
NAV = {"Chương trước", "Chương sau"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_tienvuc_page(text):
    lines = [x.strip() for x in text.replace("\r\n", "\n").split("\n") if x.strip()]
    hits = []
    for i, line in enumerate(lines):
        m = CHAPTER_RE.match(line)
        if m:
            hits.append((i, int(m.group(1)), m.group(2)))
    if not hits:
        raise ValueError("No TiênVuc chapter heading found")
    hi, no, title = hits[1] if len(hits) > 1 else hits[0]
    start = hi + 1
    seen_nav = 0
    while start < len(lines) and seen_nav < 2:
        if lines[start] in NAV:
            seen_nav += 1
        start += 1
    if seen_nav < 2:
        start = hi + 1
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i] in NAV:
            end = i
            break
    body = "\n".join(lines[start:end]).strip()
    if not body:
        raise ValueError(f"Empty body for chapter {no}")
    return {"source_part": no, "source_title": title, "body": body, "body_chars": len(body)}


def load_bible(path):
    bible = read_json(path)
    bible.setdefault("entities", [])
    bible.setdefault("style", {})
    return bible


def canonicalize_known_terms(text, bible):
    changes = []
    out = text
    for ent in bible.get("entities", []):
        canonical = ent.get("canonical", "").strip()
        if not canonical:
            continue
        for alias in ent.get("aliases", []):
            alias = alias.strip()
            if not alias or alias == canonical:
                continue
            count = out.count(alias)
            if count:
                out = out.replace(alias, canonical)
                changes.append({"from": alias, "to": canonical, "count": count})
    return out, changes


def cmd_clean(args):
    src, out_dir = Path(args.input), Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    bible = load_bible(args.bible)
    files = sorted(src.rglob("page.txt")) if src.is_dir() else [src]
    results = []
    for p in files:
        try:
            parsed = parse_tienvuc_page(p.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            continue
        body, changes = canonicalize_known_terms(parsed["body"], bible)
        rec = {**parsed, "source": "tienvuc", "body": body, "normalizations": changes,
               "cleaned_at": now_iso(), "sha256": hashlib.sha256(body.encode()).hexdigest()}
        write_json(out_dir / f"part-{parsed['source_part']:04d}.json", rec)
        results.append(rec)
    write_json(out_dir / "manifest.json", {"stage": "clean", "source": "tienvuc", "count": len(results),
                                              "parts": [x["source_part"] for x in results], "generated_at": now_iso()})
    print(json.dumps({"stage": "clean", "count": len(results)}, ensure_ascii=False))
    return 0 if results else 2


def editor_instructions(bible):
    return "\n".join(f"- {x}" for x in bible.get("style", {}).get("rules", []))


def cmd_packet(args):
    clean_dir, out_dir = Path(args.clean), Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    bible = load_bible(args.bible)
    produced = 0
    for p in sorted(clean_dir.glob("part-*.json")):
        r = read_json(p)
        relevant = []
        for ent in bible.get("entities", []):
            names = [ent.get("canonical", "")] + ent.get("aliases", [])
            if any(n and n in r["body"] for n in names):
                relevant.append(ent)
        packet = {
            "schema": "vbth-editor-packet-v1",
            "source_part": r["source_part"],
            "source_title": r["source_title"],
            "input_sha256": r["sha256"],
            "instructions": editor_instructions(bible),
            "relevant_story_bible": relevant,
            "body": r["body"],
            "expected_output": {"source_part": r["source_part"], "input_sha256": r["sha256"],
                                "edited_title": r["source_title"], "edited_body": "...",
                                "new_entities": [], "editor_notes": []}
        }
        write_json(out_dir / f"part-{r['source_part']:04d}.packet.json", packet)
        produced += 1
    print(json.dumps({"stage": "packet", "count": produced}, ensure_ascii=False))
    return 0 if produced else 2


def validate_edit(clean, edit, bible):
    errors = []
    if edit.get("source_part") != clean.get("source_part"):
        errors.append("source_part mismatch")
    if edit.get("input_sha256") != clean.get("sha256"):
        errors.append("input_sha256 mismatch/stale edit")
    body = str(edit.get("edited_body", "")).strip()
    if not body:
        errors.append("edited_body empty")
        return errors
    ratio = len(body) / max(1, len(clean["body"]))
    if ratio < 0.72 or ratio > 1.35:
        errors.append(f"length ratio suspicious: {ratio:.2f}")
    for ent in bible.get("entities", []):
        canonical = ent.get("canonical", "")
        for alias in ent.get("aliases", []):
            if alias and alias != canonical and alias in body:
                errors.append(f"noncanonical alias remains: {alias} -> {canonical}")
    return errors


def cmd_apply(args):
    clean_dir, edits_dir, out_dir = Path(args.clean), Path(args.edits), Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    bible = load_bible(args.bible)
    report = []
    for ep in sorted(edits_dir.glob("part-*.edit.json")):
        edit = read_json(ep)
        part = int(edit["source_part"])
        cp = clean_dir / f"part-{part:04d}.json"
        if not cp.exists():
            report.append({"part": part, "ok": False, "errors": ["missing clean source"]})
            continue
        clean = read_json(cp)
        errors = validate_edit(clean, edit, bible)
        report.append({"part": part, "ok": not errors, "errors": errors})
        if not errors:
            write_json(out_dir / f"part-{part:04d}.json", {
                "source_part": part, "source_title": clean["source_title"],
                "edited_title": edit.get("edited_title") or clean["source_title"],
                "body": edit["edited_body"].strip(), "input_sha256": clean["sha256"],
                "edited_at": now_iso(), "new_entities": edit.get("new_entities", []),
                "editor_notes": edit.get("editor_notes", [])})
    write_json(out_dir / "qa-apply.json", {"results": report, "generated_at": now_iso()})
    failed = sum(not x["ok"] for x in report)
    print(json.dumps({"stage": "apply", "checked": len(report), "failed": failed}, ensure_ascii=False))
    return 1 if failed else 0


def cmd_merge(args):
    edited_dir, out_dir = Path(args.edited), Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping = read_json(args.map)
    merged = []
    for ch in mapping.get("chapters", []):
        bodies, missing = [], []
        for part in ch["source_parts"]:
            p = edited_dir / f"part-{int(part):04d}.json"
            if not p.exists():
                missing.append(part)
            else:
                bodies.append(read_json(p)["body"].strip())
        if missing:
            print(f"skip original chapter {ch.get('original_no')}: missing parts {missing}", file=sys.stderr)
            continue
        body = "\n\n".join(bodies)
        rec = {"original_no": ch["original_no"], "volume": ch.get("volume"), "title_vi": ch["title_vi"],
               "title_zh": ch.get("title_zh"), "source_parts": ch["source_parts"], "body": body,
               "body_chars": len(body), "merged_at": now_iso()}
        write_json(out_dir / f"chapter-{int(ch['original_no']):04d}.json", rec)
        merged.append(rec)
    write_json(out_dir / "manifest.json", {"stage": "merge", "count": len(merged),
                                              "chapters": [x["original_no"] for x in merged], "generated_at": now_iso()})
    print(json.dumps({"stage": "merge", "count": len(merged)}, ensure_ascii=False))
    return 0 if merged else 2


def cmd_qa(args):
    chapter_dir = Path(args.chapters)
    bible = load_bible(args.bible)
    report = []
    for p in sorted(chapter_dir.glob("chapter-*.json")):
        ch = read_json(p)
        issues = []
        for ent in bible.get("entities", []):
            canonical = ent.get("canonical", "")
            for alias in ent.get("aliases", []):
                if alias and alias != canonical and alias in ch["body"]:
                    issues.append({"type": "alias", "found": alias, "canonical": canonical})
        for marker in ["Chương trước", "Chương sau", "Tiên Vực", "Đăng nhập"]:
            if marker in ch["body"]:
                issues.append({"type": "boilerplate", "found": marker})
        report.append({"chapter": ch["original_no"], "issues": issues, "ok": not issues})
    summary = {"stage": "qa", "checked": len(report), "failed": sum(not x["ok"] for x in report),
               "results": report, "generated_at": now_iso()}
    write_json(args.output, summary)
    print(json.dumps({"stage": "qa", "checked": summary["checked"], "failed": summary["failed"]}, ensure_ascii=False))
    return 1 if summary["failed"] else 0


def epub_xhtml(title, body):
    paras = []
    for raw in body.split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        paras.append("<hr/>" if raw == "---" else f"<p>{html.escape(raw)}</p>")
    return f'''<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" lang="vi"><head><title>{html.escape(title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body><h1>{html.escape(title)}</h1>{''.join(paras)}</body></html>'''


def cmd_epub(args):
    chapters = [read_json(p) for p in sorted(Path(args.chapters).glob("chapter-*.json"))]
    if not chapters:
        return 2
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    uid = "urn:uuid:" + hashlib.sha256((args.title + args.author).encode()).hexdigest()[:32]
    nav_items = []; manifest = []; spine = []; files = []
    for i, ch in enumerate(chapters, 1):
        fn = f"chapter-{i:04d}.xhtml"; label = f"Chương {ch['original_no']}: {ch['title_vi']}"
        files.append((fn, epub_xhtml(label, ch["body"])))
        nav_items.append(f'<li><a href="{fn}">{html.escape(label)}</a></li>')
        manifest.append(f'<item id="c{i}" href="{fn}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{i}"/>')
    nav = f'''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi"><head><title>Mục lục</title></head><body><nav epub:type="toc"><h1>Mục lục</h1><ol>{''.join(nav_items)}</ol></nav></body></html>'''
    opf = f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">{uid}</dc:identifier><dc:title>{html.escape(args.title)}</dc:title><dc:creator>{html.escape(args.author)}</dc:creator><dc:language>vi</dc:language><meta property="dcterms:modified">{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="css" href="style.css" media-type="text/css"/>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>'''
    container_xml = '''<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
    css = "body{font-family:serif;line-height:1.55;margin:5%;}h1{font-size:1.35em;}p{text-indent:1.5em;margin:.45em 0;}hr{margin:1.5em 30%;}"
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container_xml); z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav); z.writestr("OEBPS/style.css", css)
        for fn, xhtml in files: z.writestr("OEBPS/" + fn, xhtml)
    print(json.dumps({"stage": "epub", "chapters": len(chapters), "output": str(out)}, ensure_ascii=False))
    return 0


def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("clean"); a.add_argument("--input", required=True); a.add_argument("--output", required=True); a.add_argument("--bible", required=True); a.set_defaults(func=cmd_clean)
    a = sub.add_parser("packet"); a.add_argument("--clean", required=True); a.add_argument("--output", required=True); a.add_argument("--bible", required=True); a.set_defaults(func=cmd_packet)
    a = sub.add_parser("apply"); a.add_argument("--clean", required=True); a.add_argument("--edits", required=True); a.add_argument("--output", required=True); a.add_argument("--bible", required=True); a.set_defaults(func=cmd_apply)
    a = sub.add_parser("merge"); a.add_argument("--edited", required=True); a.add_argument("--output", required=True); a.add_argument("--map", required=True); a.set_defaults(func=cmd_merge)
    a = sub.add_parser("qa"); a.add_argument("--chapters", required=True); a.add_argument("--bible", required=True); a.add_argument("--output", required=True); a.set_defaults(func=cmd_qa)
    a = sub.add_parser("epub"); a.add_argument("--chapters", required=True); a.add_argument("--output", required=True); a.add_argument("--title", default="Vương Bài Tiến Hóa"); a.add_argument("--author", default="Quyển Thổ"); a.set_defaults(func=cmd_epub)
    args = p.parse_args(); return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
