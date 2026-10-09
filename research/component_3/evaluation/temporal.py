"""Temporal stability: do rankings stay stable across comparable research snapshots?

Two snapshots are compared only when their observation windows are comparable:
* the same channel set,
* a similar collection depth (median stored videos per channel within ``min_depth_ratio``),
* different data (identical dataset checksums carry no temporal information),
* the later snapshot extracted strictly later.

Snapshots that differ in collection depth (e.g. 10 vs 50 videos per channel) would measure the
collection change, not audience change, so they are reported but never scored. With fewer than
two comparable snapshots the result is "insufficient temporal data" (never a fabricated number).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from research.component_3.evaluation import analysis as an
from research.component_3.preprocessing import graph_features as gf
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset

INSUFFICIENT = "insufficient_temporal_data"
TEMPORAL_COLUMNS = ["method", "earlier_snapshot_id", "later_snapshot_id", "comparable", "comparability_reason",
                    "metric", "k", "value", "n_sources", "status", "reason"]


@dataclass(frozen=True)
class SnapshotProfile:
    snapshot_id: str
    extracted_at: datetime
    channels: frozenset[str]
    median_videos_per_channel: float | None
    comments: int
    data_checksums: tuple[str, ...]


def profile(snapshot_id: str) -> SnapshotProfile:
    info = snapshots.get_research_snapshot(snapshot_id)
    ch = read_dataset(snapshots.research_dataset_path(snapshot_id, "channels"), columns=["channel_id"])
    vids = read_dataset(snapshots.research_dataset_path(snapshot_id, "videos"), columns=["channel_id"])
    per = vids.groupby("channel_id").size()
    return SnapshotProfile(
        snapshot_id, gf._snapshot_time(info), frozenset("channel:" + ch["channel_id"].astype(str)),
        float(per.median()) if len(per) else None, int(info.row_counts.get("comments", 0)),
        tuple(m["sha256"] for _, m in sorted(info.manifest["datasets"].items())))


def comparability(a: SnapshotProfile, b: SnapshotProfile, min_depth_ratio: float = 0.8) -> tuple[bool, str]:
    if b.extracted_at <= a.extracted_at:
        return False, "later snapshot is not extracted after the earlier one"
    if a.channels != b.channels:
        return False, f"different channel sets ({len(a.channels)} vs {len(b.channels)} channels)"
    if a.data_checksums == b.data_checksums:
        return False, "identical data (no temporal change to measure)"
    da, db = a.median_videos_per_channel, b.median_videos_per_channel
    if not da or not db:
        return False, "a snapshot has no stored videos"
    ratio = min(da, db) / max(da, db)
    if ratio < min_depth_ratio:
        return False, (f"different observation windows: median {da:g} vs {db:g} stored videos per channel "
                       f"(depth ratio {ratio:.2f} < {min_depth_ratio})")
    return True, f"comparable (same channels, depth ratio {ratio:.2f})"


def plan(snapshot_ids: Sequence[str], min_depth_ratio: float = 0.8) -> tuple[list[SnapshotProfile], list[dict]]:
    """Profiles (oldest first) and the consecutive pairs with their comparability verdicts."""
    profiles = sorted((profile(s) for s in dict.fromkeys(snapshot_ids)), key=lambda p: p.extracted_at)
    pairs = []
    for a, b in zip(profiles, profiles[1:]):
        ok, why = comparability(a, b, min_depth_ratio)
        pairs.append({"earlier": a.snapshot_id, "later": b.snapshot_id, "comparable": ok, "reason": why})
    return profiles, pairs


def stability(snapshot_ids: Sequence[str], methods: Sequence[str], ks: Sequence[int],
              rank_fn: Callable[[str, str], pd.DataFrame | None], min_depth_ratio: float = 0.8
              ) -> tuple[pd.DataFrame, dict]:
    """``rank_fn(snapshot_id, method)`` returns that method's standard ranking table (None = unavailable)."""
    _, pairs = plan(snapshot_ids, min_depth_ratio)
    usable = [p for p in pairs if p["comparable"]]
    summary = {"snapshots": list(dict.fromkeys(snapshot_ids)), "pairs": pairs, "min_depth_ratio": min_depth_ratio,
               "comparable_pairs": len(usable)}
    rows = []
    if not usable:
        reason = ("fewer than 2 research snapshots" if len(pairs) == 0 else
                  "no consecutive pair of snapshots has comparable observation windows")
        summary.update(status=INSUFFICIENT, reason=reason)
        for m in methods:
            rows.append({"method": m, "earlier_snapshot_id": None, "later_snapshot_id": None, "comparable": False,
                         "comparability_reason": None, "metric": None, "k": None, "value": None, "n_sources": 0,
                         "status": INSUFFICIENT, "reason": reason})
        for p in pairs:   # keep the evidence of why each pair was excluded
            for m in methods:
                rows.append(_excluded(m, p))
        return _frame(rows), summary

    summary.update(status="ok", reason=None)
    for p in pairs:
        for m in methods:
            if not p["comparable"]:
                rows.append(_excluded(m, p))
                continue
            ra, rb = rank_fn(p["earlier"], m), rank_fn(p["later"], m)
            if ra is None or rb is None or ra.empty or rb.empty:
                rows.append({**_base(m, p), "metric": None, "k": None, "value": None, "n_sources": 0,
                             "status": "unavailable", "reason": "method produced no rankings for a snapshot"})
                continue
            rows += [{**_base(m, p), **r} for r in an.compare_rankings(ra, rb, ks)]
    return _frame(rows), summary


def _base(method: str, pair: dict) -> dict:
    return {"method": method, "earlier_snapshot_id": pair["earlier"], "later_snapshot_id": pair["later"],
            "comparable": pair["comparable"], "comparability_reason": pair["reason"]}


def _excluded(method: str, pair: dict) -> dict:
    return {**_base(method, pair), "metric": None, "k": None, "value": None, "n_sources": 0,
            "status": "not_comparable", "reason": pair["reason"]}


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=TEMPORAL_COLUMNS)
