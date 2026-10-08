"""Content-semantic topic layer for Component 3: video embeddings -> channel profiles -> topic similarity.

    python -m research.component_3.model.topic_similarity                     # e5 multilingual, latest snapshot
    python -m research.component_3.model.topic_similarity --backend char_lsa  # exploratory baseline
    python -m research.component_3.model.topic_similarity --topics 8          # optional topic clustering

Pipeline (snapshot-level, as of the snapshot extraction time by default):
  title + description  ->  deterministic multilingual cleaning  ->  semantic embedding per video
  ->  channel profile = mean of the channel's L2-normalized video embeddings (each video counts once)
  ->  channel-pair cosine similarity (symmetric).

Backends:
  * "e5" (primary): intfloat/multilingual-e5-small at a pinned revision (Sinhala, Tamil, English
    and ~100 more languages; cross-lingual).
  * "char_lsa" (exploratory baseline): character n-gram TF-IDF + truncated SVD (any script).

topic_similarity measures content-semantic similarity only. It does NOT show audience
overlap, audience migration, subscriber movement, causality or conversion, and it is
not an Audience Bridge Score.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
import pyarrow as pa

from research.component_3.preprocessing import graph_features as gf
from research.component_3.preprocessing import hetero_graph as hg
from research.component_3.preprocessing import research_dataset as rd
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

METHOD_VERSION = "1.0"
PREPROCESSING_VERSION = "text-v1"
TOPICS_DIR = "topics"
E5_MODEL = "intfloat/multilingual-e5-small"
E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"   # pinned for reproducibility
DESCRIPTION_CHARS = 1000

_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SPACE = re.compile(r"\s+")


# --- text preprocessing --------------------------------------------------------------------

def clean_text(text: str | None) -> str:
    """Deterministic, script-preserving cleaning (no lowercasing, no stop-word removal).

    NFC normalization; URLs and e-mail addresses removed; '#' of hashtags dropped (the word
    is kept); control characters removed; whitespace collapsed. Zero-width joiners (needed by
    Sinhala conjuncts) and all scripts are preserved.
    """
    if not isinstance(text, str):
        return ""
    t = unicodedata.normalize("NFC", text)
    t = _URL.sub(" ", t)
    t = _EMAIL.sub(" ", t)
    t = t.replace("#", " ")
    t = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in t)
    return _SPACE.sub(" ", t).strip()


def video_text(title: str | None, description: str | None) -> str:
    """Title, then the first DESCRIPTION_CHARS characters of the cleaned description."""
    parts = [clean_text(title), clean_text(description)[:DESCRIPTION_CHARS]]
    return " . ".join(p for p in parts if p)


def letter_count(text: str) -> int:
    return sum(1 for ch in text if unicodedata.category(ch)[0] in ("L", "M"))


# --- encoders ----------------------------------------------------------------------------

class Encoder(Protocol):
    name: str
    version: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class E5Encoder:
    """Primary: multilingual-e5-small sentence embeddings (L2-normalized, 384 dimensions)."""

    def __init__(self, model: str = E5_MODEL, revision: str = E5_REVISION, batch_size: int = 32):
        from sentence_transformers import SentenceTransformer
        import torch

        torch.manual_seed(0)
        self.name, self.version = model, revision
        self._model = SentenceTransformer(model, revision=revision, device="cpu")
        self._batch = batch_size

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), np.float32)
        # "query: " prefix = symmetric similarity use of e5
        return self._model.encode([f"query: {t}" for t in texts], batch_size=self._batch,
                                  normalize_embeddings=True, show_progress_bar=False).astype(np.float32)


class CharNgramLSAEncoder:
    """Exploratory baseline: character n-gram TF-IDF + truncated SVD, fitted on the snapshot's texts."""

    def __init__(self, dimensions: int = 64, ngram_range: tuple[int, int] = (2, 4), seed: int = 42):
        import sklearn

        self.name, self.version = "char_ngram_tfidf_lsa", f"scikit-learn {sklearn.__version__}"
        self.dimensions, self.ngram_range, self.seed = dimensions, ngram_range, seed

    def encode(self, texts: list[str]) -> np.ndarray:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        if not texts:
            return np.zeros((0, self.dimensions), np.float32)
        x = TfidfVectorizer(analyzer="char_wb", ngram_range=self.ngram_range, lowercase=True,
                            sublinear_tf=True).fit_transform(texts)
        k = min(self.dimensions, x.shape[1] - 1, x.shape[0] - 1)
        z = (TruncatedSVD(n_components=k, random_state=self.seed, algorithm="arpack").fit_transform(x)
             if k >= 1 else x.toarray())
        z = np.pad(z, ((0, 0), (0, self.dimensions - z.shape[1]))) if z.shape[1] < self.dimensions else z
        return _l2(z).astype(np.float32)


# --- configuration / result ----------------------------------------------------------------

@dataclass(frozen=True)
class TopicConfig:
    backend: str = "e5"                    # "e5" (primary) | "char_lsa" (exploratory baseline)
    min_letters: int = 3                   # fewer letters after cleaning -> insufficient_text
    min_videos_per_profile: int = 1        # usable videos needed for a channel profile
    max_videos_per_channel: int | None = None   # cap = most recent N (controls dominance); None = all
    n_topics: int | None = None            # optional KMeans topic clustering
    min_videos_per_topic: int = 2          # need >= n_topics * this usable videos to cluster
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TopicError(ValueError):
    pass


@dataclass
class TopicResult:
    snapshot_id: str
    experiment_id: str
    as_of: datetime
    videos: pd.DataFrame          # one row per video (embedding NULL if insufficient_text)
    profiles: pd.DataFrame        # one row per channel
    similarity: pd.DataFrame      # ordered channel pairs (symmetric values)
    topics: pd.DataFrame | None = None
    video_topics: pd.DataFrame | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --- pipeline ------------------------------------------------------------------------------

def run(snapshot_id: str, config: TopicConfig = TopicConfig(), *, as_of: datetime | None = None,
        encoder: Encoder | None = None) -> TopicResult:
    info = snapshots.get_research_snapshot(snapshot_id)
    snapshot_time = gf._snapshot_time(info)
    as_of = (as_of or snapshot_time).astimezone(timezone.utc)
    if as_of > snapshot_time:
        raise TopicError("as_of is after the snapshot: future content is not known")
    encoder = encoder or (E5Encoder() if config.backend == "e5" else CharNgramLSAEncoder(seed=config.seed)
                          if config.backend == "char_lsa" else None)
    if encoder is None:
        raise TopicError("backend must be 'e5' or 'char_lsa'")

    lit = f"TIMESTAMPTZ '{as_of.isoformat()}'"
    with rd.research_session(info.snapshot_id) as con:
        vids = con.execute(f"""SELECT video_id, channel_id, title, description, published_at FROM videos
                               WHERE published_at <= {lit} ORDER BY channel_id, published_at DESC, video_id""").df()
        channels = con.execute("SELECT channel_id FROM channels ORDER BY channel_id").df()["channel_id"].tolist()
    if config.max_videos_per_channel:
        vids = vids.groupby("channel_id", sort=True).head(config.max_videos_per_channel).reset_index(drop=True)

    text = [video_text(t, d) for t, d in zip(vids["title"], vids["description"])]
    usable = np.array([letter_count(t) >= config.min_letters for t in text], dtype=bool)
    vectors = encoder.encode([t for t, u in zip(text, usable) if u])
    if len(vectors) and not np.isfinite(vectors).all():
        raise TopicError("encoder returned non-finite values")
    dim = int(vectors.shape[1]) if len(vectors) else 0

    emb_col: list[Any] = [None] * len(vids)
    for i, v in zip(np.flatnonzero(usable), vectors):
        emb_col[i] = _l2(v[None, :])[0].astype(np.float64).tolist()
    videos = pd.DataFrame({
        "video_id": vids["video_id"].astype("string"), "channel_id": vids["channel_id"].astype("string"),
        "published_at": pd.to_datetime(vids["published_at"], utc=True),
        "text_status": np.where(usable, "ok", "insufficient_text"),
        "text_chars": [len(t) for t in text],
        "text_sha256": [hashlib.sha256(t.encode()).hexdigest() for t in text],   # provenance, not the text
        "embedding": pd.Series(emb_col, dtype=pd.ArrowDtype(pa.list_(pa.float64()))),
    }).sort_values(["channel_id", "video_id"]).reset_index(drop=True)

    profiles, prof_matrix = _profiles(videos, channels, dim, config)
    similarity = _similarity(profiles, prof_matrix)

    experiment_id = make_experiment_id(info.snapshot_id, as_of, config, encoder)
    common = {"snapshot_id": info.snapshot_id, "experiment_id": experiment_id}
    videos, profiles, similarity = (df.assign(**common) for df in (videos, profiles, similarity))
    result = TopicResult(info.snapshot_id, experiment_id, as_of, videos, profiles, similarity)
    if config.n_topics:
        result.topics, result.video_topics, cluster_info = _cluster(videos, config)
    else:
        cluster_info = {"enabled": False}

    result.metadata = {
        "experiment_id": experiment_id, "snapshot_id": info.snapshot_id,
        "as_of": as_of.isoformat().replace("+00:00", "Z"), "scope": "snapshot-level semantic similarity",
        "model": {"name": encoder.name, "version": encoder.version, "backend": config.backend,
                  "role": "primary" if config.backend == "e5" else "exploratory baseline"},
        "preprocessing": {"version": PREPROCESSING_VERSION, "fields": ["title", f"description[:{DESCRIPTION_CHARS}]"],
                          "steps": ["NFC", "remove URLs and e-mails", "drop '#'", "remove control characters",
                                    "collapse whitespace", "no lowercasing / stop-word removal"],
                          "insufficient_text": f"fewer than {config.min_letters} letters after cleaning"},
        "embedding_dimension": dim,
        "aggregation": "channel profile = L2-normalized mean of the channel's L2-normalized usable video "
                       "embeddings (equal weight per video)"
                       + (f"; at most {config.max_videos_per_channel} most recent videos" if config.max_videos_per_channel else ""),
        "similarity": {"primary": "topic_similarity = cosine(profile_A, profile_B), range [-1, 1], symmetric",
                       "secondary": "topic_similarity_centered = cosine after subtracting the mean profile of this "
                                    "snapshot's channels (removes the component shared by all channels; "
                                    "within-snapshot comparison only)"},
        "clustering": cluster_info, "config": config.to_dict(),
        "coverage": {"videos": int(len(videos)), "usable": int((videos["text_status"] == "ok").sum()),
                     "insufficient_text": int((videos["text_status"] == "insufficient_text").sum()),
                     "channels_with_profile": int(profiles["profile_available"].sum()), "channels": int(len(profiles))},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
        "note": "topic_similarity measures content-semantic similarity only; it does not show audience overlap, "
                "audience migration, subscriber movement, causality or conversion, and is not an Audience Bridge Score.",
    }
    result.metadata["validation"] = validate(result)
    return result


def _profiles(videos: pd.DataFrame, channels: list[str], dim: int, config: TopicConfig):
    rows, mats = [], []
    for ch in channels:
        v = videos[videos["channel_id"] == ch]
        ok = v[v["text_status"] == "ok"]
        total, n_ok = len(v), len(ok)
        available = n_ok >= max(1, config.min_videos_per_profile) and dim > 0
        prof = _l2(np.mean(np.array([list(e) for e in ok["embedding"]]), axis=0)[None, :])[0] if available else None
        if prof is not None and not np.linalg.norm(prof) > 0:
            prof, available = None, False   # zero vector: no profile rather than a fake direction
        rows.append({"channel_id": ch, "total_videos": total, "usable_videos": n_ok,
                     "insufficient_text_videos": total - n_ok,
                     "coverage_ratio": (n_ok / total) if total else None, "profile_available": available,
                     "profile": prof.astype(np.float64).tolist() if prof is not None else None})
        mats.append(prof)
    df = pd.DataFrame(rows)
    df = df.astype({"channel_id": "string", "total_videos": "Int64", "usable_videos": "Int64",
                    "insufficient_text_videos": "Int64", "coverage_ratio": "float64", "profile_available": "bool"})
    df["profile"] = pd.Series(df["profile"].tolist(), dtype=pd.ArrowDtype(pa.list_(pa.float64())))
    return df, mats


def _similarity(profiles: pd.DataFrame, mats: list) -> pd.DataFrame:
    ids = profiles["channel_id"].tolist()
    avail = [m is not None for m in mats]
    P = np.array([m if m is not None else np.zeros(len(next((x for x in mats if x is not None), [])))
                  for m in mats]) if any(avail) else np.zeros((len(ids), 0))
    centered = None
    if any(avail):
        mean = P[avail].mean(axis=0)
        C = np.where(np.array(avail)[:, None], P - mean, 0.0)
        norms = np.linalg.norm(C, axis=1)
        centered = np.divide(C, norms[:, None], out=np.zeros_like(C), where=norms[:, None] > 0)
    rows = []
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if i == j:
                continue
            both = avail[i] and avail[j]
            sim = cosine(P[i], P[j]) if both else None
            cen = (cosine(centered[i], centered[j]) if both and centered is not None else None)
            rows.append({"source_channel_id": f"channel:{a}", "destination_channel_id": f"channel:{b}",
                         "topic_similarity": sim, "topic_similarity_centered": cen, "both_profiles_available": both})
    cols = {"source_channel_id": "string", "destination_channel_id": "string", "topic_similarity": "float64",
            "topic_similarity_centered": "float64", "both_profiles_available": "bool"}
    return pd.DataFrame(rows, columns=list(cols)).astype(cols)


def cosine(a: np.ndarray, b: np.ndarray) -> float | None:
    """cos(A, B) = A.B / (|A| |B|); None for a zero vector (undefined, never 0 or NaN)."""
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return None
    return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))


def _cluster(videos: pd.DataFrame, config: TopicConfig):
    from sklearn.cluster import KMeans

    ok = videos[videos["text_status"] == "ok"].sort_values("video_id")
    k = int(config.n_topics)
    needed = k * config.min_videos_per_topic
    if k < 2 or len(ok) < needed:
        return None, None, {"enabled": True, "skipped": True,
                            "reason": f"need >= {needed} usable videos for {k} topics, have {len(ok)}"}
    X = np.array([list(e) for e in ok["embedding"]])
    labels = KMeans(n_clusters=k, random_state=config.seed, n_init=10).fit_predict(X)
    # stable topic ids: order clusters by size (desc), then by smallest member video id
    order = sorted(range(k), key=lambda c: (-int((labels == c).sum()), ok["video_id"][labels == c].min()))
    remap = {c: f"t{i:02d}" for i, c in enumerate(order)}
    vt = pd.DataFrame({"video_id": ok["video_id"].to_numpy(), "topic_id": [remap[c] for c in labels], "weight": 1.0})
    topics = (vt.groupby("topic_id").size().rename("video_count").reset_index()
              .assign(label=lambda d: "cluster " + d["topic_id"]))   # no fabricated semantic labels
    return topics[["topic_id", "label", "video_count"]], vt.sort_values(["topic_id", "video_id"]).reset_index(drop=True), \
        {"enabled": True, "skipped": False, "method": "KMeans", "n_topics": k, "seed": config.seed,
         "assignment": "hard (weight 1.0)", "compatible_with": "hetero_graph.build_graph(topics=, video_topics=)"}


def make_experiment_id(snapshot_id: str, as_of: datetime, config: TopicConfig, encoder) -> str:
    payload = json.dumps({"snapshot": snapshot_id, "as_of": as_of.isoformat(), "config": config.to_dict(),
                          "model": [encoder.name, encoder.version], "pre": PREPROCESSING_VERSION,
                          "method": METHOD_VERSION}, sort_keys=True)
    return f"top-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


# --- validation ------------------------------------------------------------------------------

def validate(result: TopicResult) -> dict[str, Any]:
    errors = []
    v, p, s = result.videos, result.profiles, result.similarity
    if v["video_id"].duplicated().any():
        errors.append("duplicate video representations")
    if p["channel_id"].duplicated().any():
        errors.append("duplicate channel profiles")
    if not v["channel_id"].isin(p["channel_id"]).all():
        errors.append("videos reference channels without a profile row")
    dims = {len(e) for e in v["embedding"].dropna()} | {len(e) for e in p["profile"].dropna()}
    if len(dims) > 1:
        errors.append(f"inconsistent embedding dimensions {sorted(dims)}")
    for col, df in (("embedding", v), ("profile", p)):
        if any(not np.isfinite(np.array(list(e))).all() for e in df[col].dropna()):
            errors.append(f"non-finite values in {col}")
    if ((v["text_status"] == "ok") != v["embedding"].notna()).any():
        errors.append("embedding present for insufficient_text video, or missing for a usable one")
    vals = s["topic_similarity"].dropna()
    if ((vals < -1 - 1e-9) | (vals > 1 + 1e-9)).any():
        errors.append("topic_similarity outside [-1, 1]")
    sym = s.merge(s, left_on=["source_channel_id", "destination_channel_id"],
                  right_on=["destination_channel_id", "source_channel_id"], suffixes=("", "_r"))
    if not np.allclose(sym["topic_similarity"].fillna(9.0), sym["topic_similarity_r"].fillna(9.0), atol=1e-12):
        errors.append("topic_similarity is not symmetric")
    if s["topic_similarity"].isna().ne(~s["both_profiles_available"]).any():
        errors.append("similarity present without both profiles (or missing with both)")
    for df in (v, p, s):
        if (df["snapshot_id"] != result.snapshot_id).any():
            errors.append("foreign snapshot_id")
    if result.video_topics is not None:
        if not result.video_topics["video_id"].isin(v.loc[v["text_status"] == "ok", "video_id"]).all():
            errors.append("topic assigned to an unknown or insufficient_text video")
        if not result.video_topics["topic_id"].isin(result.topics["topic_id"]).all():
            errors.append("invalid topic ids")
    if errors:
        raise TopicError("topic validation failed: " + "; ".join(errors))
    return {"passed": True, "symmetric": True}


# --- persistence ----------------------------------------------------------------------------

def topics_dir(snapshot_id: str, experiment_id: str) -> Path:
    return hg.graph_dir(snapshot_id).parent / TOPICS_DIR / experiment_id


def save(result: TopicResult) -> Path:
    """Write once per experiment; an existing identical experiment is accepted."""
    target = topics_dir(result.snapshot_id, result.experiment_id)
    if (target / "topic_run.json").is_file():
        existing = load(target)
        if existing.similarity.equals(result.similarity):
            return target
        raise FileExistsError(f"topic experiment {result.experiment_id} already exists with different outputs")
    staging = target.with_name(f".{target.name}.staging")
    write_dataset(result.videos, staging / "video_semantic_embeddings.parquet", overwrite=True)
    write_dataset(result.profiles, staging / "channel_semantic_profiles.parquet", overwrite=True)
    write_dataset(result.similarity, staging / "channel_topic_similarity.parquet", overwrite=True)
    if result.topics is not None:
        write_dataset(result.topics, staging / "topics.parquet", overwrite=True)
        write_dataset(result.video_topics, staging / "video_topics.parquet", overwrite=True)
    (staging / "topic_run.json").write_text(json.dumps(result.metadata, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


def load(directory: Path) -> TopicResult:
    meta = json.loads((directory / "topic_run.json").read_text(encoding="utf-8"))
    topics = read_dataset(directory / "topics.parquet") if (directory / "topics.parquet").is_file() else None
    vt = read_dataset(directory / "video_topics.parquet") if (directory / "video_topics.parquet").is_file() else None
    sim = read_dataset(directory / "channel_topic_similarity.parquet")
    return TopicResult(meta["snapshot_id"], meta["experiment_id"],
                       datetime.fromisoformat(meta["as_of"].replace("Z", "+00:00")),
                       read_dataset(directory / "video_semantic_embeddings.parquet"),
                       read_dataset(directory / "channel_semantic_profiles.parquet"),
                       sim.astype({"topic_similarity": "float64", "topic_similarity_centered": "float64"}),
                       topics, vt, meta)


def _l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return np.divide(x, n, out=np.zeros_like(x, dtype=float), where=n > 0)


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="topic_similarity", description="Component 3 topic similarity.")
    ap.add_argument("--snapshot", help="research snapshot id (default: latest)")
    ap.add_argument("--backend", choices=["e5", "char_lsa"], default="e5")
    ap.add_argument("--topics", type=int, help="optional number of KMeans topics")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    try:
        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        result = run(sid, TopicConfig(backend=args.backend, n_topics=args.topics, seed=args.seed))
        out = save(result)
    except (TopicError, FileExistsError, snapshots.SnapshotNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    m = result.metadata
    c = m["coverage"]
    print(f"Topic similarity {result.experiment_id} ({m['model']['name']}, {m['model']['role']}) on {sid} -> {out}")
    print(f"  videos {c['videos']} (usable {c['usable']}, insufficient_text {c['insufficient_text']}); "
          f"channel profiles {c['channels_with_profile']}/{c['channels']}; dimension {m['embedding_dimension']}")
    if m["clustering"].get("enabled"):
        print(f"  clustering: {m['clustering']}")
    s = result.similarity.dropna(subset=["topic_similarity"])
    s = s[s.source_channel_id < s.destination_channel_id]
    print(f"  topic_similarity range {s.topic_similarity.min():.3f} .. {s.topic_similarity.max():.3f}; "
          f"centered {s.topic_similarity_centered.min():.3f} .. {s.topic_similarity_centered.max():.3f}")
    for r in s.sort_values("topic_similarity_centered", ascending=False).head(3).itertuples():
        print(f"    {r.source_channel_id} ~ {r.destination_channel_id}: cosine {r.topic_similarity:.3f}, "
              f"centered {r.topic_similarity_centered:.3f}")
    print("  (content-semantic similarity only; not an Audience Bridge Score)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
