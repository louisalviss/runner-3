#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import private_backtest_worker_v2 as core

PROJECT = "private-backtest"
SCOPE = "bt-super-rsi-crypto30-binance-usdm-perp-expanded-v2"


def main():
    work = Path(tempfile.mkdtemp(prefix="crypto-perp-shib-repair-"))
    mp = work / "manifest.json"
    core.download_artifact(PROJECT, SCOPE, "manifest.json", mp)
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    helper_name = manifest["files"]["helper"]["name"]
    hp = work / "exp.py"
    core.download_artifact(PROJECT, SCOPE, helper_name, hp)
    text = hp.read_text(encoding="utf-8")
    old = '''def resolve_symbol(symbol):\n    s=str(symbol).strip().upper()\n    return s if s in ALLOWED else None\n'''
    new = '''VENUE_ALIASES={"SHIBUSDT":"1000SHIBUSDT"}\n\ndef resolve_symbol(symbol):\n    s=str(symbol).strip().upper()\n    if s not in ALLOWED:\n        return None\n    return VENUE_ALIASES.get(s, s)\n'''
    if old not in text:
        if 'VENUE_ALIASES={"SHIBUSDT":"1000SHIBUSDT"}' not in text:
            raise RuntimeError("expected resolve_symbol block not found")
    else:
        text = text.replace(old, new, 1)
    hp.write_text(text, encoding="utf-8")
    core.upload_artifact(PROJECT, SCOPE, helper_name, hp, "text/x-python; charset=utf-8")
    manifest["files"]["helper"]["sha256"] = core.sha256_file(hp)
    manifest["transport_repairs"] = list(manifest.get("transport_repairs", [])) + [
        {"repair": "BINANCE_USDM_SHIB_CONTRACT_ALIAS", "mapping": "SHIBUSDT->1000SHIBUSDT", "strategy_changes": "NONE"}
    ]
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(PROJECT, SCOPE, "manifest.json", mp, "application/json; charset=utf-8")
    print(json.dumps({"scope": SCOPE, "helper_sha256": manifest["files"]["helper"]["sha256"], "repair": "SHIBUSDT->1000SHIBUSDT"}))

if __name__ == "__main__":
    main()
