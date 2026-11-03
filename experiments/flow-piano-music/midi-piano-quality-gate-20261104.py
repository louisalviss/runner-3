#!/usr/bin/env python3
"""Structural MIDI-only audition gate; never declares musical quality."""
from pathlib import Path


def analyze_midi(path, min_seconds=7.5, max_seconds=10.0, min_piano_notes=12):
    from symusic import Score

    path = Path(path)
    score = Score.from_midi(path.read_bytes())
    ppq = score.ticks_per_quarter
    if ppq <= 0:
        raise ValueError("Invalid MIDI ticks_per_quarter")
    populated = [track for track in score.tracks if len(track.notes)]
    piano_tracks = [t for t in populated if not t.is_drum and 0 <= t.program <= 7]
    piano_notes = sum(len(t.notes) for t in piano_tracks)
    drum_notes = sum(len(t.notes) for t in populated if t.is_drum)
    other_notes = sum(len(t.notes) for t in populated if not t.is_drum and not 0 <= t.program <= 7)
    last_tick = max((int(n.time) + int(n.duration) for t in populated for n in t.notes), default=0)

    # Calculate exact MIDI musical seconds for tempo-map changes.
    tempi = sorted(score.tempos, key=lambda t: t.time)
    seconds = 0.0
    last = 0
    qpm = 120.0
    for t in tempi:
        stamp = max(0, min(int(t.time), last_tick))
        if stamp > last:
            seconds += (stamp - last) * 60.0 / (qpm * ppq)
            last = stamp
        if not 20 < float(t.qpm) < 300:
            raise ValueError("Unreasonable MIDI tempo")
        qpm = float(t.qpm)
    if last_tick > last:
        seconds += (last_tick - last) * 60.0 / (qpm * ppq)

    reasons = []
    if seconds < min_seconds:
        reasons.append("DURATION_TOO_SHORT")
    if seconds > max_seconds:
        reasons.append("DURATION_TOO_LONG")
    if piano_notes < min_piano_notes:
        reasons.append("TOO_FEW_PIANO_NOTES")
    if drum_notes:
        reasons.append("DRUMS_IN_PIANO_ONLY_OUTPUT")
    if other_notes:
        reasons.append("NON_PIANO_INSTRUMENTS")
    return {
        "status": "STRUCTURAL_PASS" if not reasons else "STRUCTURAL_FAIL",
        "duration_seconds": round(seconds, 3),
        "piano_notes": piano_notes,
        "drum_notes": drum_notes,
        "other_notes": other_notes,
        "populated_tracks": len(populated),
        "reasons": reasons,
        "note": "Structural acceptance only. Human listening decides musical quality.",
    }
