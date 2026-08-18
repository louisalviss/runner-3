#!/usr/bin/env python3

"""Compatibility entrypoint for the canonical Võ Hoàng Hạc hybrid scanner.

All parsing, freshness, Notes validation, mirror merge, hash-change detection,
and health logic live in ``rss_substack_collect.py``.  This wrapper intentionally
does not override any parser behavior so the workflow cannot drift from the
canonical implementation.

Hồ Quốc Tuấn and vnhacker remain ChatGPT-direct sources at reader runtime.
"""

import rss_substack_collect as base


if __name__ == "__main__":
    raise SystemExit(base.main())
