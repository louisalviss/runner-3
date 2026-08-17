#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "autocontent"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LATEST_PATH = OUT_DIR / "latest.json"
REQUEST_PATH = OUT_DIR / "wp-request.json"

FEEDS = [
    {"name": "InsideEVs", "url": "https://insideevs.com/rss/news/all/"},
    {"name": "Electrek", "url": "https://electrek.co/feed/"},
    {"name": "CleanTechnica", "url": "https://cleantechnica.com/feed/"},
]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 runner-3-autocontent/1.0"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.7",
})
TIMEOUT = 35


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_name(tag):
    return tag.split("}", 1)[-1].lower()


def clean_text(value):
    if not value:
        return ""
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(value):
    if not value:
        return ""
    value = value.strip()
    if not value.startswith(("https://", "http://")):
        return ""
    p = urlparse(value)
    host = p.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", p.path or "/")
    return urlunparse(("https", host, path, "", "", ""))


def find_child_text(node, names):
    names = set(names)
    for child in list(node):
        if local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def find_link(node):
    direct = find_child_text(node, {"link"})
    if direct.startswith(("http://", "https://")):
        return direct
    for child in list(node):
        if local_name(child.tag) == "link" and child.attrib.get("href"):
            if child.attrib.get("rel", "alternate") in ("alternate", ""):
                return child.attrib["href"]
    return ""


def parse_feed(xml_bytes, source):
    root = ET.fromstring(xml_bytes)
    nodes = [n for n in root.iter() if local_name(n.tag) in {"item", "entry"}]
    items = []
    for n in nodes[:35]:
        title = clean_text(find_child_text(n, {"title"}))
        link = canonical_url(find_link(n))
        desc = clean_text(find_child_text(n, {"description", "summary", "content", "encoded"}))
        published = clean_text(find_child_text(n, {"pubdate", "published", "updated", "date"}))
        if title and link:
            items.append({
                "source": source["name"],
                "feed": source["url"],
                "title": title,
                "url": link,
                "description": desc[:1400],
                "published": published,
            })
    return items


def fetch_feeds():
    all_items, health = [], []
    for src in FEEDS:
        try:
            r = SESSION.get(src["url"], timeout=TIMEOUT)
            r.raise_for_status()
            parsed = parse_feed(r.content, src)
            all_items.extend(parsed)
            health.append({"source": src["name"], "status": "ok", "items": len(parsed)})
        except Exception as e:
            health.append({"source": src["name"], "status": "error", "detail": str(e)[:240]})
    if not all_items:
        raise RuntimeError(f"All automotive feeds failed: {health}")
    return all_items, health


def normalized_title(title):
    s = unicodedata.normalize("NFKD", title).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def dedupe(items):
    kept, removed = [], []
    for item in items:
        nt = normalized_title(item["title"])
        duplicate = None
        for prior in kept:
            if item["url"] == prior["url"]:
                duplicate = prior
                break
            ratio = SequenceMatcher(None, nt, normalized_title(prior["title"])).ratio()
            if ratio >= 0.88:
                duplicate = prior
                break
        if duplicate:
            removed.append({
                "title": item["title"],
                "url": item["url"],
                "duplicate_of": duplicate["url"],
            })
        else:
            kept.append(item)
    return kept, removed


def balanced_pick(items, limit=12):
    buckets = {}
    order = []
    for item in items:
        src = item["source"]
        if src not in buckets:
            buckets[src] = []
            order.append(src)
        buckets[src].append(item)
    picked = []
    i = 0
    while len(picked) < limit:
        progress = False
        for src in order:
            if i < len(buckets[src]):
                picked.append(buckets[src][i])
                progress = True
                if len(picked) >= limit:
                    break
        if not progress:
            break
        i += 1
    return picked


def extract_article(url):
    try:
        r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for bad in soup(["script", "style", "nav", "footer", "form", "aside", "noscript", "svg"]):
            bad.decompose()
        root = soup.find("article") or soup.find("main") or soup.body
        if not root:
            return ""
        paras = []
        for p in root.find_all(["p", "h2", "h3"]):
            text = clean_text(p.get_text(" ", strip=True))
            if len(text) >= 45 and not re.search(
                r"(newsletter|sign up|cookie|advertis|privacy policy|all rights reserved)",
                text,
                re.I,
            ):
                paras.append(text)
        return "\n".join(paras)[:6500]
    except Exception:
        return ""


def enrich(items):
    enriched = []
    for item in items:
        row = dict(item)
        row["article_text"] = extract_article(item["url"])
        enriched.append(row)
        time.sleep(0.12)
    return enriched


def call_model(items, focus, model):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for GitHub Models")

    source_urls = [x["url"] for x in items]
    source_block = []
    for idx, item in enumerate(items, 1):
        body = item.get("article_text") or item.get("description") or ""
        source_block.append(
            f"SOURCE {idx}\n"
            f"Publisher: {item['source']}\n"
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Published: {item.get('published', '')}\n"
            f"Text:\n{body[:6000]}\n"
        )

    prompt = f"""
You are the editorial engine for an automotive publisher. Build ONE useful, original story from the supplied source material.

Focus requested: {focus}

Hard rules:
- Use only facts supported by the supplied sources. Do not use outside knowledge.
- Do not invent numbers, quotes, test results, dates, specifications, prices, or causal claims.
- If sources do not support a coherent cross-source story, choose the strongest single-source story and clearly attribute it.
- Never copy long phrases from sources. Synthesize and paraphrase.
- The article must be commercially usable, concise, natural English, not generic AI prose.
- Include source attribution naturally where material facts depend on a publisher.
- Article body target: 800-1200 words.
- Return JSON only. No Markdown fences.

JSON schema:
{{
  "topic": "string",
  "title": "string",
  "slug": "lowercase-hyphen-slug",
  "excerpt": "string <= 220 chars",
  "article_html": "HTML using p,h2,h3,ul,li,strong only",
  "seo": {{
    "primary_keyword": "string",
    "secondary_keywords": ["string"],
    "meta_description": "string <= 160 chars"
  }},
  "social": {{
    "x": "string <= 500 chars",
    "linkedin": "string",
    "instagram": "string"
  }},
  "video": {{
    "hook": "string",
    "script": "60-90 second narration",
    "shots": ["string"]
  }},
  "used_source_urls": ["URL from supplied sources only"],
  "claim_checks": [
    {{"claim": "material factual claim", "source_urls": ["supporting supplied URL"]}}
  ],
  "qa": {{
    "unsupported_numeric_claims": 0,
    "notes": ["string"]
  }}
}}

SOURCES:
{chr(10).join(source_block)}
"""

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict grounded automotive editor. Output valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 5000,
    }
    r = requests.post(
        "https://models.github.ai/inference/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
        timeout=120,
    )
    if not r.ok:
        raise RuntimeError(f"GitHub Models failed {r.status_code}: {r.text[:800]}")
    data = r.json()
    content = data["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
    content = re.sub(r"\s*```$", "", content)
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            raise
        result = json.loads(m.group(0))

    allowed = set(source_urls)
    used = [u for u in result.get("used_source_urls", []) if u in allowed]
    if not used:
        raise RuntimeError("Model returned no valid supplied source URL")
    result["used_source_urls"] = used
    for check in result.get("claim_checks", []):
        check["source_urls"] = [u for u in check.get("source_urls", []) if u in allowed]
    return result


def validate(result):
    required = [
        "title",
        "slug",
        "excerpt",
        "article_html",
        "seo",
        "social",
        "video",
        "used_source_urls",
    ]
    missing = [k for k in required if not result.get(k)]
    if missing:
        raise RuntimeError(f"Generated content missing fields: {missing}")
    if len(result["article_html"]) < 2200:
        raise RuntimeError("Generated article is unexpectedly short")
    if result.get("qa", {}).get("unsupported_numeric_claims", 0) != 0:
        raise RuntimeError("QA reported unsupported numeric claims")

    result["slug"] = re.sub(r"[^a-z0-9-]+", "-", result["slug"].lower()).strip("-")[:90]
    result["excerpt"] = result["excerpt"][:220]
    result["seo"]["meta_description"] = result["seo"].get("meta_description", "")[:160]


def append_sources_html(result, items):
    by_url = {x["url"]: x for x in items}
    links = []
    for url in result["used_source_urls"]:
        item = by_url[url]
        title = (
            item["title"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        publisher = (
            item["source"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        links.append(
            f'<li><a href="{url}" rel="nofollow noopener">{publisher}: {title}</a></li>'
        )
    result["article_html"] += "\n<h2>Sources</h2><ul>" + "".join(links) + "</ul>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--focus",
        default="EV technology, charging, battery economics and real-world ownership",
    )
    ap.add_argument("--status", choices=["draft", "publish"], default="draft")
    ap.add_argument(
        "--model",
        default=os.environ.get("AUTOCONTENT_MODEL", "openai/gpt-4.1"),
    )
    args = ap.parse_args()

    raw, health = fetch_feeds()
    unique, removed = dedupe(raw)
    selected = balanced_pick(unique, limit=12)
    enriched = enrich(selected)
    result = call_model(enriched, args.focus, args.model)
    validate(result)
    append_sources_html(result, enriched)

    used_lookup = {x["url"]: x for x in enriched}
    record = {
        "status": "generated",
        "generated_at": now_iso(),
        "model": args.model,
        "focus": args.focus,
        "metrics": {
            "feeds_ok": sum(1 for h in health if h["status"] == "ok"),
            "items_ingested": len(raw),
            "duplicates_removed": len(removed),
            "unique_items": len(unique),
            "items_enriched": len(enriched),
            "sources_used": len(result["used_source_urls"]),
        },
        "feed_health": health,
        "duplicates_sample": removed[:10],
        "sources_used": [
            {k: v for k, v in used_lookup[u].items() if k != "article_text"}
            for u in result["used_source_urls"]
            if u in used_lookup
        ],
        "content": result,
        "wordpress": {"requested_status": args.status, "result": None},
    }
    LATEST_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    request = {
        "site_slug": os.environ.get("WP_SITE_SLUG", "runner3-factory-smoke-2"),
        "action": "create_post",
        "payload": {
            "title": result["title"],
            "slug": result["slug"],
            "excerpt": result["excerpt"],
            "content": result["article_html"],
            "status": args.status,
        },
    }
    REQUEST_PATH.write_text(
        json.dumps(request, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "title": result["title"],
                "sources_used": len(result["used_source_urls"]),
                "wordpress_status": args.status,
                "latest": str(LATEST_PATH.relative_to(ROOT)),
                "request": str(REQUEST_PATH.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
