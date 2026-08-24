#!/usr/bin/env python3

"""Lightweight AI user-agent retry layer for Runner-3 public crawling.

This wraps crawler.py without changing its security boundary. The retry is a
content-negotiation/access-classification probe for public pages only; it must
not be treated as an auth, paywall, CAPTCHA, or private-content bypass.
"""

import json
import sys
from urllib.parse import urlparse

import crawler as base

AI_UA_PROFILES = [
    (
        "chatgpt-user",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
        "ChatGPT-User/1.0; +https://openai.com/bot",
    ),
    (
        "claude-user",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
        "Claude-User/1.0; +Claude-User@anthropic.com)",
    ),
    (
        "oai-searchbot",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 "
        "Safari/537.36; compatible; OAI-SearchBot/1.4; "
        "+https://openai.com/searchbot",
    ),
]

EXPERIMENTAL_AI_UA_PROFILES = [
    (
        "bytespider-experimental",
        "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Mobile Safari/537.36 "
        "(compatible; Bytespider; spider-feedback@bytedance.com)",
    ),
]

AUTH_BOUNDARY_MARKERS = (
    "sign in to continue",
    "log in to continue",
    "login required",
    "authentication required",
    "subscription required",
    "subscriber-only",
    "paywall",
    "prove your humanity",
    "verify you are human",
    "captcha",
)

AUTH_REDIRECT_PATH_MARKERS = (
    "/signin",
    "/login",
    "/passport",
    "/account/unhuman",
    "/challenge",
    "/captcha",
    "/verify",
    "/checkpoint",
)

AI_UA_RETRY_ENABLED = True
EXPERIMENTAL_AI_UA_RETRY_ENABLED = False
MIN_USABLE_TEXT_CHARS = 300


def _active_profiles():
    if EXPERIMENTAL_AI_UA_RETRY_ENABLED:
        return [*AI_UA_PROFILES, *EXPERIMENTAL_AI_UA_PROFILES]
    return AI_UA_PROFILES


def _redirected_to_auth(requested_url, final_url):
    if not final_url:
        return False
    requested_path = (urlparse(requested_url).path or "/").lower()
    final_path = (urlparse(final_url).path or "/").lower()
    requested_is_auth = any(marker in requested_path for marker in AUTH_REDIRECT_PATH_MARKERS)
    final_is_auth = any(marker in final_path for marker in AUTH_REDIRECT_PATH_MARKERS)
    return final_is_auth and not requested_is_auth


def _attempt_summary(profile, result, requested_url):
    text_chars = len(result.get("text") or "")
    auth_redirect = _redirected_to_auth(requested_url, result.get("final_url"))
    return {
        "profile": profile,
        "engine": result.get("engine"),
        "status": result.get("status"),
        "final_url": result.get("final_url"),
        "text_chars": text_chars,
        "html_bytes": len((result.get("html") or "").encode("utf-8", errors="ignore")),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "too_thin": text_chars < MIN_USABLE_TEXT_CHARS,
        "auth_redirect": auth_redirect,
        "blocked_or_challenge": auth_redirect or base.looks_blocked(
            result.get("status"), result.get("html"), result.get("text")
        ),
    }


def _is_auth_boundary(result, requested_url):
    status = result.get("status")
    if status in {401, 407}:
        return True
    if _redirected_to_auth(requested_url, result.get("final_url")):
        return True
    text = (result.get("text") or "").lower()
    head = text[:4000]
    # Avoid promoting generic login buttons on otherwise substantial pages.
    return len(text) < 5000 and any(marker in head for marker in AUTH_BOUNDARY_MARKERS)


def _usable_http(result, requested_url):
    status = result.get("status") or 0
    auth_redirect = _redirected_to_auth(requested_url, result.get("final_url"))
    blocked = auth_redirect or base.looks_blocked(
        status, result.get("html"), result.get("text")
    )
    too_thin = len(result.get("text") or "") < MIN_USABLE_TEXT_CHARS
    return status < 400 and not blocked and not too_thin


def _fetch_with_profile(url, timeout, headers, profile, user_agent):
    profile_headers = dict(headers or {})
    profile_headers["User-Agent"] = user_agent
    result = base.http_fetch(url, timeout, profile_headers)
    result["engine"] = "http-aiua"
    result["ai_user_agent_profile"] = profile
    return result


def crawl_one(url, mode, timeout, wait_ms, headers, user_agent):
    errors = []
    initial_result = None
    attempts = []

    if mode in ("http", "auto"):
        try:
            initial_result = base.http_fetch(url, timeout, headers)
            attempts.append(_attempt_summary("normal", initial_result, url))
            if _usable_http(initial_result, url):
                initial_result["blocked_or_challenge"] = False
                initial_result["fallback_used"] = False
                initial_result["http_attempts"] = attempts
                return initial_result, errors

            if AI_UA_RETRY_ENABLED and not _is_auth_boundary(initial_result, url):
                for profile, ai_ua in _active_profiles():
                    try:
                        alt = _fetch_with_profile(url, timeout, headers, profile, ai_ua)
                        attempts.append(_attempt_summary(profile, alt, url))
                        if _usable_http(alt, url):
                            alt["blocked_or_challenge"] = False
                            alt["fallback_used"] = True
                            alt["http_attempts"] = attempts
                            return alt, errors
                    except Exception as exc:
                        errors.append(f"http-aiua[{profile}]: {type(exc).__name__}: {exc}")
        except Exception as exc:
            errors.append(f"http: {type(exc).__name__}: {exc}")

    if mode in ("browser", "auto"):
        try:
            browser_result = base.browser_fetch(url, timeout, wait_ms, headers, user_agent)
            browser_text_chars = len(browser_result.get("text") or "")
            browser_auth_redirect = _redirected_to_auth(url, browser_result.get("final_url"))
            browser_blocked = browser_auth_redirect or base.looks_blocked(
                browser_result.get("status"),
                browser_result.get("html"),
                browser_result.get("text"),
            )
            browser_result["too_thin"] = browser_text_chars < MIN_USABLE_TEXT_CHARS
            browser_result["auth_redirect"] = browser_auth_redirect
            browser_result["blocked_or_challenge"] = browser_blocked or browser_result["too_thin"]
            browser_result["fallback_used"] = mode == "auto"
            if attempts:
                browser_result["http_attempts"] = attempts
            return browser_result, errors
        except Exception as exc:
            errors.append(f"browser: {type(exc).__name__}: {exc}")

    if initial_result is not None:
        initial_text_chars = len(initial_result.get("text") or "")
        initial_auth_redirect = _redirected_to_auth(url, initial_result.get("final_url"))
        initial_blocked = initial_auth_redirect or base.looks_blocked(
            initial_result.get("status"), initial_result.get("html"), initial_result.get("text")
        )
        initial_result["too_thin"] = initial_text_chars < MIN_USABLE_TEXT_CHARS
        initial_result["auth_redirect"] = initial_auth_redirect
        # Base crawler currently derives final ok from this field. Treat a
        # materially thin public response or auth redirect as non-usable so
        # HTTP 200 shells/login redirects do not become false-positive successes.
        initial_result["blocked_or_challenge"] = initial_blocked or initial_result["too_thin"]
        initial_result["quality_failure"] = (
            "auth_redirect" if initial_auth_redirect else
            "too_thin" if initial_result["too_thin"] and not initial_blocked else
            "blocked_or_challenge" if initial_blocked else None
        )
        initial_result["fallback_used"] = False
        initial_result["http_attempts"] = attempts
        return initial_result, errors

    return None, errors


def _load_wrapper_config():
    global AI_UA_RETRY_ENABLED, EXPERIMENTAL_AI_UA_RETRY_ENABLED
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        return
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            job = json.load(f)
        AI_UA_RETRY_ENABLED = job.get("ai_ua_retry", True) is not False
        EXPERIMENTAL_AI_UA_RETRY_ENABLED = job.get("experimental_ai_ua_retry", False) is True
    except Exception:
        # crawler.py remains authoritative for validation/error reporting.
        pass


def main():
    _load_wrapper_config()
    base.crawl_one = crawl_one
    base.main()


if __name__ == "__main__":
    main()
