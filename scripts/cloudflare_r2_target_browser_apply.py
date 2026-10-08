#!/usr/bin/env python3
"""Apply a source-encrypted R2 object bundle via authenticated Cloudflare browser.

No Cloudflare token or browser cookie is extracted. Never overwrite, never delete.
"""
import base64
import hashlib
import json
import os
import pathlib
import sys
import urllib.parse
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, "/opt/browser-stack/bin")
from raw_cdp_skill import RawCDPSkill

DEST_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
SOURCE_ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
ALLOWED = {
    "runner3-artifacts", "runner3-wp-media", "runner3-rss-fastlane-artifacts",
    "ai-vps-common-access", "clm-copilot-data", "runner-vps-dr",
    "runner3-reddit-opportunity-raw", "runner3-telegram-bobvolman-raw",
    "runner3-telegram-raw",
}
ROOT = pathlib.Path("/var/lib/cloudflare-migration/2026-10-08/ephemeral-courier")

def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: <envelope_path> <github_run_id>")
    envelope_path = pathlib.Path(sys.argv[1]).resolve()
    if not envelope_path.is_relative_to(ROOT) or envelope_path.name != "envelope.json":
        raise SystemExit("ENVELOPE_NOT_IN_ALLOWED_COURIER_DIRECTORY")
    run_id = sys.argv[2]
    if not run_id.isdigit():
        raise SystemExit("INVALID_GITHUB_RUN_ID")
    env = json.loads(envelope_path.read_text())
    if env.get("version") != 2:
        raise SystemExit("BUNDLE_VERSION_MISMATCH")
    private = serialization.load_pem_private_key(
        (ROOT / "key.pem").read_bytes(), password=None
    )
    aes = private.decrypt(
        base64.b64decode(env["wrapped_key"]),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(), label=None
        )
    )
    clear = AESGCM(aes).decrypt(
        base64.b64decode(env["nonce"]),
        base64.b64decode(env["ciphertext"]),
        base64.b64decode(env["aad"])
    )
    items = json.loads(clear)
    bucket = items.get("bucket")
    if items.get("account") != SOURCE_ACCOUNT or bucket not in ALLOWED:
        raise SystemExit("UNAUTHORIZED_BUNDLE_IDENTITY")
    objs = items.get("objects") or []
    if len(objs) > 30:
        raise SystemExit("BUNDLE_ITEM_COUNT_EXCEEDED")
    if sum(int(o.get("size") or 0) for o in objs) > 25_000_000:
        raise SystemExit("BUNDLE_MAX_BYTES_EXCEEDED")
    report = {
        "run_id":run_id, "bucket":bucket,
        "source_count":items.get("source_inventory"),
        "start_index":items.get("start_index"),
        "objects_in_bundle":len(objs),
        "copied":0,"existing_verified":0,"readback_verified":0,
        "bytes_copied":0,"source_deleted":False,
    }
    root = (
        "https://dash.cloudflare.com/api/v4/accounts/"
        + DEST_ACCOUNT + "/r2/buckets/" + bucket + "/objects/"
    )
    with RawCDPSkill(
        "gmail-otp-main", owner="cf-r2-courier-apply",
        priority="auth", new_page=True, keep_running=False
    ) as skill:
        p = skill.page
        p.goto(
            "https://dash.cloudflare.com/" + DEST_ACCOUNT,
            wait_until="domcontentloaded", timeout=60000
        )
        for item in objs:
            raw = base64.b64decode(item["payload_b64"])
            digest = hashlib.sha256(raw).hexdigest()
            logical_digest = item.get("logical_sha256") or digest
            if len(raw) != int(item.get("size") or -1) or digest != item.get("sha256"):
                raise SystemExit("SOURCE_CONTENT_CHECK_FAILED")
            key = item.get("key")
            if not isinstance(key, str) or not key:
                raise SystemExit("INVALID_OBJECT_KEY")
            url = root + urllib.parse.quote(key, safe="/")
            exists = p.request.get(url, timeout=45000)
            if exists.status == 200:
                if hashlib.sha256(exists.body()).hexdigest() != logical_digest:
                    raise SystemExit("TARGET_OBJECT_COLLISION_DIFFERENT_HASH")
                report["existing_verified"] += 1
                report["readback_verified"] += 1
                continue
            if exists.status != 404:
                raise SystemExit("TARGET_OBJECT_PRECHECK_" + str(exists.status))
            meta = item.get("http_metadata") or {}
            headers = {"Content-Type": item.get("content_type") or "application/octet-stream"}
            for src, dst in (
                ("cacheControl", "Cache-Control"),
                ("contentDisposition", "Content-Disposition"),
                ("contentLanguage", "Content-Language"),
                ("contentEncoding", "Content-Encoding"),
            ):
                if meta.get(src):
                    headers[dst] = str(meta[src])
            put = p.request.put(url, data=raw, headers=headers, timeout=90000)
            try:
                j = put.json()
            except Exception:
                j = {}
            if put.status not in (200,201) or not j.get("success"):
                raise SystemExit("TARGET_PUT_" + str(put.status) +
                                 "_CODES_" + str([x.get("code") for x in (j.get("errors") or [])]))
            report["copied"] += 1
            report["bytes_copied"] += len(raw)
            check = p.request.get(url, timeout=90000)
            if check.status != 200 or hashlib.sha256(check.body()).hexdigest() != logical_digest:
                raise SystemExit("DESTINATION_SHA256_MISMATCH")
            report["readback_verified"] += 1
    report["status"]="PASS"
    dest = ROOT / "receipts"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / (run_id + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        # In particular, Playwright HTTP exceptions may contain Cookie headers.
        # Never print their message or traceback into CI/VPS logs.
        print("TARGET_BROWSER_EXCEPTION_REDACTED", type(exc).__name__)
        raise SystemExit(2)
