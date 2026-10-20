"""Component 3 live results: nightly collection, rolling-window scoring and publishing to Supabase.

    python -m research.component_3.live                    # collect + score + publish (nightly job)
    python -m research.component_3.live --no-collect       # score + publish the data already in Supabase
    python -m research.component_3.live --window-days 60   # rolling analysis window (default 90 days)

Runs unattended (GitHub Actions, see .github/workflows/component3-nightly.yml), so the dashboard always shows
results from the newest data, even when no analyst computer is on. Steps:

  1. collection into Supabase for the configured research channels (config/research_channels.json):
     channel details, newest uploads (catches every new video; the busiest channel posts ~17 a day) and
     comments on videos published in the last ``recheck_days`` (incremental: stops at stored threads)
  2. a research snapshot of the **same rolling window for every channel** (videos published in the last
     ``window_days`` and their comments), so channels are compared over equal periods
  3. the frozen Component 3 pipeline up to the Audience Bridge Score (same quick stages as the dashboard's
     organization analysis: topics, graph, features, metapath2vec, PPR, score, Louvain, explanations)
  4. publishing aggregate results to research.c3_live_* (migration 0005): run summary, bridge scores and
     per-channel counts. Never commenter identifiers or comment text.

Every run is recorded (running -> completed | failed); a failure stores a safe message and never a partial
result set. Live results are monitoring results; the frozen thesis results stay in the Parquet snapshots.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pandas as pd

from research.component_3 import analysis as an
from research.component_3 import pilot as pl

SNAPSHOT_SOURCE = "supabase_postgresql_live"
WINDOW_DAYS = 90            # rolling analysis window: the same period for every channel
RECHECK_DAYS = 30           # comments are re-checked on videos published in this many days
MAX_VIDEOS = 50             # newest uploads per channel per night (busiest channel ~17/day)
MAX_THREADS = 100

Log = Callable[[str], None]


class LiveError(RuntimeError):
    """The nightly run failed; the message is safe to store and show."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def run_id_for(t: datetime) -> str:
    return "live-" + t.strftime("%Y%m%dT%H%M%SZ")


def research_channel_ids() -> list[str]:
    from shared.data_collection.channel_config import load_channels

    return [c.channel_id for c in load_channels()]


# --- 1. collection -------------------------------------------------------------------------------

def collect(conn, client, ids: list[str], *, now: datetime, recheck_days: int = RECHECK_DAYS,
            max_videos: int = MAX_VIDEOS, max_threads: int = MAX_THREADS, log: Log = print) -> dict[str, Any]:
    from shared.data_collection import channel_collector as chc
    from shared.data_collection import video_collector as vc
    from shared.data_collection import youtube_comment_collector as cmc

    ch = chc.collect_channels(ids, client, chc.supabase_store(conn))
    conn.commit()
    vids = vc.collect_videos(list(ch.collected) or ids, client, vc.supabase_store(conn),
                             known_channels=vc.supabase_known_channels(conn), max_videos_per_channel=max_videos)
    conn.commit()
    since = now - timedelta(days=recheck_days)
    recent = [r[0] for r in conn.execute(
        "SELECT video_id FROM research.videos WHERE channel_id = ANY(%s) AND published_at >= %s",
        [ids, since]).fetchall()]
    conn.commit()
    refs = cmc.stored_videos(conn, video_ids=recent) if recent else []
    com = cmc.collect_comments(refs, client, cmc.supabase_store(conn), max_threads_per_video=max_threads,
                               fetch_all_replies=True, incremental=True) if refs else None
    conn.commit()
    out = {"channels": len(ch.collected), "channel_failures": len(ch.failed), "videos_seen": len(vids.videos_collected),
           "video_failures": len(vids.video_failures) + len(vids.channel_failures), "videos_rechecked": len(refs),
           "comments_collected": len(com.comments_collected) if com else 0,
           "comment_failures": (len(com.video_failures) + len(com.comment_failures)) if com else 0,
           "quota_units": client.quota_used}
    log(f"collection: {out}")
    return out


# --- 2. rolling-window snapshot ----------------------------------------------------------------------

def window_snapshot(conn, ids: list[str], *, start: datetime, end: datetime, run_id: str):
    """Freeze the same period for every channel: videos published in [start, end] and their comments."""
    from shared.database.snapshot_export import export_research_snapshot

    videos = [r[0] for r in conn.execute(
        "SELECT video_id FROM research.videos WHERE channel_id = ANY(%s) AND published_at >= %s AND published_at <= %s",
        [ids, start, end]).fetchall()]
    comments = [r[0] for r in conn.execute(
        "SELECT comment_id FROM research.comments WHERE video_id = ANY(%s)", [videos]).fetchall()] if videos else []
    conn.commit()
    if not videos:
        raise LiveError(f"no videos published between {start:%Y-%m-%d} and {end:%Y-%m-%d} for the research channels")
    return export_research_snapshot(
        conn, scope={"channels": ids, "videos": videos, "comments": comments}, source=SNAPSHOT_SOURCE,
        details={"run": "live", "live_run_id": run_id, "window_start": start.isoformat(), "window_end": end.isoformat()})


# --- 3. scoring --------------------------------------------------------------------------------------

def score(snapshot_id: str, *, encoder=None, log: Log = print):
    cfg = an.quick_config("live", ["live"])
    results, st = pl.run_pipeline(snapshot_id, cfg, encoder=encoder or an._load_encoder(),
                                  on_stage=lambda r: log(f"  {r.stage}: {r.status}"))
    failed = next((r for r in results if r.status == "failed"), None)
    if failed:
        raise LiveError(f"pipeline stage {failed.stage} failed: {failed.error}")
    if "bridge" not in st:
        raise LiveError("the pipeline produced no Audience Bridge Score")
    return st["bridge"]


def channel_summary(snapshot_id: str) -> pd.DataFrame:
    from shared.utils import snapshots

    path = lambda name: snapshots.research_dataset_path(snapshot_id, name)  # noqa: E731
    ch = pd.read_parquet(path("channels"), columns=["channel_id", "channel_name"])
    v = pd.read_parquet(path("videos"), columns=["video_id", "channel_id"])
    c = pd.read_parquet(path("comments"), columns=["channel_id", "author_channel_id"])
    out = ch.set_index("channel_id")
    out["videos"] = v.groupby("channel_id").size()
    out["comments"] = c.groupby("channel_id").size()
    out["unique_commenters"] = c.dropna().groupby("channel_id")["author_channel_id"].nunique()
    return out.fillna({"videos": 0, "comments": 0, "unique_commenters": 0}).reset_index()


# --- 4. publishing --------------------------------------------------------------------------------------

BRIDGE_COLUMNS = ["source_channel_id", "destination_channel_id", "audience_bridge_score", "base_score",
                  "diffusion_contribution", "embedding_contribution", "topic_contribution", "confidence",
                  "shared_commenters", "rank", "score_status"]


def _num(v):
    return None if v is None or (isinstance(v, float) and v != v) or pd.isna(v) else float(v)


def _int(v):
    return None if v is None or pd.isna(v) else int(v)


def publish(conn, run_id: str, bridge, chans: pd.DataFrame) -> int:
    """Write scores and channel counts for one run (one transaction). Channel ids are public ids without prefix."""
    names = dict(zip(chans["channel_id"], chans["channel_name"]))
    plain = lambda node: str(node).split(":", 1)[-1]  # noqa: E731  (graph node id -> channel id)
    s = bridge.scores[BRIDGE_COLUMNS]
    rows = [(run_id, plain(r.source_channel_id), plain(r.destination_channel_id),
             names.get(plain(r.source_channel_id)), names.get(plain(r.destination_channel_id)),
             _num(r.audience_bridge_score), _num(r.base_score), _num(r.diffusion_contribution),
             _num(r.embedding_contribution), _num(r.topic_contribution), _num(r.confidence),
             _int(r.shared_commenters), _int(r.rank), str(r.score_status)) for r in s.itertuples(index=False)]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO research.c3_live_bridge_scores (run_id, source_channel_id, destination_channel_id, "
            "source_channel_name, destination_channel_name, audience_bridge_score, base_score, diffusion_component, "
            "embedding_component, topic_component, confidence, shared_commenters, rank, score_status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", rows)
        cur.executemany(
            "INSERT INTO research.c3_live_channels (run_id, channel_id, channel_name, videos, comments, unique_commenters) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [(run_id, r.channel_id, r.channel_name, int(r.videos), int(r.comments), int(r.unique_commenters))
             for r in chans.itertuples(index=False)])
    return len(rows)


def _start_run(conn, run_id: str, started: datetime, start: datetime, end: datetime) -> None:
    conn.execute("INSERT INTO research.c3_live_runs (run_id, started_at, status, window_start, window_end) "
                 "VALUES (%s, %s, 'running', %s, %s)", [run_id, started, start, end])
    conn.commit()


def _finish_run(conn, run_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = %s" for k in fields)
    conn.execute(f"UPDATE research.c3_live_runs SET {cols} WHERE run_id = %s",
                 [*(json.dumps(v) if k == "details" else v for k, v in fields.items()), run_id])
    conn.commit()


# --- the nightly run ----------------------------------------------------------------------------------

def run_nightly(*, collect_data: bool = True, window_days: int = WINDOW_DAYS, recheck_days: int = RECHECK_DAYS,
                client=None, database=None, encoder=None, log: Log = print, now: datetime | None = None) -> dict[str, Any]:
    from shared.data_collection import youtube_api_client as yc
    from shared.database.connection import database as default_database

    if not 1 <= window_days <= 3650 or not 1 <= recheck_days <= 365:
        raise LiveError("window_days must be 1-3650 and recheck_days 1-365")
    started = now or _now()
    run_id = run_id_for(started)
    start, end = started - timedelta(days=window_days), started
    ids = research_channel_ids()
    t0 = time.perf_counter()
    with (database or default_database)() as conn:
        _start_run(conn, run_id, started, start, end)
        try:
            col = {}
            client = client or (yc.YouTubeClient() if collect_data else None)
            if collect_data:
                col = collect(conn, client, ids, now=started, recheck_days=recheck_days, log=log)
            info = window_snapshot(conn, ids, start=start, end=end, run_id=run_id)
            log(f"snapshot {info.snapshot_id}: {dict(info.row_counts)}")
            bridge = score(info.snapshot_id, encoder=encoder, log=log)
            chans = channel_summary(info.snapshot_id)
            n = publish(conn, run_id, bridge, chans)
            rows = dict(info.row_counts)
            _finish_run(conn, run_id, status="completed", finished_at=_now(), snapshot_id=info.snapshot_id,
                        experiment_id=bridge.experiment_id, channels=rows.get("channels"), videos=rows.get("videos"),
                        comments=rows.get("comments"), unique_commenters=int(chans["unique_commenters"].sum()),
                        quota_units=(client.quota_used if client is not None else 0),
                        details={"collection": col, "pairs_published": n, "seconds": round(time.perf_counter() - t0, 1),
                                 "window_days": window_days})
            log(f"{run_id} completed: {n} bridge scores published")
            return {"run_id": run_id, "status": "completed", "snapshot_id": info.snapshot_id, "pairs": n}
        except Exception as exc:  # noqa: BLE001 - recorded on the run; no secrets in these messages
            conn.rollback()
            message = str(exc) if isinstance(exc, (LiveError, an.AnalysisError)) else f"{type(exc).__name__}: run failed"
            _finish_run(conn, run_id, status="failed", finished_at=_now(), error=message[:500])
            log(f"{run_id} failed: {message}")
            raise


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="live", description="Component 3 nightly collection + scoring + publishing.")
    ap.add_argument("--no-collect", action="store_true", help="skip YouTube collection; score the stored data")
    ap.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--recheck-days", type=int, default=RECHECK_DAYS)
    args = ap.parse_args(argv)
    try:
        r = run_nightly(collect_data=not args.no_collect, window_days=args.window_days, recheck_days=args.recheck_days)
    except Exception as exc:  # noqa: BLE001 - exit code for the scheduler; message already logged
        print(f"Error: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}", file=sys.stderr)
        return 1
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
