"""SQLite-backed local development store for the annotation portal."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from .assignments import section_option
from .auth import AuthenticatedAnnotator, ParticipantSession, generate_return_code, hash_private_code
from .validation import AnnotationResponse, validate_response


COMMENT_COLUMNS = [
    "comment_id",
    "channel_id",
    "channel_name",
    "video_id",
    "video_title",
    "video_description",
    "video_url",
    "parent_comment_text",
    "published_at",
    "is_reply",
    "original_text",
    "cleaned_text",
    "script_category",
    "preprocessing_flags",
    "sampling_stratum",
]


class LocalAnnotationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def initialize(
        self,
        comments: pd.DataFrame,
        assignments: pd.DataFrame,
        annotators: Iterable | None = None,
    ) -> None:
        self._create_schema()
        self._upsert_comments(comments)
        self._upsert_annotators(annotators or [])
        self._upsert_assignments(assignments)
        self.conn.commit()

    def authenticate(self, token_hash: str) -> AuthenticatedAnnotator | None:
        row = self.conn.execute(
            """
            SELECT annotator_id, display_name, role, active
            FROM annotators
            WHERE token_hash = ? AND active = 1
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        return AuthenticatedAnnotator(
            annotator_id=row["annotator_id"],
            display_name=row["display_name"],
            role=row["role"],
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
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("Display name is required")
        if len(display_name) > 80:
            raise ValueError("Display name must be 80 characters or fewer")

        option = section_option(section_id)
        participant_id = participant_id or f"participant_{uuid.uuid4().hex}"
        return_code = return_code or generate_return_code()
        return_code_hash = hash_private_code(return_code, secret)

        self.conn.execute(
            """
            INSERT INTO participants (
                participant_id, display_name, section_id, section_label,
                assignment_template_id, return_code_hash, active,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                participant_id,
                display_name,
                option.section_id,
                option.label,
                option.assignment_template_id,
                return_code_hash,
            ),
        )
        self.conn.commit()
        return ParticipantSession(
            participant_id=participant_id,
            display_name=display_name,
            section_id=option.section_id,
            section_label=option.label,
            assignment_template_id=option.assignment_template_id,
            active=True,
            return_code=return_code,
        )

    def resume_participant(self, return_code: str, secret: str) -> ParticipantSession | None:
        try:
            return_code_hash = hash_private_code(return_code, secret)
        except ValueError:
            return None
        row = self.conn.execute(
            """
            SELECT participant_id, display_name, section_id, section_label,
                   assignment_template_id, active
            FROM participants
            WHERE return_code_hash = ? AND active = 1
            """,
            (return_code_hash,),
        ).fetchone()
        return self._participant_from_row(row) if row else None

    def participant_by_id(self, participant_id: str) -> ParticipantSession | None:
        row = self.conn.execute(
            """
            SELECT participant_id, display_name, section_id, section_label,
                   assignment_template_id, active
            FROM participants
            WHERE participant_id = ? AND active = 1
            """,
            (participant_id,),
        ).fetchone()
        return self._participant_from_row(row) if row else None

    def assigned_comments_for_participant(self, participant_id: str) -> list[dict]:
        participant = self.participant_by_id(participant_id)
        if participant is None:
            raise PermissionError("Participant session is not active")
        rows = self.conn.execute(
            """
            SELECT
                a.position,
                c.*,
                r.demand_label,
                r.spam_status,
                r.demand_subtype,
                r.annotation_notes,
                r.spam_notes,
                COALESCE(r.is_submitted, 0) AS is_submitted
            FROM assignments a
            JOIN comments c ON c.comment_id = a.comment_id
            LEFT JOIN participant_responses r
                ON r.comment_id = a.comment_id AND r.participant_id = ?
            WHERE a.annotator_id = ?
            ORDER BY a.position
            """,
            (participant.participant_id, participant.assignment_template_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def save_participant_response(
        self,
        participant_id: str,
        comment_id: str,
        response: AnnotationResponse,
    ) -> None:
        participant = self.participant_by_id(participant_id)
        if participant is None:
            raise PermissionError("Participant session is not active")

        assigned = self.conn.execute(
            """
            SELECT 1
            FROM assignments
            WHERE annotator_id = ? AND comment_id = ?
            """,
            (participant.assignment_template_id, comment_id),
        ).fetchone()
        if assigned is None:
            raise PermissionError("Participant is not assigned to this comment")

        validated = validate_response(
            response.demand_label,
            response.spam_status,
            response.demand_subtype,
            response.annotation_notes,
            response.spam_notes,
            response.is_submitted,
        )
        self.conn.execute(
            """
            INSERT INTO participant_responses (
                participant_id, section_id, comment_id, demand_label, spam_status,
                demand_subtype, annotation_notes, spam_notes, is_submitted,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (participant_id, comment_id) DO UPDATE SET
                demand_label = excluded.demand_label,
                spam_status = excluded.spam_status,
                demand_subtype = excluded.demand_subtype,
                annotation_notes = excluded.annotation_notes,
                spam_notes = excluded.spam_notes,
                is_submitted = excluded.is_submitted,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                participant.participant_id,
                participant.section_id,
                comment_id,
                validated.demand_label,
                validated.spam_status,
                validated.demand_subtype,
                validated.annotation_notes,
                validated.spam_notes,
                1 if validated.is_submitted else 0,
            ),
        )
        self.conn.commit()

    def progress_for_participant(self, participant_id: str) -> dict[str, int]:
        participant = self.participant_by_id(participant_id)
        if participant is None:
            raise PermissionError("Participant session is not active")
        row = self.conn.execute(
            """
            SELECT
                COUNT(a.comment_id) AS assigned,
                COUNT(r.comment_id) AS saved,
                SUM(CASE WHEN COALESCE(r.is_submitted, 0) = 1 THEN 1 ELSE 0 END) AS submitted
            FROM assignments a
            LEFT JOIN participant_responses r
                ON r.participant_id = ? AND r.comment_id = a.comment_id
            WHERE a.annotator_id = ?
            """,
            (participant.participant_id, participant.assignment_template_id),
        ).fetchone()
        return {
            "assigned": int(row["assigned"] or 0),
            "saved": int(row["saved"] or 0),
            "submitted": int(row["submitted"] or 0),
        }

    def assigned_comments(self, annotator_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT
                a.position,
                c.*,
                r.demand_label,
                r.spam_status,
                r.demand_subtype,
                r.annotation_notes,
                r.spam_notes,
                COALESCE(r.is_submitted, 0) AS is_submitted
            FROM assignments a
            JOIN comments c ON c.comment_id = a.comment_id
            LEFT JOIN responses r
                ON r.comment_id = a.comment_id AND r.annotator_id = a.annotator_id
            WHERE a.annotator_id = ?
            ORDER BY a.position
            """,
            (annotator_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def save_response(
        self,
        annotator_id: str,
        comment_id: str,
        response: AnnotationResponse,
    ) -> None:
        assigned = self.conn.execute(
            "SELECT 1 FROM assignments WHERE annotator_id = ? AND comment_id = ?",
            (annotator_id, comment_id),
        ).fetchone()
        if assigned is None:
            raise PermissionError("Annotator is not assigned to this comment")

        validated = validate_response(
            response.demand_label,
            response.spam_status,
            response.demand_subtype,
            response.annotation_notes,
            response.spam_notes,
            response.is_submitted,
        )
        self.conn.execute(
            """
            INSERT INTO responses (
                annotator_id, comment_id, demand_label, spam_status, demand_subtype,
                annotation_notes, spam_notes, is_submitted, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (annotator_id, comment_id) DO UPDATE SET
                demand_label = excluded.demand_label,
                spam_status = excluded.spam_status,
                demand_subtype = excluded.demand_subtype,
                annotation_notes = excluded.annotation_notes,
                spam_notes = excluded.spam_notes,
                is_submitted = excluded.is_submitted,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                annotator_id,
                comment_id,
                validated.demand_label,
                validated.spam_status,
                validated.demand_subtype,
                validated.annotation_notes,
                validated.spam_notes,
                1 if validated.is_submitted else 0,
            ),
        )
        self.conn.commit()

    def progress(self, annotator_id: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
                COUNT(a.comment_id) AS assigned,
                COUNT(r.comment_id) AS saved,
                SUM(CASE WHEN COALESCE(r.is_submitted, 0) = 1 THEN 1 ELSE 0 END) AS submitted
            FROM assignments a
            LEFT JOIN responses r
                ON r.annotator_id = a.annotator_id AND r.comment_id = a.comment_id
            WHERE a.annotator_id = ?
            """,
            (annotator_id,),
        ).fetchone()
        return {
            "assigned": int(row["assigned"] or 0),
            "saved": int(row["saved"] or 0),
            "submitted": int(row["submitted"] or 0),
        }

    def export_responses(self) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            SELECT
                p.participant_id,
                p.display_name,
                p.section_id,
                p.section_label,
                p.assignment_template_id,
                a.batch_name,
                a.position,
                a.comment_id,
                r.demand_label,
                r.spam_status,
                r.demand_subtype,
                r.annotation_notes,
                r.spam_notes,
                COALESCE(r.is_submitted, 0) AS is_submitted,
                r.created_at,
                r.updated_at
            FROM participants p
            JOIN assignments a
                ON a.annotator_id = p.assignment_template_id
            LEFT JOIN participant_responses r
                ON r.participant_id = p.participant_id AND r.comment_id = a.comment_id
            WHERE p.active = 1
            ORDER BY p.created_at, p.participant_id, a.position
            """,
            self.conn,
        )

    def response_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM participant_responses").fetchone()
        return int(row["count"])

    def participant_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM participants").fetchone()
        return int(row["count"])

    def _participant_from_row(self, row: sqlite3.Row) -> ParticipantSession:
        return ParticipantSession(
            participant_id=row["participant_id"],
            display_name=row["display_name"],
            section_id=row["section_id"],
            section_label=row["section_label"],
            assignment_template_id=row["assignment_template_id"],
            active=bool(row["active"]),
        )

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS annotators (
                annotator_id TEXT PRIMARY KEY,
                display_name TEXT,
                role TEXT NOT NULL CHECK (role IN ('primary', 'volunteer', 'researcher_admin')),
                token_hash TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                assigned_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                channel_id TEXT,
                channel_name TEXT,
                video_id TEXT,
                video_title TEXT,
                video_description TEXT,
                video_url TEXT,
                parent_comment_text TEXT,
                published_at TEXT,
                is_reply TEXT,
                original_text TEXT,
                cleaned_text TEXT,
                script_category TEXT,
                preprocessing_flags TEXT,
                sampling_stratum TEXT
            );

            CREATE TABLE IF NOT EXISTS assignments (
                annotator_id TEXT NOT NULL,
                comment_id TEXT NOT NULL,
                batch_name TEXT NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY (annotator_id, comment_id),
                FOREIGN KEY (annotator_id) REFERENCES annotators (annotator_id),
                FOREIGN KEY (comment_id) REFERENCES comments (comment_id)
            );

            CREATE TABLE IF NOT EXISTS participants (
                participant_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                section_id TEXT NOT NULL,
                section_label TEXT NOT NULL,
                assignment_template_id TEXT NOT NULL,
                return_code_hash TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (assignment_template_id) REFERENCES annotators (annotator_id)
            );

            CREATE TABLE IF NOT EXISTS participant_responses (
                participant_id TEXT NOT NULL,
                section_id TEXT NOT NULL,
                comment_id TEXT NOT NULL,
                demand_label TEXT NOT NULL CHECK (demand_label IN ('DEMAND', 'NON_DEMAND', 'UNCLEAR')),
                spam_status TEXT NOT NULL CHECK (spam_status IN ('SPAM', 'NOT_SPAM', 'UNCLEAR')),
                demand_subtype TEXT NOT NULL DEFAULT '',
                annotation_notes TEXT NOT NULL DEFAULT '',
                spam_notes TEXT NOT NULL DEFAULT '',
                is_submitted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (participant_id, comment_id),
                FOREIGN KEY (participant_id) REFERENCES participants (participant_id),
                FOREIGN KEY (comment_id) REFERENCES comments (comment_id)
            );

            CREATE TABLE IF NOT EXISTS responses (
                annotator_id TEXT NOT NULL,
                comment_id TEXT NOT NULL,
                demand_label TEXT NOT NULL CHECK (demand_label IN ('DEMAND', 'NON_DEMAND', 'UNCLEAR')),
                spam_status TEXT NOT NULL CHECK (spam_status IN ('SPAM', 'NOT_SPAM', 'UNCLEAR')),
                demand_subtype TEXT NOT NULL DEFAULT '',
                annotation_notes TEXT NOT NULL DEFAULT '',
                spam_notes TEXT NOT NULL DEFAULT '',
                is_submitted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (annotator_id, comment_id),
                FOREIGN KEY (annotator_id, comment_id) REFERENCES assignments (annotator_id, comment_id)
            );
            """
        )
        existing_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(comments)").fetchall()
        }
        for column, column_type in (("published_at", "TEXT"), ("is_reply", "TEXT")):
            if column not in existing_columns:
                self.conn.execute(f"ALTER TABLE comments ADD COLUMN {column} {column_type}")

    def _upsert_comments(self, comments: pd.DataFrame) -> None:
        frame = comments.copy()
        for column in COMMENT_COLUMNS:
            if column not in frame.columns:
                frame[column] = ""
        records = frame[COMMENT_COLUMNS].fillna("").to_dict("records")
        self.conn.executemany(
            """
            INSERT INTO comments (
                comment_id, channel_id, channel_name, video_id, video_title,
                video_description, video_url, parent_comment_text, published_at, is_reply, original_text,
                cleaned_text, script_category, preprocessing_flags, sampling_stratum
            )
            VALUES (
                :comment_id, :channel_id, :channel_name, :video_id, :video_title,
                :video_description, :video_url, :parent_comment_text, :published_at, :is_reply, :original_text,
                :cleaned_text, :script_category, :preprocessing_flags, :sampling_stratum
            )
            ON CONFLICT (comment_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                channel_name = excluded.channel_name,
                video_id = excluded.video_id,
                video_title = excluded.video_title,
                video_description = excluded.video_description,
                video_url = excluded.video_url,
                parent_comment_text = excluded.parent_comment_text,
                published_at = excluded.published_at,
                is_reply = excluded.is_reply,
                original_text = excluded.original_text,
                cleaned_text = excluded.cleaned_text,
                script_category = excluded.script_category,
                preprocessing_flags = excluded.preprocessing_flags,
                sampling_stratum = excluded.sampling_stratum
            """,
            records,
        )

    def _upsert_annotators(self, annotators: Iterable) -> None:
        records = [
            {
                "annotator_id": item.annotator_id,
                "display_name": item.display_name,
                "role": item.role,
                "token_hash": item.token_hash,
                "active": 1 if item.active else 0,
                "assigned_count": item.assigned_count,
            }
            for item in annotators
        ]
        self.conn.executemany(
            """
            INSERT INTO annotators (
                annotator_id, display_name, role, token_hash, active, assigned_count
            )
            VALUES (
                :annotator_id, :display_name, :role, :token_hash, :active, :assigned_count
            )
            ON CONFLICT (annotator_id) DO UPDATE SET
                display_name = excluded.display_name,
                role = excluded.role,
                token_hash = excluded.token_hash,
                active = excluded.active,
                assigned_count = excluded.assigned_count
            """,
            records,
        )

    def _upsert_assignments(self, assignments: pd.DataFrame) -> None:
        self.conn.executemany(
            """
            INSERT INTO assignments (annotator_id, comment_id, batch_name, position)
            VALUES (:annotator_id, :comment_id, :batch_name, :position)
            ON CONFLICT (annotator_id, comment_id) DO UPDATE SET
                batch_name = excluded.batch_name,
                position = excluded.position
            """,
            assignments.fillna("").to_dict("records"),
        )
