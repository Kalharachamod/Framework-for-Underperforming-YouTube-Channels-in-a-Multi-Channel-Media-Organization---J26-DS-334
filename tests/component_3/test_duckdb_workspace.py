"""Tests for the DuckDB research workspace (views over a snapshot and its Component 3 results).

TEST DATA only: a synthetic research snapshot and small synthetic artifact files in a temp data
folder (conftest isolates DATA_DIR and DUCKDB_PATH). No Supabase or YouTube API access.
"""

import json
import shutil

import duckdb
import pandas as pd

from research.component_3 import duckdb_workspace as ws
from shared.utils.paths import component_dir, get_data_paths
from tests.component_3.test_research_dataset import make_snapshot, ticking  # noqa: F401  (fixture)


def _run(kind, run_id, files, created_at=None, meta="run.json"):
    """A synthetic artifact run folder; metadata JSON only when ``created_at`` is given (complete run)."""
    sid = _sid()
    d = component_dir(3) / sid / kind / run_id
    d.mkdir(parents=True, exist_ok=True)
    for name, df in files.items():
        df.to_parquet(d / f"{name}.parquet", index=False)
    if created_at is not None:
        (d / meta).write_text(json.dumps({"created_at": created_at}), encoding="utf-8")
    return d


def _sid():
    return sorted((get_data_paths().snapshots / "research").iterdir())[-1].name


def _scores(score):
    return pd.DataFrame({"source_channel_id": ["channel:UC_test_A"], "destination_channel_id": ["channel:UC_test_B"],
                         "audience_bridge_score": [score]})


def _setup():
    make_snapshot()
    _run("bridge", "abs-000000000001", {"audience_bridge_scores": _scores(0.1)}, "2026-10-08T10:00:00Z")
    _run("bridge", "abs-000000000002", {"audience_bridge_scores": _scores(0.9)}, "2026-10-08T11:00:00Z")
    _run("bridge", "abs-000000000003", {"audience_bridge_scores": _scores(0.5)})  # incomplete: no metadata
    emb = pd.DataFrame({"node_id": ["channel:UC_test_A"], "dim_0": [0.5]})
    _run("embeddings", "m2v-000000000001", {"embeddings": emb}, "2026-10-08T10:00:00Z")
    _run("embeddings", "hgt-000000000001", {"embeddings": emb}, "2026-10-08T10:00:00Z")


def test_builds_views_for_latest_complete_runs(isolated_data_dir, ticking):  # noqa: F811
    _setup()
    summary = ws.build_workspace()
    names = {v.qualified for v in summary.views}
    assert {"snapshot.channels", "snapshot.videos", "snapshot.comments", "bridge.audience_bridge_scores",
            "embeddings.m2v_embeddings", "embeddings.hgt_embeddings"} <= names

    with duckdb.connect(str(summary.database), read_only=True) as con:
        # newest complete run wins; the incomplete newer folder is ignored
        assert con.execute("SELECT audience_bridge_score FROM bridge.audience_bridge_scores").fetchone()[0] == 0.9
        assert con.execute("SELECT run_id FROM workspace.sources WHERE view_name = 'audience_bridge_scores'"
                           ).fetchone()[0] == "abs-000000000002"
        named = con.execute("""SELECT s.channel_name, d.channel_name FROM bridge.audience_bridge_scores b
                               JOIN workspace.channel_lookup s ON s.node_id = b.source_channel_id
                               JOIN workspace.channel_lookup d ON d.node_id = b.destination_channel_id""").fetchall()
        assert named == [("Test UC_test_A", "Test UC_test_B")]
        assert con.execute("SELECT snapshot_id, views FROM workspace.info").fetchone() == (summary.snapshot_id,
                                                                                          len(summary.views))


def test_views_work_from_any_directory(isolated_data_dir, ticking, tmp_path, monkeypatch):  # noqa: F811
    _setup()
    summary = ws.build_workspace()
    monkeypatch.chdir(tmp_path)  # a plain client elsewhere, without the project's file_search_path
    with duckdb.connect(str(summary.database), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM snapshot.channels").fetchone()[0] == 3


def test_rebuild_replaces_own_views_and_keeps_other_objects(isolated_data_dir, ticking):  # noqa: F811
    _setup()
    summary = ws.build_workspace()
    with duckdb.connect(str(summary.database)) as con:
        con.execute("CREATE TABLE main.my_notes AS SELECT 1 AS x")
    shutil.rmtree(component_dir(3) / summary.snapshot_id / "embeddings")
    ws.build_workspace()
    with duckdb.connect(str(summary.database), read_only=True) as con:
        tables = {(r[0], r[1]) for r in con.execute(
            "SELECT table_schema, table_name FROM information_schema.tables").fetchall()}
    assert ("embeddings", "m2v_embeddings") not in tables  # stale view of a removed run is gone
    assert ("main", "my_notes") in tables  # user objects are never dropped
    assert ("bridge", "audience_bridge_scores") in tables


def test_cli_reports_missing_snapshot(isolated_data_dir, capsys):
    assert ws.main([]) == 1
    assert "no research snapshot" in capsys.readouterr().err


def test_cli_builds_and_lists_views(isolated_data_dir, ticking, capsys):  # noqa: F811
    _setup()
    assert ws.main([]) == 0
    out = capsys.readouterr().out
    assert "Views:" in out and "bridge: audience_bridge_scores" in out
