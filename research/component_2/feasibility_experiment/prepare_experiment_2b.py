"""Run the development-only Experiment 2B TF-IDF retrieval study.

This experiment compares word, character, and equally weighted combined
TF-IDF representations. Researcher-reviewed calibration positives are query
seeds, while the frozen Experiment 2A.2 development partition is the only
corpus used for fitting and retrieval. Similarity is candidate evidence, not a
human label or a claim of demand actionability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sklearn.preprocessing import normalize

from .audit import sha256
from .baseline import detect_frame
from .partition_guard import DEFAULT_PARTITION_MANIFEST, PartitionGuard
from .prepare_experiment_2a import build_experiment_source, create_blank_review_template
from .prepare_experiment_2a2 import DEFAULT_CALIBRATION


EXPERIMENT_2B_SEED = 20261019
TOP_K_PER_SEED = 10
REVIEW_QUEUE_SIZE = 60
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_EXISTING_REVIEW = (
    PACKAGE_DIR
    / "outputs"
    / "experiment_2a2"
    / "development_candidate_control_review.csv"
)
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_2b"
REPRESENTATIONS = ("word", "character", "combined")


def _stable_hash(value: object, seed: int, namespace: str) -> str:
    payload = f"{seed}:{namespace}:{value}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_calibration_query_seeds(
    path: str | Path = DEFAULT_CALIBRATION,
    *,
    expected_sha256: str | None = None,
) -> pd.DataFrame:
    """Load only researcher-reviewed actionable calibration examples as queries."""

    calibration_path = Path(path)
    if not calibration_path.exists():
        raise FileNotFoundError(f"Frozen calibration file is missing: {calibration_path}")
    if expected_sha256 and sha256(calibration_path) != expected_sha256:
        raise ValueError("Calibration input differs from the frozen Experiment 2A.2 lock")

    frame = pd.read_csv(
        calibration_path,
        dtype={"comment_id": "string"},
        keep_default_na=False,
    )
    required = {
        "calibration_order",
        "comment_id",
        "original_text",
        "human_actionable_content_demand",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Calibration input is missing columns: {missing}")
    if len(frame) != 40 or frame["comment_id"].nunique() != 40:
        raise ValueError("Expected 40 unique frozen calibration comments")

    seeds = frame[frame["human_actionable_content_demand"].eq("YES")].copy()
    if seeds.empty:
        raise ValueError("No researcher-reviewed actionable calibration queries are available")
    if seeds["original_text"].astype(str).str.strip().eq("").any():
        raise ValueError("A calibration query seed has empty text")
    return seeds[["calibration_order", "comment_id", "original_text"]].reset_index(
        drop=True
    )


def load_development_corpus(
    *,
    manifest_path: str | Path = DEFAULT_PARTITION_MANIFEST,
) -> tuple[pd.DataFrame, PartitionGuard]:
    """Load and validate the exact frozen development partition."""

    guard = PartitionGuard.load(manifest_path)
    source = build_experiment_source()
    development = source[
        source["comment_id"].astype(str).isin(guard.development_comment_ids)
    ].copy()
    development = development.sort_values("comment_id", kind="mergesort").reset_index(
        drop=True
    )
    guard.validate_training_frame(development[["comment_id", "video_id"]])
    actual_ids = set(development["comment_id"].astype(str))
    if actual_ids != set(guard.development_comment_ids):
        raise ValueError("Development source does not match the frozen partition manifest")
    if development["normalized_text"].fillna("").astype(str).str.strip().eq("").any():
        raise ValueError("Development corpus contains empty normalized text")
    return development, guard


def build_tfidf_representations(
    corpus_texts: pd.Series,
    query_texts: pd.Series,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """Fit word and character TF-IDF on development text and transform queries."""

    corpus = corpus_texts.fillna("").astype(str).tolist()
    queries = query_texts.fillna("").astype(str).tolist()
    if not corpus or not queries:
        raise ValueError("TF-IDF retrieval requires non-empty corpus and query collections")

    word_vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        lowercase=True,
        min_df=1,
        sublinear_tf=True,
        norm="l2",
    )
    character_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        lowercase=True,
        min_df=1,
        sublinear_tf=True,
        norm="l2",
    )
    word_corpus = word_vectorizer.fit_transform(corpus)
    word_queries = word_vectorizer.transform(queries)
    character_corpus = character_vectorizer.fit_transform(corpus)
    character_queries = character_vectorizer.transform(queries)

    # Both source matrices are L2-normalized. Concatenating and normalizing
    # gives word and character blocks equal influence in cosine similarity.
    combined_corpus = normalize(
        hstack([word_corpus, character_corpus], format="csr"), norm="l2"
    )
    combined_queries = normalize(
        hstack([word_queries, character_queries], format="csr"), norm="l2"
    )
    corpus_matrices = {
        "word": word_corpus,
        "character": character_corpus,
        "combined": combined_corpus,
    }
    query_matrices = {
        "word": word_queries,
        "character": character_queries,
        "combined": combined_queries,
    }
    for name, matrix in query_matrices.items():
        zero_queries = int(np.count_nonzero(matrix.getnnz(axis=1) == 0))
        if zero_queries:
            raise ValueError(f"{name} representation produced {zero_queries} empty queries")

    def matrix_summary(matrix: Any) -> dict[str, Any]:
        cells = int(matrix.shape[0] * matrix.shape[1])
        return {
            "rows": int(matrix.shape[0]),
            "features": int(matrix.shape[1]),
            "nonzero_values": int(matrix.nnz),
            "density": float(matrix.nnz / cells) if cells else 0.0,
        }

    summaries = {
        name: {
            "configuration": (
                "word unigrams+bigrams; min_df=1; sublinear TF; L2"
                if name == "word"
                else "char_wb 3-5 grams; min_df=1; sublinear TF; L2"
                if name == "character"
                else "equal-block word+character concatenation; L2"
            ),
            **matrix_summary(corpus_matrices[name]),
        }
        for name in REPRESENTATIONS
    }
    return corpus_matrices, query_matrices, summaries


def retrieve_neighbors(
    development: pd.DataFrame,
    seeds: pd.DataFrame,
    corpus_matrices: dict[str, Any],
    query_matrices: dict[str, Any],
    *,
    top_k: int = TOP_K_PER_SEED,
    existing_review_ids: set[str] | None = None,
) -> pd.DataFrame:
    """Return deterministic top-k neighbors for every query and representation."""

    if top_k < 1 or top_k > len(development):
        raise ValueError("top_k must be between 1 and the development corpus size")
    existing = existing_review_ids or set()
    baseline = detect_frame(development).reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    comment_ids = development["comment_id"].astype(str).tolist()

    for representation in REPRESENTATIONS:
        scores = linear_kernel(
            query_matrices[representation], corpus_matrices[representation]
        )
        for query_position, score_row in enumerate(scores):
            positive_positions = [
                position
                for position, score in enumerate(score_row)
                if float(score) > 0.0
            ]
            order = sorted(
                positive_positions,
                key=lambda position: (-float(score_row[position]), comment_ids[position]),
            )[:top_k]
            seed = seeds.iloc[query_position]
            for rank, position in enumerate(order, start=1):
                record = development.iloc[position]
                prediction = baseline.iloc[position]
                rows.append(
                    {
                        "representation": representation,
                        "seed_calibration_order": int(seed["calibration_order"]),
                        "seed_comment_id": str(seed["comment_id"]),
                        "neighbor_rank": rank,
                        "comment_id": str(record["comment_id"]),
                        "video_id": str(record["video_id"]),
                        "channel_name": str(record["channel_name"]),
                        "script_category": str(record["script_category"]),
                        "cosine_similarity": float(score_row[position]),
                        "baseline_candidate_for_content_demand": bool(
                            prediction["candidate_for_content_demand"]
                        ),
                        "baseline_primary_signal": str(prediction["primary_signal"]),
                        "baseline_evidence_span": prediction["evidence_span"],
                        "in_existing_2a2_review_queue": str(record["comment_id"])
                        in existing,
                    }
                )
    return pd.DataFrame(rows)


def aggregate_retrievals(retrievals: pd.DataFrame) -> pd.DataFrame:
    """Collapse repeated neighbors while preserving representation provenance."""

    rows: list[dict[str, Any]] = []
    for comment_id, group in retrievals.groupby("comment_id", sort=True):
        first = group.iloc[0]
        by_method = group.groupby("representation")["cosine_similarity"].max()
        rows.append(
            {
                "comment_id": str(comment_id),
                "video_id": str(first["video_id"]),
                "channel_name": str(first["channel_name"]),
                "script_category": str(first["script_category"]),
                "representations": ";".join(sorted(group["representation"].unique())),
                "representation_count": int(group["representation"].nunique()),
                "matched_seed_count": int(group["seed_comment_id"].nunique()),
                "retrieval_pair_count": int(len(group)),
                "best_neighbor_rank": int(group["neighbor_rank"].min()),
                "reciprocal_rank_support": float((1.0 / group["neighbor_rank"]).sum()),
                "best_cosine_similarity": float(group["cosine_similarity"].max()),
                "word_max_similarity": float(by_method.get("word", np.nan)),
                "character_max_similarity": float(by_method.get("character", np.nan)),
                "combined_max_similarity": float(by_method.get("combined", np.nan)),
                "baseline_candidate_for_content_demand": bool(
                    first["baseline_candidate_for_content_demand"]
                ),
                "baseline_primary_signal": str(first["baseline_primary_signal"]),
                "in_existing_2a2_review_queue": bool(
                    first["in_existing_2a2_review_queue"]
                ),
            }
        )
    return pd.DataFrame(rows)


def select_novel_review_rows(
    aggregated: pd.DataFrame,
    development: pd.DataFrame,
    *,
    review_size: int = REVIEW_QUEUE_SIZE,
    seed: int = EXPERIMENT_2B_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select rule-negative, previously unqueued retrievals for blinded review."""

    if review_size < 1:
        raise ValueError("review_size must be positive")
    eligible = aggregated[
        ~aggregated["baseline_candidate_for_content_demand"]
        & ~aggregated["in_existing_2a2_review_queue"]
    ].copy()
    if len(eligible) < review_size:
        raise ValueError(
            f"Only {len(eligible)} novel rule-negative retrievals are available; "
            f"cannot create a {review_size}-row queue"
        )
    eligible["selection_tiebreak_hash"] = eligible["comment_id"].map(
        lambda value: _stable_hash(value, seed, "selection")
    )
    ranked = eligible.sort_values(
        [
            "representation_count",
            "matched_seed_count",
            "retrieval_pair_count",
            "reciprocal_rank_support",
            "best_cosine_similarity",
            "selection_tiebreak_hash",
        ],
        ascending=[False, False, False, False, False, True],
        kind="mergesort",
    ).head(review_size).copy()
    ranked["selection_priority"] = range(1, len(ranked) + 1)
    ranked["selection_reason"] = (
        "top-k TF-IDF neighbor absent from the existing 2A.2 queue and not selected "
        "by the frozen rule baseline"
    )

    selected_ids = set(ranked["comment_id"].astype(str))
    selected = development[
        development["comment_id"].astype(str).isin(selected_ids)
    ].copy()
    if len(selected) != review_size:
        raise ValueError("Selected retrieval IDs do not map one-to-one to development rows")
    selected["_review_hash"] = selected["comment_id"].map(
        lambda value: _stable_hash(value, seed, "review-order")
    )
    selected = selected.sort_values(
        ["_review_hash", "comment_id"], kind="mergesort"
    ).drop(columns="_review_hash")
    selected = selected.reset_index(drop=True)
    selected["review_order"] = range(1, len(selected) + 1)
    template = create_blank_review_template(selected)
    return template, ranked.reset_index(drop=True)


def representation_comparison(retrievals: pd.DataFrame) -> dict[str, Any]:
    """Summarize top-k set overlap without treating similarity as ground truth."""

    sets = {
        method: set(
            retrievals.loc[
                retrievals["representation"].eq(method), "comment_id"
            ].astype(str)
        )
        for method in REPRESENTATIONS
    }
    overlap: dict[str, dict[str, Any]] = {}
    for left, right in (("word", "character"), ("word", "combined"), ("character", "combined")):
        union = sets[left].union(sets[right])
        intersection = sets[left].intersection(sets[right])
        overlap[f"{left}_vs_{right}"] = {
            "intersection": len(intersection),
            "union": len(union),
            "jaccard": float(len(intersection) / len(union)) if union else 0.0,
        }
    return {
        "unique_retrieved_by_representation": {
            method: len(values) for method, values in sets.items()
        },
        "pairwise_top_k_overlap": overlap,
    }


def validate_outputs(
    development: pd.DataFrame,
    guard: PartitionGuard,
    seeds: pd.DataFrame,
    retrievals: pd.DataFrame,
    review_template: pd.DataFrame,
    selection_manifest: pd.DataFrame,
    existing_review_ids: set[str],
) -> None:
    """Enforce development-only retrieval, blinding, and blank annotations."""

    guard.validate_training_frame(development[["comment_id", "video_id"]])
    guard.validate_training_frame(retrievals[["comment_id", "video_id"]].drop_duplicates())
    guard.validate_training_frame(review_template[["comment_id", "video_id"]])
    if set(seeds["comment_id"].astype(str)).intersection(
        review_template["comment_id"].astype(str)
    ):
        raise ValueError("Calibration query seeds leaked into the development review queue")
    if review_template["comment_id"].duplicated().any():
        raise ValueError("Experiment 2B review queue contains duplicate comments")
    if set(review_template["comment_id"].astype(str)).intersection(existing_review_ids):
        raise ValueError("Experiment 2B review queue overlaps the existing 2A.2 queue")
    if selection_manifest["baseline_candidate_for_content_demand"].any():
        raise ValueError("Experiment 2B novel queue contains a rule-selected candidate")
    forbidden = {
        "representation",
        "representations",
        "cosine_similarity",
        "baseline_candidate_for_content_demand",
        "selection_reason",
    }
    exposed = sorted(forbidden.intersection(review_template.columns))
    if exposed:
        raise ValueError(f"Reviewer-facing queue exposes retrieval provenance: {exposed}")
    human_columns = [
        column
        for column in review_template.columns
        if column.startswith("annotator_")
        or column.startswith("final_")
        or column.startswith("adjudicat")
        or column == "spam_notes"
    ]
    if not review_template[human_columns].fillna("").eq("").all().all():
        raise ValueError("Experiment 2B reviewer queue contains nonblank human fields")


def _render_report(summary: dict[str, Any]) -> str:
    return f"""# Experiment 2B: Development-Only TF-IDF Retrieval Study

## Scope

This is an exploratory retrieval experiment, not a trained classifier and not
an estimate of demand prevalence. Word, character and combined TF-IDF models
were fitted only to the frozen Experiment 2A.2 development partition. The
held-out partition was not used for fitting, query selection, retrieval,
threshold selection or review-queue construction.

- Development corpus: {summary['development_comments']} comments across {summary['development_videos']} videos
- Researcher-reviewed calibration query seeds: {summary['query_seed_count']}
- Maximum neighbors per seed and representation: {summary['top_k_per_seed']} (positive cosine only)
- Retrieval pairs: {summary['retrieval_pairs']}
- Unique retrieved development comments: {summary['unique_retrieved_comments']}
- New blinded rule-negative review rows: {summary['review_queue_rows']}
- Existing Experiment 2A.2 review rows excluded: {summary['existing_review_rows']}

## Representations

- Word TF-IDF: Unicode word unigrams and bigrams. It is interpretable but
  brittle across spelling variation and does not bridge Sinhala and Singlish.
- Character TF-IDF: `char_wb` 3-5 grams. It can capture partial overlap and
  Singlish spelling variants, but shared fragments can also create false
  similarity and Sinhala-script/Latin-script equivalents remain disconnected.
- Combined: equal-block concatenation of normalized word and character
  features. It is an exploratory complement, not automatically a better model.

Feature summaries: `{summary['representation_summaries']}`.

Top-k set comparison: `{summary['representation_comparison']}`.

## Review queue

The queue contains development comments retrieved by at least one TF-IDF
representation that were not selected by the frozen rule baseline and were not
already in the 94-row Experiment 2A.2 review queue. Ranking uses retrieval
support only; the reviewer-facing CSV is shuffled deterministically and hides
the retrieval method, scores, baseline decision and selection provenance.

Queue channels: `{summary['review_channel_counts']}`.

Queue scripts: `{summary['review_script_counts']}`.

Every human annotation field is blank. Human review is required before any
retrieval precision, missed-demand rate or model comparison can be reported.

## Scientific decision

TF-IDF retrieval is the appropriate next step because it is transparent,
offline, reproducible and useful for expanding the annotation pool without
pretending that similarity is actionability. Logistic Regression and Linear
SVM must wait for sufficient independently reviewed development labels.
Genuine uncertainty-based active learning must also wait for a trained,
validated classifier; this experiment is retrieval-assisted annotation.

Multilingual sentence embeddings should be a separate follow-up comparison,
not mixed into this baseline. A small multilingual E5 model is a plausible
CPU-capable first candidate, but Sinhala, Singlish and code-mixed retrieval
quality must be measured on human-reviewed examples. No model was downloaded
or executed in Experiment 2B.

## Limits

The six queries come from a deliberately enriched 40-comment calibration set,
so the retrieval queue is not representative and cannot estimate prevalence.
Cosine scores are not calibrated probabilities and are not directly
comparable across representation families. Selection favors comments similar
to known positive formulations and can miss genuinely novel demand language.
Video context and request target remain human annotation decisions.
"""


def prepare(
    *,
    calibration_path: str | Path = DEFAULT_CALIBRATION,
    manifest_path: str | Path = DEFAULT_PARTITION_MANIFEST,
    existing_review_path: str | Path = DEFAULT_EXISTING_REVIEW,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    seed: int = EXPERIMENT_2B_SEED,
    top_k: int = TOP_K_PER_SEED,
    review_size: int = REVIEW_QUEUE_SIZE,
) -> dict[str, Any]:
    """Run Experiment 2B and write only Git-ignored private artifacts."""

    output = Path(output_dir)
    development, guard = load_development_corpus(manifest_path=manifest_path)
    expected_calibration_hash = str(
        guard.lock.get("input_sha256", {}).get("calibration", "")
    )
    seeds = load_calibration_query_seeds(
        calibration_path,
        expected_sha256=expected_calibration_hash or None,
    )

    existing_path = Path(existing_review_path)
    if not existing_path.exists():
        raise FileNotFoundError(f"Existing Experiment 2A.2 review queue is missing: {existing_path}")
    existing_review = pd.read_csv(
        existing_path, dtype={"comment_id": "string", "video_id": "string"}
    )
    guard.validate_training_frame(existing_review[["comment_id", "video_id"]])
    existing_review_ids = set(existing_review["comment_id"].astype(str))

    corpus_matrices, query_matrices, representation_summaries = (
        build_tfidf_representations(
            development["normalized_text"], seeds["original_text"]
        )
    )
    retrievals = retrieve_neighbors(
        development,
        seeds,
        corpus_matrices,
        query_matrices,
        top_k=top_k,
        existing_review_ids=existing_review_ids,
    )
    aggregated = aggregate_retrievals(retrievals)
    review_template, selection_manifest = select_novel_review_rows(
        aggregated,
        development,
        review_size=review_size,
        seed=seed,
    )
    validate_outputs(
        development,
        guard,
        seeds,
        retrievals,
        review_template,
        selection_manifest,
        existing_review_ids,
    )

    summary = {
        "experiment": "2B",
        "seed": seed,
        "partition_manifest_fingerprint": guard.fingerprint,
        "development_comments": len(development),
        "development_videos": int(development["video_id"].nunique()),
        "query_seed_count": len(seeds),
        "top_k_per_seed": top_k,
        "retrieval_pairs": len(retrievals),
        "unique_retrieved_comments": int(retrievals["comment_id"].nunique()),
        "unique_rule_negative_retrievals": int(
            (~aggregated["baseline_candidate_for_content_demand"]).sum()
        ),
        "novel_rule_negative_retrievals": int(
            (
                ~aggregated["baseline_candidate_for_content_demand"]
                & ~aggregated["in_existing_2a2_review_queue"]
            ).sum()
        ),
        "existing_review_rows": len(existing_review),
        "review_queue_rows": len(review_template),
        "review_queue_videos": int(review_template["video_id"].nunique()),
        "review_channel_counts": {
            str(key): int(value)
            for key, value in review_template["channel_name"]
            .value_counts()
            .sort_index()
            .items()
        },
        "review_script_counts": {
            str(key): int(value)
            for key, value in review_template["script_category"]
            .value_counts()
            .sort_index()
            .items()
        },
        "representation_summaries": representation_summaries,
        "representation_comparison": representation_comparison(retrievals),
        "inputs_sha256": {
            "calibration": sha256(calibration_path),
            "partition_manifest": sha256(manifest_path),
            "existing_development_review": sha256(existing_review_path),
        },
    }

    _write_csv(output / "tfidf_retrieval_neighbors.csv", retrievals)
    _write_csv(output / "tfidf_retrieval_selection_manifest.csv", selection_manifest)
    _write_csv(output / "tfidf_novel_candidate_review.csv", review_template)
    _write_json(output / "experiment_2b_summary.json", summary)
    (output / "experiment_2b_report.md").write_text(
        _render_report(summary), encoding="utf-8"
    )
    return {
        "summary": summary,
        "output_dir": output,
        "review_path": output / "tfidf_novel_candidate_review.csv",
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the development-only Experiment 2B TF-IDF retrieval study."
    )
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--partition-manifest", type=Path, default=DEFAULT_PARTITION_MANIFEST)
    parser.add_argument("--existing-review", type=Path, default=DEFAULT_EXISTING_REVIEW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=EXPERIMENT_2B_SEED)
    parser.add_argument("--top-k", type=int, default=TOP_K_PER_SEED)
    parser.add_argument("--review-size", type=int, default=REVIEW_QUEUE_SIZE)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = prepare(
        calibration_path=args.calibration,
        manifest_path=args.partition_manifest,
        existing_review_path=args.existing_review,
        output_dir=args.output_dir,
        seed=args.seed,
        top_k=args.top_k,
        review_size=args.review_size,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, default=str))
    print(f"Private review queue: {result['review_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
