#!/usr/bin/env python3
"""Deterministic-enough EPUB3 packaging for chapter-oriented story artifacts.

The builder intentionally owns only presentation packaging. Acquisition, editing,
continuity and QA remain source-adapter concerns. Chapter XHTML paths use the
`chNNNN.xhtml` convention consumed by `epub_semantic.py`.
"""
from __future__ import annotations

import hashlib
import html
import re
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Iterable


def _paragraphs(body: str) -> str:
    blocks: list[str] = []
    for raw in re.split(r"\n\s*\n|\n", body.replace("\r\n", "\n")):
        text = " ".join(raw.split()).strip()
        if not text:
            continue
        if re.fullmatch(r"[-—–_=*·•]{4,}", text):
            blocks.append("<hr/>")
        else:
            blocks.append(f"<p>{html.escape(text)}</p>")
    return "".join(blocks)


def _chapter_xhtml(label: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="vi" lang="vi">'
        f'<head><meta charset="utf-8"/><title>{html.escape(label)}</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
        f'<body><h1>{html.escape(label)}</h1>{_paragraphs(body)}</body></html>'
    )


def _source_xhtml(source_note: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="vi" lang="vi">'
        '<head><meta charset="utf-8"/><title>Nguồn</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
        f'<body><h1>Nguồn</h1><p>{html.escape(source_note)}</p></body></html>'
    )


def build_epub(
    chapters: Iterable[dict[str, Any]],
    output: str | Path,
    *,
    title: str,
    author: str,
    language: str = "vi",
    source_note: str | None = None,
    identifier_seed: str | None = None,
) -> dict[str, Any]:
    rows = list(chapters)
    if not rows:
        raise ValueError("at least one chapter is required")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)

    seed = identifier_seed or f"{title}\n{author}\n{len(rows)}"
    uid_hex = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    uid = str(uuid.UUID(uid_hex))

    manifest: list[str] = []
    spine: list[str] = []
    nav_items: list[str] = []
    ncx_items: list[str] = []
    chapter_files: list[tuple[str, str]] = []

    for index, row in enumerate(rows, 1):
        body = str(row.get("body") or "").strip()
        if not body:
            raise ValueError(f"chapter {index} body is empty")
        chapter_title = str(row.get("title") or row.get("title_vi") or f"Chương {index}").strip()
        label = chapter_title if chapter_title.lower().startswith("chương ") else f"Chương {index}: {chapter_title}"
        filename = f"ch{index:04d}.xhtml"
        item_id = f"ch{index:04d}"
        chapter_files.append((filename, _chapter_xhtml(label, body)))
        manifest.append(f'<item id="{item_id}" href="{filename}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{item_id}"/>')
        nav_items.append(f'<li><a href="{filename}">{html.escape(label)}</a></li>')
        ncx_items.append(
            f'<navPoint id="nav{index}" playOrder="{index}"><navLabel><text>{html.escape(label)}</text></navLabel>'
            f'<content src="{filename}"/></navPoint>'
        )

    source_manifest = ""
    source_spine = ""
    source_nav = ""
    source_file: tuple[str, str] | None = None
    if source_note:
        source_manifest = '<item id="source" href="source.xhtml" media-type="application/xhtml+xml"/>'
        source_spine = '<itemref idref="source"/>'
        source_nav = '<li><a href="source.xhtml">Nguồn</a></li>'
        source_file = ("source.xhtml", _source_xhtml(source_note))

    nav = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi">'
        f'<head><title>Mục lục</title></head><body><nav epub:type="toc" id="toc"><h1>Mục lục</h1><ol>'
        f'{"".join(nav_items)}{source_nav}</ol></nav></body></html>'
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f'<head><meta name="dtb:uid" content="urn:uuid:{uid}"/></head>'
        f'<docTitle><text>{html.escape(title)}</text></docTitle><navMap>{"".join(ncx_items)}</navMap></ncx>'
    )
    modified = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">urn:uuid:{uid}</dc:identifier>'
        f'<dc:title>{html.escape(title)}</dc:title><dc:creator>{html.escape(author)}</dc:creator>'
        f'<dc:language>{html.escape(language)}</dc:language><meta property="dcterms:modified">{modified}</meta>'
        '</metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        f'<item id="css" href="style.css" media-type="text/css"/>{"".join(manifest)}{source_manifest}</manifest>'
        f'<spine toc="ncx">{"".join(spine)}{source_spine}</spine></package>'
    )
    container = (
        '<?xml version="1.0"?><container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>'
    )
    css = (
        "body{font-family:serif;line-height:1.62;margin:5%;}"
        "h1{font-size:1.35em;text-align:center;margin:1.5em 0;}"
        "p{text-align:justify;text-indent:1.35em;margin:.42em 0;}"
        "hr{border:0;border-top:1px solid #aaa;margin:1.5em 20%;}"
    )

    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/style.css", css)
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/toc.ncx", ncx)
        zf.writestr("OEBPS/content.opf", opf)
        for filename, xhtml in chapter_files:
            zf.writestr("OEBPS/" + filename, xhtml, compress_type=zipfile.ZIP_DEFLATED)
        if source_file:
            zf.writestr("OEBPS/" + source_file[0], source_file[1], compress_type=zipfile.ZIP_DEFLATED)

    data = out.read_bytes()
    return {
        "output": str(out),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "chapter_count": len(rows),
        "identifier": f"urn:uuid:{uid}",
    }
