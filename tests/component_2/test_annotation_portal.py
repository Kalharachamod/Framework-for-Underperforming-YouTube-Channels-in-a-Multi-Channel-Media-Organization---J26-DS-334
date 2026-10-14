from __future__ import annotations

import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import os

import pandas as pd

from research.component_2.annotation_portal.assignments import (
    PRIMARY_ANNOTATOR_ID,
    PRIMARY_SECTION_ID,
    SECTION_TEMPLATE_BY_ID,
    VOLUNTEER_ANNOTATOR_IDS,
    assignment_distribution,
    create_development_annotators,
    generate_assignments,
    section_option,
)
from research.component_2.annotation_portal.auth import development_tokens, hash_invitation_token, hash_private_code
from research.component_2.annotation_portal.auth import ResumeAttemptLimiter
from research.component_2.annotation_portal.config import PortalConfig, load_config
from research.component_2.annotation_portal.db import DatabaseConnectionError
from research.component_2.annotation_portal.exports import export_for_researcher
from research.component_2.annotation_portal.local_store import LocalAnnotationStore
from research.component_2.annotation_portal.snapshot_import import load_and_validate_snapshot
from research.component_2.annotation_portal.supabase_store import SupabaseAnnotationStore
from research.component_2.annotation_portal.validation import AnnotationResponse, validate_response


def synthetic_comments(count: int = 300) -> pd.DataFrame:
    rows = []
    scripts = ["latin_script", "sinhala_script", "mixed_sinhala_latin", "emoji_only", "other_or_symbolic"]
    for index in range(count):
        channel_idx = index % 5
        script = scripts[index % len(scripts)]
        rows.append(
            {
                "comment_id": f"comment_{index:03d}",
                "channel_id": f"UC_{channel_idx}",
                "channel_name": f"Channel {channel_idx}",
                "video_id": f"video_{index % 25:03d}",
                "video_title": f"Video title {index % 25}",
                "video_description": "" if index % 17 == 0 else f"Description {index % 25}",
                "video_url": f"https://www.youtube.com/watch?v=video_{index % 25:03d}",
                "parent_comment_text": "Parent සිංහල context" if index % 41 == 0 else "",
                "original_text": "සිංහල hello" if index % 7 == 0 else f"Comment text {index}",
                "cleaned_text": "සිංහල hello" if index % 7 == 0 else f"comment text {index}",
                "script_category": script,
                "preprocessing_flags": "",
                "sampling_stratum": script,
            }
        )
    return pd.DataFrame(rows)


class AnnotationPortalTests(unittest.TestCase):
    def test_source_comment_count_and_unique_ids(self):
        comments = synthetic_comments()
        self.assertEqual(len(comments), 300)
        self.assertEqual(comments["comment_id"].nunique(), 300)

    def test_assignment_counts_and_no_volunteer_overlap(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        primary = assignments[assignments["annotator_id"] == PRIMARY_ANNOTATOR_ID]
        self.assertEqual(len(primary), 300)

        volunteer_sets = []
        for annotator_id in VOLUNTEER_ANNOTATOR_IDS:
            assigned = assignments[assignments["annotator_id"] == annotator_id]
            self.assertEqual(len(assigned), 30)
            volunteer_sets.append(set(assigned["comment_id"]))

        combined = set()
        for assigned_set in volunteer_sets:
            self.assertFalse(combined.intersection(assigned_set))
            combined.update(assigned_set)
        self.assertEqual(len(combined), 150)
        self.assertTrue(combined.issubset(set(primary["comment_id"])))

    def test_assignments_are_deterministic(self):
        comments = synthetic_comments()
        first = generate_assignments(comments, seed=20261014)
        second = generate_assignments(comments, seed=20261014)
        self.assertEqual(first.to_dict("records"), second.to_dict("records"))

    def test_volunteer_channel_distribution_is_balanced(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        volunteers = assignments[assignments["annotator_id"].isin(VOLUNTEER_ANNOTATOR_IDS)]
        counts = volunteers.merge(comments[["comment_id", "channel_id"]], on="comment_id")
        per_channel = counts.groupby(["annotator_id", "channel_id"]).size()
        self.assertEqual(set(per_channel.tolist()), {6})

    def test_script_distribution_report_includes_all_annotators(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        distribution = assignment_distribution(comments, assignments)
        self.assertTrue(set(VOLUNTEER_ANNOTATOR_IDS).issubset(set(distribution["annotator_id"])))
        self.assertIn(PRIMARY_ANNOTATOR_ID, set(distribution["annotator_id"]))

    def test_validate_response_accepts_valid_labels(self):
        response = validate_response(
            "DEMAND",
            "NOT_SPAM",
            "language_preference",
            "Needs subtitles",
            "",
            True,
        )
        self.assertEqual(response.demand_label, "DEMAND")
        self.assertTrue(response.is_submitted)

    def test_validate_response_rejects_invalid_labels(self):
        with self.assertRaises(ValueError):
            validate_response("MAYBE", "NOT_SPAM")
        with self.assertRaises(ValueError):
            validate_response("DEMAND", "BOT", "language_preference")
        with self.assertRaises(ValueError):
            validate_response("DEMAND", "NOT_SPAM")
        with self.assertRaises(ValueError):
            validate_response("NON_DEMAND", "NOT_SPAM", "language_preference")

    def test_participant_identity_does_not_use_display_name(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            participant = store.create_participant("Same Name", "section_a", secret, return_code="resume-one")
            self.assertNotEqual(participant.participant_id, participant.display_name)
            self.assertEqual(hash_private_code("resume-one", secret), hash_private_code(participant.return_code, secret))
            store.close()

    def test_participant_assignment_boundaries_and_progress(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            participant = store.create_participant("Volunteer A", "section_a", secret)
            assigned = store.assigned_comments_for_participant(participant.participant_id)
            self.assertEqual(len(assigned), 30)
            store.save_participant_response(
                participant.participant_id,
                assigned[0]["comment_id"],
                AnnotationResponse("NON_DEMAND", "NOT_SPAM", annotation_notes="ok"),
            )
            self.assertEqual(store.progress_for_participant(participant.participant_id)["saved"], 1)
            unassigned = next(comment_id for comment_id in comments["comment_id"] if comment_id not in {row["comment_id"] for row in assigned})
            with self.assertRaises(PermissionError):
                store.save_participant_response(
                    participant.participant_id,
                    unassigned,
                    AnnotationResponse("NON_DEMAND", "NOT_SPAM"),
                )
            store.close()

    def test_response_update_does_not_create_duplicate_records(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            participant = store.create_participant("Volunteer B", "section_b", secret)
            assigned = store.assigned_comments_for_participant(participant.participant_id)
            comment_id = assigned[0]["comment_id"]
            store.save_participant_response(participant.participant_id, comment_id, AnnotationResponse("UNCLEAR", "UNCLEAR"))
            store.save_participant_response(
                participant.participant_id,
                comment_id,
                AnnotationResponse("DEMAND", "NOT_SPAM", "language_preference", is_submitted=True),
            )
            self.assertEqual(store.response_count(), 1)
            self.assertEqual(store.progress_for_participant(participant.participant_id)["submitted"], 1)
            store.close()

    def test_different_names_can_annotate_same_section_independently(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            first = store.create_participant("Nilu", "section_a", secret)
            second = store.create_participant("Kavi", "section_a", secret)
            first_rows = store.assigned_comments_for_participant(first.participant_id)
            second_rows = store.assigned_comments_for_participant(second.participant_id)
            self.assertEqual([row["comment_id"] for row in first_rows], [row["comment_id"] for row in second_rows])

            comment_id = first_rows[0]["comment_id"]
            store.save_participant_response(first.participant_id, comment_id, AnnotationResponse("NON_DEMAND", "NOT_SPAM"))
            store.save_participant_response(second.participant_id, comment_id, AnnotationResponse("UNCLEAR", "UNCLEAR"))

            self.assertEqual(store.response_count(), 2)
            self.assertEqual(store.progress_for_participant(first.participant_id)["saved"], 1)
            self.assertEqual(store.progress_for_participant(second.participant_id)["saved"], 1)
            store.close()

    def test_same_name_collisions_create_distinct_participants(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            first = store.create_participant("Same Name", "section_b", secret)
            second = store.create_participant("Same Name", "section_b", secret)
            self.assertNotEqual(first.participant_id, second.participant_id)
            self.assertNotEqual(first.return_code, second.return_code)
            self.assertEqual(store.participant_count(), 2)
            store.close()

    def test_return_code_resumes_participant_session(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            participant = store.create_participant("Resume Me", "section_c", secret, return_code="resume-code")
            assigned = store.assigned_comments_for_participant(participant.participant_id)
            store.save_participant_response(participant.participant_id, assigned[0]["comment_id"], AnnotationResponse("UNCLEAR", "UNCLEAR"))

            resumed = store.resume_participant("resume-code", secret)
            self.assertIsNotNone(resumed)
            self.assertEqual(resumed.participant_id, participant.participant_id)
            self.assertEqual(store.progress_for_participant(resumed.participant_id)["saved"], 1)
            self.assertIsNone(store.resume_participant("wrong-code", secret))
            store.close()

    def test_section_assignments_remain_unchanged(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        for section_id, template_id in SECTION_TEMPLATE_BY_ID.items():
            option = section_option(section_id)
            assigned = assignments[assignments["annotator_id"] == template_id]
            self.assertEqual(len(assigned), option.assigned_count)

    def test_primary_300_comment_mode_works(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            participant = store.create_participant("Primary Researcher", PRIMARY_SECTION_ID, secret)
            self.assertEqual(participant.assignment_template_id, PRIMARY_ANNOTATOR_ID)
            self.assertEqual(len(store.assigned_comments_for_participant(participant.participant_id)), 300)
            store.close()

    def test_snapshot_import_validation_preserves_deterministic_sections(self):
        comments = synthetic_comments()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.csv"
            comments.to_csv(path, index=False)
            validation = load_and_validate_snapshot(path, seed=20261014)
            self.assertTrue(validation.is_valid, validation.errors)
            self.assertEqual(len(validation.comments), 300)
            self.assertEqual(len(validation.assignments), 450)
            self.assertEqual(validation.invalid_records, 0)

    def test_snapshot_import_validation_rejects_duplicate_ids(self):
        comments = synthetic_comments()
        comments.loc[299, "comment_id"] = comments.loc[0, "comment_id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid_snapshot.csv"
            comments.to_csv(path, index=False)
            validation = load_and_validate_snapshot(path, seed=20261014)
            self.assertFalse(validation.is_valid)
            self.assertGreater(validation.invalid_records, 0)

    def test_supabase_mode_requires_server_side_database_url(self):
        with patch.dict(
            os.environ,
            {"COMPONENT2_ANNOTATION_MODE": "supabase", "SUPABASE_DB_URL": ""},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                load_config()

    def test_streamlit_style_settings_can_configure_supabase_mode(self):
        config = load_config(
            {
                "COMPONENT2_ANNOTATION_MODE": "supabase",
                "COMPONENT2_ANNOTATION_RUN_ID": "approved-run",
                "COMPONENT2_PORTAL_SECRET": "s" * 32,
                "SUPABASE_DB_URL": "postgresql://server-side-only",
                "SUPABASE_ADMIN_DB_URL": "postgresql://admin-only",
                "SUPABASE_IMPORT_DB_URL": "postgresql://import-only",
            }
        )
        self.assertEqual(config.mode, "supabase")
        self.assertEqual(config.annotation_run_id, "approved-run")
        self.assertEqual(config.supabase_admin_db_url, "postgresql://admin-only")
        self.assertEqual(config.supabase_import_db_url, "postgresql://import-only")
        self.assertNotIn("s" * 32, repr(config))

    def test_supabase_mode_rejects_default_or_short_portal_secret(self):
        for secret in ("local-development-secret", "short"):
            with self.subTest(secret=secret):
                with self.assertRaises(ValueError):
                    load_config(
                        {
                            "COMPONENT2_ANNOTATION_MODE": "supabase",
                            "COMPONENT2_PORTAL_SECRET": secret,
                            "SUPABASE_DB_URL": "postgresql://server-side-only",
                        }
                    )

    def test_supabase_store_does_not_accept_empty_database_url(self):
        with self.assertRaises(ValueError):
            SupabaseAnnotationStore("", run_id="run")

    def test_admin_and_importer_config_can_use_separate_urls(self):
        admin_config = load_config(
            {
                "COMPONENT2_ANNOTATION_MODE": "supabase",
                "COMPONENT2_PORTAL_SECRET": "s" * 32,
                "SUPABASE_ADMIN_DB_URL": "postgresql://admin-only",
            },
            require_app_db_url=False,
        )
        import_config = load_config(
            {
                "COMPONENT2_ANNOTATION_MODE": "supabase",
                "COMPONENT2_PORTAL_SECRET": "s" * 32,
                "SUPABASE_IMPORT_DB_URL": "postgresql://import-only",
            },
            require_app_db_url=False,
        )
        self.assertIsNone(admin_config.supabase_db_url)
        self.assertEqual(admin_config.supabase_admin_db_url, "postgresql://admin-only")
        self.assertEqual(import_config.supabase_import_db_url, "postgresql://import-only")

    def test_database_connection_failure_is_explicit(self):
        store = SupabaseAnnotationStore("postgresql://not-used", run_id="run")
        store._connect = lambda: (_ for _ in ()).throw(DatabaseConnectionError("unavailable"))
        with self.assertRaises(DatabaseConnectionError):
            store.ping()

    def test_supabase_mode_has_no_sqlite_fallback(self):
        from research.component_2.annotation_portal.app import _load_store

        config = PortalConfig(
            mode="supabase",
            annotation_csv_path=Path("missing.csv"),
            local_db_path=Path("should-not-be-created.sqlite3"),
            assignment_seed=20261014,
            portal_secret="secret",
            supabase_db_url="postgresql://server-side-only",
        )
        with patch.object(SupabaseAnnotationStore, "ping") as ping:
            store = _load_store(config)
        self.assertIsInstance(store, SupabaseAnnotationStore)
        ping.assert_called_once()

    def test_resume_attempt_limiter_blocks_repeated_guesses(self):
        limiter = ResumeAttemptLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.allow())
        self.assertTrue(limiter.allow())
        self.assertFalse(limiter.allow())

    def test_prepared_sql_isolated_from_research_schema(self):
        root = Path(__file__).resolve().parents[2]
        sql_root = root / "research" / "component_2" / "annotation_portal" / "sql"
        combined = "\n".join(path.read_text(encoding="utf-8") for path in sorted(sql_root.glob("*.sql")))
        self.assertNotIn("research.", combined)
        self.assertIn("annotation.responses", combined)
        self.assertIn("annotation.participants", combined)

    def test_prepared_sql_separates_runtime_admin_and_import_roles(self):
        root = Path(__file__).resolve().parents[2]
        sql_path = root / "research" / "component_2" / "annotation_portal" / "sql" / "0002_annotation_rls.sql"
        sql = sql_path.read_text(encoding="utf-8")
        self.assertIn("'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'", sql)
        self.assertIn("'annotation_app'::text", sql)
        self.assertIn("'annotation_admin'::text", sql)
        self.assertIn("'annotation_importer'::text", sql)
        self.assertIn("NOBYPASSRLS", sql)
        self.assertNotIn("ALTER ROLE annotation_app", sql)
        self.assertNotIn("ALTER ROLE annotation_admin", sql)
        self.assertNotIn("ALTER ROLE annotation_importer", sql)
        self.assertIn("rolsuper", sql)
        self.assertIn("rolcreaterole", sql)
        self.assertIn("rolcreatedb", sql)
        self.assertIn("rolbypassrls", sql)
        self.assertIn("rolinherit", sql)
        self.assertIn("rolreplication", sql)
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertIn("FOR SELECT TO annotation_admin", sql)
        self.assertIn("FOR ALL TO annotation_importer", sql)
        self.assertIn("section_id = 'primary_researcher' AND participant_role = 'primary_researcher'", sql)
        self.assertIn("REVOKE ALL ON ALL TABLES IN SCHEMA annotation FROM annotation_app, annotation_admin, annotation_importer", sql)
        self.assertNotIn("GRANT SELECT ON annotation.researcher_admins, annotation.adjudications TO annotation_app", sql)

    def test_unicode_and_missing_optional_context_are_preserved(self):
        comments = synthetic_comments()
        comments.loc[0, "video_description"] = ""
        comments.loc[0, "original_text"] = "සිංහල mixed hello"
        assignments = generate_assignments(comments, seed=20261014)
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators("secret"))
            primary = store.create_participant("Primary", PRIMARY_SECTION_ID, "secret")
            primary_rows = store.assigned_comments_for_participant(primary.participant_id)
            first = next(row for row in primary_rows if row["comment_id"] == "comment_000")
            self.assertIn("සිංහල", first["original_text"])
            self.assertEqual(first["video_description"], "")
            store.close()

    def test_researcher_export_requires_admin_and_preserves_comment_ids(self):
        comments = synthetic_comments()
        assignments = generate_assignments(comments, seed=20261014)
        secret = "test-secret"
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalAnnotationStore(Path(tmp) / "portal.sqlite3")
            store.initialize(comments, assignments, create_development_annotators(secret))
            participant = store.create_participant("Volunteer C", "section_c", secret)
            admin = store.authenticate(hash_invitation_token(development_tokens()["researcher_admin"], secret))
            volunteer = store.authenticate(hash_invitation_token(development_tokens()["volunteer_3"], secret))
            assigned = store.assigned_comments_for_participant(participant.participant_id)
            store.save_participant_response(
                participant.participant_id,
                assigned[0]["comment_id"],
                AnnotationResponse("NON_DEMAND", "NOT_SPAM"),
            )
            export = export_for_researcher(store, admin)
            self.assertIn("comment_id", export.columns)
            self.assertIn("participant_id", export.columns)
            self.assertEqual(len(export), 30)
            with self.assertRaises(PermissionError):
                export_for_researcher(store, volunteer)
            store.close()

    def test_portal_config_repr_redacts_secrets(self):
        cfg = PortalConfig(
            mode="local",
            annotation_csv_path=Path("comments.csv"),
            local_db_path=Path("portal.sqlite3"),
            assignment_seed=1,
            portal_secret="very-secret",
            supabase_db_url="configured-secret-db-url",
        )
        text = repr(cfg)
        self.assertNotIn("very-secret", text)
        self.assertNotIn("configured-secret-db-url", text)

    def test_generated_local_database_path_is_git_ignored(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                "git",
                "check-ignore",
                "-q",
                "data/processed/component_2/annotation/annotation_portal_local.sqlite3",
            ],
            cwd=root,
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_no_unexpected_component_paths_in_portal_scope(self):
        portal_root = Path(__file__).resolve().parents[2] / "research" / "component_2" / "annotation_portal"
        self.assertTrue(portal_root.exists())
        self.assertFalse((portal_root / ".." / ".." / "component_3").resolve().is_relative_to(portal_root))


if __name__ == "__main__":
    unittest.main()
