from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.component_2.feasibility_experiment.annotation_schema import (
    REVIEW_ANNOTATION_FIELDS,
)
from research.component_2.feasibility_experiment.partition_guard import (
    DEFAULT_PARTITION_MANIFEST,
    PartitionGuard,
)
from research.component_2.feasibility_experiment.prepare_experiment_2a2 import (
    DEFAULT_CALIBRATION,
)
from research.component_2.feasibility_experiment.prepare_experiment_2b import (
    DEFAULT_EXISTING_REVIEW,
    REPRESENTATIONS,
    aggregate_retrievals,
    build_tfidf_representations,
    prepare,
    representation_comparison,
)


class Experiment2BRepresentationTests(unittest.TestCase):
    def setUp(self):
        self.corpus = pd.Series(
            [
                "please upload the full video",
                "full episode eka ko",
                "මේ ගැන තව වීඩියෝ එකක් කරන්න",
                "I love this full episode",
                "meka gena thawath video ekak danna",
            ]
        )
        self.queries = pd.Series(
            ["upload full episode", "තව වීඩියෝ එකක් කරන්න"]
        )

    def test_word_character_and_combined_representations_are_nonempty(self):
        corpus, queries, summaries = build_tfidf_representations(
            self.corpus, self.queries
        )
        self.assertEqual(set(corpus), set(REPRESENTATIONS))
        self.assertEqual(set(queries), set(REPRESENTATIONS))
        for name in REPRESENTATIONS:
            self.assertEqual(corpus[name].shape[0], 5)
            self.assertEqual(queries[name].shape[0], 2)
            self.assertGreater(corpus[name].shape[1], 0)
            self.assertGreater(summaries[name]["nonzero_values"], 0)

    def test_retrieval_comparison_uses_set_overlap_not_labels(self):
        retrievals = pd.DataFrame(
            [
                {"representation": "word", "comment_id": "a"},
                {"representation": "word", "comment_id": "b"},
                {"representation": "character", "comment_id": "b"},
                {"representation": "character", "comment_id": "c"},
                {"representation": "combined", "comment_id": "a"},
                {"representation": "combined", "comment_id": "c"},
            ]
        )
        result = representation_comparison(retrievals)
        self.assertEqual(
            result["unique_retrieved_by_representation"],
            {"word": 2, "character": 2, "combined": 2},
        )
        self.assertAlmostEqual(
            result["pairwise_top_k_overlap"]["word_vs_character"]["jaccard"],
            1 / 3,
        )

    def test_aggregation_preserves_method_and_baseline_provenance(self):
        retrievals = pd.DataFrame(
            [
                {
                    "representation": "word",
                    "seed_comment_id": "seed-1",
                    "neighbor_rank": 2,
                    "comment_id": "dev-1",
                    "video_id": "video-1",
                    "channel_name": "Channel",
                    "script_category": "latin_script",
                    "cosine_similarity": 0.5,
                    "baseline_candidate_for_content_demand": False,
                    "baseline_primary_signal": "ORDINARY_REACTION",
                    "in_existing_2a2_review_queue": False,
                },
                {
                    "representation": "character",
                    "seed_comment_id": "seed-2",
                    "neighbor_rank": 1,
                    "comment_id": "dev-1",
                    "video_id": "video-1",
                    "channel_name": "Channel",
                    "script_category": "latin_script",
                    "cosine_similarity": 0.7,
                    "baseline_candidate_for_content_demand": False,
                    "baseline_primary_signal": "ORDINARY_REACTION",
                    "in_existing_2a2_review_queue": False,
                },
            ]
        )
        result = aggregate_retrievals(retrievals)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "representations"], "character;word")
        self.assertEqual(result.loc[0, "representation_count"], 2)
        self.assertEqual(result.loc[0, "matched_seed_count"], 2)
        self.assertAlmostEqual(result.loc[0, "best_cosine_similarity"], 0.7)


@unittest.skipUnless(
    DEFAULT_PARTITION_MANIFEST.exists()
    and DEFAULT_CALIBRATION.exists()
    and DEFAULT_EXISTING_REVIEW.exists(),
    "Private local Experiment 2A.2 artifacts are unavailable",
)
class Experiment2BLocalIntegrationTests(unittest.TestCase):
    def test_actual_preparation_is_development_only_blinded_and_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            first = prepare(output_dir=Path(directory) / "first")
            second = prepare(output_dir=Path(directory) / "second")
            first_queue = pd.read_csv(first["review_path"], keep_default_na=False)
            second_queue = pd.read_csv(second["review_path"], keep_default_na=False)
            neighbors = pd.read_csv(
                Path(directory) / "first" / "tfidf_retrieval_neighbors.csv"
            )
            pd.testing.assert_frame_equal(first_queue, second_queue)

            summary = first["summary"]
            self.assertEqual(summary["development_comments"], 1293)
            self.assertEqual(summary["development_videos"], 175)
            self.assertEqual(summary["query_seed_count"], 6)
            self.assertGreater(summary["retrieval_pairs"], 0)
            self.assertLessEqual(summary["retrieval_pairs"], 180)
            self.assertTrue(neighbors["cosine_similarity"].gt(0).all())
            self.assertEqual(summary["review_queue_rows"], 60)
            self.assertEqual(first_queue["comment_id"].nunique(), 60)
            self.assertEqual(set(first_queue["channel_name"].unique()), {
                "Ada Derana",
                "Ada Derana Sports",
                "Dream Star",
                "FM Derana",
                "TV Derana",
            })

            guard = PartitionGuard.load()
            guard.validate_training_frame(first_queue[["comment_id", "video_id"]])
            existing = pd.read_csv(DEFAULT_EXISTING_REVIEW, dtype={"comment_id": "string"})
            self.assertTrue(
                set(first_queue["comment_id"].astype(str)).isdisjoint(
                    set(existing["comment_id"].astype(str))
                )
            )
            self.assertTrue(
                first_queue[REVIEW_ANNOTATION_FIELDS]
                .fillna("")
                .eq("")
                .all()
                .all()
            )
            forbidden = {
                "representation",
                "cosine_similarity",
                "baseline_candidate_for_content_demand",
                "selection_reason",
            }
            self.assertTrue(forbidden.isdisjoint(first_queue.columns))
            self.assertTrue(
                first_queue["raw_comment_text"]
                .str.contains("[\u0d80-\u0dff]", regex=True)
                .any()
            )


if __name__ == "__main__":
    unittest.main()
