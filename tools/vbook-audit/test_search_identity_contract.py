#!/usr/bin/env python3
from pathlib import Path

def test_first_search_page_token_is_empty():
    s=Path("tools/vbook-audit/vbook_search_identity.py").read_text(encoding="utf-8")
    assert "elif 'page' in al:" in s
    block=s.split("elif 'page' in al:",1)[1].split("else:",1)[0]
    assert "vals.append('')" in block
    assert "vals.append('1')" not in block
