import pandas as pd
import pytest

from shared.utils import paths


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point DATA_DIR and DUCKDB_PATH at a temp folder so tests never touch data/."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "data" / "test.duckdb"))
    # TEST salt only (never a real one); 64 characters like secrets.token_hex(32).
    monkeypatch.setenv("COMMENTER_HASH_SALT", "test-salt-" + "0" * 54)
    return tmp_path / "data"


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    """Use a temp folder as the project root, to test project-relative paths."""
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", root)
    monkeypatch.setenv("DATA_DIR", "data")
    monkeypatch.setenv("DUCKDB_PATH", "data/research.duckdb")
    return root


@pytest.fixture
def videos_df() -> pd.DataFrame:
    """TEST DATA: synthetic records for automated tests only.

    Not real YouTube data. IDs, titles and numbers are invented.
    """
    return pd.DataFrame(
        {
            "channel_id": pd.Series(["test_channel_a", "test_channel_a", "test_channel_b"], dtype="string"),
            "video_id": pd.Series(["test_video_1", "test_video_2", "test_video_3"], dtype="string"),
            "title": pd.Series(["Test video one", "Test video two", None], dtype="string"),
            "view_count": pd.Series([100, 250, 40], dtype="Int64"),
            "like_count": pd.Series([10, pd.NA, 4], dtype="Int64"),
            "engagement_rate": [0.10, 0.08, None],
            "is_short": [False, True, False],
            "published_at": pd.to_datetime(
                ["2026-01-01T10:00:00Z", "2026-01-02T12:30:00Z", "2026-01-03T08:15:00Z"]
            ),
        }
    )
