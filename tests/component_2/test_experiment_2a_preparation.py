from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.component_2.feasibility_experiment.prepare_experiment_2a import (
    ACTIONABILITY_LABELS,
    EXPERIMENT_2A_SEED,
    PRIMARY_SIGNALS,
    REVIEW_ANNOTATION_FIELDS,
    build_experiment_source,
    create_blank_review_template,
    prepare,
    select_representative_sample,
)


class Experiment2APreparationTests(unittest.TestCase):
    def test_local_source_records_reply_context_without_inventing_parent_text(self):
        source = build_experiment_source()
        self.assertEqual(len(source), 2000)
        self.assertEqual(source["comment_id"].nunique(), 2000)
        self.assertEqual(
            source["parent_context_status"].value_counts().to_dict(),
            {
                "not_a_reply": 1633,
                "available_from_local_pilot": 123,
                "missing_parent_context": 244,
            },
        )
        missing = source["parent_context_status"].eq("missing_parent_context")
        self.assertTrue(source.loc[missing, "parent_comment_text"].eq("").all())

    def test_representative_sampling_is_reproducible_and_channel_balanced(self):
        source = build_experiment_source()
        first, first_manifest = select_representative_sample(source, seed=EXPERIMENT_2A_SEED)
        second, second_manifest = select_representative_sample(source, seed=EXPERIMENT_2A_SEED)
        self.assertEqual(first["comment_id"].tolist(), second["comment_id"].tolist())
        pd.testing.assert_frame_equal(first_manifest, second_manifest)
        self.assertEqual(len(first), 500)
        self.assertEqual(first["comment_id"].nunique(), 500)
        self.assertEqual(first["channel_name"].value_counts().to_dict(), {
            "Ada Derana": 100,
            "Ada Derana Sports": 100,
            "Dream Star": 100,
            "FM Derana": 100,
            "TV Derana": 100,
        })
        self.assertTrue(first_manifest["selection_probability"].eq(0.25).all())
        self.assertTrue(first_manifest["sampling_weight"].eq(4.0).all())

    def test_blank_template_keeps_context_and_human_fields_empty(self):
        source = pd.DataFrame(
            [{
                "comment_id": "comment-1",
                "channel_id": "channel-1",
                "channel_name": "Ada Derana",
                "video_id": "video-1",
                "video_title": "Title",
                "video_description": "Description",
                "video_url": "https://www.youtube.com/watch?v=video-1",
                "parent_comment_id": "",
                "parent_comment_text": "",
                "parent_context_status": "not_a_reply",
                "video_context_status": "complete",
                "published_at": "2026-01-01T00:00:00Z",
                "is_reply": False,
                "original_text": "Sinhala \u0dc3\u0dd2\u0d82\u0dc4\u0dbd comment",
                "cleaned_text": "Sinhala \u0dc3\u0dd2\u0d82\u0dc4\u0dbd comment",
                "script_category": "mixed_sinhala_latin",
                "preprocessing_flags": "",
                "sampling_stratum": "mixed_sinhala_latin",
            }]
        )
        template = create_blank_review_template(source)
        self.assertEqual(template.loc[0, "original_text"], "Sinhala \u0dc3\u0dd2\u0d82\u0dc4\u0dbd comment")
        self.assertTrue(template[REVIEW_ANNOTATION_FIELDS].eq("").all().all())
        self.assertTrue(set(PRIMARY_SIGNALS).issuperset({"UNCLEAR", "ORDINARY_REACTION"}))
        self.assertEqual(ACTIONABILITY_LABELS, ("YES", "NO", "UNCLEAR"))

    def test_preparation_outputs_have_no_overlap_and_blank_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            result = prepare(output_dir=Path(directory))
            output = Path(directory)
            representative = pd.read_csv(output / "representative_evaluation_500.csv")
            enriched = pd.read_csv(output / "demand_enriched_candidates.csv")
            self.assertEqual(result["validation"]["representative_rows"], 500)
            self.assertEqual(representative["comment_id"].nunique(), 500)
            self.assertTrue(set(representative["comment_id"]).isdisjoint(enriched["comment_id"]))
            self.assertTrue(set(representative["video_id"]).isdisjoint(enriched["video_id"]))
            self.assertTrue(representative[REVIEW_ANNOTATION_FIELDS].fillna("").eq("").all().all())
            self.assertTrue(enriched[REVIEW_ANNOTATION_FIELDS].fillna("").eq("").all().all())


if __name__ == "__main__":
    unittest.main()
