#!/usr/bin/env python3
"""Archive fast-path runner for reddit_opportunity_scan when live Reddit transport is unavailable."""
import reddit_common as reddit
import reddit_opportunity_scan as scan

reddit.resilient_request_json = reddit.public_fallback_request_json

if __name__ == "__main__":
    scan.main()
