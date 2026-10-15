"""Server-side PostgreSQL store for the isolated annotation schema.

The Streamlit process uses a direct PostgreSQL connection held only on the
server. No Supabase browser key or database credential is sent to annotators.
Participant ownership is checked in every operation by this adapter; prepared
SQL also contains database-side policies for the dedicated application role.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import parse_qs, urlsplit

import pandas as pd

from .assignments import (
    PRIMARY_ANNOTATOR_ID,
    SECTION_TEMPLATE_BY_ID,
    section_option,
    section_options,
)
from .auth import ParticipantSession, generate_return_code, hash_private_code
from .db import DatabaseConnectionError
from .local_store import COMMENT_COLUMNS
from .validation import AnnotationResponse, validate_response


class SupabaseAnnotationStore:
    """PostgreSQL-backed store used only when explicit Supabase mode is enabled."""

    def __init__(self, db_url: str, run_id: str, connect_timeout: int = 10):
        if not db_url:
            raise ValueError("A server-side SUPABASE_DB_URL is required")
        if not run_id:
            raise ValueError("An annotation run ID is required")
        try:
            parsed = urlsplit(db_url)
            sslmodes = parse_qs(parsed.query).get("sslmode", [])
        except ValueError:
            raise ValueError("SUPABASE_DB_URL must be a valid PostgreSQL URL") from None
        if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
            raise ValueError("SUPABASE_DB_URL must be a PostgreSQL URL")
        if sslmodes and sslmodes[0].lower() not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("SUPABASE_DB_URL must require SSL")
        self.db_url = db_url
        self.run_id = run_id
        self.connect_timeout = connect_timeout

    def close(self) -> None:
        """Connections are short-lived per operation, so there is nothing to close."""

    @contextmanager
    def _transaction(
        self,
        operation: str,
        participant_id: str | None = None,
        admin_id: str | None = None,
    ) -> Iterator:
        conn = self._connect()
        try:
            self._set_context(conn, operation, participant_id=participant_id, admin_id=admin_id)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            kwargs = {
                "connect_timeout": self.connect_timeout,
                "prepare_threshold": None,
                "row_factory": dict_row,
            }
            if not parse_qs(urlsplit(self.db_url).query).get("sslmode"):
                kwargs["sslmode"] = "require"
            return psycopg.connect(self.db_url, **kwargs)
        except ImportError as exc:  # pragma: no cover - dependency installation issue
            raise DatabaseConnectionError("psycopg is required for Supabase mode") from exc
        except Exception as exc:
            raise DatabaseConnectionError("Unable to connect to the annotation database") from exc

    def _set_context(self, conn, operation: str, participant_id: str | None = None, admin_id: str | None = None) -> None:
        conn.execute("SELECT set_config(%s, %s, true)", ("annotation.operation", operation))
        conn.execute("SELECT set_config(%s, %s, true)", ("annotation.run_id", self.run_id))
        conn.execute("SELECT set_config(%s, %s, true)", ("annotation.participant_id", participant_id or ""))
        conn.execute("SELECT set_config(%s, %s, true)", ("annotation.admin_id", admin_id or ""))

    @staticmethod
    def _validate_display_name(display_name: str) -> str:
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("Display name is required")
        if len(display_name) > 80:
            raise ValueError("Display name must be 80 characters or fewer")
        return display_name

    @staticmethod
    def _participant_from_row(row: dict) -> ParticipantSession:
        return ParticipantSession(
            participant_id=row["participant_id"],
            display_name=row["display_name"],
            section_id=row["section_id"],
            section_label=row["section_label"],
            assignment_template_id=row.get("assignment_template_id", row["assignment_template"]),
            active=bool(row["active"]),
        )

    def create_participant(
        self,
        display_name: str,
        section_id: str,
        secret: str,
        participant_id: str | None = None,
        return_code: str | None = None,
    ) -> ParticipantSession:
        display_name = self._validate_display_name(display_name)
        option = section_option(section_id)
        participant_id = participant_id or f"participant_{uuid.uuid4().hex}"
        return_code = return_code or generate_return_code()

        with self._transaction("participant_create") as conn:
            section = conn.execute(
                """
                SELECT section_id, section_label, assignment_template
                FROM annotation.sections
                WHERE run_id = %s AND section_id = %s
                """,
                (self.run_id, option.section_id),
            ).fetchone()
            if section is None:
                raise RuntimeError("The selected annotation section has not been imported")
            conn.execute(
                """
                INSERT INTO annotation.participants (
                    run_id, participant_id, display_name, section_id,
                    participant_role, return_code_hash, active
                )
                VALUES (%s, %s, %s, %s, %s, %s, true)
                """,
                (
                    self.run_id,
                    participant_id,
                    display_name,
                    section["section_id"],
                    "primary_researcher" if option.section_id == "primary_researcher" else "section_annotator",
                    hash_private_code(return_code, secret),
                ),
            )
        return ParticipantSession(
            participant_id=participant_id,
            display_name=display_name,
            section_id=section["section_id"],
            section_label=section["section_label"],
            assignment_template_id=section["assignment_template"],
            active=True,
            return_code=return_code,
        )

    def resume_participant(self, return_code: str, secret: str) -> ParticipantSession | None:
        try:
            return_code_hash = hash_private_code(return_code, secret)
        except ValueError:
            return None
        with self._transaction("participant_resume") as conn:
            row = conn.execute(
                "SELECT * FROM annotation.resume_participant(%s, %s)",
                (self.run_id, return_code_hash),
            ).fetchone()
        return self._participant_from_row(row) if row else None

    def participant_by_id(self, participant_id: str) -> ParticipantSession | None:
        with self._transaction("participant_session", participant_id=participant_id) as conn:
            row = conn.execute(
                """
                SELECT p.participant_id, p.display_name, p.section_id,
                       s.section_label, s.assignment_template, p.active
                FROM annotation.participants p
                JOIN annotation.sections s
                  ON s.run_id = p.run_id AND s.section_id = p.section_id
                WHERE p.run_id = %s AND p.participant_id = %s AND p.active = true
                """,
                (self.run_id, participant_id),
            ).fetchone()
        return self._participant_from_row(row) if row else None

    def assigned_comments_for_participant(self, participant_id: str) -> list[dict]:
        with self._transaction("participant_session", participant_id=participant_id) as conn:
            participant = self._participant_row(conn, self.run_id, participant_id)
            if participant is None:
                raise PermissionError("Participant session is not active")
            rows = conn.execute(
                """
                SELECT sa.position, c.comment_id, c.channel_id, c.channel_name,
                       c.video_id, c.video_title, c.video_description, c.video_url,
                       c.parent_comment_text, c.published_at, c.is_reply,
                       c.original_text, c.cleaned_text, c.script_category,
                       c.preprocessing_flags, c.sampling_stratum,
                       r.demand_label, r.spam_status, r.demand_subtype,
                       r.annotation_notes, r.spam_notes,
                       COALESCE(r.is_submitted, false) AS is_submitted
                FROM annotation.section_assignments sa
                JOIN annotation.comments c
                  ON c.run_id = sa.run_id AND c.comment_id = sa.comment_id
                LEFT JOIN annotation.responses r
                  ON r.run_id = sa.run_id
                 AND r.section_id = sa.section_id
                 AND r.comment_id = sa.comment_id
                 AND r.participant_id = %s
                WHERE sa.run_id = %s AND sa.section_id = %s
                ORDER BY sa.position
                """,
                (participant_id, self.run_id, participant["section_id"]),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_participant_response(self, participant_id: str, comment_id: str, response: AnnotationResponse) -> None:
        validated = validate_response(
            response.demand_label,
            response.spam_status,
            response.demand_subtype,
            response.annotation_notes,
            response.spam_notes,
            response.is_submitted,
        )
        with self._transaction("participant_response", participant_id=participant_id) as conn:
            participant = self._participant_row(conn, self.run_id, participant_id)
            if participant is None:
                raise PermissionError("Participant session is not active")
            assigned = conn.execute(
                """
                SELECT 1 FROM annotation.section_assignments
                WHERE run_id = %s AND section_id = %s AND comment_id = %s
                """,
                (self.run_id, participant["section_id"], comment_id),
            ).fetchone()
            if assigned is None:
                raise PermissionError("Participant is not assigned to this comment")
            conn.execute(
                """
                INSERT INTO annotation.responses (
                    run_id, participant_id, section_id, comment_id,
                    demand_label, spam_status, demand_subtype,
                    annotation_notes, spam_notes, is_submitted
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, participant_id, comment_id) DO UPDATE SET
                    demand_label = EXCLUDED.demand_label,
                    spam_status = EXCLUDED.spam_status,
                    demand_subtype = EXCLUDED.demand_subtype,
                    annotation_notes = EXCLUDED.annotation_notes,
                    spam_notes = EXCLUDED.spam_notes,
                    is_submitted = EXCLUDED.is_submitted,
                    updated_at = now()
                """,
                (
                    self.run_id,
                    participant_id,
                    participant["section_id"],
                    comment_id,
                    validated.demand_label,
                    validated.spam_status,
                    validated.demand_subtype,
                    validated.annotation_notes,
                    validated.spam_notes,
                    validated.is_submitted,
                ),
            )

    def progress_for_participant(self, participant_id: str) -> dict[str, int]:
        with self._transaction("participant_session", participant_id=participant_id) as conn:
            participant = self._participant_row(conn, self.run_id, participant_id)
            if participant is None:
                raise PermissionError("Participant session is not active")
            row = conn.execute(
                """
                SELECT COUNT(sa.comment_id) AS assigned,
                       COUNT(r.comment_id) AS saved,
                       COUNT(*) FILTER (WHERE COALESCE(r.is_submitted, false)) AS submitted
                FROM annotation.section_assignments sa
                LEFT JOIN annotation.responses r
                  ON r.run_id = sa.run_id AND r.section_id = sa.section_id
                 AND r.comment_id = sa.comment_id AND r.participant_id = %s
                WHERE sa.run_id = %s AND sa.section_id = %s
                """,
                (participant_id, self.run_id, participant["section_id"]),
            ).fetchone()
        return {key: int(row[key] or 0) for key in ("assigned", "saved", "submitted")}

    def revoke_participant(self, participant_id: str, admin_id: str) -> None:
        with self._transaction("admin_revoke", admin_id=admin_id) as conn:
            self._require_admin(conn, admin_id)
            conn.execute(
                """
                UPDATE annotation.participants
                SET active = false, updated_at = now()
                WHERE run_id = %s AND participant_id = %s
                """,
                (self.run_id, participant_id),
            )

    def export_for_admin(self, admin_id: str) -> pd.DataFrame:
        with self._transaction("admin_export", admin_id=admin_id) as conn:
            self._require_admin(conn, admin_id)
            rows = conn.execute(
                """
                SELECT p.participant_id, p.display_name, p.section_id,
                       s.section_label, s.assignment_template AS assignment_template_id,
                       sa.batch_name, sa.position, sa.comment_id,
                       r.demand_label, r.spam_status, r.demand_subtype,
                       r.annotation_notes, r.spam_notes,
                       COALESCE(r.is_submitted, false) AS is_submitted,
                       r.created_at, r.updated_at
                FROM annotation.participants p
                JOIN annotation.sections s
                  ON s.run_id = p.run_id AND s.section_id = p.section_id
                JOIN annotation.section_assignments sa
                  ON sa.run_id = p.run_id AND sa.section_id = p.section_id
                LEFT JOIN annotation.responses r
                  ON r.run_id = p.run_id AND r.participant_id = p.participant_id
                 AND r.comment_id = sa.comment_id
                WHERE p.run_id = %s
                ORDER BY p.created_at, p.participant_id, sa.position
                """,
                (self.run_id,),
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def import_snapshot(
        self,
        comments: pd.DataFrame,
        assignments: pd.DataFrame,
        assignment_seed: int,
        source_name: str,
    ) -> dict[str, int]:
        """Idempotently import read-only snapshot data without touching responses."""
        comments = comments.copy().fillna("").reset_index(drop=True)
        section_by_template = {template: section for section, template in SECTION_TEMPLATE_BY_ID.items()}
        counts = {"inserted": 0, "updated": 0, "skipped": 0, "invalid": 0}
        comment_fields = [
            "channel_id", "channel_name", "video_id", "video_title", "video_description",
            "video_url", "parent_comment_text", "published_at", "is_reply", "original_text",
            "cleaned_text", "script_category", "preprocessing_flags", "sampling_stratum",
        ]

        with self._transaction("snapshot_import") as conn:
            conn.execute(
                """
                INSERT INTO annotation.annotation_runs (run_id, source_name, assignment_seed, comment_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    assignment_seed = EXCLUDED.assignment_seed,
                    comment_count = EXCLUDED.comment_count
                """,
                (self.run_id, source_name, assignment_seed, len(comments)),
            )
            for option in section_options():
                conn.execute(
                    """
                    INSERT INTO annotation.sections (
                        run_id, section_id, section_label, assignment_template,
                        assigned_count, is_primary_mode
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, section_id) DO UPDATE SET
                        section_label = EXCLUDED.section_label,
                        assignment_template = EXCLUDED.assignment_template,
                        assigned_count = EXCLUDED.assigned_count,
                        is_primary_mode = EXCLUDED.is_primary_mode
                    """,
                    (
                        self.run_id,
                        option.section_id,
                        option.label,
                        option.assignment_template_id,
                        option.assigned_count,
                        option.section_id == "primary_researcher",
                    ),
                )

            for source_index, row in comments.iterrows():
                comment_id = str(row.get("comment_id", "")).strip()
                if not comment_id:
                    counts["invalid"] += 1
                    continue
                values = {field: str(row.get(field, "")) for field in comment_fields}
                existing = conn.execute(
                    """
                    SELECT channel_id, channel_name, video_id, video_title, video_description,
                           video_url, parent_comment_text, published_at, is_reply, original_text,
                           cleaned_text, script_category, preprocessing_flags, sampling_stratum
                    FROM annotation.comments
                    WHERE run_id = %s AND comment_id = %s
                    """,
                    (self.run_id, comment_id),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO annotation.comments (
                            run_id, comment_id, channel_id, channel_name, video_id,
                            video_title, video_description, video_url, parent_comment_text,
                            published_at, is_reply, original_text, cleaned_text,
                            script_category, preprocessing_flags, sampling_stratum, source_row_index
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (self.run_id, comment_id, *[values[field] for field in comment_fields], source_index),
                    )
                    counts["inserted"] += 1
                elif any(str(existing[field] or "") != values[field] for field in comment_fields):
                    conn.execute(
                        """
                        UPDATE annotation.comments SET
                            channel_id = %s, channel_name = %s, video_id = %s,
                            video_title = %s, video_description = %s, video_url = %s,
                            parent_comment_text = %s, published_at = %s, is_reply = %s,
                            original_text = %s, cleaned_text = %s, script_category = %s,
                            preprocessing_flags = %s, sampling_stratum = %s,
                            source_row_index = %s
                        WHERE run_id = %s AND comment_id = %s
                        """,
                        (*[values[field] for field in comment_fields], source_index, self.run_id, comment_id),
                    )
                    counts["updated"] += 1
                else:
                    counts["skipped"] += 1

            for assignment in assignments.fillna("").to_dict("records"):
                section_id = section_by_template.get(assignment["annotator_id"])
                if section_id is None:
                    counts["invalid"] += 1
                    continue
                conn.execute(
                    """
                    INSERT INTO annotation.section_assignments (
                        run_id, section_id, comment_id, batch_name, position
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, section_id, comment_id) DO UPDATE SET
                        batch_name = EXCLUDED.batch_name,
                        position = EXCLUDED.position
                    """,
                    (
                        self.run_id,
                        section_id,
                        assignment["comment_id"],
                        assignment["batch_name"],
                        int(assignment["position"]),
                    ),
                )
        return counts

    def ping(self) -> None:
        with self._transaction("healthcheck") as conn:
            conn.execute("SELECT 1").fetchone()

    @staticmethod
    def _participant_row(conn, run_id: str, participant_id: str) -> dict | None:
        return conn.execute(
            """
            SELECT p.participant_id, p.display_name, p.section_id,
                   s.section_label, s.assignment_template, p.active
            FROM annotation.participants p
            JOIN annotation.sections s
              ON s.run_id = p.run_id AND s.section_id = p.section_id
            WHERE p.run_id = %s AND p.participant_id = %s AND p.active = true
            """,
            (run_id, participant_id),
        ).fetchone()

    @staticmethod
    def _require_admin(conn, admin_id: str) -> None:
        row = conn.execute(
            """
            SELECT 1 FROM annotation.researcher_admins
            WHERE admin_id = %s AND active = true
            """,
            (admin_id,),
        ).fetchone()
        if row is None:
            raise PermissionError("Researcher admin is not authorized")
