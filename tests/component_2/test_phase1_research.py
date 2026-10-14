from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[2] / "research" / "component_2" / "src"
sys.path.insert(0, str(SRC))

from data_io import COMMENTS_REQUIRED_COLUMNS, validate_required_columns
from text_processing import (
    clean_text,
    has_mixed_sinhala_latin,
    has_sinhala,
    is_emoji_only,
    preprocess_comment_text,
)
from validation import duplicate_count, video_match_summary


class Phase1ResearchTests(unittest.TestCase):
    def test_required_columns_validation_passes(self):
        df = pd.DataFrame(columns=sorted(COMMENTS_REQUIRED_COLUMNS))
        self.assertEqual(
            validate_required_columns(df, COMMENTS_REQUIRED_COLUMNS, "comments"),
            sorted(COMMENTS_REQUIRED_COLUMNS),
        )

    def test_required_columns_validation_fails(self):
        df = pd.DataFrame(columns=["comment_id"])
        with self.assertRaises(ValueError):
            validate_required_columns(df, COMMENTS_REQUIRED_COLUMNS, "comments")

    def test_duplicate_ids(self):
        df = pd.DataFrame({"comment_id": ["a", "b", "b"]})
        self.assertEqual(duplicate_count(df, "comment_id"), 1)

    def test_sinhala_unicode_preservation(self):
        text = "සිංහල comment"
        processed = preprocess_comment_text(text)
        self.assertIn("සිංහල", processed["cleaned_text"])
        self.assertTrue(has_sinhala(processed["cleaned_text"]))

    def test_mixed_script_detection(self):
        self.assertTrue(has_mixed_sinhala_latin("මේක good video"))
        self.assertFalse(has_mixed_sinhala_latin("Only Latin"))

    def test_emoji_only_detection(self):
        self.assertTrue(is_emoji_only("🔥🔥"))
        self.assertFalse(is_emoji_only("🔥 good"))

    def test_url_cleaning(self):
        self.assertEqual(clean_text("watch https://example.com now"), "watch <URL> now")

    def test_null_string_handling(self):
        processed = preprocess_comment_text("null")
        self.assertEqual(processed["cleaned_text"], "")
        self.assertTrue(processed["exclude_from_modeling"])

    def test_reply_identification_input_shape(self):
        df = pd.DataFrame({"parent_comment_id": [pd.NA, "abc"]})
        is_reply = df["parent_comment_id"].notna() & (df["parent_comment_id"].astype(str).str.strip() != "")
        self.assertEqual(is_reply.tolist(), [False, True])

    def test_video_id_matching(self):
        comments = pd.DataFrame({"video_id": ["v1", "v2", "v2"]})
        videos = pd.DataFrame({"video_id": ["v1", "v2", "v3"]})
        summary = video_match_summary(comments, videos)
        self.assertEqual(summary["commented_videos"], 2)
        self.assertEqual(summary["matched_videos"], 2)
        self.assertEqual(summary["missing_video_metadata"], 0)

    def test_preprocessing_is_deterministic(self):
        text = "  Helloooo https://example.com  "
        self.assertEqual(preprocess_comment_text(text), preprocess_comment_text(text))


if __name__ == "__main__":
    unittest.main()
