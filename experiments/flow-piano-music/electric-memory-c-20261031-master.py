#!/usr/bin/env python3
"""Finalize an isolated Flow Piano Music Concert Grand test.
Requires raw 44.1kHz stereo WAV and the original silent/video+guide-audio MP4.
Never changes the approved v1.2 renderer or the R2 master.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile


def run(wav_path: Path, video_path: Path, output_dir: Path, stem: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    sr, samples = wavfile.read(wav_path)
    if sr != 44100 or samples.ndim != 2 or samples.shape[1] != 2:
        raise ValueError("Expected 44100 Hz stereo source WAV")
    if len(samples) != 30 * sr:
        raise ValueError("Expected 30 seconds of input samples")
    audio = samples.astype(np.float64) / 32768.0
    audio = signal.sosfilt(
        signal.butter(2, 45, fs=sr, btype="highpass", output="sos"), audio, axis=0
    )
    dry = audio.copy()
    for delay, gain in ((0.045, 0.064), (0.098, 0.045), (0.162, 0.025)):
        n = round(delay * sr)
        audio[n:, 0] += dry[:-n, 1] * gain
        audio[n:, 1] += dry[:-n, 0] * gain
    tail = round(0.65 * sr)
    audio[-tail:] *= np.linspace(1, 0, tail)[:, None]
    audio *= 0.77 / max(0.00001, np.abs(audio).max())
    if not np.isfinite(audio).all() or np.abs(audio).max() >= 0.85:
        raise ValueError("Audio peak or NaN QA failed")

    mastered_wav = output_dir / (stem + "_master.wav")
    output_mp3 = output_dir / (stem + ".mp3")
    output_mp4 = output_dir / (stem + ".mp4")
    wavfile.write(mastered_wav, sr, (np.clip(audio, -1, 1) * 32767).astype(np.int16))

    cmds = (
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mastered_wav), "-vn",
         "-codec:a", "libmp3lame", "-b:a", "224k", "-t", "30", str(output_mp3)],
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path),
         "-i", str(mastered_wav), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
         "-t", "30", "-movflags", "+faststart", str(output_mp4)],
    )
    for cmd in cmds:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=50)
    return {"peak": round(float(np.abs(audio).max()), 5),
            "rms": round(float(np.sqrt(np.mean(audio * audio))), 5),
            "outputs": {p.name: {"bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in (output_mp3, output_mp4)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-wav", type=Path, required=True)
    parser.add_argument("--input-video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stem", default="Electric_Memory_C_30s")
    args = parser.parse_args()
    print(json.dumps(run(args.input_wav, args.input_video, args.output_dir, args.stem)))
