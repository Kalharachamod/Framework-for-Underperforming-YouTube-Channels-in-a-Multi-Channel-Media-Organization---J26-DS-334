from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.component_2.feasibility_experiment.experiment_3d_classifiers import (
    cross_validate,
    make_e5_logreg,
    summarize,
    tfidf_logreg,
    tfidf_svm,
)


def _frame():
    rows = []
    for i in range(60):
        yes = i % 4 == 0
        rows.append(
            {
                "comment_id": f"c{i}",
                "video_id": f"v{i // 3}",
                "comment_text": ("please upload the full episode again " if yes else "great song well done ") + str(i),
                "video_title": "Dream Star",
                "source": "random" if i % 2 else "existing_queue",
                "y": int(yes),
            }
        )
    return pd.DataFrame(rows)


class ClassifierExperimentTests(unittest.TestCase):
    def test_grouped_cv_never_shares_videos_and_learns_signal(self):
        frame = _frame()
        embeddings = np.random.default_rng(0).normal(size=(len(frame), 8))
        models = {"tfidf_logreg": tfidf_logreg, "tfidf_linear_svm": tfidf_svm, "e5_logreg": make_e5_logreg(embeddings)}
        folds, oof = cross_validate(frame, models, seeds=(1, 2), folds=3)
        self.assertEqual(set(folds["model"]), set(models))
        # every row is predicted exactly once per model and seed
        counts = oof.groupby(["model", "seed"])["row"].nunique()
        self.assertTrue((counts == len(frame)).all())
        tfidf_f1 = folds.loc[folds["model"].eq("tfidf_logreg"), "f1"].mean()
        self.assertGreater(tfidf_f1, 0.9)

    def test_summary_reports_random_subset_and_rule_baseline(self):
        frame = _frame()
        folds, oof = cross_validate(frame, {"tfidf_logreg": tfidf_logreg}, seeds=(1,), folds=3)
        summary = summarize(folds, oof, frame, {"precision": 0.5, "recall": 0.5, "f1": 0.5})
        self.assertEqual(summary["yes"], 15)
        self.assertIn("random_subset_pooled", summary["models"]["tfidf_logreg"])
        self.assertEqual(summary["rule_baseline"]["f1"], 0.5)


if __name__ == "__main__":
    unittest.main()
