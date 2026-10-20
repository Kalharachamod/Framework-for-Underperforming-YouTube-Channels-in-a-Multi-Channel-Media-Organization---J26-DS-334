"""Synthetic fixtures only. No sockets, real credentials or database connections."""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("c1_statistics", ROOT / "research/component_1/statistics_runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
FIXTURES = Path(__file__).with_name("fixtures")
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.manifest = runner.load_manifest(FIXTURES / "c1_cohort.json")
        self.fixture = json.loads((FIXTURES / "c1_statistics.json").read_text())

    def execute(self):
        # Unexpected network or database access must fail even if a regression adds it.
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), patch("psycopg.connect", side_effect=AssertionError("database forbidden")) as connect, patch("shared.database.repository.upsert_channels") as write_channels, patch("shared.database.repository.upsert_videos") as write_videos:
            client = runner.fixture_client(self.fixture)
            result = runner.run(self.manifest, client, self.state, self.fixture["seed"], clock=lambda: NOW)
            connect.assert_not_called()
            write_channels.assert_not_called()
            write_videos.assert_not_called()
        return result, client

    def inventory(self):
        return json.loads(sorted(self.state.glob("inventory_*.json"))[-1].read_text())

    def test_paginated_discovery_deduplicates_and_refreshes_old_inventory(self):
        result, client = self.execute()
        self.assertTrue(result["complete"])
        self.assertEqual(result["inventory_size"], 2)
        self.assertEqual(result["requested_videos"], 2)
        self.assertEqual(sum(r.resource == "playlistItems" for r in client.request_log), 2)
        ids = {v["video_id"] for v in self.inventory()["videos"]}
        self.assertEqual(ids, {"old00000001", "new00000001"})

    def test_more_than_fifty_stable_videos_are_refreshed(self):
        cid = self.manifest["channels"][0]["channel_id"]
        base = self.fixture["videos"][0]
        self.fixture["seed"] = [{"video_id": f"v{i:010d}", "channel_id": cid} for i in range(61)]
        self.fixture["videos"] = [dict(copy.deepcopy(base), id=r["video_id"]) for r in self.fixture["seed"]]
        self.fixture["playlists"] = {key: [[]] for key in self.fixture["playlists"]}
        result, client = self.execute()
        self.assertTrue(result["complete"])
        self.assertEqual(result["requested_videos"], 61)
        self.assertEqual(sum(r.resource == "videos" for r in client.request_log), 2)

    def test_unavailable_video_is_retained_and_missing_metrics_are_null(self):
        self.fixture["videos"] = self.fixture["videos"][1:]
        result, _ = self.execute()
        self.assertFalse(result["complete"])
        self.assertIn("old00000001", {v["video_id"] for v in self.inventory()["videos"]})
        for path in self.state.glob("run_*/batch_*.json"):
            batch = runner.replay_batch(path, self.manifest)
            if batch["dataset"] == "videos":
                self.assertIsNone(batch["records"][0]["like_count"])
                self.assertIsNone(batch["records"][0]["comment_count"])

    def test_wrong_channel_is_not_admitted(self):
        self.fixture["videos"][1]["snippet"]["channelId"] = "UC" + "b" * 22
        result, _ = self.execute()
        self.assertFalse(result["complete"])
        self.assertEqual({v["video_id"] for v in self.inventory()["videos"]}, {"old00000001"})

    def test_replay_preserves_timestamp_and_bytes_and_rejects_tampering(self):
        self.execute()
        path = next(self.state.glob("run_*/batch_*.json"))
        before = path.read_bytes()
        batch = runner.replay_batch(path, self.manifest)
        self.assertEqual(batch["records"][0]["collected_at"], "2026-10-16T12:00:00Z")
        self.assertEqual(path.read_bytes(), before)
        batch["records"][0]["collected_at"] = "2026-10-17T12:00:00Z"
        path.write_text(json.dumps(batch))
        with self.assertRaises(ValueError):
            runner.replay_batch(path, self.manifest)

    def test_inventory_version_and_manifest_binding(self):
        self.execute()
        self.fixture["playlists"] = {key: [[]] for key in self.fixture["playlists"]}
        self.execute()
        self.assertEqual(self.inventory()["revision"], 2)
        self.assertEqual(len(self.inventory()["videos"]), 2)
        self.manifest["version"] = "changed"
        with self.assertRaises(ValueError):
            self.execute()

    def test_failed_video_request_keeps_seed_and_reports_incomplete(self):
        client = runner.fixture_client(self.fixture)
        with patch.object(client, "videos_list", side_effect=RuntimeError("secret must not be logged")):
            result = runner.run(self.manifest, client, self.state, self.fixture["seed"], clock=lambda: NOW)
        self.assertFalse(result["complete"])
        self.assertEqual(len(self.inventory()["videos"]), 1)
        self.assertNotIn("secret must not be logged", json.dumps(result))

    def test_unaware_clock_and_foreign_seed_are_rejected(self):
        client = runner.fixture_client(self.fixture)
        with self.assertRaises(ValueError):
            runner.run(self.manifest, client, self.state, clock=lambda: datetime(2026, 1, 1))
        bad = [{"video_id": "old00000001", "channel_id": "UC" + "b" * 22}]
        with self.assertRaises(ValueError):
            runner.run(self.manifest, client, self.state, bad, clock=lambda: NOW)

    def test_write_mode_rejected_before_client_or_files(self):
        with self.assertRaises(ValueError):
            runner.run(self.manifest, None, self.state / "untouched", dry_run=False)
        self.assertFalse((self.state / "untouched").exists())

    def test_repeated_page_token_reports_failure_but_refreshes_inventory(self):
        client = runner.fixture_client(self.fixture)
        original = client.playlist_items_list
        def repeated(**kwargs):
            response = original(playlist_id=kwargs["playlist_id"], max_results=50, page_token=None)
            from dataclasses import replace
            return replace(response, next_page_token="1")
        client.playlist_items_list = repeated
        result = runner.run(self.manifest, client, self.state, self.fixture["seed"], clock=lambda: NOW)
        self.assertFalse(result["complete"])
        self.assertTrue(any(f["stage"] == "discovery_incomplete" for f in result["failures"]))
        self.assertEqual(result["inventory_size"], 2)


if __name__ == "__main__":
    unittest.main()
