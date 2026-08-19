#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

CANONICAL = "https://www.reddit.com/r/AskReddit/comments/1vrfpzb/what_is_the_creepiest_unsolved_mystery_in_your/"
TITLE = "What is the creepiest unsolved mystery in your opinion?"

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


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: reddit_crawl_adapter.py CRAWL_DIR OUT_JSON")
    crawl = Path(sys.argv[1])
    out = Path(sys.argv[2])
    manifest_path = crawl / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("crawler manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("ok_count", 0)) < 1:
        raise SystemExit(f"runner browser crawl failed: {json.dumps(manifest.get('results', []), ensure_ascii=False)[:2000]}")

    txt_files = sorted(crawl.glob("*/page.txt"))
    if not txt_files:
        raise SystemExit("crawler page.txt missing")
    text = txt_files[0].read_text(encoding="utf-8", errors="ignore")
    low = text.lower()
    if len(text) < 2500:
        raise SystemExit(f"crawler page too thin: {len(text)} chars")

    # Require evidence that this is the requested thread, not a Reddit interstitial/homepage.
    identity_terms = ["creepiest unsolved mystery", "askreddit"]
    if not any(term in low for term in identity_terms):
        raise SystemExit("crawler returned a page, but not the requested AskReddit thread")

    hits = []
    for label, patterns in TARGETS:
        positions = [low.find(p.lower()) for p in patterns if low.find(p.lower()) >= 0]
        if positions:
            hits.append((min(positions), label, patterns[0]))
    hits.sort(key=lambda x: x[0])
    if len(hits) < 5:
        raise SystemExit("browser crawl loaded thread but found only %d verified target cases: %s" % (len(hits), ", ".join(h[1] for h in hits)))

    # Build a minimal Reddit-like payload expected by reddit_unsolved_narrator.py.
    # Order comes from first appearance on the Best-sorted rendered page. We deliberately
    # do not persist raw comments here; narration uses independently verified summaries.
    comments = []
    for idx, (pos, label, match_term) in enumerate(hits, 1):
        comments.append({
            "kind": "t1",
            "data": {
                "id": f"browser-hit-{idx}",
                "author": "browser-crawl",
                "score": None,
                "body": label + " " + match_term,
                "permalink": f"/r/AskReddit/comments/1vrfpzb/browser-hit-{idx}/",
                "stickied": False,
                "runner_render_position": pos,
            },
        })

    payload = [
        {"data": {"children": [{"data": {"title": TITLE, "permalink": "/r/AskReddit/comments/1vrfpzb/what_is_the_creepiest_unsolved_mystery_in_your/"}}]}},
        {"data": {"children": comments}},
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "engine": (manifest.get("results") or [{}])[0].get("engine"),
        "final_url": (manifest.get("results") or [{}])[0].get("final_url"),
        "text_chars": len(text),
        "matched_cases": [h[1] for h in hits],
        "match_count": len(hits),
        "ordering": "first appearance on Runner browser-rendered Best page",
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
