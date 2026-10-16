import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.component_2.feasibility_experiment.audit import build_sample_frame, dataset_audit
from research.component_2.feasibility_experiment.baseline import SIGNAL_CLASSES, detect_comment, detect_frame
from research.component_2.feasibility_experiment.evaluation import evaluate_review
from research.component_2.feasibility_experiment.gemini_adapter import ExternalEvaluationDisabled, GeminiConfig
from research.component_2.feasibility_experiment.model_adapter import OptionalModelUnavailable, SemanticModelConfig
from research.component_2.feasibility_experiment.sampling import make_blinded_review_sample


class FeasibilityExperimentTests(unittest.TestCase):
    def _row(self, comment_id: str, text: str, channel: str = "Ada Derana", title: str = "Sri Lanka news") -> dict[str, str]:
        return {
            "comment_id": comment_id,
            "channel_id": f"channel-{channel}",
            "channel_name": channel,
            "channel_type": "news",
            "video_id": f"video-{comment_id}",
            "video_title": title,
            "video_description": "Public affairs update",
            "video_url": f"https://youtube.com/watch?v=video-{comment_id}",
            "parent_comment_text": "",
            "original_text": text,
            "cleaned_text": text,
            "script_category": "latin_script",
            "sampling_stratum": "test",
        }

    def test_taxonomy_is_separate_and_complete(self):
        self.assertEqual(len(SIGNAL_CLASSES), 8)
        self.assertIn("EXPLICIT_CONTENT_REQUEST", SIGNAL_CLASSES)
        self.assertIn("SPAM_OR_IRRELEVANT", SIGNAL_CLASSES)

    def test_multilingual_actionable_examples_are_candidates(self):
        examples = [
            "Please make another video about Sri Lankan cricket.",
            "මේ ගැන තව video එකක් කරන්න.",
            "Meka gena thawath video ekak danna.",
        ]
        for index, text in enumerate(examples):
            result = detect_comment(self._row(str(index), text))
            self.assertTrue(result["candidate_for_content_demand"], text)
            self.assertIn(result["primary_signal"], {"EXPLICIT_CONTENT_REQUEST", "CONTENT_CHANGE_PREFERENCE"})

    def test_current_topic_question_is_not_automatically_demand(self):
        result = detect_comment(self._row("q", "Is this news true?"))
        self.assertFalse(result["candidate_for_content_demand"])
        self.assertEqual(result["primary_signal"], "TOPICAL_INTEREST_OR_DISCUSSION")

    def test_spam_is_not_a_demand_candidate(self):
        result = detect_comment(self._row("spam", "Earn Rs. 50,000 daily! Contact me for investment opportunities."))
        self.assertFalse(result["candidate_for_content_demand"])
        self.assertEqual(result["primary_signal"], "SPAM_OR_IRRELEVANT")

    def test_negation_and_original_text_are_preserved(self):
        text = "Please do not remove the Sinhala subtitles."
        result = detect_comment(self._row("neg", text))
        self.assertIn("not", text.casefold())
        self.assertTrue(result["candidate_for_content_demand"])

    def test_detection_is_deterministic(self):
        frame = pd.DataFrame([self._row("a", "Please explain this update."), self._row("b", "Great video!")])
        first = detect_frame(frame)
        second = detect_frame(frame)
        pd.testing.assert_frame_equal(first, second)

    def test_blinded_sampling_is_balanced_and_hides_prediction(self):
        rows = [self._row("a1", "Please make another video.", "Ada Derana"), self._row("a2", "Thanks for sharing this.", "Ada Derana")]
        rows += [self._row("b1", "Please explain more.", "TV Derana"), self._row("b2", "Nice", "TV Derana")]
        frame = pd.DataFrame(rows)
        predictions = detect_frame(frame)
        review, manifest = make_blinded_review_sample(frame, predictions, seed=7, candidate_per_channel=1, control_per_channel=1)
        self.assertEqual(len(review), 4)
        self.assertEqual(manifest["review_group"].value_counts().to_dict(), {"candidate": 2, "control": 2})
        self.assertNotIn("primary_signal", review.columns)
        self.assertTrue(review["human_primary_signal"].eq("").all())

    def test_audit_has_aggregate_coverage_only(self):
        frame = pd.DataFrame([self._row("a", "Great video")])
        frame["candidate_for_content_demand"] = False
        frame["primary_signal"] = "ORDINARY_REACTION"
        audit = dataset_audit(frame, "synthetic")
        self.assertEqual(audit["rows"], 1)
        self.assertNotIn("The raw comment", str(audit))

    def test_empty_human_review_does_not_claim_metrics(self):
        review = pd.DataFrame({"review_id": ["review_001"], "human_actionable_content_demand": [""]})
        result = evaluate_review(review)
        self.assertEqual(result["status"], "not_available")

    def test_optional_adapters_are_disabled_without_configuration(self):
        with self.assertRaises(OptionalModelUnavailable):
            SemanticModelConfig.from_environment()
        with self.assertRaises(ExternalEvaluationDisabled):
            GeminiConfig.from_environment()

    def test_existing_sample_loader_is_read_only_and_preserves_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            pd.DataFrame([self._row("a", "මේ ගැන තව video එකක් කරන්න.")]).to_csv(path, index=False)
            loaded = build_sample_frame(path)
            self.assertEqual(loaded.loc[0, "original_text"], "මේ ගැන තව video එකක් කරන්න.")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
