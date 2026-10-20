"""Experiment 3D: first supervised demand classifiers on annotation batch 1.

Binary target: actionable content demand (YES vs NO); UNCLEAR rows are
excluded. Models are compared with video-grouped, stratified 5-fold
cross-validation repeated over several seeds, so no video contributes comments
to both training and testing folds.

Compared:
- frozen rule baseline (``baseline.py``; no training);
- word+character TF-IDF with Logistic Regression;
- word+character TF-IDF with a linear SVM;
- multilingual-e5-small embeddings (pinned revision) with Logistic Regression.

Thresholds are fixed (probability 0.5, SVM margin 0) rather than tuned, and
PR-AUC is reported as the threshold-free comparison. Batch 1 is
demand-enriched and its labels are AI-assisted and researcher-reviewed, so
these are development estimates; final evaluation uses blind held-out labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.svm import LinearSVC

from .baseline import detect_frame
from .build_expanded_corpus import DEFAULT_OUTPUT_DIR as CORPUS_DIR
from .build_expanded_corpus import ExpandedCorpusGuard
from .prepare_experiment_3c import DEFAULT_OUTPUT_DIR as BATCH_DIR
from .supply_topics import E5_MODEL, E5_REVISION


SEEDS = (11, 22, 33, 44, 55)
FOLDS = 5
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_3d"


def load_batch(batch_dir: Path = BATCH_DIR) -> pd.DataFrame:
    labels = pd.read_csv(batch_dir / "annotation_batch1_504.csv", dtype=str, keep_default_na=False)
    batch = pd.read_csv(batch_dir / "annotation_batch1.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    frame = labels.merge(batch[["review_id", "comment_text", "video_title"]], on="review_id", validate="one_to_one")
    frame = frame.loc[frame["actionable_content_demand"].isin(["YES", "NO"])].reset_index(drop=True)
    frame["y"] = frame["actionable_content_demand"].eq("YES").astype(int)
    return frame


def _tfidf(train: list[str], test: list[str]):
    word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)
    x_train = hstack([word.fit_transform(train), char.fit_transform(train)]).tocsr()
    x_test = hstack([word.transform(test), char.transform(test)]).tocsr()
    return x_train, x_test


def tfidf_logreg(train_text, y_train, test_text, _train_idx, _test_idx, seed):
    x_train, x_test = _tfidf(train_text, test_text)
    model = LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0, random_state=seed)
    model.fit(x_train, y_train)
    score = model.predict_proba(x_test)[:, 1]
    return score, (score >= 0.5).astype(int)


def tfidf_svm(train_text, y_train, test_text, _train_idx, _test_idx, seed):
    x_train, x_test = _tfidf(train_text, test_text)
    model = LinearSVC(class_weight="balanced", C=0.5, random_state=seed)
    model.fit(x_train, y_train)
    score = model.decision_function(x_test)
    return score, (score >= 0).astype(int)


def make_e5_logreg(embeddings: np.ndarray) -> Callable:
    def e5_logreg(_train_text, y_train, _test_text, train_idx, test_idx, seed):
        model = LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0, random_state=seed)
        model.fit(embeddings[train_idx], y_train)
        score = model.predict_proba(embeddings[test_idx])[:, 1]
        return score, (score >= 0.5).astype(int)

    return e5_logreg


def embed_e5(texts: list[str]) -> np.ndarray:
    import torch
    from sentence_transformers import SentenceTransformer

    torch.manual_seed(0)
    model = SentenceTransformer(E5_MODEL, revision=E5_REVISION, device="cpu")
    return model.encode([f"query: {t}" for t in texts], batch_size=64, normalize_embeddings=True, show_progress_bar=False)


def cross_validate(frame: pd.DataFrame, models: dict[str, Callable], seeds=SEEDS, folds=FOLDS) -> tuple[pd.DataFrame, pd.DataFrame]:
    texts = frame["comment_text"].tolist()
    y = frame["y"].to_numpy()
    groups = frame["video_id"].to_numpy()
    fold_rows, oof_rows = [], []
    for seed in seeds:
        splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
        for fold, (train_idx, test_idx) in enumerate(splitter.split(texts, y, groups)):
            if set(groups[train_idx]) & set(groups[test_idx]):
                raise RuntimeError("A video appears in both training and test folds")
            train_text = [texts[i] for i in train_idx]
            test_text = [texts[i] for i in test_idx]
            for name, fit in models.items():
                score, pred = fit(train_text, y[train_idx], test_text, train_idx, test_idx, seed)
                fold_rows.append(
                    {
                        "model": name, "seed": seed, "fold": fold,
                        "precision": precision_score(y[test_idx], pred, zero_division=0),
                        "recall": recall_score(y[test_idx], pred, zero_division=0),
                        "f1": f1_score(y[test_idx], pred, zero_division=0),
                        "pr_auc": average_precision_score(y[test_idx], score) if y[test_idx].any() else np.nan,
                    }
                )
                oof_rows += [
                    {"model": name, "seed": seed, "row": int(i), "score": float(s), "pred": int(p), "y": int(y[i])}
                    for i, s, p in zip(test_idx, score, pred)
                ]
    return pd.DataFrame(fold_rows), pd.DataFrame(oof_rows)


def rule_baseline(frame: pd.DataFrame) -> dict[str, float]:
    flags = detect_frame(frame.rename(columns={"comment_text": "original_text"})[["original_text", "video_title"]])
    pred = flags["candidate_for_content_demand"].astype(int).to_numpy()
    y = frame["y"].to_numpy()
    return {
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
    }


def summarize(folds: pd.DataFrame, oof: pd.DataFrame, frame: pd.DataFrame, rule: dict[str, float]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "rows": int(len(frame)), "yes": int(frame["y"].sum()), "videos": int(frame["video_id"].nunique()),
        "folds": FOLDS, "seeds": list(SEEDS), "rule_baseline": {k: round(v, 3) for k, v in rule.items()}, "models": {},
    }
    random_rows = set(np.flatnonzero(frame["source"].eq("random").to_numpy()))
    for name, group in folds.groupby("model"):
        pooled = oof[oof["model"].eq(name)]
        on_random = pooled[pooled["row"].isin(random_rows)]
        summary["models"][name] = {
            **{f"{m}_mean": round(float(group[m].mean()), 3) for m in ("precision", "recall", "f1", "pr_auc")},
            **{f"{m}_sd": round(float(group[m].std()), 3) for m in ("precision", "recall", "f1", "pr_auc")},
            "random_subset_pooled": {
                "precision": round(precision_score(on_random["y"], on_random["pred"], zero_division=0), 3),
                "recall": round(recall_score(on_random["y"], on_random["pred"], zero_division=0), 3),
                "yes_rows_per_seed": int(on_random["y"].sum() / len(SEEDS)),
            },
        }
    return summary


def run(output_dir: Path = DEFAULT_OUTPUT_DIR, use_e5: bool = True) -> dict[str, Any]:
    frame = load_batch()
    ExpandedCorpusGuard.load(CORPUS_DIR / "comment_partition_manifest_v2.csv").validate_training_frame(frame[["comment_id"]])
    models: dict[str, Callable] = {"tfidf_logreg": tfidf_logreg, "tfidf_linear_svm": tfidf_svm}
    if use_e5:
        models["e5_logreg"] = make_e5_logreg(embed_e5(frame["comment_text"].tolist()))
    folds, oof = cross_validate(frame, models)
    summary = summarize(folds, oof, frame, rule_baseline(frame))
    output_dir.mkdir(parents=True, exist_ok=True)
    folds.to_csv(output_dir / "cv_fold_metrics.csv", index=False)
    oof.assign(comment_id=frame["comment_id"].to_numpy()[oof["row"]]).to_csv(output_dir / "cv_out_of_fold_predictions.csv", index=False)
    (output_dir / "experiment_3d_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Experiment 3D demand classifiers with video-grouped CV.")
    parser.add_argument("--no-e5", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(use_e5=not args.no_e5), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
