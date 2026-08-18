from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Iterable


def load_config(path: str | os.PathLike) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["job", "canvas", "fps", "bpm", "sources", "sequence"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise SystemExit(f"config missing keys: {', '.join(missing)}")
    return cfg


def ensure_dir(path: str | os.PathLike) -> pathlib.Path:
    p = pathlib.Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    raise SystemExit(f"required tool not found: {name}")


def run(args: Iterable[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    cmd = [str(x) for x in args]
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def ffmpeg() -> str:
    return tool("ffmpeg")


def ffprobe() -> str:
    return tool("ffprobe")


def validate_sequence(cfg: dict) -> float:
    total_beats = sum(float(x["beats"]) for x in cfg["sequence"])
    expected = float(cfg.get("duration_beats", total_beats))
    if abs(total_beats - expected) > 1e-6:
        raise SystemExit(f"sequence beats {total_beats} != duration_beats {expected}")
    return expected * (60.0 / float(cfg["bpm"]))


def json_dump(path: str | os.PathLike, data: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
