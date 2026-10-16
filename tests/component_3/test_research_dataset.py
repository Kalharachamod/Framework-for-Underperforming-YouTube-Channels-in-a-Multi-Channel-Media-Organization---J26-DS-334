"""Tests for research snapshots and the Component 3 research-data preparation.

All data is TEST DATA with synthetic ids. Commenter ids are pseudonymized with a
test salt; the raw values are never printed. No live Supabase or YouTube API:
extraction is tested against the throwaway local PostgreSQL from conftest.
"""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from research.component_3.preprocessing import research_dataset as rd
from shared.database import repository as repo
from shared.database.snapshot_export import export_research_snapshot
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s
from shared.utils.paths import component_dir

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
RAW = {n: f"UC_raw_test_author_{n:02d}" for n in range(10)}  # TEST raw ids (never stored)


def anon(n):
    return privacy.pseudonymize_id(RAW[n], SALT)


# --- TEST DATA ------------------------------------------------------------------------------
# Channels A, B, C. Commenter 1 comments on A and B; commenter 2 on A, B and C;
# commenter 3 only on A; one comment has no commenter id.
#   expected pair overlap: (A,B)=2, (A,C)=1, (B,C)=1

def channels():
    return [Channel(channel_id=c, channel_name=f"Test {c}", subscriber_count=100, collected_at=T)
            for c in ("UC_test_A", "UC_test_B", "UC_test_C")]


def videos():
    return [Video(video_id=v, channel_id=c, title=f"Test {v}", published_at="2026-09-01T10:00:00Z",
                  view_count=10, comment_count=1, collected_at=T)
            for v, c in (("vA1", "UC_test_A"), ("vA2", "UC_test_A"), ("vB1", "UC_test_B"), ("vC1", "UC_test_C"))]


def comment(cid, vid, ch, author, published="2026-09-05T10:00:00Z", parent=None):
    return Comment(comment_id=cid, video_id=vid, channel_id=ch, author_channel_id=None if author is None else anon(author),
                   comment_text="Synthetic.", published_at=published, edited_at=published, like_count=0,
                   parent_comment_id=parent, collected_at=T)


def comments():
    return [
        comment("c1", "vA1", "UC_test_A", 1, "2026-09-05T10:00:00Z"),
        comment("c2", "vA2", "UC_test_A", 1, "2026-09-06T10:00:00Z"),
        comment("c3", "vB1", "UC_test_B", 1, "2026-09-07T10:00:00Z"),
        comment("c4", "vA1", "UC_test_A", 2),
        comment("c5", "vB1", "UC_test_B", 2),
        comment("c6", "vC1", "UC_test_C", 2),
        comment("c7", "vA1", "UC_test_A", 3),
        comment("c1.r1", "vA1", "UC_test_A", 3, "2026-09-05T11:00:00Z", parent="c1"),
        comment("c8", "vC1", "UC_test_C", None),
    ]


def frames(ch=None, vi=None, co=None):
    return {"channels": to_dataframe(ch if ch is not None else channels(), Channel),
            "videos": to_dataframe(vi if vi is not None else videos(), Video),
            "comments": to_dataframe(co if co is not None else comments(), Comment)}


def make_snapshot(**kw):
    return s.create_research_snapshot(frames(**kw), source="synthetic_test")


@pytest.fixture
def ticking(monkeypatch):
    """Distinct creation times so several snapshots get distinct ids."""
    times = iter(datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(100))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


# --- research snapshot creation --------------------------------------------------------------

def test_create_research_snapshot(isolated_data_dir, ticking):
    info = make_snapshot()
    assert info.snapshot_id == "rs-20261008T090000Z"
    assert info.path == isolated_data_dir / "snapshots" / "research" / info.snapshot_id
    assert info.row_counts == {"channels": 3, "videos": 4, "comments": 9}
    assert sorted(p.name for p in info.path.iterdir()) == ["_snapshot.json", "channels.parquet",
                                                           "comments.parquet", "videos.parquet"]
    m = info.manifest
    assert m["kind"] == "research" and m["source"] == "synthetic_test" and m["schema_version"]
    assert all(len(d["sha256"]) == 64 for d in m["datasets"].values())
    assert s.verify_research_snapshot(info.snapshot_id).ok


def test_research_snapshot_not_in_day_history(isolated_data_dir, ticking):
    make_snapshot()
    assert s.list_snapshots() == []  # not mistaken for a day snapshot
    from shared.utils.datasets import read_history
    assert read_history("videos").empty  # not part of the day-snapshot history


def test_listing_and_latest(isolated_data_dir, ticking):
    a, b = make_snapshot(), make_snapshot()
    assert [x.snapshot_id for x in s.list_research_snapshots()] == [a.snapshot_id, b.snapshot_id]
    assert s.latest_research_snapshot().snapshot_id == b.snapshot_id


def test_no_snapshot_yet(isolated_data_dir):
    with pytest.raises(s.SnapshotNotFoundError):
        s.latest_research_snapshot()


def test_snapshot_refuses_raw_commenter_ids(isolated_data_dir, ticking):
    bad = comments()
    bad[0] = bad[0].model_copy(update={"author_channel_id": RAW[1]})
    with pytest.raises(privacy.PrivacyConfigError):
        make_snapshot(co=bad)
    assert s.list_research_snapshots() == []
    assert not (isolated_data_dir / "snapshots" / "research").exists() or \
        not any((isolated_data_dir / "snapshots" / "research").iterdir())


def test_snapshot_requires_schema_columns(isolated_data_dir, ticking):
    f = frames()
    f["videos"] = f["videos"].drop(columns=["title"])
    with pytest.raises(Exception, match="schema"):
        s.create_research_snapshot(f, source="synthetic_test")


def test_tampering_detected(isolated_data_dir, ticking):
    info = make_snapshot()
    path = s.research_dataset_path(info.snapshot_id, "videos")
    path.write_bytes(path.read_bytes() + b"x")
    assert not s.verify_research_snapshot(info.snapshot_id).ok
    with pytest.raises(s.SnapshotValidationError, match="checksum mismatch"):
        rd.prepare(info.snapshot_id)  # a modified snapshot is never analysed


# --- valid data: report, datasets ----------------------------------------------------------

def test_prepare_valid_snapshot(isolated_data_dir, ticking):
    info = make_snapshot()
    report = rd.prepare(info.snapshot_id)
    assert report.research_ready, report.text()
    assert report.counts == {"channels": 3, "videos": 4, "comments": 9, "top_level_comments": 8,
                             "replies": 1, "unique_commenters": 3}
    assert report.relationships == {"videos_with_channel": 4, "comments_with_video": 9,
                                    "comments_with_channel": 9, "replies_with_parent": 1}
    assert all(d == {"duplicate_rows": 0, "conflicting_ids": 0} for d in report.duplicates.values())
    assert report.valid_nulls["comments"]["author_channel_id"] == 1      # valid null, not an error
    assert report.missing_required["comments"]["video_id"] == 0
    saved = json.loads((info.path / rd.REPORT_FILE).read_text(encoding="utf-8"))
    assert saved["research_ready"] is True and "not show audience migration" in saved["note"]
    out = component_dir(3) / info.snapshot_id
    assert sorted(p.stem for p in out.iterdir()) == sorted(rd.DATASET_VIEWS)


def test_cross_channel_readiness_and_pair_overlap(isolated_data_dir, ticking):
    info = make_snapshot()
    report = rd.prepare(info.snapshot_id, export=False, save_report=False)
    x = report.cross_channel
    assert x["commenters_on_one_channel"] == 1 and x["commenters_on_multiple_channels"] == 2
    assert x["channels_with_commenters"] == 3 and x["comments_without_commenter_id"] == 1
    assert x["top_channel_pairs"] == [
        {"channel_a": "UC_test_A", "channel_b": "UC_test_B", "shared_commenters": 2},
        {"channel_a": "UC_test_A", "channel_b": "UC_test_C", "shared_commenters": 1},
        {"channel_a": "UC_test_B", "channel_b": "UC_test_C", "shared_commenters": 1},
    ]
    with rd.research_session(info.snapshot_id) as con:
        cc = rd.query(con, "channel_commenters").set_index("channel_id")
        assert cc.loc["UC_test_A", "unique_commenters"] == 3
        assert cc.loc["UC_test_A", "commenters_also_on_other_channels"] == 2
        per = rd.query(con, "commenter_channels").set_index("commenter_id")
        assert per.loc[anon(2), "channel_count"] == 3 and per.loc[anon(3), "channel_count"] == 1


def test_commenter_participation_rows_and_timestamps(isolated_data_dir, ticking):
    info = make_snapshot()
    with rd.research_session(info.snapshot_id) as con:
        p = rd.query(con, "commenter_participation")
        one = p[(p.commenter_id == anon(3)) & (p.video_id == "vA1")].iloc[0]
        assert one.comment_count == 2 and one.reply_count == 1  # c7 + reply c1.r1
        assert one.first_comment_at < one.last_comment_at
        c1 = p[(p.commenter_id == anon(1)) & (p.video_id == "vA1")].iloc[0]
        assert c1.first_comment_at == pd.Timestamp("2026-09-05T10:00:00Z")
        comments_ds = rd.query(con, "comment_dataset").set_index("comment_id")
        assert comments_ds.loc["c1.r1", "is_reply"] and comments_ds.loc["c1.r1", "parent_comment_id"] == "c1"
        for col in ("published_at", "edited_at", "collected_at"):
            assert str(comments_ds[col].dt.tz) == "UTC"
        assert set(rd.query(con, "video_dataset").columns) >= {"published_at", "collected_at", "channel_name"}


def test_reproducible_outputs(isolated_data_dir, ticking):
    a, b = make_snapshot(), make_snapshot()
    with rd.research_session(a.snapshot_id) as ca, rd.research_session(b.snapshot_id) as cb:
        for view in rd.DATASET_VIEWS:
            pd.testing.assert_frame_equal(rd.query(ca, view), rd.query(cb, view))
    ra = rd.prepare(a.snapshot_id, export=False, save_report=False).to_dict()
    rb = rd.prepare(b.snapshot_id, export=False, save_report=False).to_dict()
    for k in ("snapshot_id", "snapshot_created_at", "prepared_at"):
        ra.pop(k), rb.pop(k)
    assert ra == rb


# --- invalid data: detected, reported, not repaired ---------------------------------------------

def codes(report):
    return {c.code for c in report.research_checks}


def test_orphans_and_missing_relationships(isolated_data_dir, ticking):
    vi = videos() + [Video(video_id="vX", channel_id="UC_test_missing", title="t",
                           published_at="2026-09-01T00:00:00Z", collected_at=T)]
    co = comments() + [comment("cX", "v_missing", "UC_test_A", 4),
                       comment("cY", "vA1", "UC_test_missing", 4),
                       comment("cZ.r", "vA1", "UC_test_A", 4, parent="c_missing")]
    report = rd.prepare(make_snapshot(vi=vi, co=co).snapshot_id, export=False, save_report=False)
    assert {"orphan_videos", "orphan_comments", "comments_without_channel", "orphan_replies",
            "comment_channel_mismatch"} <= codes(report)
    assert not report.research_ready
    assert report.relationships["videos_with_channel"] == 4


def test_duplicates_reported_not_removed(isolated_data_dir, ticking):
    f = frames()
    f["channels"] = pd.concat([f["channels"], f["channels"].iloc[[0]]], ignore_index=True)       # exact dup
    changed = f["videos"].iloc[[0]].copy()
    changed["view_count"] = changed["view_count"] + 5
    f["videos"] = pd.concat([f["videos"], changed], ignore_index=True)                             # conflicting
    f["comments"] = pd.concat([f["comments"], f["comments"].iloc[[0]]], ignore_index=True)
    info = s.create_research_snapshot(f, source="synthetic_test")
    report = rd.prepare(info.snapshot_id, export=False, save_report=False)
    assert report.duplicates["channels"] == {"duplicate_rows": 1, "conflicting_ids": 0}
    assert report.duplicates["videos"] == {"duplicate_rows": 1, "conflicting_ids": 1}
    assert report.duplicates["comments"]["duplicate_rows"] == 1
    assert {"duplicate_channels", "duplicate_videos", "duplicate_comments"} <= codes(report)
    assert info.row_counts["channels"] == 4  # raw snapshot preserved as given
    assert not (component_dir(3) / info.snapshot_id).exists()  # not exported when not research-ready


def test_missing_required_values(isolated_data_dir, ticking):
    f = frames()
    f["comments"].loc[0, "published_at"] = pd.NaT
    f["videos"].loc[0, "channel_id"] = pd.NA
    report = rd.prepare(s.create_research_snapshot(f, source="synthetic_test").snapshot_id,
                        export=False, save_report=False)
    assert report.missing_required["comments"]["published_at"] == 1
    assert report.missing_required["videos"]["channel_id"] == 1
    assert {"missing_comments_published_at", "missing_videos_channel_id"} <= codes(report)


def test_reply_on_other_video_rejected(isolated_data_dir, ticking):
    co = comments() + [comment("c1.r9", "vA2", "UC_test_A", 4, parent="c1")]
    report = rd.prepare(make_snapshot(co=co).snapshot_id, export=False, save_report=False)
    assert "invalid_reply_links" in codes(report)


def test_empty_dataset(isolated_data_dir, ticking):
    info = make_snapshot(ch=[], vi=[], co=[])
    report = rd.prepare(info.snapshot_id)
    assert report.counts["comments"] == 0 and report.cross_channel["top_channel_pairs"] == []
    assert "empty_dataset" in codes(report) and not report.research_ready
    assert "Research-ready: NO" in report.text()


# --- privacy -----------------------------------------------------------------------------

def test_no_raw_commenter_ids_in_outputs(isolated_data_dir, ticking):
    info = make_snapshot()
    report = rd.prepare(info.snapshot_id)
    texts = [report.text(), json.dumps(report.to_dict(), default=str)]
    for p in list(info.path.iterdir()) + list((component_dir(3) / info.snapshot_id).iterdir()):
        texts.append(p.read_bytes().decode("latin-1"))
    blob = " ".join(texts)
    for raw in RAW.values():
        assert raw not in blob
    with rd.research_session(info.snapshot_id) as con:
        assert "author_channel_id" not in rd.query(con, "comment_dataset").columns  # exposed as commenter_id


def test_unknown_view():
    with pytest.raises(ValueError):
        rd.query(None, "secret_view")


# --- extraction from the (throwaway) PostgreSQL ---------------------------------------------------

def test_export_research_snapshot_from_database(db, isolated_data_dir, ticking):
    repo.upsert_channels(db, channels())
    repo.upsert_videos(db, videos())
    repo.upsert_comments(db, comments())
    db.commit()
    info = export_research_snapshot(db)
    assert info.row_counts == {"channels": 3, "videos": 4, "comments": 9}
    assert info.manifest["source"] == "supabase_postgresql"
    assert info.manifest["details"]["isolation"] == "repeatable_read"
    assert info.manifest["extracted_at"]
    report = rd.prepare(info.snapshot_id)
    assert report.research_ready and report.cross_channel["commenters_on_multiple_channels"] == 2
    # the connection still works normally afterwards (isolation / read-only restored)
    repo.upsert_channels(db, [Channel(channel_id="UC_test_D", channel_name="D", collected_at=T)])
    db.commit()
    assert repo.count_rows(db, "channels") == 4


def test_cli_extract_requires_database(monkeypatch, isolated_data_dir, capsys):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    assert rd.main(["--extract"]) == 2
    assert "SUPABASE_DB_URL" in capsys.readouterr().err


def test_cli_prepare_latest(isolated_data_dir, ticking, capsys):
    make_snapshot()
    assert rd.main([]) == 0
    out = capsys.readouterr().out
    assert "Research-ready: YES" in out and "UC_test_A <-> UC_test_B: 2 shared commenter(s)" in out
