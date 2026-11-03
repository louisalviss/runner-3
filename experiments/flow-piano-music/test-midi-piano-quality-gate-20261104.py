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


    def test_short_sounding_tail_of_approved_style_is_not_rejected(self):
        # Original C ends its last note before the 8.0s audio tail.
        synth(self.path, duration_ticks=250, tick_step=450)
        info = gate.analyze_midi(self.path)
        self.assertEqual(info["status"], "STRUCTURAL_PASS", info)
        self.assertGreaterEqual(info["duration_seconds"], 7.0)
        self.assertLess(info["duration_seconds"], 7.5)

    def test_exact_repetition_rejected_and_changed_melody_candidate(self):
        ref = Path(self.tmp.name) / "ref.mid"
        full = Path(self.tmp.name) / "repeated.mid"
        synth(ref, duration_ticks=250, tick_step=450)
        s = Score.from_midi(ref.read_bytes())
        for note in list(s.tracks[0].notes):
            echo = note.copy()
            echo.time += 7200  # 7.5 seconds at 120BPM and 480TPQ.
            s.tracks[0].notes.append(echo)
        s.dump_midi(str(full))
        first = gate.compare_novelty(ref, full)
        self.assertEqual(first["status"], "NEAR_COPY_REJECT", first)
        self.assertEqual(first["duplicate_ratio"], 1.0)
        s = Score.from_midi(full.read_bytes())
        for note in s.tracks[0].notes:
            if note.time >= 7200:
                note.pitch += 7
        s.dump_midi(str(full))
        changed = gate.compare_novelty(ref, full)
        self.assertEqual(changed["status"], "NOVELTY_CANDIDATE", changed)
        self.assertLess(changed["duplicate_ratio"], 0.85)

    def test_too_few_events_novelty_unverified(self):
        synth(self.path)
        outcome = gate.compare_novelty(self.path, self.path)
        self.assertEqual(outcome["status"], "NOVELTY_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
