#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import youtube_story as ys
from story_epub import build_epub


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture() -> dict:
    segments = []
    for i in range(18):
        sentence = (f"Đoạn {i + 1}: Ngụy Nghịch Sinh bước tiếp trong đại điện và ghi nhớ biến cố thứ {i + 1}. " * 4).strip()
        segments.append({"start_ms": i * 5000, "duration_ms": 4200, "text": sentence})
    text = "\n".join(row["text"] for row in segments)
    return {
        "ok": True,
        "identity_validated": True,
        "video_id": "tRhvH4NUrZQ",
        "coverage_ratio": 0.999,
        "segment_count": len(segments),
        "segments": segments,
        "text": text,
        "language": "vi",
        "media_downloaded": False,
        "video_rendered": False,
    }


class YouTubeStoryTests(unittest.TestCase):
    def test_validate_exact_identity_and_hash(self) -> None:
        obj = fixture()
        result = ys.validate_transcript(obj, "tRhvH4NUrZQ")
        self.assertTrue(result["ok"])
        self.assertEqual(result["segment_count"], len(obj["segments"]))
        self.assertEqual(result["transcript_sha256"], hashlib.sha256(obj["text"].encode()).hexdigest())
        mismatch = ys.validate_transcript(obj, "AAAAAAAAAAA")
        self.assertFalse(mismatch["ok"])
        self.assertIn("video_id_mismatch", mismatch["failures"])

    def test_packetize_covers_every_segment_once(self) -> None:
        obj = fixture()
        packets = ys.packetize(obj["segments"], target_chars=1000, min_chars=1000, max_chars=1500)
        self.assertGreater(len(packets), 1)
        cursor = 0
        for expected_id, packet in enumerate(packets, 1):
            self.assertEqual(packet["packet_id"], expected_id)
            self.assertEqual(packet["segment_start"], cursor)
            self.assertGreaterEqual(packet["segment_end"], packet["segment_start"])
            cursor = packet["segment_end"] + 1
            self.assertEqual(packet["source_sha256"], hashlib.sha256(packet["source_text"].encode()).hexdigest())
        self.assertEqual(cursor, len(obj["segments"]))

    def test_assemble_and_qa_exact_packet_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            obj = fixture()
            packets = ys.packetize(obj["segments"], target_chars=1000, min_chars=1000, max_chars=1500)
            dump(work / "source.json", {
                "video_id": obj["video_id"],
                "transcript_sha256": hashlib.sha256(obj["text"].encode()).hexdigest(),
                "comments_policy": "skip",
                "language": "vi",
            })
            for packet in packets:
                dump(work / "packets" / f"packet-{packet['packet_id']:04d}.json", packet)
                body = packet["source_text"]
                dump(work / "edits" / f"packet-{packet['packet_id']:04d}.edit.json", {
                    "schema": ys.EDIT_SCHEMA,
                    "packet_id": packet["packet_id"],
                    "input_sha256": packet["source_sha256"],
                    "source_chars": packet["source_chars"],
                    "edited_body": body,
                    "edited_chars": len(body),
                    "length_ratio": 1.0,
                    "chapter_title_hint": "Khởi đầu" if packet["packet_id"] == 1 else "",
                    "scene_break_after": packet["packet_id"] % 2 == 0,
                    "continuity_state": {},
                })
            rc = ys.cmd_assemble(SimpleNamespace(work=str(work), min_chapter_chars=1000, max_chapter_chars=4000))
            self.assertEqual(rc, 0)
            chapters = ys.load_numbered(work / "chapters", "chapter-*.json")
            self.assertTrue(chapters)
            used = [pid for chapter in chapters for pid in chapter["source_packet_ids"]]
            self.assertEqual(used, list(range(1, len(packets) + 1)))
            rc = ys.cmd_qa(SimpleNamespace(work=str(work), expect_transcript_sha256=""))
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads((work / "qa.json").read_text())["ok"])

    def test_epub_uses_semantic_chapter_paths(self) -> None:
        chapters = [
            {"title": "Mở đầu", "body": "Ngụy Nghịch Sinh tỉnh lại.\n\nHắn nhìn quanh đại điện."},
            {"title": "Triều đình", "body": "Quần thần im lặng.\n\nMột biến cố mới bắt đầu."},
        ]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "story.epub"
            result = build_epub(chapters, out, title="Truyện thử", author="Nguồn YouTube", source_note="video test")
            self.assertEqual(result["chapter_count"], 2)
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
                self.assertEqual(names[0], "mimetype")
                self.assertEqual(zf.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                self.assertIn("OEBPS/ch0001.xhtml", names)
                self.assertIn("OEBPS/ch0002.xhtml", names)
                self.assertIn("OEBPS/source.xhtml", names)
                nav = zf.read("OEBPS/nav.xhtml").decode()
                self.assertIn("Mở đầu", nav)
                self.assertIn("Nguồn", nav)


if __name__ == "__main__":
    unittest.main()
