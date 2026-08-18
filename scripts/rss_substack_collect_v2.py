#!/usr/bin/env python3

# Compatibility entrypoint. The active Substack RSS scope is intentionally
# limited to Võ Hoàng Hạc. Hồ Quốc Tuấn and vnhacker are checked directly by
# ChatGPT at reader runtime instead of via RSS/GitHub Actions.
import rss_substack_collect as base


if __name__ == "__main__":
    raise SystemExit(base.main())
