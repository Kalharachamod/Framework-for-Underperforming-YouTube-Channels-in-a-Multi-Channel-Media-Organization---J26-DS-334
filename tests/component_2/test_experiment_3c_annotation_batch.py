from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.component_2.feasibility_experiment.prepare_experiment_3c import (
    ANNOTATION_COLUMNS,
    CONTEXT_COLUMNS,
    _round_robin,
    build_workbook_rows,
    similarity_candidates,
    stratified_random,
    write_workbook,
)


def _development(n_per_channel=10):
    rows = []
    for channel in ("Dream Star", "FM Derana"):
        for i in range(n_per_channel):
            rows.append(
                {
                    "comment_id": f"{channel[:2]}-{i}",
                    "video_id": f"vid-{channel[:2]}",
                    "channel_name": channel,
                    "parent_comment_id": "",
                    "is_reply": "False",
                    "published_at": "2026-01-01T00:00:00Z",
                    "raw_comment_text": f"comment {i} ගීතය",
                    "dataset_role": "expanded_development_pool",
                }
            )
    return pd.DataFrame(rows)


class AnnotationBatchTests(unittest.TestCase):
    def test_random_sample_is_stratified_reproducible_and_excludes_taken(self):
        dev = _development()
        a = stratified_random(dev, {"Dr-0", "Dr-1"}, per_channel=3)
        b = stratified_random(dev, {"Dr-0", "Dr-1"}, per_channel=3)
        self.assertEqual(a["comment_id"].tolist(), b["comment_id"].tolist())
        self.assertEqual(a["channel_name"].value_counts().to_dict(), {"Dream Star": 3, "FM Derana": 3})
        self.assertFalse(a["comment_id"].isin({"Dr-0", "Dr-1"}).any())

    def test_round_robin_balances_and_skips_excluded(self):
        chosen = _round_robin([["a", "b", "c"], ["x", "a", "y"]], limit=4, excluded={"b"})
        self.assertEqual(chosen, ["a", "x", "c", "y"])

    def test_similarity_keeps_only_positive_scores(self):
        scores = np.array([[0.9, 0.0, 0.5], [0.0, 0.0, 0.2]])
        self.assertEqual(similarity_candidates(scores, ["p", "q", "r"], set(), 10), ["p", "r"])

    def test_workbook_is_blind_and_preserves_text(self):
        dev = _development(3)
        selected = dev.assign(source="random")
        videos = pd.DataFrame(
            {"title": ["Song", "Talk"], "video_context": ["", ""], "published_at": ["2026-01-01", "2026-01-02"]},
            index=["vid-Dr", "vid-FM"],
        )
        rows = build_workbook_rows(selected, dev, videos)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch.xlsx"
            write_workbook(rows, path)
            sheet = pd.read_excel(path, sheet_name="Annotate", dtype=str).fillna("")
        self.assertEqual(list(sheet.columns), CONTEXT_COLUMNS + ANNOTATION_COLUMNS)
        self.assertNotIn("source", sheet.columns)
        self.assertTrue((sheet[ANNOTATION_COLUMNS] == "").all().all())
        self.assertTrue(sheet["comment_text"].str.contains("ගීතය").all())
        self.assertEqual(sheet["review_id"].tolist(), [f"B1-{i:04d}" for i in range(1, 7)])


if __name__ == "__main__":
    unittest.main()
