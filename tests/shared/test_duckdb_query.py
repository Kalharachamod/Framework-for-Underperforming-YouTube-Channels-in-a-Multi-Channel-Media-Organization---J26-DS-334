import duckdb
import pandas as pd
import pytest

from shared.utils import (
    DatasetNotFoundError,
    connect,
    duckdb_connection,
    query,
    query_parquet,
    snapshot_dir,
    write_dataset,
)


def test_connect_uses_configured_file(isolated_data_dir):
    with duckdb_connection() as con:
        assert con.execute("SELECT 42").fetchone() == (42,)
    assert (isolated_data_dir / "test.duckdb").is_file()


def test_connection_is_closed_after_context(isolated_data_dir):
    with duckdb_connection() as con:
        pass
    with pytest.raises(duckdb.ConnectionException):
        con.execute("SELECT 1")


def test_in_memory_creates_no_file(isolated_data_dir):
    with duckdb_connection(":memory:") as con:
        assert con.execute("SELECT 1").fetchone() == (1,)
    assert not (isolated_data_dir / "test.duckdb").exists()


def test_execute_sql_with_parameters():
    result = query("SELECT ? + ? AS total", [2, 3], database=":memory:")
    assert isinstance(result, pd.DataFrame)
    assert result.loc[0, "total"] == 5


def test_tables_persist_in_database_file(isolated_data_dir):
    with duckdb_connection() as con:
        con.execute("CREATE TABLE notes (id INTEGER)")
        con.execute("INSERT INTO notes VALUES (1), (2)")
    assert query("SELECT count(*) AS n FROM notes").loc[0, "n"] == 2


def test_read_only_missing_database_raises(isolated_data_dir):
    with pytest.raises(FileNotFoundError):
        connect(isolated_data_dir / "missing.duckdb", read_only=True)


def test_invalid_sql_raises():
    with pytest.raises(duckdb.Error):
        query("SELEC nonsense", database=":memory:")


def test_dataframe_to_parquet_to_duckdb_pipeline(isolated_data_dir, videos_df):
    """DataFrame -> Parquet -> DuckDB -> SQL -> expected result (TEST DATA)."""
    target = write_dataset(videos_df, isolated_data_dir / "processed" / "videos.parquet")

    result = query_parquet(
        target,
        """
        SELECT channel_id, count(*) AS videos, sum(view_count) AS views
        FROM dataset
        GROUP BY channel_id
        ORDER BY channel_id
        """,
    )

    assert result["channel_id"].tolist() == ["test_channel_a", "test_channel_b"]
    assert result["videos"].tolist() == [2, 1]
    assert result["views"].tolist() == [350, 40]


def test_query_parquet_with_parameters(isolated_data_dir, videos_df):
    target = write_dataset(videos_df, isolated_data_dir / "videos.parquet")
    result = query_parquet(target, "SELECT video_id FROM dataset WHERE view_count > ?", [50])
    assert sorted(result["video_id"]) == ["test_video_1", "test_video_2"]


def test_duckdb_keeps_types_nulls_and_utc(isolated_data_dir, videos_df):
    target = write_dataset(videos_df, isolated_data_dir / "videos.parquet")
    result = query_parquet(target, "SELECT * FROM dataset ORDER BY video_id")

    assert result["like_count"].isna().tolist() == [False, True, False]
    assert result["title"].isna().tolist() == [False, False, True]
    assert str(result["published_at"].dt.tz) == "UTC"
    assert result.loc[0, "published_at"] == pd.Timestamp("2026-01-01 10:00:00", tz="UTC")


def test_sql_can_reference_project_relative_parquet(project_root, videos_df, monkeypatch, tmp_path):
    write_dataset(videos_df, "data/processed/example.parquet")
    monkeypatch.chdir(tmp_path)  # not the project root

    result = query("SELECT count(*) AS n FROM 'data/processed/example.parquet'")
    assert result.loc[0, "n"] == 3


def test_query_folder_of_snapshots(isolated_data_dir, videos_df):
    write_dataset(videos_df, snapshot_dir("2026-10-07") / "videos.parquet")
    write_dataset(videos_df.head(1), snapshot_dir("2026-10-08") / "videos.parquet")

    result = query_parquet(
        isolated_data_dir / "snapshots",
        "SELECT count(*) AS n FROM dataset",
    )
    assert result.loc[0, "n"] == 4


def test_query_glob(isolated_data_dir, videos_df):
    write_dataset(videos_df, snapshot_dir("2026-10-07") / "videos.parquet")
    result = query_parquet(isolated_data_dir / "snapshots" / "*" / "videos.parquet",
                           "SELECT count(*) AS n FROM dataset")
    assert result.loc[0, "n"] == 3


def test_query_missing_parquet_raises_clean_error(isolated_data_dir):
    with pytest.raises(DatasetNotFoundError):
        query_parquet(isolated_data_dir / "missing.parquet")
    with pytest.raises(DatasetNotFoundError):
        query_parquet(isolated_data_dir / "snapshots" / "*" / "videos.parquet")
