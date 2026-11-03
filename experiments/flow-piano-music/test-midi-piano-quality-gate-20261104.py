#!/usr/bin/env python3
"""Structural audition gate tests, synthetic MIDI only."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from symusic import Note, Score, Tempo, Track

MOD = Path(__file__).with_name("midi-piano-quality-gate-20261104.py")
spec = importlib.util.spec_from_file_location("midi_piano_gate", MOD)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def synth(path, duration_ticks=400, with_drums=False, with_other=False, tick_step=480):
    score = Score(480)
    score.tempos.append(Tempo(0, 120.0))
    piano = Track(name="Piano", program=0, is_drum=False)
    for i in range(16):
        piano.notes.append(Note(time=i*tick_step, duration=duration_ticks,
                                pitch=60 + (i % 5), velocity=75))
    score.tracks.append(piano)
    if with_drums:
        drums = Track(name="Drums", program=0, is_drum=True)
        drums.notes.append(Note(time=0, duration=120, pitch=36, velocity=80))
        score.tracks.append(drums)
    if with_other:
        other = Track(name="Pan Flute", program=75, is_drum=False)
        other.notes.append(Note(time=0, duration=240, pitch=72, velocity=80))
        score.tracks.append(other)
    score.dump_midi(str(path))


class StructuralGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="midi-qa-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "candidate.mid"

    def test_piano_only_valid_duration_is_structurally_accepted(self):
        synth(self.path)
        info = gate.analyze_midi(self.path)
        self.assertEqual(info["status"], "STRUCTURAL_PASS", info)
        self.assertEqual(info["piano_notes"], 16)

    def test_short_midi_rejected(self):
        synth(self.path, tick_step=60)
        info = gate.analyze_midi(self.path)
        self.assertIn("DURATION_TOO_SHORT", info["reasons"])

    def test_drums_rejected(self):
        synth(self.path, with_drums=True)
        info = gate.analyze_midi(self.path)
        self.assertIn("DRUMS_IN_PIANO_ONLY_OUTPUT", info["reasons"])

    def test_non_piano_rejected(self):
        synth(self.path, with_other=True)
        info = gate.analyze_midi(self.path)
        self.assertIn("NON_PIANO_INSTRUMENTS", info["reasons"])

    def test_few_piano_notes_rejected(self):
        synth(self.path)
        s = Score.from_midi(self.path.read_bytes())
        s.tracks[0].notes = s.tracks[0].notes[:5]
        s.dump_midi(str(self.path))
        info = gate.analyze_midi(self.path)
        self.assertIn("TOO_FEW_PIANO_NOTES", info["reasons"])


if __name__ == "__main__":
    unittest.main()
