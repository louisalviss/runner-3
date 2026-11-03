#!/usr/bin/env python3
"""Small integration regression tests for blind listening gate."""
import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave

HERE = Path(__file__).resolve().parent
MODULE = HERE / "music-blind-listening-gate-20261103.py"
spec = importlib.util.spec_from_file_location("music_ab_gate", MODULE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def generate_wav(path, hz):
    sr, count = 44100, int(8.2 * 44100)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(count):
            frames.extend(struct.pack("<h", int(3000 * math.sin(2 * math.pi * hz * i / sr))))
        w.writeframes(frames)


class MusicABTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="music-ab-qa-")
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        for tag, freq in [("x", 220), ("y", 392)]:
            generate_wav(self.d / f"{tag}.wav", freq)
        self.candidates = [
            {"id": name, "path": str(self.d / f"{name}.wav"),
             "rights": "original", "origin": "SYNTHETIC_QA_ONLY"}
            for name in ["x", "y"]
        ]

    def run_gate(self, *args):
        return subprocess.run(
            ["python3", str(MODULE), *args],
            text=True, capture_output=True, timeout=80)

    def manifest(self, values):
        p = self.d / "manifest.json"
        p.write_text(json.dumps({"candidates": values}), encoding="utf-8")
        return str(p)

    def test_reject_single_candidate(self):
        p = self.run_gate("prepare", "--manifest", self.manifest(self.candidates[:1]),
                          "--output", str(self.d / "output"))
        self.assertEqual(p.returncode, 2)
        self.assertIn("2..16", p.stderr)

    def test_reject_unknown_rights(self):
        data = [dict(c) for c in self.candidates]
        data[0]["rights"] = "unknown"
        p = self.run_gate("prepare", "--manifest", self.manifest(data),
                          "--output", str(self.d / "output"))
        self.assertEqual(p.returncode, 2)
        self.assertIn("rights", p.stderr)

    def test_prepare_reveal_and_reject_double_ratings(self):
        out = self.d / "output"
        p = self.run_gate("prepare", "--manifest", self.manifest(self.candidates),
                          "--output", str(out), "--seed", "17")
        self.assertEqual(p.returncode, 0, p.stderr)
        public = json.loads((out / "blind-ratings.json").read_text())
        sealed = json.loads((out / "sealed-map.json").read_text())
        self.assertEqual(len(public["pairs"]), 1)
        self.assertEqual(set(sealed["candidates"]), {"x", "y"})
        self.assertNotIn('"x"', json.dumps(public))
        self.assertNotIn('"y"', json.dumps(public))
        self.assertTrue((out / "pair-01-A.mp3").exists())
        self.assertTrue((out / "pair-01-B.mp3").exists())
        public["pairs"][0]["choice"] = "A"
        ratings = self.d / "ratings.json"
        ratings.write_text(json.dumps(public))
        score = self.run_gate("reveal", "--sealed", str(out / "sealed-map.json"),
                              "--ratings", str(ratings))
        self.assertEqual(score.returncode, 0, score.stderr)
        scores = json.loads(score.stdout)["scores"]
        self.assertEqual(sum(v["wins"] for v in scores.values()), 1)
        self.assertEqual(sum(v["losses"] for v in scores.values()), 1)
        public["pairs"].append(public["pairs"][0])
        ratings.write_text(json.dumps(public))
        double = self.run_gate("reveal", "--sealed", str(out / "sealed-map.json"),
                               "--ratings", str(ratings))
        self.assertEqual(double.returncode, 2)
        self.assertIn("duplicated", double.stderr)
        rerun = self.run_gate("prepare", "--manifest", str(self.d / "manifest.json"),
                              "--output", str(out))
        self.assertEqual(rerun.returncode, 2)
        self.assertIn("must be empty", rerun.stderr)


if __name__ == "__main__":
    unittest.main()
