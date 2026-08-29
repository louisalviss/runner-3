#!/usr/bin/env python3
from __future__ import annotations

import os

import dcc_v3_finalize as base
from r2_cloudflare_rest import CloudflareR2RestClient

_original_s3_client = base.s3_client


def _r2_client():
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    account = (os.getenv("R2_ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if token and account:
        print("R2_TRANSPORT=cloudflare-rest-api-token")
        return CloudflareR2RestClient(account, token)
    print("R2_TRANSPORT=s3-compatible-fallback")
    return _original_s3_client()


base.s3_client = _r2_client

if __name__ == "__main__":
    base.main()
