import json, os, re, sys, time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}


def trace_search(image_url):
    r = requests.get(
        "https://api.trace.moe/search",
        params={"anilistInfo": "1", "url": image_url},
        headers=HEADERS,
        timeout=45,
    )
    out = {"status": r.status_code, "ok": r.ok}
    try:
        data = r.json()
        out["error"] = data.get("error")
        rows = []
        for x in (data.get("result") or [])[:10]:
            ani = x.get("anilist") or {}
            title = ani.get("title") or {}
            rows.append({
                "similarity": x.get("similarity"),
                "episode": x.get("episode"),
                "from": x.get("from"),
                "to": x.get("to"),
                "anilist_id": ani.get("id"),
                "title": title,
                "filename": x.get("filename"),
            })
        out["results"] = rows
    except Exception:
        out["body"] = r.text[:3000]
    return out


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def sauce_search(image_url):
    r = requests.get(
        "https://saucenao.com/search.php",
        params={"url": image_url, "db": "999"},
        headers=HEADERS,
        timeout=60,
        allow_redirects=True,
    )
    out = {"status": r.status_code, "ok": r.ok, "final_url": r.url}
    soup = BeautifulSoup(r.text, "html.parser")
    out["title"] = clean(soup.title.get_text(" ") if soup.title else "")
    out["body_head"] = clean(soup.get_text(" ", strip=True))[:2000]
    results = []
    for block in soup.select(".result")[:12]:
        sim = clean(block.select_one(".resultsimilarity").get_text(" ") if block.select_one(".resultsimilarity") else "")
        title = clean(block.select_one(".resulttitle").get_text(" ") if block.select_one(".resulttitle") else "")
        content = clean(block.select_one(".resultcontent").get_text(" ") if block.select_one(".resultcontent") else block.get_text(" "))
        links = []
        for a in block.select("a[href]"):
            href = a.get("href")
            if href and href not in links:
                links.append(href)
        if sim or title or content:
            results.append({"similarity": sim, "title": title, "content": content[:1000], "links": links[:8]})
    out["results"] = results
    return out


def lens_http(image_url):
    r = requests.get(
        "https://lens.google.com/uploadbyurl",
        params={"url": image_url},
        headers=HEADERS,
        timeout=60,
        allow_redirects=True,
    )
    soup = BeautifulSoup(r.text, "html.parser")
    return {
        "status": r.status_code,
        "ok": r.ok,
        "final_url": r.url,
        "title": clean(soup.title.get_text(" ") if soup.title else ""),
        "body_head": clean(soup.get_text(" ", strip=True))[:2000],
    }


def main():
    job = json.load(open(sys.argv[1], "r", encoding="utf-8"))
    base = job["base_raw_url"].rstrip("/")
    files = job.get("files") or ["preview.jpg", "frame_01.jpg", "frame_02.jpg"]
    outdir = Path(job.get("output_dir", "x-source-compare-results")) / job["tweet_id"]
    outdir.mkdir(parents=True, exist_ok=True)
    report = {"tweet_id": job["tweet_id"], "base_raw_url": base, "frames": {}}
    for i, name in enumerate(files):
        image_url = f"{base}/{name}"
        row = {"image_url": image_url}
        for label, fn in [("trace", trace_search), ("saucenao", sauce_search), ("lens_http", lens_http)]:
            try:
                row[label] = fn(image_url)
            except Exception as e:
                row[label] = {"ok": False, "exception": repr(e)}
            time.sleep(2)
        report["frames"][name] = row
    (outdir / "compare.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
