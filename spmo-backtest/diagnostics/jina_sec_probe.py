#!/usr/bin/env python3
import requests

PROBES = [
    (
        "control_ibqq",
        "https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/000175272422017416/0001752724-22-017416.txt",
        ["S000072469", "Invesco Nasdaq Biotechnology ETF"],
    ),
    (
        "control_spmo",
        "https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/000175272422170575/0001752724-22-170575.txt",
        ["S000050154", "Invesco S&P 500 Momentum ETF"],
    ),
]

for name, url, needles in PROBES:
    r = requests.get(url, timeout=45, headers={"User-Agent": "runner-3 spmo research"})
    print(f"{name} status={r.status_code} length={len(r.text)}")
    print(r.text[:500].replace("\n", " "))
    r.raise_for_status()
    missing = [x for x in needles if x not in r.text]
    if missing:
        raise RuntimeError(f"{name}: missing expected markers {missing}")
print("JINA_SEC_PROBE_OK")
