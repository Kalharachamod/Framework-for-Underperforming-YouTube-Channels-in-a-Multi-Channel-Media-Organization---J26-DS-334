"""Tests for the Component 3 topic layer (preprocessing, profiles, similarity, clustering).

TEST DATA (synthetic): channels A, B (sports), C (cooking), D (only an empty-text video),
E (no videos). Titles/descriptions are invented, in English, Sinhala and Tamil.
Most tests use a fake encoder with known vectors; the e5 test runs only if the model is
already cached locally (tests never download it).
"""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from research.component_3.model import topic_similarity as ts
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
RAW_AUTHOR = "UC_raw_topic_author_xx"
CH = {k: f"UC_test_{k}" for k in "ABCDE"}
CN = {k: f"channel:{v}" for k, v in CH.items()}

VIDEOS = [  # (video, channel, title, description, day)
    ("A1", "A", "Cricket final highlights", "Sri Lanka win the cricket final https://example.com/x", 1),
    ("A2", "A", "ශ්‍රී ලංකා ක්‍රිකට් තරගය", None, 2),
    ("B1", "B", "Cricket batting tips", "#cricket practice drills", 3),
    ("C1", "C", "Fish curry recipe", "How to cook spicy fish curry", 4),
    ("C2", "C", "இலங்கை சமையல் குறிப்பு", "", 5),
    ("D1", "D", "  ", "https://only-a-link.example", 6),
]


class FakeEncoder:
    """Known vectors by keyword: sports -> [1, 0], cooking -> [0, 1]."""

    name, version = "fake_keyword_encoder", "test"

    def encode(self, texts):
        out = []
        for t in texts:
            sports = any(w in t for w in ("ricket", "ක්‍රිකට්"))
            out.append([1.0, 0.0] if sports else [0.0, 1.0])
        return np.array(out, dtype=np.float32)


def build_snapshot(extra=()):
    chans = [Channel(channel_id=c, channel_name=k, collected_at=T) for k, c in CH.items()]
    vids = [Video(video_id=v, channel_id=CH[c], title=t, description=d,
                  published_at=f"2026-09-{day:02d}T00:00:00Z", collected_at=T)
            for v, c, t, d, day in list(VIDEOS) + list(extra)]
    comms = [Comment(comment_id="k1", video_id="A1", channel_id=CH["A"],
                     author_channel_id=privacy.pseudonymize_id(RAW_AUTHOR, SALT), comment_text="Synthetic.",
                     published_at="2026-09-10T00:00:00Z", collected_at=T)]
    frames = {"channels": to_dataframe(chans, Channel), "videos": to_dataframe(vids, Video),
              "comments": to_dataframe(comms, Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test",
                                      extracted_at=datetime(2026, 10, 1, tzinfo=timezone.utc)).snapshot_id


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(100))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


@pytest.fixture
def sid(isolated_data_dir, ticking):
    return build_snapshot()


@pytest.fixture
def result(sid):
    return ts.run(sid, ts.TopicConfig(), encoder=FakeEncoder())


def sim(result, a, b):
    r = result.similarity
    return r[(r.source_channel_id == CN[a]) & (r.destination_channel_id == CN[b])].iloc[0]


# --- preprocessing -------------------------------------------------------------------------

def test_clean_text_removes_urls_keeps_scripts():
    assert ts.clean_text("Watch https://x.y/z now   #cricket  www.a.b ") == "Watch now cricket"
    sinhala = "ශ්‍රී ලංකා"  # contains a zero-width joiner, which must survive
    assert ts.clean_text(sinhala) == sinhala and "‍" in ts.clean_text(sinhala)
    assert ts.clean_text("இலங்கை\x00 சமையல்") == "இலங்கை சமையல்"
    assert ts.clean_text(None) == "" and ts.clean_text("mail me@x.com ok") == "mail ok"


def test_video_text_title_and_description():
    assert ts.video_text("Title", "Desc https://u.v") == "Title . Desc"
    assert ts.video_text("Only title", None) == "Only title"
    assert ts.video_text("", "") == ""
    assert len(ts.video_text("t", "x" * 5000)) == len("t . ") + ts.DESCRIPTION_CHARS


def test_letter_count_multilingual():
    assert ts.letter_count("ශ්‍රී ලංකා") > 3 and ts.letter_count("இலங்கை") > 3
    assert ts.letter_count("  !!! 123 ") == 0


# --- video representations / coverage -------------------------------------------------------------

def test_insufficient_text_not_embedded(result):
    v = result.videos.set_index("video_id")
    assert v.loc["D1", "text_status"] == "insufficient_text" and pd.isna(v.loc["D1", "embedding"])
    assert v.loc["A2", "text_status"] == "ok"  # Sinhala-only title is usable text
    assert "text" not in result.videos.columns and "title" not in result.videos.columns  # raw text not stored


def test_coverage(result):
    p = result.profiles.set_index("channel_id")
    assert (p.loc[CH["A"], "total_videos"], p.loc[CH["A"], "usable_videos"]) == (2, 2)
    assert p.loc[CH["D"], "insufficient_text_videos"] == 1 and p.loc[CH["D"], "coverage_ratio"] == 0
    assert not p.loc[CH["D"], "profile_available"]
    assert p.loc[CH["E"], "total_videos"] == 0 and pd.isna(p.loc[CH["E"], "coverage_ratio"])
    assert result.metadata["coverage"] == {"videos": 6, "usable": 5, "insufficient_text": 1,
                                           "channels_with_profile": 3, "channels": 5}


# --- aggregation / similarity -----------------------------------------------------------------

def test_channel_profile_is_normalized_mean(result):
    p = result.profiles.set_index("channel_id")
    np.testing.assert_allclose(list(p.loc[CH["A"], "profile"]), [1.0, 0.0])           # two sports videos
    np.testing.assert_allclose(list(p.loc[CH["C"], "profile"]), [0.0, 1.0])           # two cooking videos


def test_mixed_channel_profile(sid):
    mixed = ts._profiles(pd.DataFrame({
        "channel_id": ["X", "X"], "text_status": ["ok", "ok"],
        "embedding": pd.Series([[1.0, 0.0], [0.0, 1.0]], dtype=object)}), ["X"], 2, ts.TopicConfig())[0]
    np.testing.assert_allclose(list(mixed.loc[0, "profile"]), [2 ** -0.5, 2 ** -0.5])


def test_cosine_known_values_and_zero_vector():
    assert ts.cosine(np.array([1, 0]), np.array([1, 0])) == 1.0
    assert ts.cosine(np.array([1, 0]), np.array([0, 1])) == 0.0
    assert ts.cosine(np.array([1, 0]), np.array([-1, 0])) == -1.0
    assert ts.cosine(np.array([0, 0]), np.array([1, 0])) is None


def test_similarity_values_symmetry_and_unavailable(result):
    assert sim(result, "A", "B").topic_similarity == pytest.approx(1.0)
    assert sim(result, "A", "C").topic_similarity == pytest.approx(0.0)
    assert sim(result, "A", "C").topic_similarity == sim(result, "C", "A").topic_similarity
    d = sim(result, "A", "D")
    assert pd.isna(d.topic_similarity) and not d.both_profiles_available   # no fabricated similarity
    assert len(result.similarity) == 5 * 4                                  # ordered pairs, no self pairs
    assert (result.similarity.source_channel_id != result.similarity.destination_channel_id).all()


def test_centered_similarity_labelled(result):
    assert "centered" in result.metadata["similarity"]["secondary"]
    assert sim(result, "A", "C").topic_similarity_centered < sim(result, "A", "B").topic_similarity_centered


# --- temporal boundary / capping ------------------------------------------------------------------

def test_as_of_excludes_future_videos(sid):
    r = ts.run(sid, encoder=FakeEncoder(), as_of=datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
    assert set(r.videos["video_id"]) == {"A1", "A2", "B1"}
    assert not r.profiles.set_index("channel_id").loc[CH["C"], "profile_available"]
    with pytest.raises(ts.TopicError, match="after the snapshot"):
        ts.run(sid, encoder=FakeEncoder(), as_of=datetime(2027, 1, 1, tzinfo=timezone.utc))


def test_max_videos_per_channel_keeps_most_recent(sid):
    r = ts.run(sid, ts.TopicConfig(max_videos_per_channel=1), encoder=FakeEncoder())
    assert set(r.videos.loc[r.videos.channel_id == CH["A"], "video_id"]) == {"A2"}


# --- baseline encoder / determinism -----------------------------------------------------------------

def test_char_lsa_baseline_deterministic(sid):
    a = ts.run(sid, ts.TopicConfig(backend="char_lsa"))
    b = ts.run(sid, ts.TopicConfig(backend="char_lsa"))
    pd.testing.assert_frame_equal(a.similarity, b.similarity)
    assert a.experiment_id == b.experiment_id and a.metadata["model"]["role"] == "exploratory baseline"
    assert a.metadata["validation"]["symmetric"]


def test_unknown_backend(sid):
    with pytest.raises(ts.TopicError):
        ts.run(sid, ts.TopicConfig(backend="lda"))


# --- clustering ----------------------------------------------------------------------------

def test_optional_clustering_and_graph_compatibility(sid):
    r = ts.run(sid, ts.TopicConfig(n_topics=2, min_videos_per_topic=2), encoder=FakeEncoder())
    assert set(r.topics["topic_id"]) == {"t00", "t01"}
    assert set(r.video_topics["video_id"]) == {"A1", "A2", "B1", "C1", "C2"}  # D1 (no text) never assigned
    assert r.topics["label"].str.startswith("cluster").all()                 # no fabricated semantic labels
    r2 = ts.run(sid, ts.TopicConfig(n_topics=2, min_videos_per_topic=2), encoder=FakeEncoder())
    pd.testing.assert_frame_equal(r.video_topics, r2.video_topics)
    from research.component_3.preprocessing import hetero_graph as hg
    g = hg.build_graph(sid, topics=r.topics[["topic_id", "label"]], video_topics=r.video_topics)
    assert hg.validate_graph(g) == [] and len(g.nodes_of("topic")) == 2


def test_clustering_skipped_when_too_small(sid):
    r = ts.run(sid, ts.TopicConfig(n_topics=5, min_videos_per_topic=2), encoder=FakeEncoder())
    assert r.topics is None and r.metadata["clustering"]["skipped"]


# --- metadata / persistence / privacy -------------------------------------------------------------

def test_metadata(result):
    m = result.metadata
    assert m["experiment_id"].startswith("top-") and m["snapshot_id"] == result.snapshot_id
    assert m["model"]["name"] == "fake_keyword_encoder" and m["preprocessing"]["version"] == ts.PREPROCESSING_VERSION
    assert m["embedding_dimension"] == 2 and "equal weight per video" in m["aggregation"]
    assert m["scope"] == "snapshot-level semantic similarity" and "not an Audience Bridge Score" in m["note"]


def test_save_and_reload(result):
    path = ts.save(result)
    assert {p.name for p in path.iterdir()} == {"video_semantic_embeddings.parquet", "channel_semantic_profiles.parquet",
                                                "channel_topic_similarity.parquet", "topic_run.json"}
    loaded = ts.load(path)
    pd.testing.assert_frame_equal(loaded.similarity.reset_index(drop=True), result.similarity.reset_index(drop=True),
                                  check_dtype=False)
    assert ts.save(result) == path


def test_validation_detects_problems(result):
    bad = ts.TopicResult(result.snapshot_id, result.experiment_id, result.as_of, result.videos,
                         result.profiles, result.similarity.copy())
    bad.similarity.loc[0, "topic_similarity"] = 1.5
    with pytest.raises(ts.TopicError, match="outside"):
        ts.validate(bad)
    dup = ts.TopicResult(result.snapshot_id, result.experiment_id, result.as_of,
                         pd.concat([result.videos, result.videos.iloc[[0]]], ignore_index=True),
                         result.profiles, result.similarity)
    with pytest.raises(ts.TopicError, match="duplicate video"):
        ts.validate(dup)


def test_no_raw_commenter_ids(result):
    path = ts.save(result)
    blob = " ".join([json.dumps(result.metadata, default=str)] + [p.read_bytes().decode("latin-1") for p in path.iterdir()])
    assert RAW_AUTHOR not in blob


# --- real multilingual model (only if already cached; never downloaded in tests) -------------------------

def _e5_cached() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(ts.E5_MODEL, "config.json", revision=ts.E5_REVISION), str)
    except Exception:
        return False


@pytest.mark.skipif(not _e5_cached(), reason="multilingual-e5-small not cached locally")
def test_e5_cross_lingual_and_deterministic(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    enc = ts.E5Encoder()
    a = enc.encode(["Sri Lanka cricket match", "ශ්‍රී ලංකා ක්‍රිකට් තරගය", "fish curry recipe"])
    b = enc.encode(["Sri Lanka cricket match", "ශ්‍රී ලංකා ක්‍රිකට් තරගය", "fish curry recipe"])
    np.testing.assert_allclose(a, b, atol=1e-6)
    assert a.shape[1] == 384 and float(a[0] @ a[1]) > float(a[0] @ a[2])  # cross-lingual sports > cooking
