import pandas as pd
import pytest

from shared.utils import (
    DatasetNotFoundError,
    SchemaError,
    dataset_exists,
    get_data_paths,
    read_dataset,
    snapshot_dir,
    write_dataset,
)


def test_write_creates_parent_folders(isolated_data_dir, videos_df):
    target = isolated_data_dir / "processed" / "component_3" / "nested" / "videos.parquet"
    written = write_dataset(videos_df, target)
    assert written == target
    assert target.is_file()


def test_round_trip_keeps_values_and_types(isolated_data_dir, videos_df):
    target = write_dataset(videos_df, isolated_data_dir / "videos.parquet")
    back = read_dataset(target)

    assert list(back.columns) == list(videos_df.columns)
    assert len(back) == 3
    assert back["view_count"].dtype == "Int64"
    assert str(back["channel_id"].dtype).startswith("string")
    assert back["is_short"].dtype == bool
    assert back["engagement_rate"].dtype == "float64"
    assert back["view_count"].tolist() == [100, 250, 40]


def test_missing_optional_values_survive(isolated_data_dir, videos_df):
    back = read_dataset(write_dataset(videos_df, isolated_data_dir / "videos.parquet"))
    assert back["like_count"].isna().tolist() == [False, True, False]
    assert back["title"].isna().tolist() == [False, False, True]
    assert pd.isna(back.loc[2, "engagement_rate"])


def test_timestamps_stored_as_utc(isolated_data_dir):
    df = pd.DataFrame(
        {
            "naive": pd.to_datetime(["2026-10-07 10:00:00"]),
            "colombo": pd.to_datetime(["2026-10-07 15:30:00"]).tz_localize("Asia/Colombo"),
        }
    )
    back = read_dataset(write_dataset(df, isolated_data_dir / "times.parquet"))

    assert str(back["naive"].dt.tz) == "UTC"
    assert str(back["colombo"].dt.tz) == "UTC"
    # Naive values are taken as UTC; zoned values are converted (+05:30 -> UTC).
    assert back.loc[0, "naive"] == pd.Timestamp("2026-10-07 10:00:00", tz="UTC")
    assert back.loc[0, "colombo"] == pd.Timestamp("2026-10-07 10:00:00", tz="UTC")


def test_write_does_not_modify_input(isolated_data_dir):
    df = pd.DataFrame({"t": pd.to_datetime(["2026-10-07 10:00:00"])})
    write_dataset(df, isolated_data_dir / "t.parquet")
    assert df["t"].dt.tz is None


def test_exists_detection(isolated_data_dir, videos_df):
    target = isolated_data_dir / "processed" / "videos.parquet"
    assert not dataset_exists(target)
    assert not dataset_exists(isolated_data_dir / "processed")
    write_dataset(videos_df, target)
    assert dataset_exists(target)
    assert dataset_exists(isolated_data_dir / "processed")  # folder containing Parquet


def test_refuses_overwrite_by_default(isolated_data_dir, videos_df):
    target = write_dataset(videos_df, isolated_data_dir / "videos.parquet")
    with pytest.raises(FileExistsError):
        write_dataset(videos_df.head(1), target)
    assert len(read_dataset(target)) == 3


def test_overwrite_replaces_and_leaves_no_temp_file(isolated_data_dir, videos_df):
    target = write_dataset(videos_df, isolated_data_dir / "videos.parquet")
    write_dataset(videos_df.head(1), target, overwrite=True)
    assert len(read_dataset(target)) == 1
    assert [p.name for p in target.parent.iterdir()] == ["videos.parquet"]


def test_read_selected_columns(isolated_data_dir, videos_df):
    target = write_dataset(videos_df, isolated_data_dir / "videos.parquet")
    assert list(read_dataset(target, columns=["video_id"]).columns) == ["video_id"]


def test_read_missing_dataset_raises_clean_error(isolated_data_dir):
    with pytest.raises(DatasetNotFoundError, match="No Parquet dataset"):
        read_dataset(isolated_data_dir / "does_not_exist.parquet")
    # Still a FileNotFoundError for callers that catch the built-in.
    with pytest.raises(FileNotFoundError):
        read_dataset("data/does_not_exist.parquet")


def test_rejects_non_parquet_path(isolated_data_dir, videos_df):
    with pytest.raises(ValueError, match=".parquet"):
        write_dataset(videos_df, isolated_data_dir / "videos.csv")


def test_schema_checks(isolated_data_dir, videos_df):
    target = isolated_data_dir / "videos.parquet"
    with pytest.raises(SchemaError, match="video_url"):
        write_dataset(videos_df, target, required_columns=["video_id", "video_url"])

    dupes = pd.DataFrame([[1, 2]], columns=["a", "a"])
    with pytest.raises(SchemaError, match="Duplicate"):
        write_dataset(dupes, target)

    with pytest.raises(TypeError):
        write_dataset([{"a": 1}], target)

    assert not target.exists()


def test_project_relative_paths(project_root, videos_df, monkeypatch, tmp_path):
    # Run from an unrelated folder: relative paths must still land in the project.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    written = write_dataset(videos_df, "data/processed/component_3/videos.parquet")
    assert written == project_root / "data" / "processed" / "component_3" / "videos.parquet"
    assert dataset_exists("data/processed/component_3/videos.parquet")
    assert len(read_dataset("data/processed/component_3/videos.parquet")) == 3
    assert not any(elsewhere.iterdir())


def test_snapshot_layout(isolated_data_dir, videos_df):
    for day in ["2026-10-07", "2026-10-08"]:
        write_dataset(videos_df, snapshot_dir(day) / "videos.parquet")

    snapshots = get_data_paths().snapshots
    assert sorted(p.name for p in snapshots.iterdir()) == ["2026-10-07", "2026-10-08"]
    assert len(read_dataset(snapshots / "2026-10-08" / "videos.parquet")) == 3
