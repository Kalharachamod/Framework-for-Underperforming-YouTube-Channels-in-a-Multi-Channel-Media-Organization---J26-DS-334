"""Tests for data validation and quality checks (shared/utils/quality.py).

All records are TEST DATA: synthetic IDs, names and text invented for testing.
Invalid files are written deliberately (bypassing store_records) so the
validator can be tested against the problems it must detect.
"""

import json

import pandas as pd
import pytest

from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import latest_path, store_records, write_dataset
from shared.utils import quality as q
from shared.utils import snapshots as s
from shared.utils.datasets import snapshot_path

DAY = "2026-09-30"  # fixed past date: tests must not depend on the clock
AT = f"{DAY}T08:00:00Z"


# --- TEST DATA ------------------------------------------------------------------------

def channels():
    return [Channel(channel_id="test_ch_a", channel_name="Test A", subscriber_count=100, collected_at=AT),
            Channel(channel_id="test_ch_b", channel_name="Test B", subscriber_count=None, collected_at=AT)]


def videos():
    return [Video(video_id="test_v1", channel_id="test_ch_a", title="Test 1", published_at="2026-09-01T09:00:00Z",
                  view_count=100, like_count=10, comment_count=2, collected_at=AT),
            Video(video_id="test_v2", channel_id="test_ch_b", title="Test 2", published_at="2026-09-02T09:00:00Z",
                  view_count=50, like_count=None, comment_count=0, collected_at=AT)]


def comments():
    return [Comment(comment_id="test_c1", video_id="test_v1", channel_id="test_ch_a", author_channel_id="test_author_1",
                    comment_text="Synthetic.", published_at="2026-09-03T10:00:00Z", like_count=0, collected_at=AT),
            Comment(comment_id="test_c2", video_id="test_v2", channel_id="test_ch_b", author_channel_id=None,
                    comment_text="Synthetic.", published_at="2026-09-04T10:00:00Z", like_count=1, collected_at=AT)]


MODELS = {"channels": (Channel, channels), "videos": (Video, videos), "comments": (Comment, comments)}


@pytest.fixture
def good(isolated_data_dir):
    store_records("channels", channels())
    store_records("videos", videos())
    store_records("comments", comments())


def frame(dataset):
    model, make = MODELS[dataset]
    return to_dataframe(make(), model)


def put(dataset, df):
    """Overwrite a latest table with an arbitrary (possibly broken) DataFrame."""
    write_dataset(df, latest_path(dataset), overwrite=True)


def codes(run, dataset):
    return {i.code for i in run.results[dataset].issues}


# --- valid data ----------------------------------------------------------------------

def test_valid_datasets(good):
    run = q.validate_latest()
    for name in ("channels", "videos", "comments"):
        r = run.results[name]
        assert r.status is q.Status.VALID, (name, [i.message for i in r.issues])
        assert r.total_rows == 2
    assert run.status is q.Status.VALID


def test_nullable_optional_fields_are_not_problems(good):
    r = q.validate_latest().results
    assert r["channels"].null_counts["subscriber_count"] == 1
    assert r["videos"].null_counts["like_count"] == 1
    assert r["comments"].null_counts["author_channel_id"] == 1
    assert all(res.status is q.Status.VALID for res in r.values())


def test_result_structure(good):
    d = q.validate_latest().to_dict()
    assert d["status"] == "VALID" and d["scope"] == "latest"
    v = d["datasets"]["videos"]
    for key in ("dataset", "status", "total_rows", "error_count", "warning_count", "duplicate_count",
                "null_counts", "relationship_violations", "timestamp_violations", "numeric_violations", "issues"):
        assert key in v
    json.dumps(d)  # serializable


# --- structure ------------------------------------------------------------------------

def test_missing_required_column(good):
    put("videos", frame("videos").drop(columns=["published_at"]))
    r = q.validate_latest().results["videos"]
    assert r.status is q.Status.INVALID
    assert any(i.code == "missing_column" and "published_at" in i.message for i in r.issues)


def test_wrong_data_type(good):
    df = frame("videos")
    df["view_count"] = df["view_count"].astype("string")
    put("videos", df)
    r = q.validate_latest().results["videos"]
    assert any(i.code == "wrong_type" and "view_count" in i.message and "VARCHAR" in i.message for i in r.issues)
    assert r.status is q.Status.INVALID


def test_naive_timestamp_type_detected(good):
    df = pd.DataFrame(frame("channels"))
    write_dataset(df, latest_path("channels"), overwrite=True)  # write_dataset keeps UTC; break it via DuckDB
    import duckdb
    path = latest_path("channels").as_posix()
    duckdb.sql(f"COPY (SELECT * REPLACE (CAST(collected_at AS TIMESTAMP) AS collected_at) "
               f"FROM read_parquet('{path}')) TO '{path}.tmp' (FORMAT parquet)")
    import os
    os.replace(path + ".tmp", path)
    r = q.validate_latest().results["channels"]
    assert any(i.code == "wrong_type" and "collected_at" in i.message for i in r.issues)


def test_unexpected_extra_column_is_warning(good):
    df = frame("channels")
    df["extra_note"] = "x"
    put("channels", df)
    r = q.validate_latest().results["channels"]
    assert r.status is q.Status.VALID_WITH_WARNINGS
    assert codes(q.validate_latest(), "channels") == {"unexpected_columns"}


def test_missing_and_unreadable_files(isolated_data_dir):
    store_records("channels", channels())
    latest_path("videos").parent.mkdir(parents=True, exist_ok=True)
    latest_path("videos").write_bytes(b"not parquet")
    run = q.validate_latest()
    assert codes(run, "videos") == {"dataset_unreadable"}
    assert codes(run, "comments") == {"dataset_missing"}
    assert run.status is q.Status.INVALID


def test_empty_datasets(isolated_data_dir):
    for name, (model, _) in MODELS.items():
        write_dataset(to_dataframe([], model), latest_path(name))
    run = q.validate_latest()
    for name in MODELS:
        assert run.results[name].status is q.Status.VALID_WITH_WARNINGS
        assert codes(run, name) == {"empty_dataset"}
        assert run.results[name].total_rows == 0


# --- identifiers and duplicates ----------------------------------------------------------

def test_null_required_identifier(good):
    df = frame("comments")
    df.loc[0, "video_id"] = pd.NA
    put("comments", df)
    r = q.validate_latest().results["comments"]
    assert any(i.code == "null_required" and "video_id" in i.message for i in r.issues)
    assert r.status is q.Status.INVALID


def test_invalid_identifier_values(good):
    df = frame("channels")
    df.loc[0, "channel_id"] = "bad id/with space"
    put("channels", df)
    issue = next(i for i in q.validate_latest().results["channels"].issues if i.code == "invalid_identifier")
    assert issue.count == 1 and issue.examples == ["bad id/with space"]


def test_exact_duplicate_rows_are_warning(good):
    df = frame("videos")
    put("videos", pd.concat([df, df.iloc[[0]]], ignore_index=True))
    r = q.validate_latest().results["videos"]
    assert codes(q.validate_latest(), "videos") == {"exact_duplicate_rows"}
    assert r.status is q.Status.VALID_WITH_WARNINGS
    assert r.duplicate_count == 1


def test_duplicate_ids_with_different_values_are_error(good):
    df = frame("videos")
    changed = df.iloc[[0]].copy()
    changed["view_count"] = changed["view_count"] + 1
    put("videos", pd.concat([df, changed], ignore_index=True))
    r = q.validate_latest().results["videos"]
    issue = next(i for i in r.issues if i.code == "conflicting_duplicates")
    assert issue.examples == ["test_v1"]
    assert r.status is q.Status.INVALID
    assert "exact_duplicate_rows" not in codes(q.validate_latest(), "videos")


def test_snapshot_allows_same_id_at_different_times(isolated_data_dir):
    store_records("channels", channels())
    store_records("channels", [c.model_copy(update={"collected_at": pd.Timestamp(f"{DAY}T20:00:00Z").to_pydatetime(),
                                                    "subscriber_count": 200}) for c in channels()[:1]])
    run = q.validate_files({"channels": snapshot_path("channels", DAY)}, unique_by_collection=True)
    assert run.results["channels"].status is q.Status.VALID
    strict = q.validate_files({"channels": snapshot_path("channels", DAY)}, unique_by_collection=False)
    assert "conflicting_duplicates" in codes(strict, "channels")


# --- relationships -----------------------------------------------------------------------

def test_orphan_videos(good):
    put("channels", frame("channels").iloc[[0]])  # test_ch_b removed
    r = q.validate_latest().results["videos"]
    issue = next(i for i in r.issues if i.code == "orphan_videos")
    assert issue.count == 1 and issue.examples == ["test_v2"]
    assert r.status is q.Status.VALID_WITH_WARNINGS
    assert r.relationship_violations == 1


def test_orphan_comments(good):
    put("videos", frame("videos").iloc[[0]])
    r = q.validate_latest().results["comments"]
    issue = next(i for i in r.issues if i.code == "orphan_comments")
    assert issue.examples == ["test_c2"]


def test_comment_channel_mismatch_is_error(good):
    df = frame("comments")
    df.loc[0, "channel_id"] = "test_ch_b"  # but test_v1 belongs to test_ch_a
    put("comments", df)
    r = q.validate_latest().results["comments"]
    assert "comment_channel_mismatch" in codes(q.validate_latest(), "comments")
    assert r.status is q.Status.INVALID


def test_relationship_checks_skip_broken_datasets(good):
    put("channels", frame("channels").drop(columns=["channel_id"]))
    run = q.validate_latest()
    assert "orphan_videos" not in codes(run, "videos")  # cannot be judged; channels already INVALID
    assert run.results["channels"].status is q.Status.INVALID


# --- timestamps and numbers ----------------------------------------------------------------

def test_published_after_collected(good):
    df = frame("videos")
    df.loc[0, "published_at"] = pd.Timestamp("2026-10-05T00:00:00Z")
    put("videos", df)
    issue = next(i for i in q.validate_latest().results["videos"].issues if i.code == "published_after_collected")
    assert issue.examples == ["test_v1"]


def test_null_required_timestamp(good):
    df = frame("comments")
    df.loc[1, "published_at"] = pd.NaT
    put("comments", df)
    r = q.validate_latest().results["comments"]
    assert any(i.code == "null_required" and "published_at" in i.message for i in r.issues)


def test_implausible_and_future_timestamps(good):
    df = frame("videos")
    df.loc[0, "published_at"] = pd.Timestamp("1999-01-01T00:00:00Z")
    df.loc[1, "collected_at"] = pd.Timestamp("2099-01-01T00:00:00Z")
    put("videos", df)
    c = codes(q.validate_latest(), "videos")
    assert {"published_before_youtube", "collected_in_future"} <= c


def test_comment_before_video_warning(good):
    df = frame("comments")
    df.loc[0, "published_at"] = pd.Timestamp("2026-08-01T00:00:00Z")  # video test_v1 published 09-01
    put("comments", df)
    r = q.validate_latest().results["comments"]
    assert "comment_before_video" in codes(q.validate_latest(), "comments")
    assert r.status is q.Status.VALID_WITH_WARNINGS


@pytest.mark.parametrize("col", ["view_count", "like_count", "comment_count"])
def test_negative_engagement_metrics(good, col):
    df = frame("videos")
    df.loc[0, col] = -5
    put("videos", df)
    r = q.validate_latest().results["videos"]
    issue = next(i for i in r.issues if i.code == "negative_metric")
    assert col in issue.message and issue.examples == ["test_v1"]
    assert r.status is q.Status.INVALID and r.numeric_violations == 1


def test_likes_exceed_views_warning(good):
    df = frame("videos")
    df.loc[0, "like_count"] = 1000
    put("videos", df)
    assert "likes_exceed_views" in codes(q.validate_latest(), "videos")


# --- privacy ---------------------------------------------------------------------------

def test_raw_commenter_ids_warned_but_never_shown(good):
    raw = "UC" + "x" * 22  # TEST DATA shaped like a raw channel id
    df = frame("comments")
    df.loc[0, "author_channel_id"] = raw
    put("comments", df)
    run = q.validate_latest()
    assert "unhashed_commenter_ids" in codes(run, "comments")
    text = run.report() + json.dumps(run.to_dict())
    assert raw not in text
    assert "Synthetic." not in text  # comment text never appears


def test_report_has_no_secrets(good, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "TEST_KEY_NEVER_PRINTED")
    run = q.validate_latest()
    assert "TEST_KEY_NEVER_PRINTED" not in run.report() + json.dumps(run.to_dict())


# --- no repair --------------------------------------------------------------------------

def test_validation_never_modifies_data(good):
    df = frame("videos")
    put("videos", pd.concat([df, df.iloc[[0]]], ignore_index=True))  # duplicate + kept as is
    before = {p: p.read_bytes() for p in latest_path("videos").parent.glob("*.parquet")}
    q.validate_latest()
    assert {p: p.read_bytes() for p in latest_path("videos").parent.glob("*.parquet")} == before


# --- report ---------------------------------------------------------------------------

def test_report_text(good):
    put("channels", frame("channels").iloc[[0]])
    text = q.validate_latest().report()
    assert text.startswith("Data validation report - latest")
    assert "Overall: VALID_WITH_WARNINGS" in text
    assert "VIDEOS" in text and "WARN  [relationship]" in text and "test_v2" in text
    assert "CHANNELS  VALID" in text


def test_cli_exit_codes(good, capsys):
    assert q.main(["latest"]) == 0
    put("videos", frame("videos").drop(columns=["video_id"]))
    assert q.main(["latest"]) == 1
    assert "INVALID" in capsys.readouterr().out


# --- snapshots --------------------------------------------------------------------------

def test_snapshot_validation_saves_quality_file(good):
    s.create_snapshot(DAY)
    run = q.validate_snapshot_quality(DAY)
    assert run.scope == f"snapshot:{DAY}" and run.status is q.Status.VALID
    saved = q.load_snapshot_quality(DAY)
    assert saved["status"] == "VALID"
    assert set(saved["validated_files"]) == {"channels", "videos", "comments"}
    assert q.is_research_ready(DAY)
    assert q.latest_research_ready_snapshot() == DAY


def test_quality_file_does_not_change_sealed_snapshot(good):
    s.create_snapshot(DAY)
    manifest = s.manifest_path(DAY).read_bytes()
    q.validate_snapshot_quality(DAY)
    assert s.manifest_path(DAY).read_bytes() == manifest
    assert s.verify_snapshot(DAY).ok
    assert s.get_snapshot(DAY).status == "complete"


def test_not_research_ready_without_validation_or_when_incomplete(good):
    assert not q.is_research_ready(DAY)            # incomplete, not validated
    q.validate_snapshot_quality(DAY)
    assert not q.is_research_ready(DAY)            # validated but not sealed
    s.create_snapshot(DAY)
    # Sealed files are byte-identical to the validated ones (checksums match), so it applies.
    assert q.is_research_ready(DAY)


def test_not_research_ready_without_quality_file(good):
    s.create_snapshot(DAY)
    assert not q.is_research_ready(DAY)
    q.validate_snapshot_quality(DAY)
    assert q.is_research_ready(DAY)


def test_invalid_snapshot_not_research_ready(good):
    s.create_snapshot(DAY)
    # A comment pointing at a video of another channel passes snapshot sealing
    # (structure is fine) but fails quality validation.
    s.reopen_snapshot(DAY, confirm=True)
    bad = to_dataframe(comments(), Comment)
    bad.loc[0, "channel_id"] = "test_ch_b"
    write_dataset(bad, snapshot_path("comments", DAY), overwrite=True)
    s.create_snapshot(DAY, replace=True)

    run = q.validate_snapshot_quality(DAY)
    assert run.status is q.Status.INVALID
    assert not q.is_research_ready(DAY)
    assert q.latest_research_ready_snapshot() is None


def test_research_ready_lost_when_files_change(good):
    s.create_snapshot(DAY)
    q.validate_snapshot_quality(DAY)
    assert q.is_research_ready(DAY)
    df = to_dataframe(videos(), Video)
    df.loc[0, "view_count"] = 101
    write_dataset(df, snapshot_path("videos", DAY), overwrite=True)  # tampering
    assert not q.is_research_ready(DAY)


def test_snapshot_outside_day_rows(good):
    s.create_snapshot(DAY)
    run = q.validate_snapshot_quality(DAY, save=False)
    assert "outside_snapshot_day" not in codes(run, "videos")
    assert not q.quality_path(DAY).exists()  # save=False writes nothing


def test_unknown_dataset_name():
    with pytest.raises(ValueError):
        q.validate_files({"playlists": latest_path("channels")})
