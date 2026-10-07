"""Tests for commenter-id pseudonymization (shared/utils/privacy.py).

All ids and salts are TEST DATA; no real commenter ids or salts are used.
"""

import json

import pandas as pd
import pytest

from shared.schemas import Comment
from shared.utils import latest_path, read_latest, store_records
from shared.utils import privacy as p
from shared.utils import quality as q
from shared.utils.datasets import snapshot_path

SALT_A = b"test-salt-A-" + b"0" * 40
SALT_B = b"test-salt-B-" + b"0" * 40
RAW = "UC" + "t" * 22  # TEST id shaped like a YouTube channel id


def comment(com="test_c1", author=RAW, **kw):
    return Comment(comment_id=com, video_id="test_v1", channel_id="test_ch_a", author_channel_id=author,
                   comment_text="Synthetic.", published_at="2026-09-02T00:00:00Z",
                   collected_at="2026-09-30T08:00:00Z", **kw)


# --- hashing ---------------------------------------------------------------------

def test_pseudonym_format_and_determinism():
    h = p.pseudonymize_id(RAW, SALT_A)
    assert h.startswith("anon_") and len(h) == 69 and p.is_pseudonymized(h)
    assert p.pseudonymize_id(RAW, SALT_A) == h                  # same commenter -> same pseudonym
    assert p.pseudonymize_id("UC" + "u" * 22, SALT_A) != h      # different commenter -> different
    assert RAW not in h


def test_salt_changes_pseudonym():
    assert p.pseudonymize_id(RAW, SALT_A) != p.pseudonymize_id(RAW, SALT_B)


def test_already_pseudonymized_is_unchanged():
    h = p.pseudonymize_id(RAW, SALT_A)
    assert p.pseudonymize_id(h, SALT_B) == h  # idempotent: never double-hashed


def test_matches_reference_hmac():
    import hashlib, hmac
    expected = "anon_" + hmac.new(SALT_A, RAW.encode(), hashlib.sha256).hexdigest()
    assert p.pseudonymize_id(RAW, SALT_A) == expected


@pytest.mark.parametrize("bad", ["", "   ", None, 123])
def test_invalid_input(bad):
    with pytest.raises(ValueError):
        p.pseudonymize_id(bad, SALT_A)


@pytest.mark.parametrize("value", [None, "", "your_commenter_hash_salt_here", "short-salt"])
def test_salt_required_and_strong(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("COMMENTER_HASH_SALT", raising=False)
    else:
        monkeypatch.setenv("COMMENTER_HASH_SALT", value)
    with pytest.raises(p.PrivacyConfigError) as err:
        p.get_salt()
    assert "short-salt" not in str(err.value)  # the salt value is never echoed


# --- storage integration ------------------------------------------------------------

def test_store_records_never_writes_raw_ids(isolated_data_dir):
    store_records("comments", [comment("test_c1"), comment("test_c2", author=None)])
    df = read_latest("comments").set_index("comment_id")
    assert p.is_pseudonymized(df.loc["test_c1", "author_channel_id"])
    assert pd.isna(df.loc["test_c2", "author_channel_id"])  # missing stays missing, never invented
    for path in (latest_path("comments"), snapshot_path("comments", "2026-09-30")):
        assert RAW.encode() not in path.read_bytes()


def test_same_commenter_links_across_channels(isolated_data_dir):
    store_records("comments", [comment("test_c1"),
                               comment("test_c2").model_copy(update={"channel_id": "test_ch_b"})])
    authors = read_latest("comments")["author_channel_id"].tolist()
    assert authors[0] == authors[1]  # cross-channel audience link preserved


def test_storage_fails_closed_without_salt(isolated_data_dir, monkeypatch):
    monkeypatch.delenv("COMMENTER_HASH_SALT")
    with pytest.raises(p.PrivacyConfigError):
        store_records("comments", [comment()])
    assert not latest_path("comments").exists()  # nothing written
    store_records("comments", [comment(author=None)])  # no commenter id: no salt needed


def test_rerun_is_idempotent(isolated_data_dir):
    store_records("comments", [comment()])
    summary = store_records("comments", [comment()])
    assert (summary.snapshot_rows_added, summary.latest_updated) == (0, 0)


def test_schema_still_holds_raw_value_in_memory():
    # The schema is unchanged; pseudonymization happens at storage time.
    assert comment().author_channel_id == RAW


# --- quality check ------------------------------------------------------------------

def test_quality_passes_for_pseudonymized_comments(isolated_data_dir):
    store_records("comments", [comment()])
    run = q.validate_files({"comments": latest_path("comments")})
    assert "unhashed_commenter_ids" not in {i.code for i in run.results["comments"].issues}


def test_salt_never_in_outputs(isolated_data_dir):
    store_records("comments", [comment()])
    run = q.validate_files({"comments": latest_path("comments")})
    text = run.report() + json.dumps(run.to_dict()) + latest_path("comments").read_bytes().decode("latin-1")
    assert "test-salt-" not in text
