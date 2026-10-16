from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shared.data_collection.comment_collector import CommentCollector
from shared.data_collection.config import (
    ChannelConfig,
    filter_comment_channels,
    load_channel_registry,
)
from shared.data_collection.youtube_client import YouTubeApiError


class FakeYouTubeClient:
    def __init__(self) -> None:
        self.request_count = 0
        self.comment_pages_served = 0

    def channels_list(self, **_params):
        self.request_count += 1
        return {
            "items": [
                {
                    "contentDetails": {
                        "relatedPlaylists": {"uploads": "UPLOADS_1"}
                    }
                }
            ]
        }

    def playlist_items_list(self, **params):
        self.request_count += 1
        token = params.get("pageToken")
        if token == "next":
            return {
                "items": [
                    {"contentDetails": {"videoId": "video-2"}},
                ]
            }
        return {
            "items": [
                {"contentDetails": {"videoId": "video-1"}},
            ],
            "nextPageToken": "next",
        }

    def comment_threads_list(self, **params):
        self.request_count += 1
        self.comment_pages_served += 1
        video_id = params["videoId"]
        if video_id == "quota-video":
            raise YouTubeApiError(
                "quota exhausted", reason="quotaExceeded", quota_exhausted=True
            )
        return {
            "items": [
                {
                    "id": f"thread-{video_id}",
                    "snippet": {
                        "totalReplyCount": 0,
                        "topLevelComment": {
                            "id": f"comment-{video_id}",
                            "snippet": {
                                "textDisplay": "සිංහල English Tanglish comment",
                                "publishedAt": "2026-01-01T00:00:00Z",
                                "updatedAt": "2026-01-01T00:00:00Z",
                                "likeCount": 3,
                            },
                        },
                    },
                }
            ]
        }

    def comments_list(self, **_params):
        self.request_count += 1
        return {"items": []}


class QuotaClient(FakeYouTubeClient):
    def playlist_items_list(self, **_params):
        self.request_count += 1
        return {"items": [{"contentDetails": {"videoId": "quota-video"}}]}


def channel() -> ChannelConfig:
    return ChannelConfig(
        channel_name="Test Channel",
        channel_id="UC_TEST",
        is_active=True,
        collect_comments=True,
        max_videos_initial=2,
        max_comments_per_video=10,
        snapshot_recent_days=90,
    )


class CommentCollectionTests(unittest.TestCase):
    def test_loads_registry_and_filters_comment_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.csv"
            path.write_text(
                "channel_name,channel_id,is_active,collect_comments,max_videos_initial,max_comments_per_video,snapshot_recent_days\n"
                "A,UC_A,true,true,5,10,90\n"
                "B,UC_B,false,true,5,10,90\n",
                encoding="utf-8",
            )
            channels = filter_comment_channels(load_channel_registry(path))
            self.assertEqual(len(channels), 1)
            self.assertEqual(channels[0].channel_id, "UC_A")

    def test_pagination_and_utf8_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector = CommentCollector(FakeYouTubeClient(), output_dir=tmp)
            stats = collector.collect([channel()], run_id="test")
            output = Path(tmp) / "test" / "comments.jsonl"
            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(stats.videos_seen, 2)
            self.assertEqual(stats.comments_written, 2)
            self.assertIn("සිංහල", records[0]["text"])

    def test_resume_prevents_duplicate_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector = CommentCollector(FakeYouTubeClient(), output_dir=tmp)
            first = collector.collect([channel()], run_id="resume")
            second = collector.collect([channel()], run_id="resume", resume=True)
            output = Path(tmp) / "resume" / "comments.jsonl"
            self.assertEqual(first.comments_written, 2)
            self.assertEqual(second.comments_written, 0)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 2)

    def test_quota_handling_writes_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector = CommentCollector(QuotaClient(), output_dir=tmp)
            stats = collector.collect([channel()], run_id="quota")
            stats_path = Path(tmp) / "quota" / "run_stats.json"
            self.assertTrue(stats.quota_exhausted)
            self.assertTrue(stats_path.exists())

    def test_dry_run_creates_checkpoint_without_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector = CommentCollector(FakeYouTubeClient(), output_dir=tmp, dry_run=True)
            stats = collector.collect([channel()], run_id="dry", max_videos=1)
            self.assertEqual(stats.comments_written, 0)
            self.assertTrue((Path(tmp) / "dry" / "checkpoint.json").exists())
            self.assertFalse((Path(tmp) / "dry" / "comments.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
