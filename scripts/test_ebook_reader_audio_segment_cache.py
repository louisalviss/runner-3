#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

import ebook_reader_audio_tts_v2 as cache_mod


class EbookAudioSegmentCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_dir = cache_mod.CACHE_DIR
        self.old_max = cache_mod.CACHE_MAX_BYTES
        cache_mod.CACHE_DIR = self.root / "cache"
        cache_mod.CACHE_MAX_BYTES = 16 * 1024
        self.boundaries = [
            {"text": "Xin", "offsetMs": 0.0, "durationMs": 100.0},
            {"text": "chao", "offsetMs": 120.0, "durationMs": 140.0},
        ]

    def tearDown(self):
        cache_mod.CACHE_DIR = self.old_dir
        cache_mod.CACHE_MAX_BYTES = self.old_max
        self.temp.cleanup()

    def source(self, name="source.mp3", fill=b"a"):
        path = self.root / name
        path.write_bytes(b"ID3" + fill * 2000)
        return path

    def test_store_and_reuse_exact_bytes_and_boundaries(self):
        text = "Xin chao."
        source = self.source()
        cache_mod._store_cached_segment(text, source, self.boundaries)
        target = self.root / "target.mp3"
        loaded = cache_mod._load_cached_segment(text, target)
        self.assertEqual(loaded, self.boundaries)
        self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_corrupt_media_is_rejected(self):
        text = "Doan bi loi."
        source = self.source()
        cache_mod._store_cached_segment(text, source, self.boundaries)
        key = cache_mod._cache_key(text)
        media_path, _meta_path = cache_mod._cache_paths(key)
        media_path.write_bytes(media_path.read_bytes() + b"corrupt")
        self.assertIsNone(cache_mod._load_cached_segment(text, self.root / "out.mp3"))

    def test_cache_key_changes_with_text(self):
        self.assertNotEqual(cache_mod._cache_key("A"), cache_mod._cache_key("B"))

    def test_prune_keeps_cache_bounded(self):
        cache_mod.CACHE_MAX_BYTES = 3000
        cache_mod._store_cached_segment("one", self.source("one.mp3", b"1"), self.boundaries)
        cache_mod._store_cached_segment("two", self.source("two.mp3", b"2"), self.boundaries)
        total = sum(path.stat().st_size for path in cache_mod.CACHE_DIR.glob("*.mp3"))
        self.assertLessEqual(total, cache_mod.CACHE_MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
