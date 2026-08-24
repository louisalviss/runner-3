#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ebook_checkpoint as ec


class EbookCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manifest = {
            "schema_version": 1,
            "book_id": "sample-book",
            "title": "Sample Book",
            "artifact_store": {"kind": "dropbox", "relative_root": "sample-book"},
            "editorial": {
                "pipeline_version": 1,
                "editor_profile": "gold-standard",
                "prompt_version": "v1",
                "story_bible_version": 1,
                "glossary_version": 1,
                "model": "test-model",
            },
        }
        self.source = self.root / "source.txt"
        self.artifact = self.root / "chapter.txt"
        self.meta = self.root / "chapter.meta.json"
        self.config = self.root / "rules.md"
        self.source.write_text("source-v1", encoding="utf-8")
        self.artifact.write_text("edited-v1", encoding="utf-8")
        self.config.write_text("rules-v1", encoding="utf-8")
        sidecar = ec.build_sidecar(
            self.manifest,
            4,
            source_file=self.source,
            artifact_file=self.artifact,
            config_files=[self.config],
        )
        ec.write_json(self.meta, sidecar)

    def tearDown(self):
        self.tmp.cleanup()

    def decision(self, checkpoint):
        with patch.object(ec, "get_chapter", return_value=checkpoint):
            return ec.inspect_resume(
                self.manifest,
                4,
                source_file=self.source,
                artifact_file=self.artifact,
                artifact_meta_file=self.meta,
                config_files=[self.config],
            )

    def test_verified_artifact_recovers_missing_checkpoint(self):
        result = self.decision(None)
        self.assertEqual(result["action"], "recover")
        self.assertTrue(result["sidecar_verified"])

    def test_matching_checkpoint_skips(self):
        sidecar = json.loads(self.meta.read_text(encoding="utf-8"))
        checkpoint = {
            "status": "success",
            "position": {
                "phase": "complete",
                "semantic_input_sha256": sidecar["semantic_input_sha256"],
                "artifact_sha256": sidecar["artifact_sha256"],
                "artifact_meta_sha256": ec.file_sha256(self.meta),
            },
        }
        result = self.decision(checkpoint)
        self.assertEqual(result["action"], "skip")

    def test_source_change_forces_edit(self):
        self.source.write_text("source-v2", encoding="utf-8")
        result = self.decision(None)
        self.assertEqual(result["action"], "edit")
        self.assertFalse(result["sidecar_verified"])

    def test_config_change_forces_edit(self):
        self.config.write_text("rules-v2", encoding="utf-8")
        result = self.decision(None)
        self.assertEqual(result["action"], "edit")
        self.assertFalse(result["sidecar_verified"])

    def test_artifact_change_forces_edit(self):
        self.artifact.write_text("tampered-output", encoding="utf-8")
        result = self.decision(None)
        self.assertEqual(result["action"], "edit")
        self.assertFalse(result["sidecar_verified"])

    def test_missing_sidecar_never_recovers(self):
        self.meta.unlink()
        result = self.decision(None)
        self.assertEqual(result["action"], "edit")


if __name__ == "__main__":
    unittest.main()
