"""PostgreSQL/Supabase deployment guardrails.

The production implementation is ``supabase_store.SupabaseAnnotationStore``.
This module keeps the deployment plan and safety wording separate from the
database adapter; local development and tests continue to use SQLite.
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
