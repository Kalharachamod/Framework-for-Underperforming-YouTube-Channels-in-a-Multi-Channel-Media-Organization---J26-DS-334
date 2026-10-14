"""PostgreSQL/Supabase database access notes and guardrails.

The live Supabase implementation is intentionally thin in this phase: SQL
migrations are prepared under ``sql/`` but are not executed automatically. Local
development and tests use ``LocalAnnotationStore``. Production wiring should be
enabled only after the section/participant schema and server-side write path are
reviewed and approved.
"""

from __future__ import annotations

from dataclasses import dataclass


class LiveDatabaseNotInitialized(RuntimeError):
    """Raised when production database access has not been approved/configured."""


class DatabaseConnectionError(RuntimeError):
    """Raised when the approved server-side database cannot be reached."""


@dataclass(frozen=True)
class SupabaseDeploymentPlan:
    schema: str = "annotation"
    required_secret: str = "SUPABASE_DB_URL (app), SUPABASE_ADMIN_DB_URL (admin), SUPABASE_IMPORT_DB_URL (import)"
    exposed_rest_schema: str = "annotation"

    def safety_summary(self) -> str:
        return (
            "Apply the prepared annotation schema migrations only after review; "
            "do not expose participant response tables directly to anonymous browser clients; "
            "keep service-role and database credentials server-side only."
        )
