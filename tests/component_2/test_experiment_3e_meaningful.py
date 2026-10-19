from __future__ import annotations

import unittest

import pandas as pd

from research.component_2.feasibility_experiment.annotation_schema import PRIMARY_SIGNALS
from research.component_2.feasibility_experiment.experiment_3e_meaningful import (
    MEANINGFUL,
    NOT_MEANINGFUL,
    heuristic,
)


class MeaningfulFilterTests(unittest.TestCase):
    def test_grouping_covers_every_signal_except_unclear(self):
        self.assertTrue(MEANINGFUL.isdisjoint(NOT_MEANINGFUL))
        self.assertEqual(MEANINGFUL | NOT_MEANINGFUL | {"UNCLEAR"}, set(PRIMARY_SIGNALS))

    def test_heuristic_counts_sinhala_and_latin_words_not_emoji(self):
        texts = pd.Series(["🔥🔥🔥❤️", "great song", "මේකේ full video එකක් නැද්ද", "please upload the full episode"])
        self.assertEqual(heuristic(texts).tolist(), [0, 0, 1, 1])


if __name__ == "__main__":
    unittest.main()
