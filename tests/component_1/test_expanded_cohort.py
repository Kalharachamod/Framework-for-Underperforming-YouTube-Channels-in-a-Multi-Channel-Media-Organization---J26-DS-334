import json
import unittest
from pathlib import Path

from research.component_1 import statistics_runner as runner


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config/cohorts/component_1_audited43_v0.2.0.proposed.json"
METADATA_PATH = ROOT / "research/component_1/results/cohort_channel_metadata.json"


class ExpandedCohortOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        cls.confirmed = set(cls.manifest["confirmed_derana_channel_ids"])

    def fixture(self):
        channels = []
        playlists = {}
        for item in self.manifest["channels"]:
            channel_id = item["channel_id"]
            channels.append({
                "id": channel_id,
                "snippet": {"title": item["channel_name"]},
                "statistics": {},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU" + channel_id[2:]}},
            })
            playlists["UU" + channel_id[2:]] = [[]]
        return {"channels": channels, "videos": [], "playlists": playlists}

    def test_scope_counts_and_disabled_state(self):
        self.assertEqual(len(self.manifest["channels"]), 43)
        self.assertEqual(len({x["channel_id"] for x in self.manifest["channels"]}), 43)
        self.assertEqual(sum(x["existing_videos"] for x in self.manifest["channels"]), 1497)
        self.assertEqual(sum(x["existing_videos"] for x in self.metadata["channels"]
                             if x["channel_id"] in self.confirmed), 1136)
        self.assertFalse(self.manifest["enabled"])
        self.assertEqual(self.manifest["activation"]["scheduling"], "disabled")
        self.assertIn("2026-10-19", self.manifest["activation"]["leader_approval"])
        self.assertIn("all 43 channels", self.manifest["activation"]["leader_approval"])
        self.assertIn("approver name", self.manifest["activation"]["leader_approval"])

    def test_budget_allocation_matches_expanded_edge_plan(self):
        plan = self.manifest["collection_plan"]
        self.assertEqual(plan["channel_metadata_requests_per_run"], 1)
        self.assertEqual(plan["refresh_batches_of_50"], 30)
        self.assertEqual(plan["discovery"]["minimum_initial_attempts"], 43)
        self.assertEqual(plan["discovery"]["global_attempt_budget"], 49)
        self.assertEqual(plan["discovery"]["retry_allowance"], 6)
        self.assertEqual(plan["candidate_attempt_reserve"], 20)
        self.assertEqual(1 + 30 + 49 + 20, plan["total_attempt_budget"])

    def test_fair_first_page_discovery_covers_all_channels(self):
        report = runner.run(self.manifest, runner.fixture_client(self.fixture()), None,
                            seed=(), max_pages=1, no_persist=True, discovery_budget=49)
        self.assertTrue(report["discovery"]["complete"])
        self.assertEqual(len(report["discovery"]["channels"]), 43)
        self.assertEqual(sum(x["pages_returned"] for x in report["discovery"]["channels"].values()), 43)

    def test_discovery_budget_is_enforced_without_claiming_completion(self):
        client = runner.fixture_client(self.fixture())
        calls = 0
        original = client.playlist_items_list

        def bounded_playlist_items_list(**kwargs):
            nonlocal calls
            if calls >= 42:
                raise runner.PhaseLimit("discovery budget exhausted")
            calls += 1
            return original(**kwargs)

        client.playlist_items_list = bounded_playlist_items_list
        report = runner.run(self.manifest, client, None,
                            seed=(), max_pages=1, no_persist=True, discovery_budget=42)
        self.assertFalse(report["discovery"]["complete"])
        self.assertEqual(calls, 42)
        self.assertTrue(report["discovery"]["incomplete_channels"])


if __name__ == "__main__":
    unittest.main()
