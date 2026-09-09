#!/usr/bin/env python3
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import reddit_common


class RedditCommonUrlTests(unittest.TestCase):
    def test_subredditless_comments_url_from_reddit_shortlink_is_canonical(self):
        canonical, post_id, meta = reddit_common.resolve_reddit_url(
            "https://www.reddit.com/comments/1waxm7z"
        )
        self.assertEqual(canonical, "https://www.reddit.com/comments/1waxm7z/")
        self.assertEqual(post_id, "1waxm7z")
        self.assertEqual(meta["via"], "canonical")

    def test_subreddit_comments_url_remains_canonical(self):
        canonical, post_id = reddit_common.canonical_from_url(
            "https://www.reddit.com/r/ChatGPT/comments/1waxm7z/example_title/"
        )
        self.assertEqual(
            canonical,
            "https://www.reddit.com/r/ChatGPT/comments/1waxm7z/example_title/",
        )
        self.assertEqual(post_id, "1waxm7z")

    def test_non_reddit_host_is_rejected(self):
        canonical, post_id = reddit_common.canonical_from_url(
            "https://example.com/comments/1waxm7z"
        )
        self.assertIsNone(canonical)
        self.assertIsNone(post_id)


if __name__ == "__main__":
    unittest.main()
