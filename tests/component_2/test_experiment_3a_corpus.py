from __future__ import annotations

import unittest

import pandas as pd

from research.component_2.feasibility_experiment.build_expanded_corpus import (
    CALIBRATION_QUARANTINE,
    EXPANDED_DEVELOPMENT,
    EXPANDED_HELDOUT,
    HELDOUT_QUARANTINE,
    ExpandedCorpusGuard,
    assign_v2_roles,
    manifest_fingerprint,
    merge_comments,
    role_counts,
)
from research.component_2.feasibility_experiment.partition_guard import PartitionIntegrityError


def _comment(comment_id, video_id, text="text", source="expansion_20261019", channel="Dream Star"):
    return {
        "comment_id": comment_id,
        "video_id": video_id,
        "channel_id": "ch",
        "channel_name": channel,
        "parent_comment_id": None,
        "is_reply": False,
        "published_at": "2026-01-01T00:00:00Z",
        "like_count": 0,
        "author_hash": "anon_x" if source != "pilot_v1" else pd.NA,
        "source": source,
        "raw_comment_text": text,
    }


class Experiment3ACorpusTests(unittest.TestCase):
    def setUp(self):
        self.v1 = pd.DataFrame(
            [
                {"comment_id": "dev-1", "video_id": "v-dev", "dataset_role": "development_pool"},
                {"comment_id": "held-1", "video_id": "v-held", "dataset_role": "held_out_evaluation"},
                {"comment_id": "cal-1", "video_id": "v-cal", "dataset_role": "calibration_only"},
            ]
        )
        pilot = pd.DataFrame(
            [_comment(r.comment_id, r.video_id, "pilot text", "pilot_v1") for r in self.v1.itertuples()]
        )
        new_rows = [
            _comment("dev-1", "v-dev", "re-collected text"),
            _comment("new-on-held", "v-held"),
            _comment("new-on-cal", "v-cal"),
            _comment("new-on-dev", "v-dev"),
        ]
        new_rows += [_comment(f"n{i}-{j}", f"v-new-{i}") for i in range(20) for j in range(2)]
        self.comments = merge_comments(pilot, pd.DataFrame(new_rows))
        self.videos = pd.DataFrame(
            {
                "video_id": [f"v-new-{i}" for i in range(20)],
                "channel_name": "Dream Star",
                "published_at": "2026-01-15T00:00:00Z",
            }
        )

    def test_merge_keeps_pilot_text_and_dedupes(self):
        self.assertFalse(self.comments["comment_id"].duplicated().any())
        row = self.comments.set_index("comment_id").loc["dev-1"]
        self.assertEqual(row["raw_comment_text"], "pilot text")
        self.assertEqual(row["author_hash"], "anon_x")
        self.assertTrue(row["also_in_expansion"])

    def test_routing_quarantines_protected_videos_and_keeps_v1(self):
        roles, _ = assign_v2_roles(self.comments, self.v1, self.videos, seed=1)
        role = roles.set_index("comment_id")["dataset_role"]
        self.assertEqual(role["dev-1"], "development_pool")
        self.assertEqual(role["held-1"], "held_out_evaluation")
        self.assertEqual(role["cal-1"], "calibration_only")
        self.assertEqual(role["new-on-held"], HELDOUT_QUARANTINE)
        self.assertEqual(role["new-on-cal"], CALIBRATION_QUARANTINE)
        self.assertEqual(role["new-on-dev"], EXPANDED_DEVELOPMENT)

    def test_expanded_heldout_is_video_grouped_and_reproducible(self):
        roles_a, selection = assign_v2_roles(self.comments, self.v1, self.videos, seed=7)
        roles_b, _ = assign_v2_roles(self.comments, self.v1, self.videos, seed=7)
        pd.testing.assert_frame_equal(roles_a, roles_b)
        held = roles_a[roles_a["dataset_role"].eq(EXPANDED_HELDOUT)]
        self.assertEqual(held["video_id"].nunique(), 3)  # round(20 * 0.15)
        per_video = roles_a[roles_a["video_id"].str.startswith("v-new")].groupby("video_id")["dataset_role"].nunique()
        self.assertTrue(per_video.eq(1).all())
        self.assertEqual(int(selection["selected_heldout"].sum()), 3)

    def test_guard_rejects_protected_roles(self):
        roles, _ = assign_v2_roles(self.comments, self.v1, self.videos, seed=1)
        comments, videos = role_counts(roles)
        lock = {
            "lock_version": "component2.experiment-3a.corpus-lock.v2",
            "manifest_fingerprint": manifest_fingerprint(roles),
            "comment_role_counts": comments,
            "video_role_counts": videos,
        }
        guard = ExpandedCorpusGuard(roles, lock)
        guard.validate_training_frame(pd.DataFrame({"comment_id": ["dev-1", "new-on-dev"]}))
        for protected in ("held-1", "cal-1", "new-on-held", "new-on-cal"):
            with self.assertRaises(PartitionIntegrityError):
                guard.validate_training_frame(pd.DataFrame({"comment_id": [protected]}))
        heldout_id = roles.loc[roles["dataset_role"].eq(EXPANDED_HELDOUT), "comment_id"].iloc[0]
        with self.assertRaises(PartitionIntegrityError):
            guard.validate_training_frame(pd.DataFrame({"comment_id": [heldout_id]}))

    def test_guard_rejects_tampered_manifest(self):
        roles, _ = assign_v2_roles(self.comments, self.v1, self.videos, seed=1)
        comments, videos = role_counts(roles)
        lock = {
            "manifest_fingerprint": manifest_fingerprint(roles),
            "comment_role_counts": comments,
            "video_role_counts": videos,
        }
        tampered = roles.copy()
        tampered.loc[tampered["comment_id"].eq("new-on-held"), "dataset_role"] = EXPANDED_DEVELOPMENT
        with self.assertRaises(PartitionIntegrityError):
            ExpandedCorpusGuard(tampered, lock)

    def test_changed_v1_role_is_rejected(self):
        broken = self.comments.copy()
        v1 = self.v1.copy()
        roles, _ = assign_v2_roles(broken, v1, self.videos, seed=1)
        v1.loc[v1["comment_id"].eq("held-1"), "dataset_role"] = "development_pool"
        from research.component_2.feasibility_experiment.build_expanded_corpus import _check_v2_invariants

        with self.assertRaises(PartitionIntegrityError):
            _check_v2_invariants(roles, v1)


class PilotLoaderTests(unittest.TestCase):
    def test_literal_null_parent_is_a_top_level_comment(self):
        import tempfile
        from pathlib import Path

        from research.component_2.feasibility_experiment.build_expanded_corpus import load_pilot_comments

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            pd.DataFrame(
                {
                    "comment_id": ["a", "b"], "channel_id": ["c", "c"], "channel_name": ["Dream Star"] * 2,
                    "video_id": ["v", "v"], "comment_text": ["x", "y"], "published_at": ["2026-01-01"] * 2,
                    "edited_at": ["2026-01-01"] * 2, "like_count": ["0", "0"], "parent_comment_id": ["null", "a"],
                }
            ).to_csv(path, index=False)
            pilot = load_pilot_comments(path)
        self.assertEqual(pilot["is_reply"].tolist(), [False, True])
        self.assertTrue(pd.isna(pilot.loc[0, "parent_comment_id"]))


if __name__ == "__main__":
    unittest.main()
