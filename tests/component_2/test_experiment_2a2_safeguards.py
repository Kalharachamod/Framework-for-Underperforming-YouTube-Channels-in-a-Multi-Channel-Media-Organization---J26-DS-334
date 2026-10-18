from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.component_2.feasibility_experiment.annotation_schema import (
    ANNOTATION_SCHEMA_VERSION,
    REVIEW_ANNOTATION_FIELDS,
    TEXT_PROVENANCE_VERSION,
    normalized_text,
    raw_text_sha256,
    validate_annotation_frame,
)
from research.component_2.feasibility_experiment.partition_guard import (
    PARTITION_FINGERPRINT_ALGORITHM,
    PartitionGuard,
    PartitionIntegrityError,
    load_partition_lock,
    manifest_fingerprint,
)
from research.component_2.feasibility_experiment.prepare_experiment_2a import (
    create_blank_review_template,
)


class Experiment2A2PartitionGuardTests(unittest.TestCase):
    def setUp(self):
        self.manifest = pd.DataFrame(
            [
                {"comment_id": "dev-1", "video_id": "video-dev", "dataset_role": "development_pool"},
                {"comment_id": "dev-2", "video_id": "video-dev", "dataset_role": "development_pool"},
                {"comment_id": "held-1", "video_id": "video-held", "dataset_role": "held_out_evaluation"},
                {"comment_id": "cal-1", "video_id": "video-cal", "dataset_role": "calibration_only"},
            ]
        )
        self.lock = {
            "fingerprint_algorithm": PARTITION_FINGERPRINT_ALGORITHM,
            "manifest_fingerprint": manifest_fingerprint(self.manifest),
            "comment_count": 4,
            "video_count": 3,
            "comment_role_counts": {
                "development_pool": 2,
                "held_out_evaluation": 1,
                "calibration_only": 1,
            },
            "video_role_counts": {
                "development_pool": 1,
                "held_out_evaluation": 1,
                "calibration_only": 1,
            },
            "split_seed": 20261018,
        }
        self.guard = PartitionGuard.verify(self.manifest, self.lock)

    def test_development_records_are_allowed(self):
        frame = pd.DataFrame(
            [
                {"comment_id": "dev-1", "video_id": "video-dev", "text": "one"},
                {"comment_id": "dev-2", "video_id": "video-dev", "text": "two"},
            ]
        )
        checked = self.guard.validate_training_frame(frame)
        self.assertEqual(checked.astype(str).to_dict("records"), frame.to_dict("records"))

    def test_held_out_comment_and_video_are_rejected(self):
        with self.assertRaisesRegex(PartitionIntegrityError, "protected comments"):
            self.guard.validate_training_frame(
                pd.DataFrame([{"comment_id": "held-1", "video_id": "video-held"}])
            )
        with self.assertRaisesRegex(PartitionIntegrityError, "protected videos"):
            self.guard.validate_training_frame(
                pd.DataFrame([{"video_id": "video-held"}])
            )

    def test_calibration_only_comment_is_rejected(self):
        with self.assertRaisesRegex(PartitionIntegrityError, "calibration_only"):
            self.guard.validate_training_frame(
                pd.DataFrame([{"comment_id": "cal-1", "video_id": "video-cal"}])
            )

    def test_duplicate_and_conflicting_identifiers_are_rejected(self):
        duplicate = pd.concat([self.manifest, self.manifest.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(PartitionIntegrityError, "duplicate comment IDs"):
            manifest_fingerprint(duplicate)

        conflict = pd.concat(
            [
                self.manifest,
                pd.DataFrame(
                    [{"comment_id": "other", "video_id": "video-dev", "dataset_role": "held_out_evaluation"}]
                ),
            ],
            ignore_index=True,
        )
        with self.assertRaisesRegex(PartitionIntegrityError, "crosses partition roles"):
            manifest_fingerprint(conflict)

        training_duplicate = pd.DataFrame(
            [
                {"comment_id": "dev-1", "video_id": "video-dev"},
                {"comment_id": "dev-1", "video_id": "video-dev"},
            ]
        )
        with self.assertRaisesRegex(PartitionIntegrityError, "duplicate comment IDs"):
            self.guard.validate_training_frame(training_duplicate)

    def test_fingerprint_change_and_missing_lock_are_rejected(self):
        changed = self.manifest.copy()
        changed.loc[changed["video_id"].eq("video-dev"), "dataset_role"] = "held_out_evaluation"
        changed.loc[changed["video_id"].eq("video-held"), "dataset_role"] = "development_pool"
        with self.assertRaisesRegex(PartitionIntegrityError, "fingerprint differs"):
            PartitionGuard.verify(changed, self.lock)

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-lock.json"
            with self.assertRaises(FileNotFoundError):
                load_partition_lock(missing)

            invalid = Path(directory) / "invalid-lock.json"
            invalid.write_text(json.dumps({"fingerprint_algorithm": "other"}), encoding="utf-8")
            with self.assertRaises(PartitionIntegrityError):
                load_partition_lock(invalid)


class CanonicalAnnotationSchemaTests(unittest.TestCase):
    def _template(self) -> pd.DataFrame:
        raw = "e\u0301 සිංහල comment"
        source = pd.DataFrame(
            [
                {
                    "review_order": 1,
                    "comment_id": "comment-1",
                    "raw_comment_text": raw,
                    "raw_comment_text_sha256": raw_text_sha256(raw),
                    "normalized_text": normalized_text(raw),
                    "text_provenance_version": TEXT_PROVENANCE_VERSION,
                    "evidence_text_field": "raw_comment_text",
                    "original_text": normalized_text(raw),
                    "cleaned_text": normalized_text(raw),
                }
            ]
        )
        return create_blank_review_template(source)

    def test_template_preserves_raw_text_separately_from_nfc_text(self):
        template = self._template()
        self.assertEqual(template.loc[0, "raw_comment_text"], "e\u0301 සිංහල comment")
        self.assertEqual(template.loc[0, "normalized_text"], "é සිංහල comment")
        self.assertNotEqual(
            template.loc[0, "raw_comment_text"], template.loc[0, "normalized_text"]
        )
        self.assertEqual(
            template.loc[0, "raw_comment_text_sha256"],
            raw_text_sha256(template.loc[0, "raw_comment_text"]),
        )
        self.assertEqual(
            template.loc[0, "annotation_schema_version"], ANNOTATION_SCHEMA_VERSION
        )
        self.assertTrue(template[REVIEW_ANNOTATION_FIELDS].eq("").all().all())
        validate_annotation_frame(template)

    def test_invalid_label_and_modified_raw_hash_are_rejected(self):
        template = self._template()
        template.loc[0, "annotator_1_primary_signal"] = "DEMAND"
        with self.assertRaisesRegex(ValueError, "Invalid annotator_1 primary"):
            validate_annotation_frame(template)

        template = self._template()
        template.loc[0, "raw_comment_text_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_annotation_frame(template)


if __name__ == "__main__":
    unittest.main()
