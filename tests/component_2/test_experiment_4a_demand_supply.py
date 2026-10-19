from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon

from research.component_2.feasibility_experiment.experiment_4a_demand_supply import (
    assign_to_centroids,
    center_by_group,
    jsd_components,
    prior_shift,
    window_table,
)


class JensenShannonTests(unittest.TestCase):
    def test_matches_scipy_squared_distance_and_contributions_sum(self):
        p = np.array([50.0, 30.0, 20.0])
        q = np.array([10.0, 70.0, 20.0])
        value, contributions = jsd_components(p, q)
        self.assertAlmostEqual(value, jensenshannon(p / p.sum(), q / q.sum(), base=2) ** 2, places=10)
        self.assertAlmostEqual(contributions.sum(), value, places=12)

    def test_identical_disjoint_and_zero_topics(self):
        self.assertAlmostEqual(jsd_components(np.array([1, 2, 0]), np.array([2, 4, 0]))[0], 0.0)
        self.assertAlmostEqual(jsd_components(np.array([1, 0]), np.array([0, 1]))[0], 1.0)

    def test_rejects_invalid_input(self):
        for p, q in (([0, 0], [1, 1]), ([1, -1], [1, 1]), ([1, 2], [1])):
            with self.assertRaises(ValueError):
                jsd_components(np.array(p, float), np.array(q, float))


class AlignmentTests(unittest.TestCase):
    def test_videos_go_to_nearest_comment_topic_centroid(self):
        comment_emb = np.array([[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], float)
        comment_emb /= np.linalg.norm(comment_emb, axis=1, keepdims=True)
        topics = np.array([0, 0, 1, 1])
        video_emb = np.array([[0.95, 0.05], [0.05, 0.95]])
        assigned, similarity, labels = assign_to_centroids(topics, comment_emb, video_emb)
        self.assertEqual(assigned.tolist(), [0, 1])
        self.assertEqual(labels, [0, 1])
        self.assertTrue((similarity > 0.9).all())

    def test_window_counts_requests_unique_requesters_and_gap(self):
        comments = pd.DataFrame(
            {
                "published_at": ["2025-05-01T00:00:00Z"] * 4 + ["2026-05-01T00:00:00Z"],
                "topic": [0, 0, 0, 1, 1],
                "is_request": [True, True, False, False, True],
                "p_request_adj": [0.9, 0.8, 0.1, 0.2, 0.7],
                "author_hash": ["a", "a", "b", "c", "d"],
            }
        )
        videos = pd.DataFrame({"published_at": ["2025-05-02T00:00:00Z", "2025-06-01T00:00:00Z"], "topic": [1, 1]})
        table, stats = window_table(comments, videos, [0, 1], "2025-04-01", "2026-02-01")
        row = table.set_index("topic")
        self.assertEqual(row.loc[0, "flagged_requests"], 2)
        self.assertAlmostEqual(row.loc[0, "expected_requests"], 1.8)
        self.assertEqual(row.loc[0, "unique_requesters"], 1)
        self.assertAlmostEqual(row.loc[0, "signed_gap"], 0.75)
        self.assertEqual(stats["meaningful_comments"], 4)
        self.assertGreater(stats["jsd_interest_vs_supply"], 0.5)


class CorrectionTests(unittest.TestCase):
    def test_prior_shift_lowers_balanced_probabilities_to_natural_rate(self):
        self.assertAlmostEqual(float(prior_shift(np.array([0.5]), 0.1)[0]), 0.1)
        adjusted = prior_shift(np.array([0.2, 0.5, 0.9]), 0.1)
        self.assertTrue(np.all(np.diff(adjusted) > 0))
        self.assertTrue(np.all(adjusted < np.array([0.2, 0.5, 0.9])))

    def test_center_by_group_removes_each_group_mean(self):
        rng = np.random.default_rng(0)
        emb = np.vstack([rng.normal(5, 1, (20, 4)), rng.normal(-5, 1, (20, 4))])
        groups = np.array(["sinhala"] * 20 + ["latin"] * 20)
        centred = center_by_group(emb, groups)
        self.assertTrue(np.allclose(np.linalg.norm(centred, axis=1), 1.0))
        gap = np.linalg.norm(centred[:20].mean(axis=0) - centred[20:].mean(axis=0))
        self.assertLess(gap, 0.5)


if __name__ == "__main__":
    unittest.main()
