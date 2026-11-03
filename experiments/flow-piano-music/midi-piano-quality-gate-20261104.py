#!/usr/bin/env python3
"""Structural MIDI-only audition gate; never declares musical quality."""
from pathlib import Path


def analyze_midi(path, min_seconds=7.0, max_seconds=8.3, min_piano_notes=12):
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


def compare_novelty(reference_path, candidate_path, *,
                    reference_window=(0.0, 7.5), candidate_window=(7.5, 15.0),
                    max_duplicate_ratio=0.85):
    """Check for direct note-event repetition in corresponding windows.

    Works only with single, constant tempos. A changed tempo-map or very few
    notes means UNVERIFIED, never a claimed original composition.
    Designed for the user's original 4-bar hook vs its next 4 bars, and
    for middle-bar infill using matching windows.
    """
    from symusic import Score
    if not 0 < max_duplicate_ratio < 1:
        raise ValueError("Bad duplication threshold")

    def extract(path, window):
        score = Score.from_midi(Path(path).read_bytes())
        if len(score.tempos) != 1 or score.tempos[0].time != 0:
            return None
        ppq = score.ticks_per_quarter
        bpm = float(score.tempos[0].qpm)
        if not 20 < bpm < 300 or ppq <= 0:
            return None
        a, b = window
        if not 0 <= a < b:
            raise ValueError("Bad comparison window")
        rows = []
        for track in score.tracks:
            if track.is_drum or not 0 <= track.program <= 7:
                continue
            for note in track.notes:
                onset = note.time * 60 / (ppq * bpm)
                duration = note.duration * 60 / (ppq * bpm)
                if a <= onset < b:
                    rows.append((onset - a, duration, note.pitch))
        return sorted(rows)

    ref = extract(reference_path, reference_window)
    candidate = extract(candidate_path, candidate_window)
    if ref is None or candidate is None or len(candidate) < 12 or len(ref) < 12:
        return {"status": "NOVELTY_UNVERIFIED", "reason": "TEMPO_OR_NOTE_COUNT",
                "matched": None, "candidate_count": None, "duplicate_ratio": None}
    used = set()
    matched = 0
    for onset, duration, pitch in candidate:
        options = [(abs(onset - ro) + 0.2 * abs(duration - rd), i)
                   for i, (ro, rd, rp) in enumerate(ref)
                   if i not in used and pitch == rp and abs(onset - ro) <= 0.14
                   and abs(duration - rd) <= 0.30]
        if options:
            _, index = min(options)
            used.add(index)
            matched += 1
    ratio = matched / len(candidate)
    return {"status": "NEAR_COPY_REJECT" if ratio >= max_duplicate_ratio else "NOVELTY_CANDIDATE",
            "matched": matched, "candidate_count": len(candidate),
            "duplicate_ratio": round(ratio, 4),
            "note": "Novelty candidate is not a human quality or copyright clearance."}
