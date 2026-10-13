from datetime import date

import pytest

from shared.utils import paths


def test_defaults_are_project_relative(project_root):
    p = paths.get_data_paths()
    assert p.root == project_root / "data"
    assert p.raw == project_root / "data" / "raw"
    assert p.processed == project_root / "data" / "processed"
    assert p.features == project_root / "data" / "features"
    assert p.snapshots == project_root / "data" / "snapshots"
    assert p.duckdb == project_root / "data" / "research.duckdb"


def test_env_override(isolated_data_dir):
    assert paths.get_data_paths().root == isolated_data_dir


def test_real_project_root_is_repository():
    assert (paths.PROJECT_ROOT / "pyproject.toml").is_file()
    assert (paths.PROJECT_ROOT / "shared").is_dir()


def test_snapshot_dir_accepts_date_or_string(isolated_data_dir):
    expected = isolated_data_dir / "snapshots" / "2026-10-07"
    assert paths.snapshot_dir("2026-10-07") == expected
    assert paths.snapshot_dir(date(2026, 10, 7)) == expected


def test_snapshot_dir_rejects_bad_date():
    with pytest.raises(ValueError):
        paths.snapshot_dir("07/10/2026")


def test_component_dir(isolated_data_dir):
    assert paths.component_dir(3) == isolated_data_dir / "processed" / "component_3"
    with pytest.raises(ValueError):
        paths.component_dir(5)
