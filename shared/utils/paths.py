"""Central configuration of research data locations.

All paths are resolved relative to the repository root, so the project works on
any machine. ``DATA_DIR`` and ``DUCKDB_PATH`` can be overridden in ``.env``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_DATA_DIR = "data"
DEFAULT_DUCKDB_PATH = "data/research.duckdb"


@dataclass(frozen=True)
class DataPaths:
    root: Path
    raw: Path
    processed: Path
    features: Path
    snapshots: Path
    duckdb: Path


def resolve_path(path: str | os.PathLike[str]) -> Path:
    """Return an absolute path; relative paths are taken from the project root."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


def get_data_paths() -> DataPaths:
    """Read the configured data locations (environment first, then defaults)."""
    root = resolve_path(os.getenv("DATA_DIR") or DEFAULT_DATA_DIR)
    return DataPaths(
        root=root,
        raw=root / "raw",
        processed=root / "processed",
        features=root / "features",
        snapshots=root / "snapshots",
        duckdb=resolve_path(os.getenv("DUCKDB_PATH") or DEFAULT_DUCKDB_PATH),
    )


def snapshot_dir(snapshot_date: date | str) -> Path:
    """Folder for one historical snapshot, e.g. ``data/snapshots/2026-10-07``."""
    if isinstance(snapshot_date, str):
        snapshot_date = date.fromisoformat(snapshot_date)
    return get_data_paths().snapshots / snapshot_date.isoformat()


def component_dir(component: int) -> Path:
    """Processed-output folder of one research component (1-4)."""
    if component not in (1, 2, 3, 4):
        raise ValueError(f"component must be 1-4, got {component!r}")
    return get_data_paths().processed / f"component_{component}"
