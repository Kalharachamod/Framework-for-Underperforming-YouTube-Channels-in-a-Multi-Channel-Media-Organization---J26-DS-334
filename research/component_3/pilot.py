"""Component 3 controlled real-data runs: the pilot (STEP 26) and the full-scale experiment (STEP 27).

    python -m research.component_3.pilot --preflight-only      # checks + quota estimate, no API calls
    python -m research.component_3.pilot                       # preflight, collect, snapshot, pipeline, report
    python -m research.component_3.pilot --config config/experiments/component_3_full.json
    python -m research.component_3.pilot --config ... --snapshot rs-...   # resume: pipeline only, no API calls

Uses only existing project code: the YouTube Data API v3 collectors and Supabase store, the
research snapshot export (scoped to the records observed in this pilot), and the Component 3
pipeline stages. Every stage records its status, duration, artifact id and error; a failed
stage stops the run and the remaining stages are reported as not executed (never as passed).

Nothing existing is overwritten: the pilot creates a new research snapshot (new id), all other
snapshots are checksum-verified before and after, and research artifacts are write-once.
No secret or commenter identifier is printed, logged or written to the report.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from shared.utils import paths, privacy, snapshots

CONFIG_PATH = paths.PROJECT_ROOT / "config" / "pilots" / "component_3_pilot.json"
ORGS_DIR = paths.PROJECT_ROOT / "config" / "organizations"
PIPELINE_STAGES = ("research_data", "topics", "graph", "features", "metapath2vec", "hgt", "ppr_diffusion",
                   "audience_bridge", "louvain", "node2vec", "explainability", "evaluation")
REQUIRED_ENV = ("YOUTUBE_API_KEY", "COMMENTER_HASH_SALT", "SUPABASE_DB_URL")
DEPENDENCIES = ("duckdb", "pyarrow", "psycopg", "networkx", "scipy", "gensim", "torch", "torch_geometric",
                "sentence_transformers", "sklearn")
INTERPRETATION = ("Pilot results validate the pipeline on a small real sample. They do not show audience migration, "
                  "causal influence, subscriber transfer or future growth, and three channels are too few for "
                  "general conclusions.")


class PilotError(RuntimeError):
    pass


# --- configuration ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PilotConfig:
    channel_titles: tuple[str, ...] = ()              # pilot: explicit channels (by configured title)
    channel_groups: tuple[str, ...] = ()              # full run: every channel of these research_channels.json groups
    name: str = "pilot"                               # run kind; also the record folder name
    title: str = "Component 3 Controlled Real-Data Pilot (STEP 26)"
    snapshot_source: str = "supabase_postgresql_pilot"
    expected_channel_counts: tuple[tuple[str, int], ...] = ()   # group -> count stated by the research plan
    reply_page_rate: float | None = None              # measured comments.list pages per thread (None = worst case)
    max_videos_per_channel: int = 15
    max_threads_per_video: int = 50
    fetch_all_replies: bool = False
    published_since: date | None = None
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    max_quota_units: int = 500
    stages: tuple[str, ...] = PIPELINE_STAGES
    n_topics: int = 10
    seed: int = 42
    topic_backend: str = "e5"
    evaluation_sparse_fractions: tuple[float, ...] = (0.5,)
    evaluation_sparse_seeds: tuple[int, ...] = (0, 1)
    min_free_disk_gb: float = 1.0
    report_path: str = "docs/component_3_pilot_report.md"
    channel_note: str = ""

    def __post_init__(self):
        if not self.channel_titles and not self.channel_groups:
            raise PilotError("the run needs channel_titles or channel_groups")
        if not 1 <= self.max_videos_per_channel <= 50:
            raise PilotError("max_videos_per_channel must be between 1 and 50")
        if not 1 <= self.max_threads_per_video <= 100:
            raise PilotError("max_threads_per_video must be between 1 and 100")
        if not self.name.isidentifier():
            raise PilotError("name must be a simple identifier (used as a folder name)")
        if self.reply_page_rate is not None and not 0 <= self.reply_page_rate <= 1:
            raise PilotError("reply_page_rate must be in [0, 1]")
        unknown = [s for s in self.stages if s not in PIPELINE_STAGES]
        if unknown:
            raise PilotError(f"unknown pipeline stage(s) {unknown}; available {list(PIPELINE_STAGES)}")
        if self.max_quota_units < 1:
            raise PilotError("max_quota_units must be positive")

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["published_since"] = self.published_since.isoformat() if self.published_since else None
        return d


def load_config(path: Path = CONFIG_PATH) -> PilotConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    col, pipe = raw.get("collection", {}), raw.get("pipeline", {})
    since = col.get("published_since")
    return PilotConfig(
        channel_titles=tuple(raw.get("channel_titles", ())), channel_groups=tuple(raw.get("channel_groups", ())),
        name=raw.get("name", "pilot"), title=raw.get("title", PilotConfig.title),
        snapshot_source=raw.get("snapshot_source", PilotConfig.snapshot_source),
        expected_channel_counts=tuple(sorted(raw.get("expected_channel_counts", {}).items())),
        reply_page_rate=col.get("reply_page_rate"), channel_note=raw.get("channel_note", ""),
        max_videos_per_channel=int(col.get("max_videos_per_channel", 15)),
        max_threads_per_video=int(col.get("max_threads_per_video", 50)),
        fetch_all_replies=bool(col.get("fetch_all_replies", False)),
        published_since=date.fromisoformat(since) if since else None,
        request_timeout_seconds=float(col.get("request_timeout_seconds", 30)),
        max_retries=int(col.get("max_retries", 3)), retry_backoff_seconds=float(col.get("retry_backoff_seconds", 1.0)),
        max_quota_units=int(col.get("max_quota_units", 500)),
        stages=tuple(pipe.get("stages", PIPELINE_STAGES)), n_topics=int(pipe.get("n_topics", 10)),
        seed=int(pipe.get("seed", 42)), topic_backend=str(pipe.get("topic_backend", "e5")),
        evaluation_sparse_fractions=tuple(pipe.get("evaluation_sparse_fractions", [0.5])),
        evaluation_sparse_seeds=tuple(pipe.get("evaluation_sparse_seeds", [0, 1])),
        min_free_disk_gb=float(raw.get("min_free_disk_gb", 1.0)), report_path=raw.get("report_path", PilotConfig.report_path))


def channel_titles_by_id() -> dict[str, str]:
    out: dict[str, str] = {}
    for f in sorted(ORGS_DIR.glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8")).get("channels", []):
            out.setdefault(c.get("channel_id"), c.get("title"))
    return out


def resolve_registry(config: PilotConfig) -> tuple[dict[str, str], dict[str, str], dict[str, Any]]:
    """(title -> id, id -> group, registry report). Channels come only from research_channels.json
    (+ organization files for titles); nothing is invented or substituted."""
    from collections import Counter

    from shared.data_collection.channel_config import load_channels
    from shared.data_collection.youtube_api_client import is_valid_id

    configured = load_channels()
    group_of = {c.channel_id: c.group for c in configured}
    titles = channel_titles_by_id()
    if config.channel_titles:
        channels = resolve_channels(config.channel_titles)
    else:
        selected = [c for c in configured if c.group in config.channel_groups]
        channels = {titles.get(c.channel_id) or c.channel_id: c.channel_id for c in selected}
    ids = [c.channel_id for c in configured]
    counts = Counter(c.group for c in configured)
    groups_requested = config.channel_groups or tuple(sorted({group_of[i] for i in channels.values()}))
    report = {
        "configured_total": len(configured), "configured_by_group": dict(sorted(counts.items())),
        "requested_groups": list(groups_requested), "selected": len(channels),
        "duplicate_ids": sorted(i for i, n in Counter(ids).items() if n > 1),
        "invalid_ids": sorted(i for i in ids if not is_valid_id(i)),
        "expected_by_group": dict(config.expected_channel_counts),
        "gaps": {g: {"expected": n, "configured": counts.get(g, 0)}
                 for g, n in config.expected_channel_counts if counts.get(g, 0) != n},
    }
    return channels, {i: group_of[i] for i in channels.values()}, report


def resolve_channels(titles: tuple[str, ...]) -> dict[str, str]:
    """title -> channel id from config/organizations/*.json; every id must be in a research_channels.json group."""
    from shared.data_collection.channel_config import load_channels

    by_title: dict[str, str] = {}
    for f in sorted(ORGS_DIR.glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8")).get("channels", []):
            by_title.setdefault(c.get("title"), c.get("channel_id"))
    configured = {c.channel_id for c in load_channels()}
    out, problems = {}, []
    for t in titles:
        cid = by_title.get(t)
        if cid is None:
            problems.append(f"{t!r} is not a configured channel title")
        elif cid not in configured:
            problems.append(f"{t!r} ({cid}) is not in any research_channels.json group")
        else:
            out[t] = cid
    if problems:
        raise PilotError("; ".join(problems))
    return out


# --- quota estimate -------------------------------------------------------------------------------

def estimate_quota(config: PilotConfig, n_channels: int) -> dict[str, Any]:
    """Upper-bound estimate from the collectors' request pattern (1 unit per list call):
    channels.list per 50 channels (channel collector) + per 50 channels (uploads playlists);
    playlistItems.list per 50 videos per channel; videos.list per 50 videos per channel;
    commentThreads.list per 100 threads per video; comments.list per thread only with fetch_all_replies."""
    pages = math.ceil(config.max_videos_per_channel / 50)
    videos = n_channels * config.max_videos_per_channel
    parts = {
        "channels.list": 2 * math.ceil(n_channels / 50),
        "playlistItems.list": n_channels * pages,
        "videos.list": n_channels * pages,
        "commentThreads.list": videos * math.ceil(config.max_threads_per_video / 100),
        "comments.list": (math.ceil(videos * config.max_threads_per_video *
                                    (1.0 if config.reply_page_rate is None else config.reply_page_rate))
                          if config.fetch_all_replies else 0),
    }
    total = sum(parts.values())
    return {"per_endpoint": parts, "total_upper_bound": total, "cap": config.max_quota_units,
            "within_cap": total <= config.max_quota_units,
            "reply_page_rate": config.reply_page_rate,
            "note": "upper bound for list calls; reply pages use the measured rate when given (otherwise one page "
                    "per thread); videos with zero comments spend no comment quota; the daily quota is 10,000 units"}


# --- preflight ---------------------------------------------------------------------------------------

def _check(name: str, ok: bool, detail: str, required: bool = True) -> dict[str, Any]:
    return {"check": name, "status": "pass" if ok else ("fail" if required else "warn"), "detail": detail}


def preflight(config: PilotConfig, *, connect: Callable | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    present = {n: bool(os.getenv(n, "").strip()) and "your" not in os.getenv(n, "").lower() for n in REQUIRED_ENV}
    checks.append(_check("environment variables", all(present.values()),
                         ", ".join(f"{n}: {'set' if ok else 'MISSING'}" for n, ok in present.items())))
    try:
        from shared.data_collection.youtube_api_client import YouTubeClient

        YouTubeClient(timeout=config.request_timeout_seconds)
        checks.append(_check("YouTube Data API v3 client", True, "client configured (key present, not a placeholder)"))
    except Exception as exc:  # noqa: BLE001 - reported, never printed with values
        checks.append(_check("YouTube Data API v3 client", False, type(exc).__name__))
    channels: dict[str, str] = {}
    groups: dict[str, str] = {}
    registry: dict[str, Any] = {}
    try:
        channels, groups, registry = resolve_registry(config)
        bad = registry["invalid_ids"] + registry["duplicate_ids"]
        checks.append(_check("channel ids", bool(channels) and not bad,
                             f"{len(channels)} selected from configuration ({registry['configured_by_group']})"
                             + (f"; invalid or duplicate: {bad}" if bad else "")))
        if registry["gaps"]:
            checks.append(_check("channel registry vs research plan", False,
                                 "; ".join(f"{g}: plan {v['expected']}, configured {v['configured']}"
                                           for g, v in registry["gaps"].items())
                                 + " (missing channels are not invented; the run uses the configured set)",
                                 required=False))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("channel ids", False, str(exc)))
    try:
        from shared.database.connection import database

        with (connect or database)() as conn:
            row = conn.execute("SELECT count(*) FROM research.channels WHERE channel_id = ANY(%s)",
                               [list(channels.values())]).fetchone()
            conn.rollback()
        checks.append(_check("shared database (read-only)", True, f"reachable; {row[0]} of {len(channels)} selected "
                                                                    "channels already stored"))
    except Exception as exc:  # noqa: BLE001 - connection errors are already redacted by the project
        checks.append(_check("shared database (read-only)", False, type(exc).__name__))
    data = paths.get_data_paths()
    writable = all(os.access(_existing_ancestor(p), os.W_OK) for p in (data.processed, data.snapshots))
    checks.append(_check("output directories", writable, f"data directory {'writable' if writable else 'NOT writable'}"))
    free_gb = shutil.disk_usage(data.root if data.root.exists() else paths.PROJECT_ROOT).free / 1e9
    checks.append(_check("disk space", free_gb >= config.min_free_disk_gb, f"{free_gb:.1f} GB free "
                                                                           f"(minimum {config.min_free_disk_gb} GB)"))
    missing = []
    for mod in DEPENDENCIES:
        try:
            importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            missing.append(mod)
    checks.append(_check("pipeline dependencies", not missing, "all importable" if not missing else f"missing: {missing}"))
    try:
        probe = privacy.pseudonymize_id("UC_preflight_probe_value", privacy.get_salt())
        checks.append(_check("commenter pseudonymization", privacy.is_pseudonymized(probe),
                             "salt configured; ids are HMAC-SHA256 pseudonyms"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("commenter pseudonymization", False, type(exc).__name__))
    existing = snapshots.list_research_snapshots()
    unverified = [s.snapshot_id for s in existing if not snapshots.verify_research_snapshot(s.snapshot_id).ok]
    checks.append(_check("existing snapshots intact", not unverified,
                         f"{len(existing)} research snapshot(s) verified" + (f"; FAILED: {unverified}" if unverified else "")))
    checks.append(_check("new snapshot, no overwrite", True, "a new rs-<timestamp> id is created; existing ids are "
                                                            "refused by create_research_snapshot"))
    quota = estimate_quota(config, len(channels) or len(config.channel_titles))
    checks.append(_check("quota estimate", quota["within_cap"], f"upper bound {quota['total_upper_bound']} units "
                                                                f"(cap {config.max_quota_units})"))
    estimate = storage_estimate(config, len(channels))
    if estimate:
        checks.append(_check("storage estimate", estimate["estimated_gb"] < free_gb, estimate["detail"]))
    return {"ok": all(c["status"] != "fail" for c in checks), "checks": checks, "channels": channels,
            "groups": groups, "registry": registry, "quota": quota}


def storage_estimate(config: PilotConfig, n_channels: int) -> dict[str, Any] | None:
    """Scale the measured size of the latest pilot snapshot + its artifacts to this run's video count."""
    pilots = [x for x in snapshots.list_research_snapshots() if x.source == "supabase_postgresql_pilot"]
    if not pilots:
        return None
    p = pilots[-1]
    size = sum(f.stat().st_size for d in (p.path, paths.component_dir(3) / p.snapshot_id) if d.exists()
               for f in d.rglob("*") if f.is_file())
    videos = max(1, p.row_counts.get("videos", 1))
    gb = size / videos * n_channels * config.max_videos_per_channel / 1e9
    return {"estimated_gb": gb, "detail": f"about {gb:.2f} GB, scaled from pilot {p.snapshot_id} "
                                          f"({size / 1e6:.1f} MB for {videos} videos)"}


def _existing_ancestor(path: Path) -> Path:
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


# --- collection ---------------------------------------------------------------------------------------

def collect(config: PilotConfig, channels: dict[str, str], *, client=None, database=None) -> dict[str, Any]:
    """Collect with the existing collectors into the shared database, then export a pilot snapshot
    containing exactly the channels, videos and comments observed in this run."""
    from shared.data_collection import channel_collector as chc
    from shared.data_collection import youtube_comment_collector as cmc
    from shared.data_collection import video_collector as vc
    from shared.data_collection import youtube_api_client as yc
    from shared.database.connection import database as default_database
    from shared.database.snapshot_export import export_research_snapshot

    client = client or yc.YouTubeClient(timeout=config.request_timeout_seconds,
                                        retry=yc.RetryPolicy(max_retries=config.max_retries,
                                                             backoff_seconds=config.retry_backoff_seconds))
    ids = list(channels.values())
    out: dict[str, Any] = {}
    t0 = time.perf_counter()
    with (database or default_database)() as conn:
        ch = chc.collect_channels(ids, client, chc.supabase_store(conn))
        conn.commit()
        out["channels"] = {"requested": len(ids), "collected": len(ch.collected), "failed": [f.reason for f in ch.failed]}
        vids = vc.collect_videos(ids, client, vc.supabase_store(conn), known_channels=vc.supabase_known_channels(conn),
                                 max_videos_per_channel=config.max_videos_per_channel,
                                 published_since=config.published_since)
        conn.commit()
        out["videos"] = {"collected": len(vids.videos_collected), "inserted": len(vids.videos_inserted),
                         "updated": len(vids.videos_updated), "unchanged": len(vids.videos_unchanged),
                         "channel_failures": [f.reason for f in vids.channel_failures],
                         "video_failures": [f.reason for f in vids.video_failures]}
        if not vids.videos_collected:
            raise PilotError("no videos were collected; stopping before comment collection")
        refs = cmc.stored_videos(conn, video_ids=vids.videos_collected)
        com = cmc.collect_comments(refs, client, cmc.supabase_store(conn),
                                   max_threads_per_video=config.max_threads_per_video,
                                   fetch_all_replies=config.fetch_all_replies)
        conn.commit()
        zero = sorted(r.video_id for r in refs if r.comment_count == 0)
        unknown_count = sorted(r.video_id for r in refs if r.comment_count is None)
        out["comments"] = {
            "collected": len(com.comments_collected), "top_level": com.top_level_comments, "replies": com.replies,
            "inserted": len(com.comments_inserted), "updated": len(com.comments_updated),
            "skipped_entries": com.comments_skipped,
            "videos_processed": len(com.videos_processed),
            "videos_with_zero_public_comments": len(zero),
            "videos_with_comments_disabled": len(com.videos_with_comments_disabled),
            "videos_with_unknown_public_count": len(unknown_count),
            "video_failures": [f.reason for f in com.video_failures],
            "comment_failures": [f.reason for f in com.comment_failures],
        }
        log = client.request_log
        out["requests"] = {"total": len(log), "succeeded": sum(r.succeeded for r in log),
                           "failed": sum(not r.succeeded for r in log), "retries": sum(max(0, r.attempts - 1) for r in log),
                           "quota_units": client.quota_used,
                           "by_endpoint": {k: int(v) for k, v in pd.Series([f"{r.resource}.{r.method}" for r in log])
                                           .value_counts().sort_index().items()} if log else {}}
        info = export_research_snapshot(
            conn, scope={"channels": ids, "videos": vids.videos_collected, "comments": com.comments_collected},
            source=config.snapshot_source,
            details={"run": config.name, "channels": sorted(channels), "config": config.to_dict()})
    out["snapshot_id"] = info.snapshot_id
    out["snapshot_rows"] = dict(info.row_counts)
    out["seconds"] = round(time.perf_counter() - t0, 2)
    return out


# --- pipeline -----------------------------------------------------------------------------------------

@dataclass
class StageResult:
    stage: str
    status: str                      # completed | failed | not_executed | disabled
    seconds: float | None = None
    artifact: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def run_pipeline(snapshot_id: str, config: PilotConfig, *, encoder=None, m2v_config=None, hgt_config=None,
                 node2vec_config=None,
                 on_stage: Callable[[StageResult], None] | None = None) -> tuple[list[StageResult], dict[str, Any]]:
    """Run each enabled stage on the pilot snapshot; stop at the first failure.

    ``on_stage`` (optional) is called with a ``running`` result before each executed stage and with
    the final result after it, so callers can report progress."""
    from research.component_3.evaluation import evaluate as ev
    from research.component_3.explainability import explain as ex
    from research.component_3.model import audience_bridge as ab
    from research.component_3.model import baselines as bl
    from research.component_3.model import hgt
    from research.component_3.model import metapath2vec as m2v
    from research.component_3.model import ppr_diffusion as ppr
    from research.component_3.model import topic_similarity as ts
    from research.component_3.preprocessing import graph_features as gf
    from research.component_3.preprocessing import hetero_graph as hg
    from research.component_3.preprocessing import research_dataset as rd

    from dataclasses import replace

    seed = config.seed
    topic_cfg = ts.TopicConfig(backend=config.topic_backend, n_topics=config.n_topics, seed=seed)
    m2v_cfg = m2v_config or m2v.Config(seed=seed)
    hgt_cfg = hgt_config or hgt.HGTConfig(seed=seed)
    n2v_cfg = node2vec_config or bl.Node2VecConfig(seed=seed)
    st: dict[str, Any] = {}

    def research_data():
        report = rd.prepare(snapshot_id)
        if not report.research_ready:
            raise PilotError(f"snapshot is not research-ready (quality {report.quality_status})")
        return None, {"quality": report.quality_status, "counts": report.counts,
                      "commenters_on_multiple_channels": report.cross_channel["commenters_on_multiple_channels"]}

    def topics():
        as_of = gf._snapshot_time(snapshots.get_research_snapshot(snapshot_id))
        r = ts.run(snapshot_id, topic_cfg, as_of=as_of, encoder=encoder)
        ts.save(r)
        st["topic"] = r
        c = r.metadata["coverage"]
        return r.experiment_id, {"videos": c["videos"], "usable_videos": c["usable"],
                                 "channels_with_profile": f"{c['channels_with_profile']}/{c['channels']}",
                                 "clusters": r.metadata.get("clustering", {}).get("n_topics")
                                 if not r.metadata.get("clustering", {}).get("skipped") else "skipped"}

    def graph():
        topics_df, vt = hg.load_topic_assignments(snapshot_id) if "topics" in config.stages else (None, None)
        g = hg.build_graph(snapshot_id, topics=topics_df, video_topics=vt)
        hg.save_graph(g)
        st["graph"] = g
        s = g.manifest["statistics"]
        return g.fingerprint()[:16], {"node_counts": s["node_counts"], "edge_counts": s["edge_counts"],
                                      "commenters_on_multiple_channels": s["commenters_on_multiple_channels"]}

    def features():
        fs = gf.build_features(snapshot_id, graph=st["graph"])
        gf.save_features(fs)
        return gf.features_dir(snapshot_id, fs.as_of).name, {
            "channel_pairs_with_shared_commenters": int(len(fs["channel_pair_features"]))}

    def metapath2vec():
        # deterministic + write-once: an artifact with the same experiment id (graph + config) is reused
        saved = m2v.embeddings_dir(snapshot_id, m2v.make_experiment_id(st["graph"], m2v_cfg))
        r = m2v.load_embeddings(saved) if (saved / "experiment.json").is_file() else m2v.train(st["graph"], m2v_cfg)
        m2v.save_embeddings(r)
        st["m2v"] = r
        return r.experiment_id, {"embedded_nodes": int(len(r.nodes)),
                                 "metapaths_used": sorted(r.metadata["walks"]["per_metapath"]),
                                 "metapaths_skipped": sorted(r.metadata["walks"]["skipped_metapaths"])}

    def hgt_stage():
        saved = m2v.embeddings_dir(snapshot_id, hgt.make_experiment_id(st["graph"], hgt_cfg))
        if (saved / "experiment.json").is_file() and (saved / "model.pt").is_file():
            r = m2v.load_embeddings(saved)
            return r.experiment_id, {"embedded_nodes": int(len(r.nodes)), "reused": True,
                                     "split": r.metadata.get("split", {}).get("kind")}
        r, model = hgt.train(st["graph"], hgt_cfg)
        hgt.save(r, model)
        return r.experiment_id, {"embedded_nodes": int(len(r.nodes)), "split": r.metadata.get("split", {}).get("kind")}

    def ppr_stage():
        saved = ppr.diffusion_dir(snapshot_id, ppr.make_experiment_id(st["graph"], ppr.PPRConfig()))
        r = ppr.load_run(saved) if (saved / "diffusion_run.json").is_file() else ppr.run_diffusion(st["graph"])
        ppr.save_run(r)
        st["ppr"] = r
        return r.experiment_id, {"sources": len(r.metadata["sources"]), "skipped_sources": len(r.metadata["skipped_sources"]),
                                 "reachable_pairs": int(r.results["reachable"].sum()), "pairs": int(len(r.results))}

    def bridge():
        inp = bl.load_input(snapshot_id)
        r = ab.score(inp, st["ppr"], st["topic"], ab.BridgeConfig(), st["m2v"])
        ab.save(r)
        st["bridge"] = r
        return r.experiment_id, {"pairs": r.metadata["coverage"]["pairs"], "scored": r.metadata["coverage"]["scored"],
                                 "status_counts": r.metadata["coverage"]["status_counts"]}

    def louvain():
        r = bl.run_louvain(bl.load_input(snapshot_id), bl.LouvainConfig(seed=seed))
        bl.save_louvain(r)
        st["louvain"] = r
        return r.experiment_id, {"communities": r.metadata["communities"], "modularity": r.metadata["modularity"],
                                 "isolated_channels": r.metadata["isolated_channels"]}

    def node2vec():
        r = bl.run_node2vec(bl.load_input(snapshot_id), n2v_cfg)
        bl.save_node2vec(r)
        st["node2vec"] = r
        return r.experiment_id, {"embedded_nodes": int(len(r.embeddings.nodes))}

    def explainability():
        r = ex.explain(st["bridge"])
        ex.save(r)
        st["explanation"] = r
        return r.explanation_id, {"status_counts": r.metadata["status_counts"]}

    def evaluation():
        cfg = ev.EvaluationConfig(sparse_fractions=tuple(config.evaluation_sparse_fractions),
                                  sparse_seeds=tuple(config.evaluation_sparse_seeds))
        r = ev.evaluate(snapshot_id, cfg, encoder=encoder, topic_config=topic_cfg, m2v_config=m2v_config,
                        hgt_config=hgt_config, node2vec_config=n2v_cfg)
        ev.save(r)
        st["evaluation"] = r
        return r.evaluation_id, {"methods": {m: v["status"] for m, v in r.metadata["methods"].items()},
                                 "labels": r.metadata["labels"].get("status", "supplied"),
                                 "temporal": r.metadata["temporal"].get("status"),
                                 "sparse_runs": len(r.metadata["sparse_robustness"].get("runs", []))}

    stages: dict[str, Callable] = {
        "research_data": research_data, "topics": topics, "graph": graph, "features": features,
        "metapath2vec": metapath2vec, "hgt": hgt_stage, "ppr_diffusion": ppr_stage, "audience_bridge": bridge,
        "louvain": louvain, "node2vec": node2vec, "explainability": explainability, "evaluation": evaluation,
    }
    needs = {"features": ["graph"], "metapath2vec": ["graph"], "hgt": ["graph"], "ppr_diffusion": ["graph"],
             "audience_bridge": ["topics", "metapath2vec", "ppr_diffusion"], "explainability": ["audience_bridge"],
             "graph": ["research_data"]}
    results: list[StageResult] = []
    failed = False
    for name in PIPELINE_STAGES:
        if name not in config.stages:
            results.append(StageResult(name, "disabled", details={"reason": "not enabled in the pilot configuration"}))
            continue
        missing = [n for n in needs.get(name, []) if n not in config.stages]
        if failed or missing:
            results.append(StageResult(name, "not_executed", details={
                "reason": "an earlier stage failed" if failed else f"needs disabled stage(s) {missing}"}))
            continue
        t0 = time.perf_counter()
        if on_stage:
            on_stage(StageResult(name, "running"))
        try:
            artifact, details = stages[name]()
            results.append(StageResult(name, "completed", round(time.perf_counter() - t0, 2), artifact, details))
        except Exception as exc:  # noqa: BLE001 - reported per stage; secrets never reach these messages
            failed = True
            where = traceback.extract_tb(exc.__traceback__)[-1]
            results.append(StageResult(name, "failed", round(time.perf_counter() - t0, 2), error=(
                f"{type(exc).__name__}: {str(exc).splitlines()[0][:300] if str(exc) else ''} "
                f"(at {Path(where.filename).name}:{where.lineno})")))
        if on_stage:
            on_stage(results[-1])
    return results, st


# --- validity checks ---------------------------------------------------------------------------------

def validity_checks(snapshot_id: str, channels: dict[str, str], st: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    pilot = {f"channel:{c}" for c in channels.values()}
    b = st.get("bridge")
    if b is not None:
        s = b.scores
        checks.append(_check("scored channels are pilot channels",
                             set(s.source_channel_id) | set(s.destination_channel_id) <= pilot,
                             f"{len(set(s.source_channel_id))} source channels"))
        checks.append(_check("no self pairs", bool((s.source_channel_id != s.destination_channel_id).all()), "source != destination"))
        sc = s.audience_bridge_score.dropna().astype(float)
        conf = s.confidence.dropna().astype(float)
        checks.append(_check("scores finite and in [0, 1]", bool(np.isfinite(sc).all() and sc.between(0, 1).all()
                                                                 and conf.between(0, 1).all()),
                             f"{len(sc)} scores, {len(conf)} confidence values"))
        ok = s[s.score_status == "ok"]
        err = float(((ok.diffusion_contribution + ok.embedding_contribution + ok.topic_contribution) * ok.confidence
                     - ok.audience_bridge_score).abs().max()) if len(ok) else 0.0
        checks.append(_check("decomposition matches the formula", err < 1e-9, f"max reconstruction error {err:.1e}"))
        missing = s[s.score_status != "ok"]
        checks.append(_check("missing evidence not scored as zero", bool(missing.audience_bridge_score.isna().all()),
                             f"{len(missing)} incomplete pair(s) carry no score"))
        fp = b.metadata["graph_fingerprint"]
        same = [n for n in ("louvain", "node2vec") if n in st and st[n].metadata.get("graph_fingerprint") == fp]
        checks.append(_check("baselines use the same snapshot and graph", len(same) == sum(n in st for n in ("louvain", "node2vec")),
                             f"same graph: {same}"))
    t = st.get("topic")
    if t is not None:
        prof = t.profiles
        checks.append(_check("topic profiles from the pilot channels' videos",
                             set("channel:" + prof.channel_id.astype(str)) == pilot,
                             f"{int(prof.profile_available.sum())}/{len(prof)} channels with a profile", required=False))
    e = st.get("evaluation")
    if e is not None:
        rel = e.tables["ranking_evaluation_results"]
        rel = rel[rel.analysis == "relevance"]
        checks.append(_check("relevance metrics not reported without labels", bool((rel.status != "ok").all()),
                             "no labels supplied"))
        checks.append(_check("temporal evaluation reported honestly", e.metadata["temporal"].get("status") in
                             ("insufficient_temporal_data", "ok"), str(e.metadata["temporal"].get("reason"))))
    prov = [name for name in ("topic", "m2v", "ppr", "bridge", "louvain", "node2vec", "explanation", "evaluation")
            if name in st and getattr(st[name], "snapshot_id", snapshot_id) != snapshot_id]
    checks.append(_check("artifact provenance", not prov, "all artifacts reference the pilot snapshot" if not prov
                         else f"wrong snapshot: {prov}"))
    leaks = privacy_scan(snapshot_id)
    checks.append(_check("no commenter identifiers in derived artifacts", not leaks,
                         "scanned scores, explanations, evaluation, diffusion and baselines" if not leaks else f"{leaks}"))
    return checks


def privacy_scan(snapshot_id: str) -> list[str]:
    """Derived research outputs (scores, explanations, evaluation, diffusion, community and similarity
    tables) must contain no commenter identifier at all. Embedding files hold one vector per graph
    node by design; their commenter node ids must all be pseudonyms (never raw ids)."""
    root = paths.component_dir(3) / snapshot_id
    leaks = []
    for kind in ("bridge", "explanations", "evaluation", "diffusion", "baselines", "topics", "embeddings"):
        for f in root.glob(f"{kind}/*/*.parquet"):
            df = pd.read_parquet(f)
            if f.name == "embeddings.parquet":
                ids = df.loc[df["node_type"] == "commenter", "node_id"].astype(str).str.removeprefix("commenter:")
                if not ids.map(privacy.is_pseudonymized).all():
                    leaks.append(f"{kind}/{f.parent.name}/{f.name} (non-pseudonymized commenter ids)")
            elif privacy.HASH_PREFIX in df.to_csv():
                leaks.append(f"{kind}/{f.parent.name}/{f.name}")
    return leaks


# --- data quality, distributions and comparison ---------------------------------------------------

def channel_quality(snapshot_id: str, channels: dict[str, str], groups: dict[str, str]) -> list[dict[str, Any]]:
    """Per-channel collection coverage from the snapshot (aggregate counts only)."""
    import duckdb

    f = {n: snapshots.research_dataset_path(snapshot_id, n).as_posix() for n in ("channels", "videos", "comments")}
    sql = f"""
    WITH v AS (SELECT channel_id, count(*) AS n_videos, sum(CASE WHEN comment_count = 0 THEN 1 ELSE 0 END) zero_public,
                      sum(CASE WHEN comment_count IS NULL THEN 1 ELSE 0 END) unknown_public, min(published_at) first_video,
                      max(published_at) last_video, sum(comment_count) public_comments
               FROM read_parquet('{f["videos"]}') GROUP BY 1),
         c AS (SELECT channel_id, count(*) AS n_comments, sum(CASE WHEN parent_comment_id IS NULL THEN 1 ELSE 0 END) top_level,
                      count(DISTINCT author_channel_id) commenters, count(DISTINCT video_id) videos_with_comments,
                      min(published_at) first_comment, max(published_at) last_comment
               FROM read_parquet('{f["comments"]}') GROUP BY 1)
    SELECT ch.channel_id, coalesce(v.n_videos, 0) AS n_videos, coalesce(v.zero_public, 0) zero_public,
           coalesce(v.unknown_public, 0) unknown_public, coalesce(v.public_comments, 0) public_comments,
           coalesce(c.n_comments, 0) AS n_comments, coalesce(c.top_level, 0) top_level, coalesce(c.commenters, 0) commenters,
           coalesce(c.videos_with_comments, 0) videos_with_comments, v.first_video, v.last_video, c.first_comment,
           c.last_comment
    FROM read_parquet('{f["channels"]}') ch LEFT JOIN v USING (channel_id) LEFT JOIN c USING (channel_id)"""
    df = duckdb.sql(sql).df()
    title = {i: t for t, i in channels.items()}
    out = []
    for r in df.sort_values("n_comments", ascending=False).itertuples():
        out.append({"channel": title.get(r.channel_id, r.channel_id), "group": groups.get(r.channel_id, "?"),
                    "videos": int(r.n_videos), "videos_with_comments": int(r.videos_with_comments),
                    "zero_public_comments": int(r.zero_public), "public_count_hidden": int(r.unknown_public),
                    "comments": int(r.n_comments), "top_level": int(r.top_level), "commenters": int(r.commenters),
                    "stored_vs_public": None if not r.public_comments else round(float(r.n_comments) / float(r.public_comments), 3),
                    "video_window": f"{str(r.first_video)[:10]} .. {str(r.last_video)[:10]}" if r.n_videos else "—",
                    "comment_window": f"{str(r.first_comment)[:10]} .. {str(r.last_comment)[:10]}" if r.n_comments else "—"})
    return out


def distributions(st: dict[str, Any]) -> list[dict[str, Any]]:
    """Summary of score components and confidence over the scored pairs (no individual records)."""
    b = st.get("bridge")
    if b is None:
        return []
    ok = b.scores[b.scores.score_status == "ok"]
    rows = []
    for col in ("audience_bridge_score", "diffusion_contribution", "embedding_contribution", "topic_contribution",
                "confidence", "evidence_confidence", "topic_coverage_confidence", "shared_commenters"):
        v = ok[col].dropna().astype(float)
        rows.append({"measure": col, "pairs": int(len(v)), **({} if v.empty else {
            "min": round(float(v.min()), 4), "median": round(float(v.median()), 4), "p90": round(float(v.quantile(0.9)), 4),
            "max": round(float(v.max()), 4), "share_zero": round(float((v == 0).mean()), 3)})})
    return rows


def insufficient_data(st: dict[str, Any], channels: dict[str, str]) -> list[str]:
    """Channels whose results rest on missing or zero evidence (named explicitly in the report)."""
    b = st.get("bridge")
    if b is None:
        return []
    title = {f"channel:{i}": t for t, i in channels.items()}
    s = b.scores
    out = []
    for src, g in s.groupby("source_channel_id"):
        name = title.get(src, src)
        if (g.score_status != "ok").all():
            out.append(f"{name}: no destination could be scored ({g.score_status.iloc[0]})")
        elif (g.shared_commenters == 0).all():
            out.append(f"{name}: shares no commenter with any other channel, so every score is 0")
        elif (g.shared_commenters < float(b.metadata["config"]["confidence_k"])).all():
            out.append(f"{name}: fewer than k shared commenters with every other channel (low confidence)")
    return out


def compare_with_pilot(snapshot_id: str, run: dict[str, Any]) -> dict[str, Any] | None:
    """Totals of this run next to the latest controlled pilot (different scope and depth by design)."""
    pilots = [x for x in snapshots.list_research_snapshots()
              if x.source == "supabase_postgresql_pilot" and x.snapshot_id != snapshot_id]
    if not pilots:
        return None
    p = pilots[-1]
    rec = paths.component_dir(3) / p.snapshot_id / "pilot" / "pilot_run.json"
    prev = json.loads(rec.read_text(encoding="utf-8")) if rec.is_file() else {}
    col = run.get("collection") or {}
    return {"pilot_snapshot": p.snapshot_id,
            "rows": {"pilot": p.row_counts, "this_run": col.get("snapshot_rows")},
            "quota_units": {"pilot": prev.get("collection", {}).get("requests", {}).get("quota_units"),
                            "this_run": col.get("requests", {}).get("quota_units")},
            "depth": {"pilot": [prev.get("config", {}).get("max_videos_per_channel"),
                                prev.get("config", {}).get("max_threads_per_video")],
                      "this_run": [run["config"]["max_videos_per_channel"], run["config"]["max_threads_per_video"]]}}


# --- report ----------------------------------------------------------------------------------------------

def _md(v) -> str:
    """Markdown table cell: escape '|' (channel names may contain it)."""
    return str(v).replace("|", "\\|")


def render_report(run: dict[str, Any]) -> str:
    groups = run.get("groups", {})
    channel_list = ", ".join(f"{t} ({groups.get(i, '?')})" for t, i in run["channels"].items())
    c, col, cfg = run["channels"], run.get("collection") or {}, run["config"]
    lines = [
        f"# {cfg['title']}", "",
        f"Run: {run['started_at']} to {run['finished_at']} (UTC) · Snapshot: `{run.get('snapshot_id') or 'not created'}`",
        "", f"> {INTERPRETATION}", "",
        "## Configuration", "",
        "| Setting | Value |", "|---|---|",
        f"| Channels | {len(c)}: {channel_list} |",
        f"| Channel note | {cfg.get('channel_note') or '—'} |",
        f"| Videos per channel (max) | {cfg['max_videos_per_channel']} |",
        f"| Comment threads per video (max) | {cfg['max_threads_per_video']} (all replies fetched: {cfg['fetch_all_replies']}) |",
        f"| Observation window | {cfg['published_since'] or 'newest videos, no date limit'} |",
        f"| Retries / timeout | {cfg['max_retries']} retries, {cfg['request_timeout_seconds']} s |",
        f"| Quota cap | {cfg['max_quota_units']} units |",
        f"| Topic clusters / seed | {cfg['n_topics']} / {cfg['seed']} |",
        f"| Sparse simulations | fractions {cfg['evaluation_sparse_fractions']}, seeds {cfg['evaluation_sparse_seeds']} |",
        "", "## Preflight", "", "| Check | Status | Detail |", "|---|---|---|",
        *[f"| {x['check']} | {x['status']} | {x['detail']} |" for x in run["preflight"]["checks"]],
        "", f"Quota estimate (upper bound): {run['preflight']['quota']['total_upper_bound']} units "
            f"{run['preflight']['quota']['per_endpoint']}.", "",
    ]
    if col:
        r, v, cm = col["requests"], col["videos"], col["comments"]
        lines += [
            "## Collection (YouTube Data API v3)", "",
            "| Measure | Value |", "|---|---|",
            f"| API requests | {r['total']} ({r['succeeded']} succeeded, {r['failed']} failed, {r['retries']} retries) |",
            f"| Quota units used | {r['quota_units']} |",
            f"| Requests by endpoint | {r['by_endpoint']} |",
            f"| Channels collected | {col['channels']['collected']} of {col['channels']['requested']} |",
            f"| Videos collected | {v['collected']} (new {v['inserted']}, updated {v['updated']}, unchanged {v['unchanged']}) |",
            f"| Comments collected | {cm['collected']} ({cm['top_level']} top-level, {cm['replies']} replies) |",
            f"| Videos with zero public comments | {cm['videos_with_zero_public_comments']} |",
            f"| Videos with comments disabled | {cm['videos_with_comments_disabled']} |",
            f"| Videos without a public comment count | {cm['videos_with_unknown_public_count']} |",
            f"| Collection failures | channels {col['channels']['failed'] or 'none'}; videos {v['video_failures'] or 'none'}; "
            f"comments {cm['video_failures'] + cm['comment_failures'] or 'none'} |",
            f"| Pilot snapshot rows | {col['snapshot_rows']} |",
            f"| Collection time | {col['seconds']} s |", "",
        ]
    else:
        lines += ["## Collection", "", "Not executed.", ""]
    reg = run.get("registry") or {}
    if reg:
        lines += ["## Channel registry", "", "| Measure | Value |", "|---|---|",
                  f"| Configured channels | {reg.get('configured_total', '—')} {reg.get('configured_by_group', '')} |",
                  f"| Selected for this run | {reg.get('selected', len(run['channels']))} (groups {reg.get('requested_groups', '—')}) |",
                  f"| Research plan | {reg.get('expected_by_group') or '—'} |",
                  f"| Gaps | {reg.get('gaps') or 'none'} |",
                  f"| Duplicate / invalid ids | {reg.get('duplicate_ids') or 'none'} / {reg.get('invalid_ids') or 'none'} |", ""]
    if run.get("channel_quality"):
        lines += ["## Data quality by channel", "",
                  "Comment counts are bounded by the collection limits (videos per channel, threads per video) and "
                  "differ with channel size and content, so commenter counts are not comparable as audience sizes.", "",
                  "| Channel | Group | Videos | With comments | Zero public comments | Count hidden | Comments | "
                  "Top-level | Unique commenters | Stored / public | Video window | Comment window |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|",
                  *[f"| {_md(q['channel'])} | {q['group']} | {q['videos']} | {q['videos_with_comments']} | "
                    f"{q['zero_public_comments']} | {q['public_count_hidden']} | {q['comments']} | {q['top_level']} | "
                    f"{q['commenters']} | {q['stored_vs_public'] if q['stored_vs_public'] is not None else '—'} | "
                    f"{q['video_window']} | {q['comment_window']} |" for q in run["channel_quality"]], ""]
    if run.get("comparison"):
        cmp_ = run["comparison"]
        lines += ["## Difference from the controlled pilot", "", "| Measure | Pilot | This run |", "|---|---|---|",
                  f"| Snapshot rows | {cmp_['rows']['pilot']} | {cmp_['rows']['this_run']} |",
                  f"| Quota units | {cmp_['quota_units']['pilot']} | {cmp_['quota_units']['this_run']} |",
                  f"| Depth (videos, threads) | {cmp_['depth']['pilot']} | {cmp_['depth']['this_run']} |", ""]
    lines += ["## Pipeline stages", "", "| Stage | Status | Time (s) | Artifact | Details |", "|---|---|---|---|---|"]
    for s in run.get("stages", []):
        detail = s["error"] or json.dumps(s["details"], default=str)
        lines.append(f"| {s['stage']} | {s['status']} | {s['seconds'] if s['seconds'] is not None else '—'} | "
                     f"{('`' + s['artifact'] + '`') if s['artifact'] else '—'} | {detail.replace('|', '/')} |")
    lines += ["", "## Research validity checks", "", "| Check | Status | Detail |", "|---|---|---|",
              *[f"| {x['check']} | {x['status']} | {x['detail']} |" for x in run.get("validity", [])], ""]
    if run.get("top_bridges"):
        lines += ["## Audience Bridge Score results (top destination per source)", "",
                  "| Source | Destination | Score | Diffusion | Embedding | Topic | Confidence | Shared commenters |",
                  "|---|---|---|---|---|---|---|---|",
                  *[f"| {_md(b['source'])} | {_md(b['destination'])} | {b['score']} | {b['diffusion']} | {b['embedding']} | "
                    f"{b['topic']} | {b['confidence']} | {b['shared']} |" for b in run["top_bridges"]], ""]
    if run.get("distributions"):
        lines += ["## Score component and confidence distributions (scored pairs)", "",
                  "| Measure | Pairs | Min | Median | P90 | Max | Share = 0 |", "|---|---|---|---|---|---|---|",
                  *[f"| {d['measure']} | {d['pairs']} | {d.get('min', '—')} | {d.get('median', '—')} | {d.get('p90', '—')} | "
                    f"{d.get('max', '—')} | {d.get('share_zero', '—')} |" for d in run["distributions"]], ""]
    if run.get("insufficient_data"):
        lines += ["## Channels affected by insufficient data", "", *[f"- {x}" for x in run["insufficient_data"]], ""]
    if run.get("agreement"):
        lines += ["## Evaluation", "", "| Comparison | Metric | Value | Sources | Status / reason |", "|---|---|---|---|---|",
                  *[f"| {a['pair']} | {a['metric']} | {a['value']} | {a['n_sources']} | {a['status']} |"
                    for a in run["agreement"]], ""]
    lines += ["## Errors, warnings and limitations", "", *[f"- {x}" for x in run.get("limitations", [])], "",
              f"**Recommendation:** {run.get('recommendation', 'not determined')}", ""]
    return "\n".join(lines)


def summarize(st: dict[str, Any], channels: dict[str, str]) -> tuple[list[dict], list[dict]]:
    names = {f"channel:{i}": t for t, i in channels.items()}
    top = []
    b = st.get("bridge")
    if b is not None:
        s = b.scores[b.scores["rank"] == 1]
        f = lambda v, d=4: "—" if pd.isna(v) else f"{float(v):.{d}f}"  # noqa: E731
        top = [{"source": names.get(r.source_channel_id, r.source_channel_id),
                "destination": names.get(r.destination_channel_id, r.destination_channel_id),
                "score": f(r.audience_bridge_score), "diffusion": f(r.diffusion_contribution),
                "embedding": f(r.embedding_contribution), "topic": f(r.topic_contribution),
                "confidence": f(r.confidence), "shared": int(r.shared_commenters)} for r in s.itertuples()]
    agreement = []
    e = st.get("evaluation")
    if e is not None:
        t = e.tables["ranking_evaluation_results"]
        t = t[(t.analysis == "agreement") & (t.method == "audience_bridge_score")]
        agreement = [{"pair": f"audience_bridge_score vs {r.reference_method}",
                      "metric": r.metric + (f"@{int(r.k)}" if pd.notna(r.k) else ""),
                      "value": "—" if pd.isna(r.value) else f"{float(r.value):+.3f}", "n_sources": int(r.n_sources),
                      "status": r.status if pd.isna(r.reason) else f"{r.status}: {r.reason}"} for r in t.itertuples()]
    return top, agreement


def record_path(snapshot_id: str, config: PilotConfig) -> Path:
    return paths.component_dir(3) / snapshot_id / config.name / f"{config.name}_run.json"


def resume_collection(snapshot_id: str, config: PilotConfig | None = None) -> dict[str, Any]:
    """Collection record of an earlier run of ``snapshot_id`` (no API call): rerun the pipeline only."""
    config = config or PilotConfig(channel_titles=("resume",))
    record = record_path(snapshot_id, config)
    if not record.is_file():
        raise PilotError(f"no {config.name} run record for {snapshot_id}; only snapshots created by this runner "
                         "can be resumed")
    previous = json.loads(record.read_text(encoding="utf-8"))
    if not previous.get("collection") or previous.get("snapshot_id") != snapshot_id:
        raise PilotError(f"the pilot record of {snapshot_id} has no collection results")
    if snapshots.get_research_snapshot(snapshot_id).source != config.snapshot_source:
        raise PilotError(f"{snapshot_id} was not created by a {config.name} run")
    return {**previous["collection"], "resumed_from_run_started_at": previous["started_at"]}


def run_pilot(config: PilotConfig, *, preflight_only: bool = False, collect_fn=None, encoder=None,
              model_configs: dict[str, Any] | None = None, write_report: bool = True,
              resume_snapshot: str | None = None) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    before = {s.snapshot_id: s.manifest["datasets"] for s in snapshots.list_research_snapshots()}
    pre = preflight(config)
    run: dict[str, Any] = {"started_at": started.isoformat(timespec="seconds"), "config": config.to_dict(),
                           "channels": pre["channels"], "groups": pre.get("groups", {}),
                           "registry": pre.get("registry", {}), "preflight": pre, "collection": None, "stages": [],
                           "validity": [], "limitations": []}
    if preflight_only or not pre["ok"]:
        run["recommendation"] = ("preflight only" if pre["ok"] else
                                 "remediate: a required preflight check failed, nothing was collected")
        return _finish(run, config, write_report)
    try:
        run["collection"] = resume_collection(resume_snapshot, config) if resume_snapshot else \
            (collect_fn or collect)(config, pre["channels"])
    except Exception as exc:  # noqa: BLE001
        run["limitations"].append(f"collection failed: {type(exc).__name__}: {str(exc).splitlines()[0][:200]}")
        run["recommendation"] = "remediate: collection failed; existing data is unchanged"
        return _finish(run, config, write_report)
    sid = run["snapshot_id"] = run["collection"]["snapshot_id"]
    stages, st = run_pipeline(sid, config, encoder=encoder, **(model_configs or {}))
    run["stages"] = [s.__dict__ for s in stages]
    run["validity"] = validity_checks(sid, pre["channels"], st)
    run["top_bridges"], run["agreement"] = summarize(st, pre["channels"])
    after = {s.snapshot_id: s.manifest["datasets"] for s in snapshots.list_research_snapshots()}
    unchanged = all(after.get(k) == v for k, v in before.items()) and all(
        snapshots.verify_research_snapshot(k).ok for k in before)
    run["validity"].append(_check("existing snapshots unchanged", unchanged, f"{len(before)} earlier snapshot(s) verified"))
    lim = run["limitations"]
    n = len(pre["channels"])
    if n <= 5:
        lim.append(f"Small sample: {n} channels give {n * (n - 1)} ordered pairs and {n - 1} candidate destinations "
                   "per source; rank correlations need at least 3 shared destinations per source, so they are "
                   "undefined here.")
    lim.append("No relevance labels: ranking quality (precision, recall, NDCG, MRR) is not computed.")
    if "evaluation" in st:
        t = st["evaluation"].metadata["temporal"]
        lim.append(f"Temporal stability: {t.get('status')}" + (f" ({t.get('reason')})" if t.get("reason") else "")
                   + ". Comparable snapshots are judged on channel set and collection depth only; other collection "
                     "differences (e.g. reply fetching) are not detected automatically.")
    for g, v in (run.get("registry") or {}).get("gaps", {}).items():
        lim.append(f"Channel registry: the research plan names {v['expected']} {g} channel(s), the configuration "
                   f"has {v['configured']}; missing channels were not invented or substituted.")
    lim.append("This snapshot becomes the newest research snapshot, so commands and the dashboard default to it; "
               "select another snapshot explicitly where needed.")
    run["channel_quality"] = channel_quality(sid, pre["channels"], pre.get("groups", {}))
    run["distributions"] = distributions(st)
    run["insufficient_data"] = insufficient_data(st, pre["channels"])
    run["comparison"] = compare_with_pilot(sid, run)
    if resume_snapshot:
        lim.append(f"This report comes from a pipeline rerun on the existing pilot snapshot (collection run started "
                   f"{run['collection'].get('resumed_from_run_started_at')}); no new API calls were made. Stage times "
                   "are from the rerun.")
    if n - 1 <= 2:
        lim.append(f"Top-k overlap for k >= {n - 1} is trivially 1, because each source has only {n - 1} candidate "
                   "destinations.")
    thin = False
    if "bridge" in st:
        shared = st["bridge"].scores["shared_commenters"]
        k = float(st["bridge"].metadata["config"]["confidence_k"])
        thin = int(shared.max()) < k
        lim.append(f"Shared-commenter evidence per channel pair: max {int(shared.max())}, median {float(shared.median()):g} "
                   f"(confidence k = {k:g}). " + ("This is below k for every pair, so scores are small and say little "
                                                  "about audience bridges at this collection depth." if thin else ""))
    failed = [s for s in stages if s.status == "failed"]
    bad = [v for v in run["validity"] if v["status"] == "fail"]
    run["recommendation"] = (
        f"remediate: stage '{failed[0].stage}' failed ({failed[0].error})" if failed else
        f"remediate: validity check(s) failed: {[v['check'] for v in bad]}" if bad else
        "pipeline validated: scale to the full approved channel set, but at the full collection depth (e.g. 50 videos, "
        "100 threads per video); the pilot depth yields too little shared-commenter evidence for research conclusions"
        if thin else
        ("ready to scale to the full approved channel set (repeat the same configuration on all channels)"
         if config.name == "pilot" else
         "complete: all stages and validity checks passed; results are ready for analysis within the stated "
         "limitations (no relevance labels, provisional formula)"))
    return _finish(run, config, write_report)


def _finish(run: dict[str, Any], config: PilotConfig, write_report: bool) -> dict[str, Any]:
    run["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if write_report:
        text = render_report(run)
        if privacy.HASH_PREFIX in text:
            raise PilotError("report refused: it would contain commenter identifiers")
        path = paths.PROJECT_ROOT / config.report_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        run["report_path"] = str(config.report_path)
        if run.get("snapshot_id"):
            record = record_path(run["snapshot_id"], config)
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(json.dumps(run, indent=2, default=str) + "\n", encoding="utf-8")
    return run


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="pilot", description="Component 3 controlled real-data runs (STEP 26 pilot, "
                                                       "STEP 27 full experiment).")
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--preflight-only", action="store_true", help="checks and quota estimate only; no API calls")
    ap.add_argument("--snapshot", help="rerun the pipeline on a snapshot created by this runner (no collection, "
                                       "no API calls)")
    args = ap.parse_args(argv)
    try:
        config = load_config(Path(args.config))
        run = run_pilot(config, preflight_only=args.preflight_only, resume_snapshot=args.snapshot)
    except PilotError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Report: {run.get('report_path')}")
    for c in run["preflight"]["checks"]:
        print(f"  [{c['status']}] {c['check']}: {c['detail']}")
    if run.get("collection"):
        col = run["collection"]
        print(f"  collected: videos {col['videos']['collected']}, comments {col['comments']['collected']}, "
              f"quota {col['requests']['quota_units']} units -> snapshot {run['snapshot_id']}")
    for s in run["stages"]:
        print(f"  {s['stage']:<16} {s['status']:<13} {s['seconds'] if s['seconds'] is not None else '':>8} "
              f"{s['artifact'] or ''} {s['error'] or ''}")
    for v in run["validity"]:
        print(f"  [{v['status']}] {v['check']}")
    print(f"  Recommendation: {run['recommendation']}")
    return 0 if run["preflight"]["ok"] and not any(s["status"] == "failed" for s in run["stages"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
