#!/usr/bin/env python3
import argparse
import io
import os
import zipfile
from pathlib import Path

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--run-id", required=True, type=int)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN missing")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    api = f"https://api.github.com/repos/{args.repo}/actions/runs/{args.run_id}/artifacts?per_page=100"
    r = requests.get(api, headers=headers, timeout=30)
    r.raise_for_status()
    artifacts = r.json().get("artifacts", [])
    selected = [a for a in artifacts if not a.get("expired") and a.get("name", "").startswith(args.prefix)]
    print(f"found={len(artifacts)} selected={len(selected)}", flush=True)
    if not selected:
        raise SystemExit("No matching artifacts")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for i, a in enumerate(selected, 1):
        url = a["archive_download_url"]
        rr = requests.get(url, headers=headers, timeout=60, allow_redirects=True)
        rr.raise_for_status()
        dest = out / a["name"]
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(rr.content)) as z:
            z.extractall(dest)
        print(f"{i}/{len(selected)} {a['name']} files={len(list(dest.rglob('*')))}", flush=True)


if __name__ == "__main__":
    main()
