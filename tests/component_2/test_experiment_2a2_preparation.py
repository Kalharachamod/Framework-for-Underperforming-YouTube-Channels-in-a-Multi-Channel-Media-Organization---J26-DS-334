from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.component_2.feasibility_experiment.config import DEFAULT_PILOT_COMMENTS
from research.component_2.feasibility_experiment.prepare_experiment_2a import (
    REVIEW_ANNOTATION_FIELDS,
    build_experiment_source,
)
from research.component_2.feasibility_experiment.prepare_experiment_2a2 import (
    EXPERIMENT_2A2_SEED,
    attach_video_partitions,
    create_video_partition_manifest,
    load_calibration_frame,
    prepare,
)
from research.component_2.feasibility_experiment.partition_guard import (
    PartitionGuard,
)


class Experiment2A2PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = build_experiment_source()
        cls.calibration = load_calibration_frame()
        cls.video_manifest = create_video_partition_manifest(
            cls.source, cls.calibration, seed=EXPERIMENT_2A2_SEED
        )
        cls.partitioned = attach_video_partitions(cls.source, cls.video_manifest)

    def test_actual_partition_counts_match_the_frozen_inputs(self):
        self.assertEqual(len(self.source), 2000)
        self.assertEqual(self.source["video_id"].nunique(), 255)
        self.assertEqual(
            self.video_manifest["dataset_role"].value_counts().to_dict(),
            {
                "development_pool": 175,
                "held_out_evaluation": 43,
                "calibration_only": 37,
            },
        )
        self.assertEqual(
            self.partitioned["dataset_role"].value_counts().to_dict(),
            {
                "development_pool": 1293,
                "calibration_only": 396,
                "held_out_evaluation": 311,
            },
        )
        self.assertEqual(
            set(self.partitioned["comment_id"].astype(str)),
            set(self.source["comment_id"].astype(str)),
        )
        self.assertEqual(
            set(self.partitioned["video_id"].astype(str)),
            set(self.video_manifest["video_id"].astype(str)),
        )

    def test_calibration_videos_are_excluded_from_all_new_model_partitions(self):
        calibration_videos = set(
            self.video_manifest.loc[
                self.video_manifest["dataset_role"].eq("calibration_only"), "video_id"
            ]
        )
        held_out_videos = set(
            self.video_manifest.loc[
                self.video_manifest["dataset_role"].eq("held_out_evaluation"), "video_id"
            ]
        )
        development_videos = set(
            self.video_manifest.loc[
                self.video_manifest["dataset_role"].eq("development_pool"), "video_id"
            ]
        )
        self.assertTrue(calibration_videos.isdisjoint(held_out_videos))
        self.assertTrue(calibration_videos.isdisjoint(development_videos))
        self.assertTrue(held_out_videos.isdisjoint(development_videos))
        self.assertEqual(
            self.partitioned.groupby("video_id")["dataset_role"].nunique().max(), 1
        )

    def test_split_is_reproducible_and_independent_of_comment_order(self):
        shuffled = self.source.sample(frac=1, random_state=91).reset_index(drop=True)
        repeated = create_video_partition_manifest(
            shuffled, self.calibration, seed=EXPERIMENT_2A2_SEED
        )
        columns = [
            "video_id",
            "temporal_stratum",
            "dataset_role",
            "video_selection_probability",
        ]
        first = self.video_manifest[columns].sort_values("video_id").reset_index(drop=True)
        second = repeated[columns].sort_values("video_id").reset_index(drop=True)
        pd.testing.assert_frame_equal(first, second)

    def test_split_does_not_use_comment_text_or_script_features(self):
        altered = self.source.copy()
        altered["original_text"] = "replacement"
        altered["cleaned_text"] = "replacement"
        altered["script_category"] = "other_or_symbolic"
        repeated = create_video_partition_manifest(
            altered, self.calibration, seed=EXPERIMENT_2A2_SEED
        )
        first_roles = self.video_manifest.set_index("video_id")["dataset_role"].sort_index()
        second_roles = repeated.set_index("video_id")["dataset_role"].sort_index()
        pd.testing.assert_series_equal(first_roles, second_roles)

    def test_held_out_selection_uses_valid_recorded_probabilities(self):
        eligible = self.video_manifest[
            ~self.video_manifest["dataset_role"].eq("calibration_only")
        ]
        expected = eligible["selected_video_count"] / eligible["stratum_video_count"]
        pd.testing.assert_series_equal(
            eligible["video_selection_probability"].reset_index(drop=True),
            expected.astype(float).reset_index(drop=True),
            check_names=False,
        )
        self.assertTrue(eligible["video_selection_probability"].between(0, 1).all())
        self.assertTrue(
            self.video_manifest.loc[
                self.video_manifest["dataset_role"].eq("calibration_only"),
                "video_selection_probability",
            ].eq(0).all()
        )

    def test_full_preparation_is_blinded_balanced_and_unicode_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            result = prepare(output_dir=Path(directory))
            output = Path(directory)
            held_out = pd.read_csv(output / "held_out_evaluation_comments.csv")
            development = pd.read_csv(output / "development_candidate_control_review.csv")
            selection = pd.read_csv(output / "development_selection_manifest.csv")
            crosswalk = pd.read_csv(output / "exploratory_500_crosswalk.csv")

            self.assertEqual(result["summary"]["comment_role_counts"]["held_out_evaluation"], 311)
            self.assertEqual(len(held_out), 311)
            self.assertEqual(len(development), 94)
            self.assertEqual(
                selection["selection_group"].value_counts().to_dict(),
                {"demand_enriched_candidate": 47, "matched_control": 47},
            )
            self.assertEqual(
                selection.loc[
                    selection["selection_group"].eq("matched_control"),
                    "control_match_level",
                ].value_counts().to_dict(),
                {"channel_script_time": 47},
            )
            self.assertTrue(
                held_out[REVIEW_ANNOTATION_FIELDS].fillna("").eq("").all().all()
            )
            self.assertTrue(
                development[REVIEW_ANNOTATION_FIELDS].fillna("").eq("").all().all()
            )
            self.assertNotIn("selection_group", development.columns)
            self.assertNotIn("baseline_primary_signal", development.columns)
            self.assertEqual(len(crosswalk), 500)
            self.assertEqual(int(crosswalk["exact_calibration_comment_overlap"].sum()), 10)
            self.assertEqual(
                crosswalk["corrected_video_role"].value_counts().to_dict(),
                {
                    "development_pool": 314,
                    "calibration_only": 100,
                    "held_out_evaluation": 86,
                },
            )
            self.assertTrue(
                held_out["raw_comment_text"].fillna("").str.contains("[\u0d80-\u0dff]", regex=True).any()
            )
            source_text = self.source.set_index("comment_id")["raw_comment_text"]
            expected_raw = held_out["comment_id"].map(source_text)
            self.assertTrue(held_out["raw_comment_text"].eq(expected_raw).all())
            raw_source = pd.read_csv(
                DEFAULT_PILOT_COMMENTS,
                usecols=["comment_id", "comment_text"],
                dtype={"comment_id": "string", "comment_text": "string"},
                keep_default_na=False,
            ).set_index("comment_id")["comment_text"]
            exact_source_text = held_out["comment_id"].map(raw_source)
            self.assertTrue(held_out["raw_comment_text"].eq(exact_source_text).all())
            self.assertEqual(
                int(held_out["raw_comment_text"].ne(held_out["normalized_text"]).sum()),
                5,
            )
            guard = PartitionGuard.load(output / "comment_partition_manifest.csv")
            self.assertEqual(
                result["summary"]["partition_manifest_fingerprint"],
                guard.fingerprint,
            )


if __name__ == "__main__":
    unittest.main()
