from __future__ import annotations

import sys
import subprocess
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[2] / "research" / "component_2" / "src"
sys.path.insert(0, str(SRC))

from annotation import (
    ANNOTATION_COLUMNS,
    DEMAND_ANNOTATION_COLUMNS,
    SPAM_ANNOTATION_COLUMNS,
    SPAM_STATUS_VALUES,
    VIDEO_CONTEXT_COLUMNS,
    AnnotationSamplingConfig,
    add_spam_annotation_fields,
    add_video_context_fields,
    create_annotation_sample,
    create_annotation_template,
    ensure_no_human_annotations,
    nonblank_annotation_counts,
    prepare_annotation_source,
    spreadsheet_safe_text,
    validate_existing_annotation_template,
)


def synthetic_source() -> pd.DataFrame:
    rows = []
    for channel_idx in range(5):
        channel_id = f"UC_{channel_idx}"
        for item_idx in range(20):
            comment_id = f"c_{channel_idx}_{item_idx}"
            script_type = item_idx % 5
            rows.append(
                {
                    "comment_id": comment_id,
                    "channel_id": channel_id,
                    "video_id": f"v_{channel_idx}_{item_idx % 4}",
                    "original_text": "සිංහල hello"
                    if script_type == 0
                    else "සිංහල"
                    if script_type == 1
                    else "hello"
                    if script_type == 2
                    else "🔥🔥"
                    if script_type == 3
                    else "ok",
                    "cleaned_text": "සිංහල hello"
                    if script_type == 0
                    else "සිංහල"
                    if script_type == 1
                    else "hello"
                    if script_type == 2
                    else "🔥🔥"
                    if script_type == 3
                    else "ok",
                    "has_sinhala": script_type in {0, 1},
                    "has_latin": script_type in {0, 2, 4},
                    "mixed_sinhala_latin": script_type == 0,
                    "emoji_only": script_type == 3,
                    "char_length": 2 if script_type == 4 else 10,
                    "word_count": 1,
                    "has_repeated_char_pattern": False,
                    "changed_by_preprocessing": False,
                    "review_reasons": "very_short" if script_type == 4 else "",
                    "exclude_from_modeling": False,
                    "repeated_cleaned_text": False,
                    "channel_name": f"Channel {channel_idx}",
                    "parent_comment_id": "p1" if item_idx % 7 == 0 else pd.NA,
                    "published_at": f"2026-01-{(item_idx % 28) + 1:02d} 00:00:00+00",
                }
            )
    return pd.DataFrame(rows)


def synthetic_videos() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "video_id": f"v_{channel_idx}_{video_idx}",
                "title": f"Video {channel_idx}-{video_idx}",
                "description": f"Description {channel_idx}-{video_idx}",
            }
            for channel_idx in range(5)
            for video_idx in range(4)
        ]
    )


def synthetic_comments() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"comment_id": "parent_1", "comment_text": "Parent context", "parent_comment_id": pd.NA},
            {"comment_id": "c_0_0", "comment_text": "Reply text", "parent_comment_id": "parent_1"},
            {"comment_id": "c_0_1", "comment_text": "Top level", "parent_comment_id": pd.NA},
        ]
    )


class AnnotationPreparationTests(unittest.TestCase):
    def test_deterministic_sampling(self):
        source = synthetic_source()
        config = AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2)
        first = create_annotation_sample(source, config)
        second = create_annotation_sample(source, config)
        self.assertEqual(first["comment_id"].tolist(), second["comment_id"].tolist())

    def test_unique_selected_comment_ids_and_size(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        self.assertEqual(len(sample), 50)
        self.assertEqual(sample["comment_id"].nunique(), 50)

    def test_five_channel_coverage(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        self.assertEqual(sample["channel_id"].nunique(), 5)

    def test_script_category_coverage(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        categories = set(sample["script_category"])
        self.assertIn("mixed_sinhala_latin", categories)
        self.assertIn("sinhala_script", categories)
        self.assertIn("latin_script", categories)
        self.assertIn("emoji_only", categories)

    def test_blank_annotation_fields(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        for column in DEMAND_ANNOTATION_COLUMNS + SPAM_ANNOTATION_COLUMNS:
            self.assertTrue((template[column] == "").all())

    def test_existing_demand_annotation_columns_unchanged(self):
        self.assertEqual(
            DEMAND_ANNOTATION_COLUMNS,
            [
                "primary_label",
                "demand_subtype",
                "annotation_notes",
                "annotator_1_label",
                "annotator_2_label",
                "final_adjudicated_label",
            ],
        )
        self.assertLess(
            ANNOTATION_COLUMNS.index("final_adjudicated_label"),
            ANNOTATION_COLUMNS.index("annotator_1_spam_status"),
        )

    def test_new_spam_fields_blank_by_default(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        self.assertEqual(SPAM_STATUS_VALUES, ["SPAM", "NOT_SPAM", "UNCLEAR"])
        for column in SPAM_ANNOTATION_COLUMNS:
            self.assertIn(column, template.columns)
            self.assertTrue((template[column] == "").all())

    def test_add_spam_fields_preserves_existing_rows_and_columns(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        old_template = create_annotation_template(sample).drop(columns=SPAM_ANNOTATION_COLUMNS)
        migrated = add_spam_annotation_fields(old_template)
        self.assertEqual(migrated["comment_id"].tolist(), old_template["comment_id"].tolist())
        self.assertEqual(migrated["original_text"].tolist(), old_template["original_text"].tolist())
        self.assertEqual(migrated["cleaned_text"].tolist(), old_template["cleaned_text"].tolist())
        for column in SPAM_ANNOTATION_COLUMNS:
            self.assertTrue((migrated[column] == "").all())

    def test_safe_handling_of_previously_annotated_csv_files(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        annotated = template.copy()
        annotated.loc[0, "primary_label"] = "DEMAND"
        with self.assertRaises(ValueError):
            ensure_no_human_annotations(annotated)
        self.assertEqual(nonblank_annotation_counts(annotated)["primary_label"], 1)

    def test_existing_annotation_template_validation_detects_changed_sample(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        changed = template.copy()
        changed.loc[0, "comment_id"] = "changed_comment"
        with self.assertRaises(ValueError):
            validate_existing_annotation_template(changed, template)

    def test_no_duplicate_comment_ids(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        self.assertFalse(sample["comment_id"].duplicated().any())

    def test_no_loss_of_multilingual_text(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        joined_original = " ".join(template["original_text"].astype(str))
        joined_cleaned = " ".join(template["cleaned_text"].astype(str))
        self.assertIn("සිංහල", joined_original)
        self.assertIn("සිංහල", joined_cleaned)
        self.assertIn("🔥", joined_original)

    def test_output_schema(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        self.assertEqual(template.columns.tolist(), ANNOTATION_COLUMNS)

    def test_video_context_fields_are_blank_by_default(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        for column in VIDEO_CONTEXT_COLUMNS:
            self.assertIn(column, template.columns)
            self.assertTrue(template[column].fillna("").astype(str).str.strip().eq("").all())

    def test_video_context_enrichment_preserves_rows_and_labels(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        template.loc[0, "primary_label"] = "DEMAND"
        template.loc[0, "annotator_1_spam_status"] = "NOT_SPAM"

        enriched = add_video_context_fields(template, synthetic_videos(), synthetic_comments())

        self.assertEqual(enriched["comment_id"].tolist(), template["comment_id"].tolist())
        self.assertEqual(enriched["original_text"].tolist(), template["original_text"].tolist())
        self.assertEqual(enriched["cleaned_text"].tolist(), template["cleaned_text"].tolist())
        self.assertEqual(enriched.loc[0, "primary_label"], "DEMAND")
        self.assertEqual(enriched.loc[0, "annotator_1_spam_status"], "NOT_SPAM")

    def test_video_titles_match_correct_video_id_and_urls_are_constructed(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        enriched = add_video_context_fields(create_annotation_template(sample), synthetic_videos())

        matched = enriched[enriched["video_title"].astype(str).str.len() > 0]
        for _, row in matched.iterrows():
            expected_title = synthetic_videos().set_index("video_id").loc[row["video_id"], "title"]
            self.assertEqual(row["video_title"], expected_title)
            self.assertEqual(row["video_url"], f"https://www.youtube.com/watch?v={row['video_id']}")

    def test_missing_video_metadata_does_not_remove_comment(self):
        sample = create_annotation_sample(
            synthetic_source(),
            AnnotationSamplingConfig(sample_size=50, random_seed=123, minority_target_per_channel=2),
        )
        template = create_annotation_template(sample)
        videos = synthetic_videos().iloc[0:0].copy()
        enriched = add_video_context_fields(template, videos)
        self.assertEqual(len(enriched), len(template))
        self.assertTrue(enriched["video_title"].fillna("").eq("").all())
        self.assertTrue(enriched["video_description"].fillna("").eq("").all())

    def test_parent_comment_text_resolved_when_available(self):
        template = create_annotation_template(synthetic_source().head(2))
        enriched = add_video_context_fields(template, synthetic_videos(), synthetic_comments())
        parent_text = enriched.loc[enriched["comment_id"] == "c_0_0", "parent_comment_text"].iloc[0]
        self.assertEqual(parent_text, "Parent context")

    def test_context_enrichment_does_not_duplicate_columns_on_rerun(self):
        template = create_annotation_template(synthetic_source().head(2))
        first = add_video_context_fields(template, synthetic_videos(), synthetic_comments())
        second = add_video_context_fields(first, synthetic_videos(), synthetic_comments())
        self.assertEqual(second.columns.tolist().count("video_title"), 1)
        self.assertEqual(second.columns.tolist().count("parent_comment_text"), 1)
        self.assertEqual(second["comment_id"].tolist(), first["comment_id"].tolist())

    def test_spreadsheet_safe_context_does_not_change_canonical_comment_text(self):
        self.assertEqual(spreadsheet_safe_text("=IMPORTDATA(\"http://example.com\")"), "'=IMPORTDATA(\"http://example.com\")")
        template = create_annotation_template(synthetic_source().head(1))
        template.loc[0, "original_text"] = "=not a formula in canonical comment text"
        videos = pd.DataFrame(
            [{"video_id": template.loc[0, "video_id"], "title": "=unsafe title", "description": "+unsafe description"}]
        )
        enriched = add_video_context_fields(template, videos)
        self.assertEqual(enriched.loc[0, "original_text"], "=not a formula in canonical comment text")
        self.assertEqual(enriched.loc[0, "video_title"], "'=unsafe title")
        self.assertEqual(enriched.loc[0, "video_description"], "'+unsafe description")

    def test_prepare_annotation_source_references_validated_data(self):
        preprocessed = synthetic_source().drop(columns=["channel_name", "parent_comment_id", "published_at"])
        validated = synthetic_source()[["comment_id", "channel_name", "parent_comment_id", "published_at"]]
        source = prepare_annotation_source(preprocessed, validated)
        self.assertIn("channel_name", source.columns)
        self.assertIn("is_reply", source.columns)
        self.assertTrue(source["is_reply"].any())

    def test_current_300_comment_sample_is_preserved_when_available(self):
        root = Path(__file__).resolve().parents[2]
        processed = root / "data" / "processed" / "component_2"
        annotation_csv = processed / "annotation" / "component2_demand_annotation_sample.csv"
        preprocessed_path = processed / "preprocessed_comments.csv"
        validated_path = processed / "validated_comments.csv"
        if not annotation_csv.exists() or not preprocessed_path.exists() or not validated_path.exists():
            self.skipTest("Local processed Component 2 annotation files are not available")

        current = pd.read_csv(annotation_csv, dtype="string").fillna("")
        preprocessed = pd.read_csv(
            preprocessed_path,
            dtype={"comment_id": "string", "channel_id": "string", "video_id": "string"},
        )
        validated = pd.read_csv(
            validated_path,
            dtype={"comment_id": "string", "parent_comment_id": "string"},
        )
        source = prepare_annotation_source(preprocessed, validated)
        expected = create_annotation_template(
            create_annotation_sample(source, AnnotationSamplingConfig(sample_size=300, random_seed=334))
        )

        validate_existing_annotation_template(current, expected)
        self.assertEqual(len(current), 300)
        self.assertEqual(current["comment_id"].nunique(), 300)
        self.assertEqual(set(current.groupby("channel_id")["comment_id"].count()), {60})
        for column in VIDEO_CONTEXT_COLUMNS:
            self.assertIn(column, current.columns)
        for column in DEMAND_ANNOTATION_COLUMNS + SPAM_ANNOTATION_COLUMNS:
            self.assertIn(column, current.columns)
            self.assertTrue(current[column].fillna("").astype(str).str.strip().eq("").all())

    def test_committed_notebook_outputs_do_not_embed_raw_comment_text_columns(self):
        notebook_path = (
            Path(__file__).resolve().parents[2]
            / "research"
            / "component_2"
            / "notebooks"
            / "04_demand_annotation_preparation.ipynb"
        )
        text = notebook_path.read_text(encoding="utf-8")
        for raw_column_header in [
            "<th>original_text</th>",
            "<th>cleaned_text</th>",
            "<th>comment_text</th>",
        ]:
            self.assertNotIn(raw_column_header, text)

    def test_generated_annotation_files_remain_git_ignored(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                "git",
                "check-ignore",
                "-q",
                "data/processed/component_2/annotation/component2_demand_annotation_sample.csv",
            ],
            cwd=root,
            check=False,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
