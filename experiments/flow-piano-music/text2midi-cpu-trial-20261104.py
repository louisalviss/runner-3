#!/usr/bin/env python3
"""Text2MIDI CPU-only, bounded offline research trial.

Requires the official AMAAI-Lab/Text2midi source and checkpoint downloaded,
inspected and staged separately. This script does not download or publish.
It does NOT modify the approved Flow Piano Music project.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--official-source", required=True, help="Local reviewed official Text2midi checkout")
    p.add_argument("--checkpoint", required=True, help="Local official pytorch_model.bin")
    p.add_argument("--vocab", required=True, help="Local official vocab_remi.pkl")
    p.add_argument("--checkpoint-sha256", required=True)
    p.add_argument("--vocab-sha256", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--caption", required=True)
    p.add_argument("--max-tokens", type=int, default=500)
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--seed", type=int, default=20261104)
    args = p.parse_args()

    if not 64 <= args.max_tokens <= 650:
        p.error("max-tokens must be 64..650 for bounded CPU research")
    if not 0.8 <= args.temperature <= 1.1:
        p.error("temperature must be 0.8..1.1")
    if not 1 <= args.threads <= 2:
        p.error("threads must be 1 or 2")
    if not 20 <= len(args.caption) <= 1000:
        p.error("caption length must be 20..1000 characters")
    model_path = Path(args.checkpoint).resolve(strict=True)
    vocab_path = Path(args.vocab).resolve(strict=True)
    source = Path(args.official_source).resolve(strict=True)
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        p.error("output directory must be empty; no overwrite of previous tests")
    if not model_path.is_file() or not vocab_path.is_file():
        p.error("checkpoint and vocabulary files must exist")
    if sha256(model_path) != args.checkpoint_sha256:
        p.error("checkpoint SHA-256 mismatch")
    if sha256(vocab_path) != args.vocab_sha256:
        p.error("vocab SHA-256 mismatch")
    if model_path.stat().st_size < 50_000_000:
        p.error("checkpoint file unexpectedly small")
    if not (source / "model" / "transformer_model.py").is_file():
        p.error("official model source missing")

    # Do not import model code or deserialize third-party pickle until the
    # supplied bytes match the independently vetted expected hashes.
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)
    import pickle
    import torch
    import torch.nn as nn
    from transformers import T5Tokenizer

    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)

    sys.path.insert(0, str(source))
    from model.transformer_model import Transformer

    with vocab_path.open("rb") as f:
        tokenizer = pickle.load(f)  # vetted official bytes ONLY; untrusted pickle is unsafe

    model = Transformer(len(tokenizer), 768, 8, 2048, 18, 1024, False, 8, device="cpu")
    state = torch.load(str(model_path), map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()
    text_tokenizer = T5Tokenizer.from_pretrained("google/flan-t5-base")
    inputs = text_tokenizer(args.caption, return_tensors="pt", padding=True, truncation=True)
    input_ids = nn.utils.rnn.pad_sequence(inputs.input_ids, batch_first=True, padding_value=0)
    mask = nn.utils.rnn.pad_sequence(inputs.attention_mask, batch_first=True, padding_value=0)

    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with torch.inference_mode():
        output = model.generate(input_ids, mask, max_len=args.max_tokens, temperature=args.temperature)
    elapsed = round(time.monotonic() - start, 2)
    song = tokenizer.decode(output[0].tolist())
    midi = out / "text2midi-original-candidate.mid"
    song.dump_midi(str(midi))
    if not midi.is_file() or midi.stat().st_size < 100:
        raise RuntimeError("no credible MIDI output was created")
    with midi.open("rb") as file:
        if file.read(4) != b"MThd":
            raise RuntimeError("output is not a standard MIDI file")
    result = {
        "status": "MODEL_GENERATED_MIDI_TECHNICAL_ONLY",
        "musical_approval": "NOT_TESTED",
        "model": "amaai-lab/text2midi",
        "checkpoint_sha256": args.checkpoint_sha256,
        "vocab_sha256": args.vocab_sha256,
        "seed": args.seed, "caption": args.caption,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "threads": args.threads,
        "duration_s_inference": elapsed,
        "file": midi.name,
        "midi_sha256": sha256(midi),
        "midi_bytes": midi.stat().st_size,
    }
    (out / "trial-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
