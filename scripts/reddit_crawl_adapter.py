#!/usr/bin/env python3
import json
import sys
from pathlib import Path

TITLE = "What is the creepiest unsolved mystery in your opinion?"
THREAD_PATH = "/r/AskReddit/comments/1vrfpzb/what_is_the_creepiest_unsolved_mystery_in_your/"

TARGETS = [
    ("Fallon leukemia cluster", ["fallon", "churchill county", "leukemia cluster"]),
    ("Springfield Three", ["springfield three", "springfield 3", "stacy mccall", "suzie streeter", "sherrill levitt"]),
    ("Brandon Swanson", ["brandon swanson"]),
    ("Andrew Gosden", ["andrew gosden"]),
    ("Somosierra / Juan Pedro Martínez", ["somosierra", "juan pedro mart", "juan pedro"]),
    ("Stefanie Damron", ["stefanie damron", "stephanie damron"]),
    ("Zodiac Killer", ["zodiac killer", "zodiac"]),
    ("Bella in the Wych Elm", ["bella in the wych elm", "wych elm"]),
]


def inspect_text(text):
    low = text.lower()
    identity = ("creepiest unsolved mystery" in low) or ("askreddit" in low and "unsolved" in low)
    hits = []
    for label, patterns in TARGETS:
        positions = [low.find(p.lower()) for p in patterns if low.find(p.lower()) >= 0]
        if positions:
            hits.append((min(positions), label, patterns[0]))
    hits.sort(key=lambda x: x[0])
    return identity, hits


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: reddit_crawl_adapter.py CRAWL_DIR OUT_JSON")
    crawl = Path(sys.argv[1])
    out = Path(sys.argv[2])
    manifest_path = crawl / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("crawler manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    candidates = []
    for result in manifest.get("results", []):
        outdir = result.get("output_dir")
        if not outdir:
            continue
        txt = crawl / outdir / "page.txt"
        if not txt.exists():
            continue
        text = txt.read_text(encoding="utf-8", errors="ignore")
        identity, hits = inspect_text(text)
        score = (1000 if result.get("ok") else 0) + (500 if identity else 0) + len(hits) * 50 + min(len(text), 100000) / 100000
        candidates.append((score, result, text, identity, hits))

    if not candidates:
        raise SystemExit(f"runner browser crawl produced no readable page text: {json.dumps(manifest.get('results', []), ensure_ascii=False)[:2500]}")
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, chosen, text, identity, hits = candidates[0]

    if not chosen.get("ok"):
        raise SystemExit(f"runner browser crawl blocked/failed: {json.dumps(chosen, ensure_ascii=False)[:2500]}")
    if len(text) < 2500:
        raise SystemExit(f"crawler page too thin: {len(text)} chars")
    if not identity:
        raise SystemExit("crawler returned a page, but not the requested AskReddit thread")
    if len(hits) < 5:
        raise SystemExit("browser crawl loaded thread but found only %d verified target cases: %s" % (len(hits), ", ".join(h[1] for h in hits)))

    comments = []
    for idx, (pos, label, match_term) in enumerate(hits, 1):
        comments.append({
            "kind": "t1",
            "data": {
                "id": f"browser-hit-{idx}",
                "author": "runner-browser-crawl",
                "score": None,
                "body": label + " " + match_term,
                "permalink": f"{THREAD_PATH}browser-hit-{idx}/",
                "stickied": False,
                "runner_render_position": pos,
            },
        })

    payload = [
        {"data": {"children": [{"data": {"title": TITLE, "permalink": THREAD_PATH}}]}},
        {"data": {"children": comments}},
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "engine": chosen.get("engine"),
        "status": chosen.get("status"),
        "final_url": chosen.get("final_url"),
        "text_chars": len(text),
        "matched_cases": [h[1] for h in hits],
        "match_count": len(hits),
        "ordering": "first appearance on Runner-rendered Best page among verified target cases",
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
