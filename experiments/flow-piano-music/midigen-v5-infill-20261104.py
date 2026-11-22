#!/usr/bin/env python3
"""Research-only v5 MIDI infill around the user-approved Electric Memory C motif.

This module does not publish R2, update D1 or declare musical quality.
Model source, weights and tokenizer must match pinned identities.
Run ONLY in an isolated environment with an external memory/swap/time watchdog.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

UPSTREAM_SHA = "17c7fb775789089dc848eb13b5fd477657f024ab"
WEIGHTS_SHA = "05026cd7a721a5ef50059d48e687bd77b1c5fb25429d7fed09d1bc628e6aaa74"
TOKENIZER_SHA = "2cb58beac8be709a12967383503d6de9078730e179ba3edccdf82b46a106df18"
SEED_SHA = "32fccd81dcb6a0b576f153cfdf46e409cec1856178881bf8e7df5bfda50ec6ee"
QA_NAME = "midi-piano-quality-gate-20261104.py"
SCALE_C_SHARP_MINOR = {1, 3, 4, 6, 8, 9, 11}
GAP = (1.875, 5.625)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for b in iter(lambda: file.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def load_gate():
    p = Path(__file__).with_name(QA_NAME)
    if not p.exists():
        raise RuntimeError("Research QA gate missing: " + str(p))
    spec = importlib.util.spec_from_file_location("midi_gate", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def musical_features(candidate):
    from symusic import Score
    score = Score(str(candidate))
    if len(score.tempos) != 1:
        raise RuntimeError("Expected one constant MIDI tempo")
    bpm = float(score.tempos[0].qpm)
    ppq = score.ticks_per_quarter
    in_gap = []
    for track in score.tracks:
        for note in track.notes:
            onset = note.time * 60 / (ppq * bpm)
            if GAP[0] <= onset < GAP[1]:
                in_gap.append(note.pitch)
    if not in_gap:
        return {"gap_notes": 0, "in_key_fraction": 0, "upper_melody_notes": 0}
    return {
        "gap_notes": len(in_gap),
        "in_key_fraction": round(sum(p % 12 in SCALE_C_SHARP_MINOR for p in in_gap) / len(in_gap), 4),
        "upper_melody_notes": sum(p >= 71 for p in in_gap),
    }


def check(reference, candidate):
    gate = load_gate()
    structure = gate.analyze_midi(candidate)
    novelty = gate.compare_novelty(
        reference, candidate, reference_window=GAP, candidate_window=GAP
    )
    features = musical_features(candidate)
    accept = (
        structure["status"] == "STRUCTURAL_PASS"
        and novelty["status"] == "NOVELTY_CANDIDATE"
        and features["gap_notes"] >= 12
        and features["in_key_fraction"] >= 0.9
        and features["upper_melody_notes"] >= 4
    )
    return {
        "status": "AUDITION_CANDIDATE" if accept else "REJECTED_FOR_AUDITION",
        "structure": structure,
        "novelty": novelty,
        "features": features,
        "musical_quality": "NOT_ASSESSED_BY_HUMAN",
    }


def check_hash(path, expected):
    if not Path(path).is_file() or sha(path) != expected:
        raise RuntimeError("Pinned SHA-256 check failed for " + str(path))


def generate(args):
    import torch
    check_hash(args.reference, SEED_SHA)
    check_hash(args.checkpoint, WEIGHTS_SHA)
    check_hash(args.tokenizer, TOKENIZER_SHA)
    upstream = Path(args.upstream).resolve()
    pinned = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if pinned != UPSTREAM_SHA:
        raise RuntimeError("Upstream source commit does not match pinned SHA")
    implementation = upstream / "midigenai" / "generate.py"
    body = implementation.read_text()
    if 'torch.load(checkpoint_path, map_location="cpu", weights_only=True)' not in body:
        raise RuntimeError("Use isolated, audited weights_only=True checkpoint loader")
    torch.set_num_threads(2)
    sys.path.insert(0, str(upstream))
    from midigenai.generate import Generator
    from midigenai import infill_span
    output = Path(args.output)
    if output.exists():
        raise RuntimeError("Output exists; refusing to overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    gen = Generator(
        checkpoint_path=args.checkpoint, tokenizer_path=args.tokenizer,
        device=torch.device("cpu"), dtype="float32", backend="torch"
    )
    started = time.monotonic()
    _, generated, counts = infill_span.run(
        gen, Path(args.reference).read_bytes(), start=1, bars=2,
        n_samples=1, tempo_bpm=128, temperature=args.temperature,
        top_k=args.top_k, seed=args.seed
    )
    generated[0].dump_midi(str(output))
    report = check(args.reference, output)
    report.update({
        "seed": args.seed, "temperature": args.temperature,
        "top_k": args.top_k, "model": "nicholasbien/midigenai-v5",
        "model_sha256": WEIGHTS_SHA, "seed_sha256": SEED_SHA,
        "midi_sha256": sha(output), "midi_bytes": output.stat().st_size,
        "generated_gap_note_count": counts[0],
        "inference_seconds": round(time.monotonic() - started, 2),
    })
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "AUDITION_CANDIDATE" else 3


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reference", required=True)
    p.add_argument("--candidate", help="Existing MIDI to inspect, with no inference")
    p.add_argument("--upstream", help="Pinned upstream source checkout")
    p.add_argument("--checkpoint")
    p.add_argument("--tokenizer")
    p.add_argument("--output")
    p.add_argument("--seed", type=int, default=20261108)
    p.add_argument("--temperature", type=float, default=0.87)
    p.add_argument("--top-k", type=int, default=35)
    a = p.parse_args()
    if a.candidate:
        check_hash(a.reference, SEED_SHA)
        report = check(a.reference, a.candidate)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] == "AUDITION_CANDIDATE" else 3
    if not all([a.upstream, a.checkpoint, a.tokenizer, a.output]):
        p.error("Generation requires --upstream --checkpoint --tokenizer --output")
    if not 0.7 <= a.temperature <= 1.1 or not 15 <= a.top_k <= 75:
        p.error("Bounded generation params violated")
    return generate(a)


if __name__ == "__main__":
    sys.exit(main())
