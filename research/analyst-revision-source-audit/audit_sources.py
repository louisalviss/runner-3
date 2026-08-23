import json
import re
import sys
from urllib.parse import quote

import requests

S = requests.Session()
S.headers.update({"User-Agent": "louis-research-source-audit/1.0"})

KEYS = ("analyst", "estimate", "revision", "forecast", "consensus", "recommendation", "earnings")


def get_json(url, timeout=30):
    r = S.get(url, timeout=timeout)
    print("HTTP", r.status_code, url)
    r.raise_for_status()
    return r.json()


def hf_search(q, limit=50):
    url = f"https://huggingface.co/api/datasets?search={quote(q)}&limit={limit}&full=true"
    data = get_json(url)
    out = []
    for x in data:
        did = x.get("id") or x.get("modelId") or ""
        if any(k in did.lower() for k in KEYS):
            out.append({
                "id": did,
                "downloads": x.get("downloads"),
                "lastModified": x.get("lastModified"),
                "tags": x.get("tags", [])[:15],
            })
    return out


def hf_author(author="sovai", limit=100):
    url = f"https://huggingface.co/api/datasets?author={quote(author)}&limit={limit}&full=true"
    data = get_json(url)
    out = []
    for x in data:
        did = x.get("id") or ""
        if any(k in did.lower() for k in KEYS):
            out.append({
                "id": did,
                "downloads": x.get("downloads"),
                "lastModified": x.get("lastModified"),
                "tags": x.get("tags", [])[:15],
            })
    return out


def dataset_probe(did):
    info = get_json(f"https://huggingface.co/api/datasets/{did}")
    card = info.get("cardData") or {}
    siblings = [x.get("rfilename") for x in info.get("siblings", []) if x.get("rfilename")]
    result = {
        "id": did,
        "private": info.get("private"),
        "gated": info.get("gated"),
        "lastModified": info.get("lastModified"),
        "description": (card.get("description") or "")[:800],
        "license": card.get("license"),
        "siblings_sample": siblings[:30],
    }
    # datasets-server parquet inventory, if supported
    try:
        pq = get_json(f"https://datasets-server.huggingface.co/parquet?dataset={quote(did)}")
        result["parquet"] = pq.get("parquet_files", [])[:20]
    except Exception as e:
        result["parquet_error"] = repr(e)
    return result


def public_endpoint_probe():
    probes = {}
    urls = {
        "fmp_docs_search": "https://site.financialmodelingprep.com/developer/docs",
        "alpha_vantage_docs": "https://www.alphavantage.co/documentation/",
        "finnhub_docs": "https://finnhub.io/docs/api",
    }
    for name, url in urls.items():
        try:
            r = S.get(url, timeout=30)
            text = re.sub(r"\s+", " ", r.text.lower())
            probes[name] = {
                "status": r.status_code,
                "url": url,
                "mentions_revision": "revision" in text,
                "mentions_estimate": "estimate" in text,
                "mentions_analyst": "analyst" in text,
                "mentions_historical": "historical" in text,
                "bytes": len(r.content),
            }
        except Exception as e:
            probes[name] = {"url": url, "error": repr(e)}
    return probes


def main():
    queries = [
        "analyst estimate",
        "earnings estimate",
        "estimate revision",
        "analyst revision",
        "consensus estimate",
        "analyst recommendation",
    ]
    found = {}
    for q in queries:
        try:
            found[q] = hf_search(q)
        except Exception as e:
            found[q] = {"error": repr(e)}

    try:
        sovai = hf_author("sovai")
    except Exception as e:
        sovai = {"error": repr(e)}

    ids = set()
    for v in found.values():
        if isinstance(v, list):
            ids.update(x["id"] for x in v)
    if isinstance(sovai, list):
        ids.update(x["id"] for x in sovai)

    # Probe only likely financial candidates, capped to avoid wandering.
    likely = [
        x for x in sorted(ids)
        if any(k in x.lower() for k in ("estimate", "revision", "analyst", "earnings", "consensus"))
    ][:25]

    details = {}
    for did in likely:
        try:
            details[did] = dataset_probe(did)
        except Exception as e:
            details[did] = {"id": did, "error": repr(e)}

    out = {
        "queries": found,
        "sovai_matches": sovai,
        "likely_ids": likely,
        "details": details,
        "public_endpoint_probe": public_endpoint_probe(),
    }

    print("AUDIT_JSON_BEGIN")
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    print("AUDIT_JSON_END")

    # Conservative source verdict: only candidate if public, ungated and appears to expose
    # historical row files. Schema/PIT semantics still require a second audit before returns.
    candidates = []
    for did, d in details.items():
        if d.get("error"):
            continue
        if d.get("private") or d.get("gated") not in (False, None, "false"):
            continue
        pqs = d.get("parquet") or []
        if pqs:
            candidates.append(did)
    print("PUBLIC_DATASET_CANDIDATES", json.dumps(candidates))
    print("SOURCE_AUDIT_DONE")


if __name__ == "__main__":
    main()
