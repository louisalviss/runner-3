#!/usr/bin/env python3
import json
import sys
from urllib.parse import quote
import requests

BASE = "https://runner3-core.ducduy2411.workers.dev"

def fail(message):
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    raise SystemExit(1)

r = requests.get(BASE + "/artifact-library/api/list", headers={"Cache-Control": "no-cache"}, timeout=60)
if r.status_code != 200:
    fail(f"list HTTP {r.status_code}")
data = r.json()
objects = data.get("objects") or []
if data.get("ok") is not True or not objects:
    fail("no canonical final EPUB in live library")
key = str(objects[0].get("key") or "")
if not key:
    fail("first object missing key")

reader = requests.get(BASE + "/artifact-library/read?key=" + quote(key, safe=""), headers={"Cache-Control": "no-cache"}, timeout=60)
if reader.status_code != 200:
    fail(f"reader HTTP {reader.status_code}")
html = reader.text
checks = {
    "playerV2": 'data-r3-ebook-audio-v6="2"' in html,
    "seek": 'id="r3AudioSeek"' in html,
    "rewind15": 'id="r3AudioBack"' in html,
    "forward15": 'id="r3AudioForward"' in html,
    "speed": 'id="r3AudioSpeed"' in html,
    "mediaSession": "mediaSession" in html,
}
if not all(checks.values()):
    fail("missing live player markers: " + ",".join(k for k,v in checks.items() if not v))
print(json.dumps({"ok": True, "bookKey": key, "readerHttp": reader.status_code, **checks}, ensure_ascii=False))
