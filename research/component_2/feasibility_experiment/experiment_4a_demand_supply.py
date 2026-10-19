"""Experiment 4A: demand-anchored topic space and Jensen-Shannon gaps for one channel.

1. Comments of the channel from the training pool only (held-out and
   quarantined comments are never read).
2. The Experiment 3E meaningful filter and the Experiment 3D demand classifier
   (multilingual-e5 + logistic regression, trained on all of batch 1) mark
   meaningful comments and explicit requests.
3. Embeddings are centred within each script group (Sinhala, Latin, mixed)
   and within each domain, because raw multilingual-e5 vectors cluster by
   script and by writing style (titles versus comments) before content.
   BERTopic with k-means clustering then discovers audience topics from the
   meaningful comments, and each video is assigned to its nearest topic
   centroid in the same centred space.
   Request probabilities are corrected from the balanced training prior to the
   natural request rate among meaningful comments (prior-shift correction,
   Saerens et al. 2002) and summed into expected request counts.
4. Per season window, demand (meaningful comments), requests and supply
   (videos) become topic distributions. Jensen-Shannon divergence (base 2)
   summarises the mismatch; per-topic contributions, signed shares, request
   counts and unique requesters locate it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .build_expanded_corpus import DEFAULT_OUTPUT_DIR as CORPUS_DIR
from .build_expanded_corpus import TRAINING_ROLES, ExpandedCorpusGuard
from .experiment_3d_classifiers import embed_e5, load_batch
from .experiment_3e_meaningful import load_meaningful_batch
from research.component_2.src.text_processing import script_features
from .supply_topics import build_supply_documents


SEED = 42
N_TOPICS = 15
SENSITIVITY_K = (10, 15, 20, 25)
# Share of actionable requests among meaningful comments in the random batch-1 sample (12/110).
NATURAL_REQUEST_PRIOR = 12 / 110
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_4a"
# Dream Star season structure observed in the upload history (Experiment 3A).
DEFAULT_WINDOWS = {
    "season_2025": ("2025-04-01", "2026-02-01"),
    "off_season_2026": ("2026-02-01", "2026-09-15"),
    "new_season_2026": ("2026-09-15", "2026-11-01"),
}


def jsd_components(p: np.ndarray, q: np.ndarray) -> tuple[float, np.ndarray]:
    """Base-2 Jensen-Shannon divergence and each topic's additive contribution."""

    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    if p.shape != q.shape or p.sum() <= 0 or q.sum() <= 0 or (p < 0).any() or (q < 0).any():
        raise ValueError("Distributions must be non-negative, non-empty and the same length")
    p, q = p / p.sum(), q / q.sum()
    m = (p + q) / 2

    def term(a: np.ndarray) -> np.ndarray:
        out = np.zeros_like(a)
        mask = a > 0
        out[mask] = a[mask] * np.log2(a[mask] / m[mask])
        return out

    contributions = 0.5 * term(p) + 0.5 * term(q)
    return float(contributions.sum()), contributions


def load_channel_comments(channel: str, corpus_dir: Path = CORPUS_DIR) -> pd.DataFrame:
    comments = pd.read_csv(corpus_dir / "expanded_comments.csv", dtype=str, keep_default_na=False)
    frame = comments.loc[comments["channel_name"].eq(channel) & comments["dataset_role"].isin(TRAINING_ROLES)]
    frame = frame.loc[frame["cleaned_text"].str.strip().ne("")].reset_index(drop=True)
    ExpandedCorpusGuard.load(corpus_dir / "comment_partition_manifest_v2.csv").validate_training_frame(frame[["comment_id"]])
    return frame


def train_filters() -> tuple[LogisticRegression, LogisticRegression]:
    """Fit the 3E meaningful filter and the 3D demand classifier on all batch-1 labels."""

    meaningful = load_meaningful_batch()
    demand = load_batch()
    models = []
    for frame in (meaningful, demand):
        model = LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0, random_state=SEED)
        model.fit(embed_e5(frame["comment_text"].tolist()), frame["y"].to_numpy())
        models.append(model)
    return models[0], models[1]


def script_group(text: str) -> str:
    features = script_features(text)
    if features["mixed_sinhala_latin"]:
        return "mixed"
    return "sinhala" if features["has_sinhala"] else "latin"


def center_by_group(embeddings: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Remove each group's mean direction (script or domain style), then re-normalise."""

    centred = np.asarray(embeddings, dtype=float).copy()
    for group in np.unique(groups):
        rows = groups == group
        centred[rows] -= centred[rows].mean(axis=0)
    norms = np.linalg.norm(centred, axis=1, keepdims=True)
    return centred / np.where(norms == 0, 1, norms)


def prior_shift(p: np.ndarray, target_prior: float, train_prior: float = 0.5) -> np.ndarray:
    """Re-weight posterior odds from the training class prior to the target prior."""

    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    odds = p / (1 - p) * (target_prior / (1 - target_prior)) / (train_prior / (1 - train_prior))
    return odds / (1 + odds)


def fit_topics(texts: list[str], embeddings: np.ndarray, k: int = N_TOPICS) -> tuple[Any, np.ndarray]:
    from bertopic import BERTopic
    from bertopic.dimensionality import BaseDimensionalityReduction
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import CountVectorizer

    from .supply_topics import tokenize

    model = BERTopic(
        embedding_model=None,
        umap_model=BaseDimensionalityReduction(),
        hdbscan_model=KMeans(n_clusters=k, random_state=SEED, n_init=10),
        vectorizer_model=CountVectorizer(tokenizer=tokenize, lowercase=False, token_pattern=None, min_df=3),
        top_n_words=10,
    )
    topics, _ = model.fit_transform(texts, embeddings=embeddings)
    return model, np.asarray(topics)


def assign_to_centroids(topic_ids: np.ndarray, comment_emb: np.ndarray, video_emb: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[int]]:
    labels = sorted(set(topic_ids.tolist()))
    centroids = np.vstack([comment_emb[topic_ids == t].mean(axis=0) for t in labels])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    sims = video_emb @ centroids.T
    best = sims.argmax(axis=1)
    return np.array([labels[i] for i in best]), sims.max(axis=1), labels


def window_table(comments: pd.DataFrame, videos: pd.DataFrame, labels: list[int], start: str, end: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Per-topic demand, expected requests and supply for one time window."""

    c_time = pd.to_datetime(comments["published_at"], utc=True, format="ISO8601")
    v_time = pd.to_datetime(videos["published_at"], utc=True, format="ISO8601")
    lo, hi = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    c = comments.loc[(c_time >= lo) & (c_time < hi)]
    v = videos.loc[(v_time >= lo) & (v_time < hi)]
    flagged = c.loc[c["is_request"]]
    table = pd.DataFrame({"topic": labels})
    table["meaningful_comments"] = table["topic"].map(c["topic"].value_counts()).fillna(0).astype(int)
    table["expected_requests"] = table["topic"].map(c.groupby("topic")["p_request_adj"].sum()).fillna(0.0)
    table["flagged_requests"] = table["topic"].map(flagged["topic"].value_counts()).fillna(0).astype(int)
    table["unique_requesters"] = table["topic"].map(flagged.groupby("topic")["author_hash"].nunique()).fillna(0).astype(int)
    table["videos"] = table["topic"].map(v["topic"].value_counts()).fillna(0).astype(int)
    stats: dict[str, Any] = {
        "meaningful_comments": int(len(c)),
        "expected_requests": float(c["p_request_adj"].sum()),
        "flagged_requests": int(len(flagged)),
        "videos": int(len(v)),
    }
    if len(c) and len(v):
        p = table["meaningful_comments"].to_numpy(float)
        q = table["videos"].to_numpy(float)
        stats["jsd_interest_vs_supply"], contrib = jsd_components(p, q)
        stats["jsd_requests_vs_supply"], _ = jsd_components(table["expected_requests"].to_numpy(float), q)
        table["demand_share"] = p / p.sum()
        table["supply_share"] = q / q.sum()
        table["signed_gap"] = table["demand_share"] - table["supply_share"]
        table["jsd_contribution"] = contrib
    return table, stats


def topic_keywords(model: Any, labels: list[int], n: int = 8) -> dict[int, str]:
    return {int(t): " ".join(w for w, _ in (model.get_topic(t) or [])[:n] if w) for t in labels}


def run(channel: str = "Dream Star", output_dir: Path = DEFAULT_OUTPUT_DIR, windows: dict[str, tuple[str, str]] = DEFAULT_WINDOWS) -> dict[str, Any]:
    out = output_dir / channel.lower().replace(" ", "_")
    out.mkdir(parents=True, exist_ok=True)
    comments = load_channel_comments(channel)
    cache = out / "comment_embeddings.npy"
    if cache.exists() and np.load(cache).shape[0] == len(comments):
        comment_emb = np.load(cache)
    else:
        comment_emb = embed_e5(comments["normalized_text"].tolist())
        np.save(cache, comment_emb)

    meaningful_model, demand_model = train_filters()
    comments["p_meaningful"] = meaningful_model.predict_proba(comment_emb)[:, 1]
    keep = comments["p_meaningful"].ge(0.5).to_numpy()
    meaningful = comments.loc[keep].reset_index(drop=True)
    raw_emb = comment_emb[keep]
    meaningful["p_request"] = demand_model.predict_proba(raw_emb)[:, 1]
    meaningful["p_request_adj"] = prior_shift(meaningful["p_request"].to_numpy(), NATURAL_REQUEST_PRIOR)
    meaningful["is_request"] = meaningful["p_request_adj"].ge(0.5)
    meaningful["script"] = meaningful["normalized_text"].map(script_group)
    centred = center_by_group(raw_emb, meaningful["script"].to_numpy())

    videos_all = pd.read_csv(CORPUS_DIR / "expanded_videos.csv", dtype=str, keep_default_na=False)
    videos = build_supply_documents(videos_all.loc[videos_all["channel_name"].eq(channel)]).reset_index(drop=True)
    video_cache = out / "video_embeddings.npy"
    if video_cache.exists() and np.load(video_cache).shape[0] == len(videos):
        video_emb = np.load(video_cache)
    else:
        video_emb = embed_e5(videos["document"].tolist())
        np.save(video_cache, video_emb)
    videos["script"] = videos["document"].map(script_group)
    video_centred = center_by_group(video_emb, videos["script"].to_numpy())

    sensitivity: dict[str, Any] = {}
    for k in SENSITIVITY_K:
        model_k, topics_k = fit_topics(meaningful["normalized_text"].tolist(), centred, k)
        assigned_k, _, labels_k = assign_to_centroids(topics_k, centred, video_centred)
        tmp_c = meaningful.assign(topic=topics_k)
        tmp_v = videos.assign(topic=assigned_k)
        sensitivity[str(k)] = {
            name: round(window_table(tmp_c, tmp_v, labels_k, start, end)[1].get("jsd_interest_vs_supply", float("nan")), 4)
            for name, (start, end) in windows.items()
        }
        if k == N_TOPICS:
            topic_model, topic_ids, assigned, labels = model_k, topics_k, assigned_k, labels_k
    meaningful["topic"] = topic_ids
    videos["topic"] = assigned
    videos["topic_similarity"] = (video_centred @ np.vstack([
        centred[topic_ids == t].mean(axis=0) / np.linalg.norm(centred[topic_ids == t].mean(axis=0)) for t in labels
    ]).T).max(axis=1)

    words = topic_keywords(topic_model, labels)
    title_overlap = float(np.mean([
        bool(set(words[t].split()) & set(tokenize_title(title))) for t, title in zip(videos["topic"], videos["title"])
    ]))
    summary: dict[str, Any] = {
        "channel": channel,
        "training_pool_comments": int(len(comments)),
        "meaningful_comments": int(len(meaningful)),
        "expected_requests": round(float(meaningful["p_request_adj"].sum()), 1),
        "flagged_requests": int(meaningful["is_request"].sum()),
        "natural_request_prior": round(NATURAL_REQUEST_PRIOR, 4),
        "videos": int(len(videos)),
        "topics": len(labels),
        "video_title_keyword_overlap": round(title_overlap, 3),
        "jsd_by_k": sensitivity,
        "windows": {},
    }
    for name, (start, end) in windows.items():
        table, stats = window_table(meaningful, videos, labels, start, end)
        table["top_words"] = table["topic"].map(words)
        order = "jsd_contribution" if "jsd_contribution" in table else "meaningful_comments"
        table.sort_values(order, ascending=False).to_csv(out / f"topics_{name}.csv", index=False, encoding="utf-8")
        summary["windows"][name] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()}
    overall, stats = window_table(meaningful, videos, labels, "2000-01-01", "2100-01-01")
    overall["top_words"] = overall["topic"].map(words)
    overall.to_csv(out / "topics_overall.csv", index=False, encoding="utf-8")
    summary["overall"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()}
    meaningful[["comment_id", "video_id", "published_at", "script", "topic", "p_meaningful", "p_request", "p_request_adj", "is_request"]].to_csv(
        out / "comment_topics.csv", index=False
    )
    videos[["video_id", "published_at", "title", "script", "topic", "topic_similarity"]].to_csv(out / "video_topics.csv", index=False, encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def tokenize_title(title: str) -> list[str]:
    from .supply_topics import tokenize

    return tokenize(str(title))


def main() -> int:
    parser = argparse.ArgumentParser(description="Experiment 4A demand-anchored topics and JSD gaps.")
    parser.add_argument("--channel", default="Dream Star")
    args = parser.parse_args()
    print(json.dumps(run(channel=args.channel), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
