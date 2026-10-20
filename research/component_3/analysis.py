"""Quick organization analysis: collect a small, fresh sample for any confirmed channel set and score it.

Used by the dashboard's "Analyze organization" page (through the API job runner) and usable directly:

    from research.component_3 import analysis
    analysis.run_analysis("Sirasa", {"UC...": "Sirasa TV", "UC...": "Shakthi TV"})

What it does, in order (every step reuses existing project code):
  1. light preflight: API key, commenter salt and disk space
  2. collection into the shared database with *quick* limits (QUICK_LIMITS: newest videos per channel,
     comment threads per video, no extra reply pages), so a run takes minutes rather than hours
  3. a research snapshot that contains exactly the channels / videos / comments of this run, labelled
     with the organization (manifest ``details.organization``), so it never mixes with other data
  4. the Component 3 pipeline up to the Audience Bridge Score: QUICK_STAGES (topics, graph, features,
     metapath2vec, PPR, score, Louvain baseline, explanations). HGT, node2vec and the evaluation are
     skipped for speed; run them later with the normal commands if needed
  5. public channel icons for the dashboard (best effort, 1 quota unit)

Quick analyses are exploratory: they use smaller samples than the research runs and are not part of
the frozen thesis dataset (config/research_channels.json is never changed here). Results remain potential
audience bridge signals; they do not show audience migration, subscriber transfer, causality or growth.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any, Callable

from shared.utils import paths, privacy

from research.component_3 import pilot as pl

QUICK_LIMITS = {"max_videos_per_channel": 15, "max_threads_per_video": 50, "fetch_all_replies": False}
QUICK_STAGES = ("research_data", "topics", "graph", "features", "metapath2vec", "ppr_diffusion",
                "audience_bridge", "louvain", "explainability")
SNAPSHOT_SOURCE = "supabase_postgresql_analysis"
MIN_CHANNELS, MAX_CHANNELS = 2, 25
MAX_QUOTA_UNITS = 2000
COMMENT_BATCH = 20          # videos per progress update during comment collection

STEP_LABELS = {
    "preflight": "Checking configuration",
    "channels": "Collecting channel details",
    "videos": "Collecting recent videos",
    "comments": "Collecting public comments",
    "snapshot": "Creating the organization snapshot",
    "research_data": "Validating the data",
    "topics": "Topic similarity (multilingual E5)",
    "graph": "Building the heterogeneous graph",
    "features": "Graph features",
    "metapath2vec": "metapath2vec embeddings",
    "ppr_diffusion": "Personalized PageRank diffusion",
    "audience_bridge": "Audience Bridge Score",
    "louvain": "Louvain baseline",
    "explainability": "Explanations",
    "icons": "Channel icons",
}
STEPS = ("preflight", "channels", "videos", "comments", "snapshot") + QUICK_STAGES + ("icons",)

Progress = Callable[[str, str, dict[str, Any]], None]   # (step, status, details)


class AnalysisError(RuntimeError):
    """A quick analysis cannot start or failed; the message is safe to show (no secrets, no ids of people)."""


def quick_config(organization: str, titles: list[str]) -> pl.PilotConfig:
    return pl.PilotConfig(channel_titles=tuple(titles), name="analysis",
                          title=f"Quick organization analysis: {organization}", snapshot_source=SNAPSHOT_SOURCE,
                          max_quota_units=MAX_QUOTA_UNITS, stages=QUICK_STAGES, **QUICK_LIMITS)


def validate_channels(channels: dict[str, str]) -> None:
    from shared.data_collection.youtube_api_client import is_valid_id

    if not MIN_CHANNELS <= len(channels) <= MAX_CHANNELS:
        raise AnalysisError(f"select between {MIN_CHANNELS} and {MAX_CHANNELS} channels (got {len(channels)}); "
                            "audience bridges need at least two channels")
    bad = [c for c in channels if not is_valid_id(c)]
    if bad:
        raise AnalysisError(f"{len(bad)} channel id(s) are not valid YouTube channel ids")


def preflight(config: pl.PilotConfig, n_channels: int) -> dict[str, Any]:
    """Fast checks only (no database round trip, no snapshot verification)."""
    from shared.data_collection.youtube_api_client import YouTubeClient

    problems = []
    try:
        YouTubeClient(timeout=config.request_timeout_seconds)
    except Exception:  # noqa: BLE001 - never echo configuration values
        problems.append("the YouTube API key is missing or invalid in .env")
    try:
        privacy.pseudonymize_id("UC_preflight_probe_value", privacy.get_salt())
    except Exception:  # noqa: BLE001
        problems.append("COMMENTER_HASH_SALT is not configured in .env")
    if not os.getenv("SUPABASE_DB_URL", "").strip():
        problems.append("SUPABASE_DB_URL is not configured in .env")
    data = paths.get_data_paths()
    free_gb = shutil.disk_usage(data.root if data.root.exists() else paths.PROJECT_ROOT).free / 1e9
    if free_gb < config.min_free_disk_gb:
        problems.append(f"only {free_gb:.1f} GB disk space free (need {config.min_free_disk_gb} GB)")
    quota = pl.estimate_quota(config, n_channels)
    if not quota["within_cap"]:
        problems.append(f"estimated quota {quota['total_upper_bound']} units exceeds the cap {config.max_quota_units}")
    if problems:
        raise AnalysisError("; ".join(problems))
    return {"free_disk_gb": round(free_gb, 1), "quota_upper_bound": quota["total_upper_bound"]}


def collect(organization: str, channels: dict[str, str], config: pl.PilotConfig, progress: Progress,
            *, client=None, database=None) -> dict[str, Any]:
    """Collect with the existing collectors and export a snapshot of exactly this run's records."""
    from shared.data_collection import channel_collector as chc
    from shared.data_collection import video_collector as vc
    from shared.data_collection import youtube_api_client as yc
    from shared.data_collection import youtube_comment_collector as cmc
    from shared.database.connection import database as default_database
    from shared.database.snapshot_export import export_research_snapshot

    client = client or yc.YouTubeClient(timeout=config.request_timeout_seconds,
                                        retry=yc.RetryPolicy(max_retries=config.max_retries,
                                                             backoff_seconds=config.retry_backoff_seconds))
    ids = list(channels)
    out: dict[str, Any] = {}
    with (database or default_database)() as conn:
        progress("channels", "running", {})
        ch = chc.collect_channels(ids, client, chc.supabase_store(conn))
        conn.commit()
        out["channels"] = {"requested": len(ids), "collected": len(ch.collected), "failed": len(ch.failed)}
        progress("channels", "completed", out["channels"])
        if not ch.collected:
            raise AnalysisError("no channel could be collected from YouTube")

        progress("videos", "running", {})
        vids = vc.collect_videos(list(ch.collected), client, vc.supabase_store(conn),
                                 known_channels=vc.supabase_known_channels(conn),
                                 max_videos_per_channel=config.max_videos_per_channel)
        conn.commit()
        out["videos"] = {"collected": len(vids.videos_collected), "failed": len(vids.video_failures)
                         + len(vids.channel_failures)}
        progress("videos", "completed", out["videos"])
        if not vids.videos_collected:
            raise AnalysisError("no videos were collected; the channels may have no public uploads")

        refs = cmc.stored_videos(conn, video_ids=vids.videos_collected)
        collected: list[str] = []
        disabled = failed = 0
        progress("comments", "running", {"videos_done": 0, "videos_total": len(refs)})
        for start in range(0, len(refs), COMMENT_BATCH):
            res = cmc.collect_comments(refs[start:start + COMMENT_BATCH], client, cmc.supabase_store(conn),
                                       max_threads_per_video=config.max_threads_per_video,
                                       fetch_all_replies=config.fetch_all_replies)
            conn.commit()
            collected.extend(res.comments_collected)
            disabled += len(res.videos_with_comments_disabled)
            failed += len(res.video_failures) + len(res.comment_failures)
            progress("comments", "running", {"videos_done": min(start + COMMENT_BATCH, len(refs)),
                                             "videos_total": len(refs), "comments": len(collected)})
        out["comments"] = {"collected": len(collected), "videos": len(refs),
                           "videos_with_comments_disabled": disabled, "failed": failed}
        progress("comments", "completed", out["comments"])

        progress("snapshot", "running", {})
        info = export_research_snapshot(
            conn, scope={"channels": list(ch.collected), "videos": vids.videos_collected, "comments": collected},
            source=config.snapshot_source,
            details={"run": "quick_analysis", "organization": organization, "channels": sorted(channels.values()),
                     "limits": QUICK_LIMITS})
        out["snapshot_id"] = info.snapshot_id
        out["snapshot_rows"] = dict(info.row_counts)
        progress("snapshot", "completed", {"snapshot_id": info.snapshot_id, **dict(info.row_counts)})
    out["quota_units"] = client.quota_used
    out["client"] = client
    return out


def _load_encoder():
    """The pinned multilingual E5 encoder, loaded once and shared by all stages of a job."""
    from research.component_3.model import topic_similarity as ts

    return ts.E5Encoder()


def fetch_channel_icons(client, channel_ids: list[str]) -> int:
    """Merge public profile-image URLs of these channels into the dashboard icon file (best effort)."""
    from research.component_3.preprocessing import channel_icons as ci

    path = ci.icons_path()
    existing = (json.loads(path.read_text(encoding="utf-8")).get("items") or {}) if path.is_file() else {}
    new = ci.fetch_icons(client, channel_ids)
    ci.write_icons({**existing, **new})
    return len(new)


def run_analysis(organization: str, channels: dict[str, str], progress: Progress | None = None,
                 *, client=None, database=None, encoder=None) -> dict[str, Any]:
    """channels: channel id -> title. Returns a summary; raises AnalysisError on a failure."""
    progress = progress or (lambda step, status, details: None)
    validate_channels(channels)
    config = quick_config(organization, list(channels.values()))
    t0 = time.perf_counter()

    progress("preflight", "running", {})
    progress("preflight", "completed", preflight(config, len(channels)))

    col = collect(organization, channels, config, progress, client=client, database=database)
    sid = col["snapshot_id"]
    encoder = encoder or _load_encoder()   # loaded once per job (fewer model loads, fewer network checks)

    def on_stage(r: pl.StageResult) -> None:
        details = dict(r.details or {})
        if r.artifact:
            details["artifact"] = r.artifact
        if r.error:
            details["error"] = r.error
        progress(r.stage, r.status, details)

    results, _ = pl.run_pipeline(sid, config, encoder=encoder, on_stage=on_stage)
    failed = next((r for r in results if r.status == "failed"), None)
    if failed:
        raise AnalysisError(f"pipeline stage '{STEP_LABELS.get(failed.stage, failed.stage)}' failed: {failed.error}")

    progress("icons", "running", {})
    try:
        n = fetch_channel_icons(col["client"], list(channels))
        progress("icons", "completed", {"icons": n})
    except Exception as exc:  # noqa: BLE001 - decoration only; never fails the analysis
        progress("icons", "skipped", {"reason": type(exc).__name__})

    artifacts = {r.stage: r.artifact for r in results if r.artifact}
    return {"organization": organization, "snapshot_id": sid, "experiment_id": artifacts.get("audience_bridge"),
            "explanation_id": artifacts.get("explainability"), "rows": col["snapshot_rows"],
            "quota_units": col["quota_units"], "seconds": round(time.perf_counter() - t0, 1)}


# --- completing a quick analysis (optional, from the dashboard) ------------------------------------

COMPLETE_STEPS = ("hgt", "node2vec", "evaluation")
STEP_LABELS.update({"hgt": "HGT embeddings (alternative model)", "node2vec": "node2vec baseline",
                    "evaluation": "Evaluation (agreement, top-k, temporal; no sparse re-runs)"})


def organization_snapshots(organization: str) -> list[str]:
    """Quick-analysis snapshots of one organization, oldest first."""
    from shared.utils import snapshots

    return [s.snapshot_id for s in snapshots.list_research_snapshots()
            if s.source == SNAPSHOT_SOURCE and (s.manifest.get("details") or {}).get("organization") == organization]


def complete_analysis(snapshot_id: str, progress: Progress | None = None, *, encoder=None) -> dict[str, Any]:
    """Run the stages a quick analysis skips: HGT, node2vec and an evaluation without sparse re-runs.

    Temporal stability compares only snapshots of the same organization (never the research dataset).
    Existing deterministic results are reused, so running it twice costs little."""
    from research.component_3.evaluation import evaluate as ev
    from research.component_3.model import baselines as bl
    from research.component_3.model import hgt
    from research.component_3.model import metapath2vec as m2v
    from research.component_3.model import topic_similarity as ts
    from research.component_3.preprocessing import hetero_graph as hg
    from shared.utils import snapshots

    progress = progress or (lambda step, status, details: None)
    info = snapshots.get_research_snapshot(snapshot_id)
    organization = (info.manifest.get("details") or {}).get("organization")
    if info.source != SNAPSHOT_SOURCE or not organization:
        raise AnalysisError("only quick-analysis snapshots can be completed here; use the research commands for "
                            "the research dataset")
    t0 = time.perf_counter()
    encoder = encoder or _load_encoder()   # after validation: a refused snapshot never loads the model
    graph = hg.load_graph(hg.graph_dir(snapshot_id))
    out: dict[str, Any] = {"organization": organization, "snapshot_id": snapshot_id}

    progress("hgt", "running", {})
    cfg = hgt.HGTConfig(seed=42)
    saved = m2v.embeddings_dir(snapshot_id, hgt.make_experiment_id(graph, cfg))
    if (saved / "experiment.json").is_file() and (saved / "model.pt").is_file():
        out["hgt"] = saved.name
    else:
        r, model = hgt.train(graph, cfg)
        hgt.save(r, model)
        out["hgt"] = r.experiment_id
    progress("hgt", "completed", {"artifact": out["hgt"]})

    progress("node2vec", "running", {})
    inp = bl.load_input(snapshot_id)
    n2v_cfg = bl.Node2VecConfig(seed=42)
    r = bl.run_node2vec(inp, n2v_cfg)
    if not (bl.baseline_dir(snapshot_id, r.experiment_id) / "experiment.json").is_file():
        bl.save_node2vec(r)
    out["node2vec"] = r.experiment_id
    progress("node2vec", "completed", {"artifact": r.experiment_id})

    progress("evaluation", "running", {})
    same_org = organization_snapshots(organization)
    temporal = [s for s in same_org if s <= snapshot_id]
    cfg_ev = ev.EvaluationConfig(run_sparse=False, run_temporal=len(temporal) >= 2,
                                 temporal_snapshots=tuple(temporal) if len(temporal) >= 2 else None)
    res = ev.evaluate(snapshot_id, cfg_ev, encoder=encoder,
                      topic_config=ts.TopicConfig(n_topics=10, seed=42), node2vec_config=n2v_cfg)
    ev.save(res)
    out["evaluation"] = res.evaluation_id
    methods = res.metadata.get("methods", {})
    failed = {m: v.get("reason") for m, v in methods.items() if v.get("status") != "ok"}
    if "audience_bridge_score" in failed:   # the proposed method must be evaluated; never report this as done
        progress("evaluation", "failed", {"artifact": res.evaluation_id, "error": failed["audience_bridge_score"]})
        raise AnalysisError(f"the evaluation could not score the Audience Bridge Score: "
                            f"{str(failed['audience_bridge_score'])[:200]}; run 'Complete analysis' again")
    progress("evaluation", "completed", {"artifact": res.evaluation_id,
                                          "temporal": res.metadata["temporal"].get("status", "skipped"),
                                          **({"failed_methods": sorted(failed)} if failed else {})})
    out["seconds"] = round(time.perf_counter() - t0, 1)
    return out
