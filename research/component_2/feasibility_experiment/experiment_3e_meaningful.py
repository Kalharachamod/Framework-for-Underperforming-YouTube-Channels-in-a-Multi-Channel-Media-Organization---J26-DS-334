"""Experiment 3E: meaningful-comment filter for the audience-interest layer.

The interest layer of the gap analysis uses every comment that says something
about content, not only explicit requests. The eight primary signals are
grouped into:

- meaningful: EXPLICIT_CONTENT_REQUEST, CONTENT_CHANGE_PREFERENCE,
  INFORMATION_NEED, CONTENT_QUALITY_FEEDBACK, TOPICAL_INTEREST_OR_DISCUSSION;
- not meaningful: ORDINARY_REACTION, SPAM_OR_IRRELEVANT;
- UNCLEAR rows are excluded.

The same video-grouped repeated cross-validation as Experiment 3D compares a
length/emoji heuristic with TF-IDF and multilingual-e5 classifiers.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

from .build_expanded_corpus import DEFAULT_OUTPUT_DIR as CORPUS_DIR
from .build_expanded_corpus import ExpandedCorpusGuard
from .experiment_3d_classifiers import cross_validate, embed_e5, make_e5_logreg, tfidf_logreg, tfidf_svm
from .prepare_experiment_3c import DEFAULT_OUTPUT_DIR as BATCH_DIR


MEANINGFUL = frozenset({
    "EXPLICIT_CONTENT_REQUEST", "CONTENT_CHANGE_PREFERENCE", "INFORMATION_NEED",
    "CONTENT_QUALITY_FEEDBACK", "TOPICAL_INTEREST_OR_DISCUSSION",
})
NOT_MEANINGFUL = frozenset({"ORDINARY_REACTION", "SPAM_OR_IRRELEVANT"})
HEURISTIC_MIN_WORDS = 4
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_3e"
_WORD = re.compile(r"[\w඀-෿‍]+", re.UNICODE)


def load_meaningful_batch(batch_dir: Path = BATCH_DIR) -> pd.DataFrame:
    labels = pd.read_csv(batch_dir / "annotation_batch1_504.csv", dtype=str, keep_default_na=False)
    batch = pd.read_csv(batch_dir / "annotation_batch1.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    frame = labels.merge(batch[["review_id", "comment_text", "video_title"]], on="review_id", validate="one_to_one")
    frame = frame.loc[frame["primary_signal"].isin(MEANINGFUL | NOT_MEANINGFUL)].reset_index(drop=True)
    frame["y"] = frame["primary_signal"].isin(MEANINGFUL).astype(int)
    return frame


def heuristic(texts: pd.Series) -> np.ndarray:
    """Meaningful if the comment has at least four word tokens (emoji-only comments have none)."""

    return texts.map(lambda t: int(len(_WORD.findall(str(t))) >= HEURISTIC_MIN_WORDS)).to_numpy()


def run(output_dir: Path = DEFAULT_OUTPUT_DIR, use_e5: bool = True) -> dict[str, Any]:
    frame = load_meaningful_batch()
    ExpandedCorpusGuard.load(CORPUS_DIR / "comment_partition_manifest_v2.csv").validate_training_frame(frame[["comment_id"]])
    models: dict[str, Callable] = {"tfidf_logreg": tfidf_logreg, "tfidf_linear_svm": tfidf_svm}
    if use_e5:
        models["e5_logreg"] = make_e5_logreg(embed_e5(frame["comment_text"].tolist()))
    folds, oof = cross_validate(frame, models)
    y = frame["y"].to_numpy()
    pred = heuristic(frame["comment_text"])
    summary: dict[str, Any] = {
        "rows": int(len(frame)), "meaningful": int(y.sum()), "not_meaningful": int(len(y) - y.sum()),
        "videos": int(frame["video_id"].nunique()),
        "heuristic_baseline": {
            "rule": f"at least {HEURISTIC_MIN_WORDS} word tokens",
            "precision": round(precision_score(y, pred), 3), "recall": round(recall_score(y, pred), 3), "f1": round(f1_score(y, pred), 3),
        },
        "models": {
            name: {f"{m}_{s}": round(float(getattr(group[m], s)()), 3) for m in ("precision", "recall", "f1", "pr_auc") for s in ("mean", "std")}
            for name, group in folds.groupby("model")
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    folds.to_csv(output_dir / "cv_fold_metrics.csv", index=False)
    (output_dir / "experiment_3e_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Experiment 3E meaningful-comment filter.")
    parser.add_argument("--no-e5", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(use_e5=not args.no_e5), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
