#!/usr/bin/env python3

"""Runner3 ingestion for the 8 non-ChatGPT-direct AI RSS Reader sources.

Hồ Quốc Tuấn / Đọc Chậm and ThaiDN / vnhacker are intentionally excluded
from Runner3 because GitHub-runner transport to Substack is unreliable.
Those two logical sources are fetched directly by ChatGPT at reader runtime.
"""

import rss_reader_collect as core

CHATGPT_DIRECT_KEYS = {"hoquoctuan", "vnhacker"}
core.SOURCES = [s for s in core.SOURCES if s.get("key") not in CHATGPT_DIRECT_KEYS]

if __name__ == "__main__":
    raise SystemExit(core.main())
