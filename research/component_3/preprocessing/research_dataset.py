"""Component 3 research-data preparation: research snapshot -> DuckDB -> validation -> research-ready dataset.

    python -m research.component_3.preprocessing.research_dataset --extract        # Supabase -> new snapshot -> prepare
    python -m research.component_3.preprocessing.research_dataset                  # prepare the latest snapshot
    python -m research.component_3.preprocessing.research_dataset --snapshot rs-20261008T091800Z

Boundary between RAW/CURRENT collection data (Supabase) and RESEARCH-READY data:

    Supabase -> research snapshot (immutable Parquet) -> DuckDB views -> checks -> report
             -> research-ready Parquet datasets in data/processed/component_3/<snapshot_id>/

All transformations are deterministic DuckDB SQL over the snapshot's Parquet
files (nothing is copied into a permanent database). Data is never repaired or
deduplicated here: problems are reported and block the "research-ready" status.

Commenters appear only as pseudonyms (``commenter_id``). Shared commenters are
observable interaction signals; they do not show audience migration,
subscription, identity or causality. No graph algorithm or score is computed.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from shared.schemas import Channel, Comment, Video
from shared.utils import quality, snapshots
from shared.utils.datasets import DATASETS
from shared.utils.duckdb_query import MEMORY, duckdb_connection
from shared.utils.parquet_io import write_dataset
from shared.utils.paths import component_dir
from shared.utils.privacy import HASH_PREFIX

REPORT_FILE = "_research_report.json"
PSEUDONYM_RE = rf"{HASH_PREFIX}[0-9a-f]{{64}}"
TOP_PAIRS = 20

# Research-ready datasets (DuckDB views) exported per snapshot.
DATASET_VIEWS = ("channel_dataset", "video_dataset", "comment_dataset", "commenter_participation",
                 "commenter_channels", "channel_commenters", "channel_pair_overlap")

_VIEWS = {
    # One row per channel, with how much of it is represented in the snapshot.
    "channel_dataset": """
        SELECT ch.*, coalesce(v.n, 0) AS stored_videos, coalesce(c.n, 0) AS stored_comments
        FROM channels ch
        LEFT JOIN (SELECT channel_id, count(*) AS n FROM videos GROUP BY channel_id) v USING (channel_id)
        LEFT JOIN (SELECT channel_id, count(*) AS n FROM comments GROUP BY channel_id) c USING (channel_id)
        ORDER BY ch.channel_id""",
    # One row per video, with its channel name (all original timestamps kept).
    "video_dataset": """
        SELECT v.*, ch.channel_name
        FROM videos v LEFT JOIN channels ch USING (channel_id)
        ORDER BY v.channel_id, v.published_at, v.video_id""",
    # One row per comment; the pseudonym is exposed as commenter_id.
    "comment_dataset": """
        SELECT comment_id, video_id, channel_id, author_channel_id AS commenter_id,
               parent_comment_id, parent_comment_id IS NOT NULL AS is_reply,
               comment_text, like_count, published_at, edited_at, collected_at
        FROM comments
        ORDER BY video_id, published_at, comment_id""",
    # commenter x channel x video participation (event timestamps aggregated per video only).
    "commenter_participation": """
        SELECT author_channel_id AS commenter_id, channel_id, video_id,
               count(*) AS comment_count,
               count(*) FILTER (WHERE parent_comment_id IS NOT NULL) AS reply_count,
               min(published_at) AS first_comment_at, max(published_at) AS last_comment_at
        FROM comments
        WHERE author_channel_id IS NOT NULL
        GROUP BY author_channel_id, channel_id, video_id
        ORDER BY commenter_id, channel_id, video_id""",
    # Per commenter: on how many channels / videos they commented.
    "commenter_channels": """
        SELECT author_channel_id AS commenter_id,
               count(DISTINCT channel_id) AS channel_count,
               count(DISTINCT video_id) AS video_count,
               count(*) AS comment_count,
               min(published_at) AS first_comment_at, max(published_at) AS last_comment_at
        FROM comments
        WHERE author_channel_id IS NOT NULL
        GROUP BY author_channel_id
        ORDER BY channel_count DESC, commenter_id""",
    # Per channel: distinct commenters, and how many of them also comment elsewhere.
    "channel_commenters": """
        WITH cc AS (SELECT DISTINCT author_channel_id AS commenter_id, channel_id
                    FROM comments WHERE author_channel_id IS NOT NULL),
             multi AS (SELECT commenter_id FROM cc GROUP BY commenter_id HAVING count(*) > 1)
        SELECT cc.channel_id,
               count(*) AS unique_commenters,
               count(*) FILTER (WHERE cc.commenter_id IN (SELECT commenter_id FROM multi))
                   AS commenters_also_on_other_channels
        FROM cc GROUP BY cc.channel_id
        ORDER BY unique_commenters DESC, cc.channel_id""",
    # Unordered channel pairs (channel_a < channel_b) and their number of shared commenters.
    "channel_pair_overlap": """
        WITH cc AS (SELECT DISTINCT author_channel_id AS commenter_id, channel_id
                    FROM comments WHERE author_channel_id IS NOT NULL)
        SELECT a.channel_id AS channel_a, b.channel_id AS channel_b, count(*) AS shared_commenters
        FROM cc a JOIN cc b ON a.commenter_id = b.commenter_id AND a.channel_id < b.channel_id
        GROUP BY a.channel_id, b.channel_id
        ORDER BY shared_commenters DESC, channel_a, channel_b""",
}


@dataclass
class ResearchCheck:
    code: str
    message: str
    count: int
    severity: str = "error"   # research-level problems block research readiness
    examples: list[str] = field(default_factory=list)


@dataclass
class ResearchDataReport:
    """Descriptive data-quality statistics of one research snapshot (not research findings)."""

    snapshot_id: str
    snapshot_created_at: str
    prepared_at: str
    counts: dict[str, int]
    quality_status: str                       # STEP 07 status of the three datasets
    quality_by_dataset: dict[str, str]
    duplicates: dict[str, dict[str, int]]
    missing_required: dict[str, dict[str, int]]
    valid_nulls: dict[str, dict[str, int]]
    relationships: dict[str, int]
    cross_channel: dict[str, Any]
    research_checks: list[ResearchCheck]
    quality_issues: list[dict[str, Any]]

    @property
    def research_ready(self) -> bool:
        return self.quality_status != quality.Status.INVALID.value and not any(
            c.severity == "error" for c in self.research_checks)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["research_ready"] = self.research_ready
        d["note"] = ("Descriptive data-quality statistics. Shared commenters are interaction signals; "
                     "they do not show audience migration or causality.")
        return d

    def text(self) -> str:
        c, r, x = self.counts, self.relationships, self.cross_channel
        lines = [
            f"Research data report - snapshot {self.snapshot_id} (created {self.snapshot_created_at})",
            f"Research-ready: {'YES' if self.research_ready else 'NO'}   |   STEP 07 quality: {self.quality_status}",
            "",
            f"Counts: channels {c['channels']} | videos {c['videos']} | comments {c['comments']} "
            f"(top-level {c['top_level_comments']}, replies {c['replies']}) | unique commenters {c['unique_commenters']}",
            "Duplicates (rows beyond the first per id): " + ", ".join(
                f"{n} {d['duplicate_rows']} (conflicting ids {d['conflicting_ids']})" for n, d in self.duplicates.items()),
            "Missing required values: " + (", ".join(
                f"{n}.{col}={v}" for n, cols in self.missing_required.items() for col, v in cols.items() if v) or "none"),
            f"Relationships: video->channel {r['videos_with_channel']}/{c['videos']} | "
            f"comment->video {r['comments_with_video']}/{c['comments']} | "
            f"comment->channel {r['comments_with_channel']}/{c['comments']} | "
            f"reply->parent {r['replies_with_parent']}/{c['replies']}",
            "",
            "Cross-channel readiness (descriptive, not findings):",
            f"  commenters on one channel {x['commenters_on_one_channel']} | on 2+ channels "
            f"{x['commenters_on_multiple_channels']} | channels with commenters {x['channels_with_commenters']} "
            f"| comments without commenter id {x['comments_without_commenter_id']} | channel pairs with overlap "
            f"{x['channel_pairs_with_overlap']}",
        ]
        for p in x["top_channel_pairs"][:10]:
            lines.append(f"    {p['channel_a']} <-> {p['channel_b']}: {p['shared_commenters']} shared commenter(s)")
        problems = [ch for ch in self.research_checks]
        if problems:
            lines.append("")
            lines += [f"  {ch.severity.upper():7} {ch.code}: {ch.message}"
                      + (f" (e.g. {', '.join(ch.examples)})" if ch.examples else "") for ch in problems]
        if self.quality_issues:
            lines.append("")
            lines.append("STEP 07 quality issues:")
            lines += [f"  {i['severity'].upper():7} [{i['dataset']}] {i['message']}" for i in self.quality_issues]
        return "\n".join(lines) + "\n"


# --- DuckDB session over a research snapshot ------------------------------------------------

@contextmanager
def research_session(snapshot_id: str) -> Iterator[duckdb.DuckDBPyConnection]:
    """In-memory DuckDB session: raw views (channels, videos, comments) over the snapshot's
    Parquet files plus the research-ready views. Nothing is written."""
    info = snapshots.get_research_snapshot(snapshot_id)
    with duckdb_connection(MEMORY) as con:
        for name in DATASETS:
            path = snapshots.research_dataset_path(info.snapshot_id, name).as_posix().replace("'", "''")
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
        for view, sql in _VIEWS.items():
            con.execute(f"CREATE VIEW {view} AS {sql}")
        yield con


def query(con: duckdb.DuckDBPyConnection, view: str) -> pd.DataFrame:
    if view not in _VIEWS:
        raise ValueError(f"unknown research view {view!r}; available: {sorted(_VIEWS)}")
    return con.execute(f"SELECT * FROM {view}").df()


# --- preparation -------------------------------------------------------------------------

def prepare(snapshot_id: str, *, export: bool = True, save_report: bool = True) -> ResearchDataReport:
    """Validate a research snapshot and (if research-ready) export the research datasets.

    Raises ``SnapshotValidationError`` if the snapshot files no longer match their checksums.

    Exports go to data/processed/component_3/<snapshot_id>/ and are written once
    (an existing export is left untouched). The report is saved next to the
    snapshot as derived metadata; the snapshot files themselves are never changed.
    """
    info = snapshots.get_research_snapshot(snapshot_id)
    integrity = snapshots.verify_research_snapshot(info.snapshot_id)
    if not integrity.ok:  # never analyse files that differ from what was frozen
        raise snapshots.SnapshotValidationError(info.snapshot_id, integrity.errors)
    files = {name: snapshots.research_dataset_path(info.snapshot_id, name) for name in DATASETS}
    step07 = quality.validate_files(files, scope=f"research:{info.snapshot_id}", unique_by_collection=False)

    with research_session(info.snapshot_id) as con:
        report = _build_report(con, info, step07)

    if save_report:
        _write_json(info.path / REPORT_FILE, report.to_dict())
    if export and report.research_ready:
        export_research_datasets(info.snapshot_id)
    return report


def export_research_datasets(snapshot_id: str) -> Path:
    """Write the research-ready views as Parquet (once per snapshot)."""
    target = component_dir(3) / snapshot_id
    if target.exists():
        return target
    staging = target.with_name(f".{snapshot_id}.staging")
    with research_session(snapshot_id) as con:
        for view in DATASET_VIEWS:
            write_dataset(query(con, view), staging / f"{view}.parquet", overwrite=True)
    os.replace(staging, target)
    return target


def _build_report(con, info, step07: quality.ValidationRun) -> ResearchDataReport:
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    counts = {
        "channels": one("SELECT count(*) FROM channels"),
        "videos": one("SELECT count(*) FROM videos"),
        "comments": one("SELECT count(*) FROM comments"),
        "top_level_comments": one("SELECT count(*) FROM comments WHERE parent_comment_id IS NULL"),
        "replies": one("SELECT count(*) FROM comments WHERE parent_comment_id IS NOT NULL"),
        "unique_commenters": one("SELECT count(DISTINCT author_channel_id) FROM comments"),
    }
    keys = {"channels": "channel_id", "videos": "video_id", "comments": "comment_id"}
    duplicates = {
        n: {"duplicate_rows": one(f"SELECT count(*) - count(DISTINCT {k}) FROM {n}"),
            "conflicting_ids": one(f"SELECT count(*) FROM (SELECT {k} FROM {n} GROUP BY {k} "
                                   f"HAVING count(DISTINCT {n}) > 1)")}
        for n, k in keys.items()}

    models = {"channels": Channel, "videos": Video, "comments": Comment}
    missing_required: dict[str, dict[str, int]] = {}
    valid_nulls: dict[str, dict[str, int]] = {}
    for n, model in models.items():
        nulls = step07.results[n].null_counts
        req = {c for c, f in model.model_fields.items() if f.is_required()}
        missing_required[n] = {c: int(v) for c, v in nulls.items() if c in req}
        valid_nulls[n] = {c: int(v) for c, v in nulls.items() if c not in req and v}

    relationships = {
        "videos_with_channel": one("SELECT count(*) FROM videos WHERE channel_id IN (SELECT channel_id FROM channels)"),
        "comments_with_video": one("SELECT count(*) FROM comments WHERE video_id IN (SELECT video_id FROM videos)"),
        "comments_with_channel": one(
            "SELECT count(*) FROM comments WHERE channel_id IN (SELECT channel_id FROM channels)"),
        "replies_with_parent": one("SELECT count(*) FROM comments WHERE parent_comment_id IN "
                                   "(SELECT comment_id FROM comments)"),
    }

    checks = _research_checks(con, counts, duplicates, missing_required, relationships)

    pairs = con.execute(f"SELECT * FROM channel_pair_overlap LIMIT {TOP_PAIRS}").df()
    cross = {
        "commenters_on_one_channel": one("SELECT count(*) FROM commenter_channels WHERE channel_count = 1"),
        "commenters_on_multiple_channels": one("SELECT count(*) FROM commenter_channels WHERE channel_count > 1"),
        "channels_with_commenters": one("SELECT count(*) FROM channel_commenters"),
        "comments_without_commenter_id": one("SELECT count(*) FROM comments WHERE author_channel_id IS NULL"),
        "channel_pairs_with_overlap": one("SELECT count(*) FROM channel_pair_overlap"),
        "top_channel_pairs": [{"channel_a": r.channel_a, "channel_b": r.channel_b,
                               "shared_commenters": int(r.shared_commenters)} for r in pairs.itertuples()],
    }
    quality_issues = [{"dataset": n, "code": i.code, "severity": i.severity, "message": i.message, "count": i.count}
                      for n, res in step07.results.items() for i in res.issues]
    return ResearchDataReport(
        snapshot_id=info.snapshot_id,
        snapshot_created_at=info.manifest["created_at"],
        prepared_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        counts=counts, quality_status=step07.status.value,
        quality_by_dataset={n: r.status.value for n, r in step07.results.items()},
        duplicates=duplicates, missing_required=missing_required, valid_nulls=valid_nulls,
        relationships=relationships, cross_channel=cross, research_checks=checks, quality_issues=quality_issues,
    )


def _research_checks(con, counts, duplicates, missing_required, relationships) -> list[ResearchCheck]:
    """Research-level rules: in a full snapshot these are errors (STEP 07 treats some as warnings)."""
    checks: list[ResearchCheck] = []

    def add(code, message, count, examples_sql=None, severity="error"):
        if count:
            ex = [str(r[0]) for r in con.execute(examples_sql).fetchall()] if examples_sql else []
            checks.append(ResearchCheck(code, message, int(count), severity, ex))

    for n, d in duplicates.items():
        add(f"duplicate_{n}", f"{d['duplicate_rows']} duplicate {n} row(s)", d["duplicate_rows"])
    for n, cols in missing_required.items():
        for col, v in cols.items():
            add(f"missing_{n}_{col}", f"{v} {n} row(s) missing required '{col}'", v)

    add("orphan_videos", "videos whose channel is not in the snapshot",
        counts["videos"] - relationships["videos_with_channel"],
        "SELECT video_id FROM videos WHERE channel_id NOT IN (SELECT channel_id FROM channels) ORDER BY 1 LIMIT 5")
    add("orphan_comments", "comments whose video is not in the snapshot",
        counts["comments"] - relationships["comments_with_video"],
        "SELECT comment_id FROM comments WHERE video_id NOT IN (SELECT video_id FROM videos) ORDER BY 1 LIMIT 5")
    add("comments_without_channel", "comments whose channel is not in the snapshot",
        counts["comments"] - relationships["comments_with_channel"],
        "SELECT comment_id FROM comments WHERE channel_id NOT IN (SELECT channel_id FROM channels) ORDER BY 1 LIMIT 5")
    add("orphan_replies", "replies whose parent comment is not in the snapshot",
        counts["replies"] - relationships["replies_with_parent"],
        "SELECT comment_id FROM comments WHERE parent_comment_id IS NOT NULL AND parent_comment_id NOT IN "
        "(SELECT comment_id FROM comments) ORDER BY 1 LIMIT 5")
    sql = ("FROM comments r JOIN comments p ON p.comment_id = r.parent_comment_id "
           "WHERE r.video_id <> p.video_id OR r.parent_comment_id = r.comment_id")
    add("invalid_reply_links", "replies on a different video than their parent (or replying to themselves)",
        con.execute(f"SELECT count(*) {sql}").fetchone()[0], f"SELECT r.comment_id {sql} ORDER BY 1 LIMIT 5")
    sql = "FROM comments c JOIN videos v USING (video_id) WHERE c.channel_id <> v.channel_id"
    add("comment_channel_mismatch", "comments whose channel_id differs from their video's channel",
        con.execute(f"SELECT count(*) {sql}").fetchone()[0], f"SELECT c.comment_id {sql} ORDER BY 1 LIMIT 5")
    # Privacy: commenter ids must be pseudonyms. Never show the offending values.
    add("unpseudonymized_commenter_ids", "commenter ids that are not pseudonyms (values not shown)",
        con.execute("SELECT count(*) FROM comments WHERE author_channel_id IS NOT NULL "
                    "AND NOT regexp_full_match(author_channel_id, ?)", [PSEUDONYM_RE]).fetchone()[0])
    if counts["channels"] == 0 or counts["videos"] == 0:
        checks.append(ResearchCheck("empty_dataset", "the snapshot has no channels or no videos", 1))
    return checks


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


# --- command line -------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="research_dataset", description="Prepare the Component 3 research dataset.")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--extract", action="store_true", help="create a new research snapshot from Supabase first")
    src.add_argument("--snapshot", help="research snapshot id (default: latest)")
    parser.add_argument("--no-export", action="store_true", help="validate and report only")
    args = parser.parse_args(argv)

    try:
        if args.extract:
            from shared.database.connection import connect
            from shared.database.snapshot_export import export_research_snapshot
            with connect() as conn:
                info = export_research_snapshot(conn)
            print(f"Created research snapshot {info.snapshot_id}: {info.row_counts}")
            sid = info.snapshot_id
        else:
            sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        report = prepare(sid, export=not args.no_export)
    except Exception as exc:  # report cleanly; secrets are never part of these messages
        print(f"Error: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}", file=sys.stderr)
        return 2
    print(report.text())
    if report.research_ready and not args.no_export:
        print(f"Research-ready datasets: {component_dir(3) / sid}")
    return 0 if report.research_ready else 1


if __name__ == "__main__":
    sys.exit(main())
