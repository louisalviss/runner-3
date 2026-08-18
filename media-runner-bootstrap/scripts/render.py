from __future__ import annotations

import argparse
import json
import pathlib
import urllib.parse
import urllib.request

from common import ensure_dir, ffmpeg, json_dump, load_config, run, validate_sequence

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def resolve_itunes_preview(music: dict, dest: pathlib.Path) -> dict:
    params = urllib.parse.urlencode({
        "term": music["search_term"],
        "entity": "song",
        "limit": 50,
        "country": music.get("country", "US"),
    })
    req = urllib.request.Request(
        f"https://itunes.apple.com/search?{params}", headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.load(r)

    wanted_track = music.get("track_name", "").strip().lower()
    wanted_artist = music.get("artist_contains", "").strip().lower()
    match = None
    for item in data.get("results", []):
        track = (item.get("trackName") or "").strip().lower()
        artist = (item.get("artistName") or "").strip().lower()
        if wanted_track and track != wanted_track:
            continue
        if wanted_artist and wanted_artist not in artist:
            continue
        if item.get("previewUrl"):
            match = item
            break
    if not match:
        raise SystemExit("no matching iTunes preview found")

    req = urllib.request.Request(match["previewUrl"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return {
        "track": match.get("trackName"),
        "artist": match.get("artistName"),
        "preview_url": match.get("previewUrl"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("source_dir")
    ap.add_argument("output")
    args = ap.parse_args()

    cfg = load_config(args.config)
    expected_duration = validate_sequence(cfg)
    source_root = pathlib.Path(args.source_dir)
    manifest_path = source_root / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing source manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    source_map = {
        x["id"]: source_root / x["normalized_file"] for x in manifest["sources"]
    }
    missing = sorted({x["source"] for x in cfg["sequence"]} - set(source_map))
    if missing:
        raise SystemExit(f"sequence references missing source ids: {', '.join(missing)}")

    out = pathlib.Path(args.output)
    work = ensure_dir(out.parent / "work")
    ensure_dir(out.parent)
    filter_path = work / "filter.txt"
    visual_path = work / "visual.mp4"
    music_path = work / "music.m4a"
    edit_plan_path = out.parent / "edit_plan.txt"

    canvas = cfg["canvas"]
    W = int(canvas.get("width", 1080))
    H = int(canvas.get("height", 1920))
    fps = int(cfg.get("fps", 30))
    base_fw = int(canvas.get("foreground_width", 960))
    beat = 60.0 / float(cfg["bpm"])

    source_ids = [x["id"] for x in manifest["sources"]]
    input_index = {sid: i for i, sid in enumerate(source_ids)}
    ff_inputs = []
    for sid in source_ids:
        ff_inputs += ["-i", str(source_map[sid])]

    parts: list[str] = []
    labels: list[str] = []
    plan: list[str] = []
    t = 0.0
    warm_styles = {"bomb", "massive", "explode", "fire"}
    sharp_styles = {"fight", "bomb", "action", "chainsaw"}

    for k, shot in enumerate(cfg["sequence"]):
        idx = input_index[shot["source"]]
        st = float(shot["start"])
        en = float(shot["end"])
        beats = float(shot["beats"])
        style = str(shot.get("style", "normal"))
        if en <= st:
            raise SystemExit(f"invalid shot {k + 1}: end <= start")
        od = beats * beat
        sd = en - st

        parts.append(
            f"[{idx}:v]trim=start={st}:end={en},"
            f"setpts=(PTS-STARTPTS)*{od / sd:.8f},split=2[b{k}][f{k}]"
        )
        parts.append(
            f"[b{k}]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma=32,eq=brightness=-.20:saturation=.90[b2{k}]"
        )

        fw = base_fw + (40 if style in {"hit", "fight", "bomb"} else 0)
        fw = min(fw, W)
        fh = int(round(fw * 534 / 1280 / 2) * 2)
        fx = f"[f{k}]scale={fw}:{fh},eq=contrast=1.20:saturation=1.30:gamma=.95"
        if style in warm_styles:
            fx += ",colorbalance=rs=.10:bs=-.035"
        else:
            fx += ",colorbalance=bs=.08:rs=-.02"
        if style == "hit":
            fx += ",rgbashift=rh=6:bh=-6,drawbox=x=0:y=0:w=iw:h=ih:color=white@.30:t=fill:enable='lt(t,.045)'"
        if style in sharp_styles:
            fx += ",unsharp=5:5:.35:5:5:0"
        parts.append(fx + f"[f2{k}]")
        parts.append(
            f"[b2{k}][f2{k}]overlay=(W-w)/2:(H-h)/2,"
            f"setsar=1,fps={fps},format=yuv420p[v{k}]"
        )
        labels.append(f"[v{k}]")
        plan.append(
            f"{k+1:02d} out={t:.3f}-{t+od:.3f} source={shot['source']} "
            f"src={st:.3f}-{en:.3f} beats={beats:g} style={style}"
        )
        t += od

    parts.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[vout]")
    filter_path.write_text(";".join(parts), encoding="utf-8")
    edit_plan_path.write_text("\n".join(plan) + f"\nTOTAL={t:.6f}\n", encoding="utf-8")

    run([
        ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        *ff_inputs,
        "-filter_complex_script", str(filter_path),
        "-map", "[vout]", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
        str(visual_path),
    ])

    music = cfg.get("music")
    music_meta = None
    if music:
        provider = music.get("provider")
        if provider != "itunes_preview":
            raise SystemExit(f"unsupported music provider: {provider}")
        music_meta = resolve_itunes_preview(music, music_path)
        start = float(music.get("start_seconds", 0.0))
        run([
            ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(visual_path), "-ss", f"{start:.3f}", "-i", str(music_path),
            "-t", f"{expected_duration:.6f}",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-af", "volume=1,bass=g=3:f=90,alimiter=limit=.94",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(out),
        ])
    else:
        run([
            ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(visual_path), "-t", f"{expected_duration:.6f}",
            "-c:v", "copy", "-an", "-movflags", "+faststart", str(out),
        ])

    json_dump(out.parent / "render_manifest.json", {
        "job": cfg["job"],
        "output": out.name,
        "expected_duration": expected_duration,
        "source_manifest_job": manifest.get("job"),
        "music": music_meta,
        "sequence_shots": len(cfg["sequence"]),
    })
    print(f"rendered {out} ({expected_duration:.3f}s target)")


if __name__ == "__main__":
    main()
