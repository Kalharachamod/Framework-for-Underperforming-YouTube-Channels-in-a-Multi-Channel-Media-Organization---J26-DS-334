from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[2] / "research" / "component_2" / "src"
sys.path.insert(0, str(SRC))

from annotation import (
    ANNOTATION_COLUMNS,
    AnnotationSamplingConfig,
    create_annotation_sample,
    create_annotation_template,
    prepare_annotation_source,
)


def synthetic_source() -> pd.DataFrame:
    rows = []
    for channel_idx in range(5):
        channel_id = f"UC_{channel_idx}"
        for item_idx in range(20):
            comment_id = f"c_{channel_idx}_{item_idx}"
            script_type = item_idx % 5
            rows.append(
                {
                    "comment_id": comment_id,
                    "channel_id": channel_id,
                    "video_id": f"v_{channel_idx}_{item_idx % 4}",
                    "original_text": "සිංහල hello"
                    if script_type == 0
                    else "සිංහල"
                    if script_type == 1
                    else "hello"
                    if script_type == 2
                    else "🔥🔥"
                    if script_type == 3
                    else "ok",
                    "cleaned_text": "සිංහල hello"
                    if script_type == 0
                    else "සිංහල"
                    if script_type == 1
                    else "hello"
                    if script_type == 2
                    else "🔥🔥"
                    if script_type == 3
                    else "ok",
                    "has_sinhala": script_type in {0, 1},
                    "has_latin": script_type in {0, 2, 4},
                    "mixed_sinhala_latin": script_type == 0,
                    "emoji_only": script_type == 3,
                    "char_length": 2 if script_type == 4 else 10,
                    "word_count": 1,
                    "has_repeated_char_pattern": False,
                    "changed_by_preprocessing": False,
                    "review_reasons": "very_short" if script_type == 4 else "",
                    "exclude_from_modeling": False,
                    "repeated_cleaned_text": False,
                    "channel_name": f"Channel {channel_idx}",
                    "parent_comment_id": "p1" if item_idx % 7 == 0 else pd.NA,
                    "published_at": f"2026-01-{(item_idx % 28) + 1:02d} 00:00:00+00",
                }
            )
    return pd.DataFrame(rows)


class AnnotationPreparationTests(unittest.TestCase):
    def test_deterministic_sampling(self):
        source = synthetic_source()
        config = AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2)
        first = create_annotation_sample(source, config)
        second = create_annotation_sample(source, config)
        self.assertEqual(first["comment_id"].tolist(), second["comment_id"].tolist())

    def test_unique_selected_comment_ids_and_size(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        self.assertEqual(len(sample), 50)
        self.assertEqual(sample["comment_id"].nunique(), 50)

    def test_five_channel_coverage(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        self.assertEqual(sample["channel_id"].nunique(), 5)

    def test_script_category_coverage(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        categories = set(sample["script_category"])
        self.assertIn("mixed_sinhala_latin", categories)
        self.assertIn("sinhala_script", categories)
        self.assertIn("latin_script", categories)
        self.assertIn("emoji_only", categories)

    def test_blank_annotation_fields(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        for column in [
            "primary_label",
            "demand_subtype",
            "annotation_notes",
            "annotator_1_label",
            "annotator_2_label",
            "final_adjudicated_label",
        ]:
            self.assertTrue((template[column] == "").all())

    def test_output_schema(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        self.assertEqual(template.columns.tolist(), ANNOTATION_COLUMNS)

    def test_prepare_annotation_source_references_validated_data(self):
        preprocessed = synthetic_source().drop(columns=["channel_name", "parent_comment_id", "published_at"])
        validated = synthetic_source()[["comment_id", "channel_name", "parent_comment_id", "published_at"]]
        source = prepare_annotation_source(preprocessed, validated)
        self.assertIn("channel_name", source.columns)
        self.assertIn("is_reply", source.columns)
        self.assertTrue(source["is_reply"].any())


if __name__ == "__main__":
    unittest.main()
