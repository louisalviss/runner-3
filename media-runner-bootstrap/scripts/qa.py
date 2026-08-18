from __future__ import annotations

import argparse
import json
import pathlib

from common import ensure_dir, ffmpeg, ffprobe, json_dump, load_config, run, validate_sequence


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("video")
    ap.add_argument("qa_dir")
    args = ap.parse_args()

    cfg = load_config(args.config)
    expected = validate_sequence(cfg)
    video = pathlib.Path(args.video)
    qa_dir = ensure_dir(args.qa_dir)
    if not video.exists():
        raise SystemExit(f"video not found: {video}")

    probe = run([
        ffprobe(), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)
    ], capture=True)
    info = json.loads(probe.stdout)
    streams = info.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(info.get("format", {}).get("duration") or 0)

    canvas = cfg["canvas"]
    width = int(canvas.get("width", 1080))
    height = int(canvas.get("height", 1920))
    safe_width = int(canvas.get("iphone_safe_width", 886))
    safe_x = max(0, (width - safe_width) // 2)

    checks = {
        "has_video": video_stream is not None,
        "codec_h264": bool(video_stream and video_stream.get("codec_name") == "h264"),
        "dimensions": bool(video_stream and int(video_stream.get("width", 0)) == width and int(video_stream.get("height", 0)) == height),
        "pix_fmt_yuv420p": bool(video_stream and video_stream.get("pix_fmt") == "yuv420p"),
        "duration": abs(duration - expected) <= 0.20,
    }
    if cfg.get("music"):
        checks.update({
            "has_audio": audio_stream is not None,
            "audio_aac": bool(audio_stream and audio_stream.get("codec_name") == "aac"),
            "audio_48khz": bool(audio_stream and str(audio_stream.get("sample_rate")) == "48000"),
            "audio_stereo": bool(audio_stream and int(audio_stream.get("channels", 0)) == 2),
        })

    interval = max(expected / 14.0, 0.20)
    fps_expr = f"1/{interval:.6f}"
    run([
        ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", f"fps={fps_expr},scale=180:-2,tile=7x2:padding=3:margin=3",
        "-frames:v", "1", str(qa_dir / "master_contact.jpg"),
    ])
    run([
        ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", f"crop={safe_width}:{height}:{safe_x}:0,fps={fps_expr},scale=180:-2,tile=7x2:padding=3:margin=3",
        "-frames:v", "1", str(qa_dir / "iphone_19_5_contact.jpg"),
    ])
    sample_t = min(max(expected * 0.50, 0.10), max(expected - 0.10, 0.10))
    run([
        ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{sample_t:.3f}", "-i", str(video),
        "-vf", f"drawbox=x={safe_x}:y=120:w={safe_width}:h={max(100, height-360)}:color=green@0.35:t=4",
        "-frames:v", "1", str(qa_dir / "safe_zone_overlay.jpg"),
    ])

    report = {
        "job": cfg["job"],
        "video": video.name,
        "expected_duration": expected,
        "actual_duration": duration,
        "iphone_safe_width": safe_width,
        "checks": checks,
        "pass": all(checks.values()),
        "video_stream": video_stream,
        "audio_stream": audio_stream,
    }
    json_dump(qa_dir / "qa_report.json", report)
    print(json.dumps({"pass": report["pass"], "checks": checks}, indent=2))
    if not report["pass"]:
        raise SystemExit("QA_FAILED")


if __name__ == "__main__":
    main()
