#!/usr/bin/env python3
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    root = Path(args.input)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    summaries = []
    for p in root.rglob("summary.json"):
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
            if "source" in row and "threads_attempted" in row:
                summaries.append(row)
        except Exception:
            pass

    per_source = defaultdict(lambda: {
        "shards": 0,
        "threads_attempted": 0,
        "pages_attempted": 0,
        "pages_ok": 0,
        "chars_read": 0,
        "words_read": 0,
        "qa": Counter(),
    })
    for s in summaries:
        x = per_source[s["source"]]
        x["shards"] += 1
        x["threads_attempted"] += int(s.get("threads_attempted", 0))
        x["pages_attempted"] += int(s.get("pages_attempted", 0))
        x["pages_ok"] += int(s.get("pages_ok", 0))
        x["chars_read"] += int(s.get("chars_read", 0))
        x["words_read"] += int(s.get("words_read", 0))
        x["qa"].update(s.get("qa", {}))

    result = {"sources": {}, "total": {}}
    total_qa = Counter()
    for source, x in sorted(per_source.items()):
        d = dict(x)
        d["qa"] = dict(x["qa"])
        d["page_success_rate"] = round(x["pages_ok"] / x["pages_attempted"], 6) if x["pages_attempted"] else 0
        result["sources"][source] = d
        total_qa.update(x["qa"])

    result["total"] = {
        "shards": sum(x["shards"] for x in per_source.values()),
        "threads_attempted": sum(x["threads_attempted"] for x in per_source.values()),
        "pages_attempted": sum(x["pages_attempted"] for x in per_source.values()),
        "pages_ok": sum(x["pages_ok"] for x in per_source.values()),
        "chars_read": sum(x["chars_read"] for x in per_source.values()),
        "words_read": sum(x["words_read"] for x in per_source.values()),
        "qa": dict(total_qa),
    }
    result["total"]["page_success_rate"] = round(result["total"]["pages_ok"] / result["total"]["pages_attempted"], 6) if result["total"]["pages_attempted"] else 0

    (out / "fulltext_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    audit_out = out / "fulltext_audit.jsonl"
    with audit_out.open("w", encoding="utf-8") as dst:
        for p in sorted(root.rglob("audit.jsonl")):
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        dst.write(line + "\n")
            except Exception:
                pass
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
