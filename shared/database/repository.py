"""Data access for the shared Supabase research database.

Writes go through the STEP 03 schemas and the STEP 04 rules
(``shared.utils.datasets.validate_records``): records are validated, commenter
ids are pseudonymized, and conflicting duplicates in one batch are rejected.

Upsert rule (same as the Parquet latest table):
  * new id                              -> inserted
  * same id, newer or equal collected_at -> current row updated (if anything changed)
  * same id, older collected_at          -> current row kept (late data never overwrites newer data)
  * every channel/video observation is also written to *_stats_history,
    so updating current values never loses earlier metrics.

Transactions: writes join the caller's transaction. Each batch is atomic (a
savepoint: either the whole batch is written or nothing), and the caller decides
when to commit, e.g. with ``shared.database.connection.database()`` which commits
on success and rolls back on error. Reads return schema objects.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

from shared.schemas import Channel, Comment, ResearchRecord, Video
from shared.utils.datasets import COLLECTED_AT, get_spec, validate_records

MAX_LIST_LIMIT = 100_000

_TABLES = {"channels": "research.channels", "videos": "research.videos", "comments": "research.comments"}
_HISTORY = {
    "channels": ("research.channel_stats_history", ["subscriber_count", "view_count", "video_count"]),
    "videos": ("research.video_stats_history", ["view_count", "like_count", "comment_count"]),
}


class DatabaseError(RuntimeError):
    """Base class for research-database errors."""


class DuplicateKeyError(DatabaseError):
    """``insert_*`` was given an id that already exists."""


class ReferentialIntegrityError(DatabaseError):
    """A record refers to a channel or video that is not in the database."""


class ConstraintViolationError(DatabaseError):
    """A database rule rejected a value (e.g. a raw commenter id, a negative count)."""


@dataclass(frozen=True)
class WriteSummary:
    dataset: str
    received: int
    inserted: int
    updated: int
    unchanged_or_older: int
    inserted_ids: tuple[str, ...] = ()
    updated_ids: tuple[str, ...] = ()
    changed_ids: tuple[str, ...] = ()    # updated, and at least one value changed
    refreshed_ids: tuple[str, ...] = ()  # updated, only collected_at moved (values identical)


# --- writes ---------------------------------------------------------------------

def upsert_channels(conn: psycopg.Connection, records: Iterable[Channel | Mapping[str, Any]]) -> WriteSummary:
    return _write(conn, "channels", records, upsert=True)


def upsert_videos(conn: psycopg.Connection, records: Iterable[Video | Mapping[str, Any]]) -> WriteSummary:
    return _write(conn, "videos", records, upsert=True)


def upsert_comments(conn: psycopg.Connection, records: Iterable[Comment | Mapping[str, Any]]) -> WriteSummary:
    return _write(conn, "comments", records, upsert=True)


def insert_channel(conn: psycopg.Connection, record: Channel | Mapping[str, Any]) -> None:
    """Insert one new channel; ``DuplicateKeyError`` if the id exists."""
    _write(conn, "channels", [record], upsert=False)


def insert_video(conn: psycopg.Connection, record: Video | Mapping[str, Any]) -> None:
    _write(conn, "videos", [record], upsert=False)


def insert_comment(conn: psycopg.Connection, record: Comment | Mapping[str, Any]) -> None:
    _write(conn, "comments", [record], upsert=False)


# Updating = upserting a newer observation of an existing record.
update_channel = upsert_channels
update_video = upsert_videos
update_comment = upsert_comments


# --- reads ----------------------------------------------------------------------

def get_channel(conn: psycopg.Connection, channel_id: str) -> Channel | None:
    return _get(conn, "channels", channel_id)


def get_video(conn: psycopg.Connection, video_id: str) -> Video | None:
    return _get(conn, "videos", video_id)


def get_comment(conn: psycopg.Connection, comment_id: str) -> Comment | None:
    return _get(conn, "comments", comment_id)


def list_channels(conn: psycopg.Connection, *, limit: int | None = None) -> list[Channel]:
    return _list(conn, "channels", "", [], "channel_id", limit)


def list_videos(conn: psycopg.Connection, channel_id: str, *, limit: int | None = None) -> list[Video]:
    """A channel's videos, newest published first."""
    return _list(conn, "videos", "channel_id = %s", [channel_id], "published_at DESC, video_id", limit)


def list_comments(conn: psycopg.Connection, *, video_id: str | None = None, channel_id: str | None = None,
                  limit: int | None = None) -> list[Comment]:
    """Comments of one video or one channel, oldest first."""
    if (video_id is None) == (channel_id is None):
        raise ValueError("give exactly one of video_id or channel_id")
    column, value = ("video_id", video_id) if video_id is not None else ("channel_id", channel_id)
    return _list(conn, "comments", f"{column} = %s", [value], "published_at, comment_id", limit)


def stats_history(conn: psycopg.Connection, dataset: str, record_id: str) -> list[dict[str, Any]]:
    """Every stored metric observation of one channel or video, oldest first."""
    if dataset not in _HISTORY:
        raise ValueError("stats history exists for 'channels' and 'videos'")
    table, metrics = _HISTORY[dataset]
    key = get_spec(dataset).key
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT collected_at, {', '.join(metrics)} FROM {table} "
                    f"WHERE {key} = %s ORDER BY collected_at", [record_id])
        return cur.fetchall()


def count_rows(conn: psycopg.Connection, dataset: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {_TABLES[get_spec(dataset).name]}").fetchone()[0]


def fetch_collected_on(conn: psycopg.Connection, dataset: str, day: str) -> list[ResearchRecord]:
    """Current rows whose latest observation was collected on ``day`` (UTC date)."""
    spec = get_spec(dataset)
    where = "collected_at >= %s::date AND collected_at < %s::date + 1"
    return _list(conn, spec.name, where, [day, day], f"{COLLECTED_AT}, {spec.key}", None)


# --- internals ---------------------------------------------------------------------

def _write(conn: psycopg.Connection, dataset: str, records: Iterable, *, upsert: bool) -> WriteSummary:
    spec = get_spec(dataset)
    models = sorted(validate_records(dataset, records), key=lambda r: getattr(r, COLLECTED_AT))
    if not models:
        return WriteSummary(spec.name, 0, 0, 0, 0)

    columns = list(spec.model.DTYPES)
    rows = [m.model_dump() for m in models]
    sql = _insert_sql(spec, columns, upsert)
    if not conn.autocommit and conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE:
        conn.execute("SELECT 1")  # open the caller's transaction so the batch becomes a savepoint
    ids = list(dict.fromkeys(getattr(m, spec.key) for m in models))
    before = {getattr(m, spec.key): m for m in _list(conn, dataset, f"{spec.key} = ANY(%s)", [ids], spec.key, None)}
    newest = {getattr(m, spec.key): m for m in models}  # models are sorted by collected_at
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(sql, rows, returning=True)
            results = []
            while True:
                results.extend(cur.fetchall())
                if not cur.nextset():
                    break
            if dataset in _HISTORY:
                cur.executemany(_history_sql(spec), rows)
    except errors.UniqueViolation:
        raise DuplicateKeyError(f"{spec.name}: id already exists (use upsert_{spec.name} to update)") from None
    except errors.ForeignKeyViolation as exc:
        raise ReferentialIntegrityError(f"{spec.name}: {_detail(exc)}") from None
    except (errors.CheckViolation, errors.NotNullViolation) as exc:
        raise ConstraintViolationError(f"{spec.name}: {_detail(exc)}") from None

    inserted_ids = tuple(dict.fromkeys(rid for rid, was_insert in results if was_insert))
    updated_ids = tuple(dict.fromkeys(rid for rid, was_insert in results if not was_insert and rid not in inserted_ids))
    # Of the updated rows: did any value change, or only collected_at (a re-observation)?
    changed_ids = tuple(rid for rid in updated_ids
                        if rid in before and _values(before[rid]) != _values(newest[rid]))
    refreshed_ids = tuple(rid for rid in updated_ids if rid not in changed_ids)
    return WriteSummary(spec.name, len(models), len(inserted_ids), len(updated_ids),
                        len(models) - len(results), inserted_ids, updated_ids, changed_ids, refreshed_ids)


def _values(record: ResearchRecord) -> dict[str, Any]:
    """Comparable field values, ignoring when the record was observed."""
    return record.model_dump(exclude={COLLECTED_AT})


def _insert_sql(spec, columns: list[str], upsert: bool) -> str:
    table = _TABLES[spec.name]
    cols = columns + ["first_collected_at", "updated_at"]
    values = [f"%({c})s" for c in columns] + [f"%({COLLECTED_AT})s", "now()"]
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(values)})"
    if not upsert:
        return sql + f" RETURNING {spec.key}, true"
    mutable = [c for c in columns if c != spec.key]
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in mutable)
    current = ", ".join(f"{table}.{c}" for c in mutable)
    incoming = ", ".join(f"EXCLUDED.{c}" for c in mutable)
    return (
        f"{sql} ON CONFLICT ({spec.key}) DO UPDATE SET {assignments}, "
        f"first_collected_at = LEAST({table}.first_collected_at, EXCLUDED.first_collected_at), "
        f"updated_at = now() "
        # Only newer-or-equal observations replace current values, and only if something changed.
        f"WHERE {table}.{COLLECTED_AT} <= EXCLUDED.{COLLECTED_AT} "
        f"AND ({current}) IS DISTINCT FROM ({incoming}) "
        f"RETURNING {spec.key}, (xmax = 0)"
    )


def _history_sql(spec) -> str:
    table, metrics = _HISTORY[spec.name]
    cols = [spec.key, COLLECTED_AT] + metrics
    return (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(f'%({c})s' for c in cols)}) "
            f"ON CONFLICT ({spec.key}, {COLLECTED_AT}) DO UPDATE SET "
            + ", ".join(f"{m} = EXCLUDED.{m}" for m in metrics))


def _get(conn: psycopg.Connection, dataset: str, record_id: str):
    spec = get_spec(dataset)
    found = _list(conn, dataset, f"{spec.key} = %s", [record_id], spec.key, None)
    return found[0] if found else None


def _list(conn, dataset: str, where: str, params: list, order: str, limit: int | None) -> list:
    spec = get_spec(dataset)
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT):
        raise ValueError(f"limit must be an integer from 1 to {MAX_LIST_LIMIT}")
    columns = ", ".join(spec.model.DTYPES)
    sql = f"SELECT {columns} FROM {_TABLES[spec.name]}"
    if where:
        sql += f" WHERE {where}"
    sql += f" ORDER BY {order}"
    if limit is not None:
        sql += " LIMIT %s"
        params = [*params, limit]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [spec.model.model_validate(row) for row in cur.fetchall()]


def _detail(exc: psycopg.Error) -> str:
    diag = exc.diag
    return diag.message_detail or diag.message_primary or type(exc).__name__
