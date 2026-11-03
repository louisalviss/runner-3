#!/usr/bin/env python3
"""Blind music-composition comparison gate (research only).

No model training, no automatic quality claims, no external upload.
Audio candidates must be original or carry an appropriate license.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys

ALLOWED_RIGHTS = {"original", "licensed_for_commercial_derivatives"}
TARGET_SEC = 8.0


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def probe(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)], capture_output=True, text=True,
        timeout=20, check=True)
    return float(json.loads(p.stdout)["format"]["duration"])


def encode_clip(src, dst):
    # Comparable durations and approximate one-pass loudness normalization.
    # This is NOT an objective human-perceptual loudness match.
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-i", str(src), "-t", str(TARGET_SEC), "-vn",
         "-af", "loudnorm=I=-17:TP=-2:LRA=7",
         "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a",
         "192k", str(dst)],
        check=True, timeout=90)


def write_json(path, data, private=False):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if private:
        path.chmod(0o600)


def prepare(args):
    raw = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    candidates = raw.get("candidates", [])
    if not 2 <= len(candidates) <= 16:
        raise ValueError("Provide 2..16 candidates")
    ids = [c.get("id") for c in candidates]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Candidate ids must be distinct nonempty strings")
    out = Path(args.output)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory must be empty; never overwrite an earlier experiment")
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for c in candidates:
        if c.get("rights") not in ALLOWED_RIGHTS:
            raise ValueError("Candidate must declare usable music rights")
        path = Path(c["path"]).resolve(strict=True)
        if not path.is_file():
            raise ValueError("Not an audio file")
        seconds = probe(path)
        if seconds < TARGET_SEC - 0.05:
            raise ValueError("All candidate clips must contain at least 8 seconds")
        files[c["id"]] = {
            "path": str(path), "sha256": file_hash(path), "seconds": seconds,
            "rights": c["rights"], "origin": c.get("origin", "unspecified")
        }
    pairs = list(itertools.combinations(ids, 2))
    rng = random.Random(args.seed)
    rng.shuffle(pairs)
    pairs = pairs[:args.max_pairs]
    sealed = {"schema": 1, "seed": args.seed, "target_seconds": TARGET_SEC,
              "candidates": files, "pairs": []}
    public = {"schema": 1, "target_seconds": TARGET_SEC,
              "note": "Compare each A/B pair at equal playback volume. Listen without reading the sealed map.",
              "pairs": []}
    for index, pair in enumerate(pairs, 1):
        a, b = list(pair)
        if rng.randrange(2):
            a, b = b, a
        pid = f"pair-{index:02d}"
        for label, candidate_id in [("A", a), ("B", b)]:
            encode_clip(files[candidate_id]["path"], out / f"{pid}-{label}.mp3")
        sealed["pairs"].append({"pair_id": pid, "A": a, "B": b,
                                "sha256_A": file_hash(out / f"{pid}-A.mp3"),
                                "sha256_B": file_hash(out / f"{pid}-B.mp3")})
        public["pairs"].append({"pair_id": pid, "A": f"{pid}-A.mp3",
                                "B": f"{pid}-B.mp3", "choice": None})
    write_json(out / "sealed-map.json", sealed, private=True)
    write_json(out / "blind-ratings.json", public)
    print(json.dumps({"prepared_pairs": len(pairs), "directory": str(out),
                      "status": "AUDIO_TECHNICAL_PREP_ONLY"}, ensure_ascii=False))


def reveal(args):
    sealed = json.loads(Path(args.sealed).read_text(encoding="utf-8"))
    ratings = json.loads(Path(args.ratings).read_text(encoding="utf-8"))
    mapping = {x["pair_id"]: x for x in sealed["pairs"]}
    scores = {k: {"wins": 0, "losses": 0, "ties": 0}
              for k in sealed["candidates"]}
    observed = set()
    for row in ratings["pairs"]:
        pid, choice = row["pair_id"], row.get("choice")
        if pid not in mapping or pid in observed or choice not in ("A", "B", "tie"):
            raise ValueError("Unknown, duplicated, or unrated pair")
        observed.add(pid)
        p = mapping[pid]
        if choice == "tie":
            for side in ("A", "B"):
                scores[p[side]]["ties"] += 1
        else:
            win, lose = p[choice], p["B" if choice == "A" else "A"]
            scores[win]["wins"] += 1
            scores[lose]["losses"] += 1
    if observed != set(mapping):
        raise ValueError("All pairs must be rated before reveal")
    print(json.dumps({"status": "RATED_NOT_MUSICALLY_VALIDATED",
                      "ratings_count": len(observed), "scores": scores},
                     ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--manifest", required=True)
    prep.add_argument("--output", required=True)
    prep.add_argument("--seed", type=int, default=20261103)
    prep.add_argument("--max-pairs", type=int, default=8)
    rev = sub.add_parser("reveal")
    rev.add_argument("--sealed", required=True)
    rev.add_argument("--ratings", required=True)
    args = p.parse_args()
    if args.command == "prepare":
        if not 1 <= args.max_pairs <= 32:
            p.error("max-pairs must be in 1..32")
        prepare(args)
    else:
        reveal(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
