import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "reddit_deep_sweep.py"
spec = importlib.util.spec_from_file_location("reddit_deep_sweep", MODULE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_select_comments_for_d1_caps_and_ranks():
    rows = [
        {"comment_id": f"c{i}", "quality_score": float(i), "score": i, "body_text": "x" * i}
        for i in range(20)
    ]
    kept = mod.select_comments_for_d1(rows, cap=12)
    assert len(kept) == 12
    assert [x["comment_id"] for x in kept] == [f"c{i}" for i in range(19, 7, -1)]


def test_select_comments_for_d1_does_not_mutate_source():
    rows = [
        {"comment_id": "low", "quality_score": 1.0, "score": 1, "body_text": "short"},
        {"comment_id": "high", "quality_score": 9.0, "score": 2, "body_text": "longer"},
    ]
    original = list(rows)
    kept = mod.select_comments_for_d1(rows, cap=1)
    assert kept[0]["comment_id"] == "high"
    assert rows == original
