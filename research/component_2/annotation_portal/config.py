"""Configuration for the Component 2 annotation portal."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ANNOTATION_CSV = PROJECT_ROOT / "data" / "processed" / "component_2" / "annotation" / "component2_demand_annotation_sample.csv"
DEFAULT_LOCAL_DB = PROJECT_ROOT / "data" / "processed" / "component_2" / "annotation" / "annotation_portal_local.sqlite3"
DEFAULT_ASSIGNMENT_SEED = 20261014
DEFAULT_ANNOTATION_RUN_ID = "component2_phase2a_20261014"
DEFAULT_LOCAL_PORTAL_SECRET = "local-development-secret"


@dataclass(frozen=True)
class PortalConfig:
    mode: str
    annotation_csv_path: Path
    local_db_path: Path
    assignment_seed: int
    portal_secret: str
    supabase_db_url: str | None
    annotation_run_id: str = DEFAULT_ANNOTATION_RUN_ID
    db_connect_timeout: int = 10
    supabase_admin_db_url: str | None = None
    supabase_import_db_url: str | None = None

    def __repr__(self) -> str:
        db_state = "***" if self.supabase_db_url else None
        admin_db_state = "***" if self.supabase_admin_db_url else None
        import_db_state = "***" if self.supabase_import_db_url else None
        secret_state = "***" if self.portal_secret else None
        return (
            "PortalConfig("
            f"mode={self.mode!r}, annotation_csv_path={str(self.annotation_csv_path)!r}, "
            f"local_db_path={str(self.local_db_path)!r}, assignment_seed={self.assignment_seed!r}, "
            f"portal_secret={secret_state!r}, supabase_db_url={db_state!r}, "
            f"supabase_admin_db_url={admin_db_state!r}, supabase_import_db_url={import_db_state!r}, "
            f"annotation_run_id={self.annotation_run_id!r}, db_connect_timeout={self.db_connect_timeout!r})"
        )


def load_config(
    settings: Mapping[str, object] | None = None,
    *,
    require_app_db_url: bool = True,
) -> PortalConfig:
    def get_value(name: str, default: str = "") -> str:
        if settings is not None and name in settings:
            return str(settings[name])
        return os.getenv(name, default)

    mode = get_value("COMPONENT2_ANNOTATION_MODE", "local").strip().lower()
    if mode not in {"local", "supabase"}:
        raise ValueError("COMPONENT2_ANNOTATION_MODE must be 'local' or 'supabase'")
    annotation_csv = Path(get_value("COMPONENT2_ANNOTATION_CSV", str(DEFAULT_ANNOTATION_CSV))).expanduser()
    local_db = Path(get_value("COMPONENT2_ANNOTATION_LOCAL_DB", str(DEFAULT_LOCAL_DB))).expanduser()
    seed = int(get_value("COMPONENT2_ASSIGNMENT_SEED", str(DEFAULT_ASSIGNMENT_SEED)))
    secret = get_value("COMPONENT2_PORTAL_SECRET", DEFAULT_LOCAL_PORTAL_SECRET)
    db_url = get_value("SUPABASE_DB_URL", "").strip() or None
    if mode == "supabase" and require_app_db_url and not db_url:
        raise ValueError("SUPABASE_DB_URL is required when COMPONENT2_ANNOTATION_MODE=supabase")
    if mode == "supabase" and (secret == DEFAULT_LOCAL_PORTAL_SECRET or len(secret) < 32):
        raise ValueError("COMPONENT2_PORTAL_SECRET must be a unique secret of at least 32 characters in Supabase mode")
    admin_db_url = get_value("SUPABASE_ADMIN_DB_URL", "").strip() or None
    import_db_url = get_value("SUPABASE_IMPORT_DB_URL", "").strip() or None
    run_id = get_value("COMPONENT2_ANNOTATION_RUN_ID", DEFAULT_ANNOTATION_RUN_ID).strip()
    if not run_id:
        raise ValueError("COMPONENT2_ANNOTATION_RUN_ID must not be empty")
    if mode == "supabase" and run_id != DEFAULT_ANNOTATION_RUN_ID:
        raise ValueError(
            f"Supabase mode must use the imported run ID {DEFAULT_ANNOTATION_RUN_ID}"
        )
    if mode == "supabase" and seed != DEFAULT_ASSIGNMENT_SEED:
        raise ValueError(
            f"Supabase mode must use the imported assignment seed {DEFAULT_ASSIGNMENT_SEED}"
        )
    timeout = int(get_value("COMPONENT2_DB_CONNECT_TIMEOUT", "10"))
    if timeout <= 0:
        raise ValueError("COMPONENT2_DB_CONNECT_TIMEOUT must be positive")
    return PortalConfig(
        mode=mode,
        annotation_csv_path=annotation_csv,
        local_db_path=local_db,
        assignment_seed=seed,
        portal_secret=secret,
        supabase_db_url=db_url,
        annotation_run_id=run_id,
        db_connect_timeout=timeout,
        supabase_admin_db_url=admin_db_url,
        supabase_import_db_url=import_db_url,
    )
