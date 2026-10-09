"""Sparse-data robustness: controlled, seeded subsampling simulations.

For each (retain_fraction, seed) the source snapshot's comments are subsampled, either by
comment or by commenter (all of a commenter's comments kept or dropped together). Channels and
videos are kept unchanged, and the simulated snapshot keeps the source extraction time, so
``as_of`` (leakage control) is identical.

Isolation: every simulation runs in its own temporary data directory (``DATA_DIR`` is pointed
there for the duration and restored afterwards). The simulated snapshot, graph and features
live only there and are deleted afterwards. The source snapshot is checksum-verified before
and after; production data (Supabase, research snapshots, processed artifacts) is never written.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from research.component_3.evaluation import analysis as an
from research.component_3.preprocessing import graph_features as gf
from shared.utils import snapshots
from shared.utils.datasets import DATASETS, _conform, get_spec
from shared.utils.parquet_io import read_dataset

UNITS = ("comments", "commenters")
ROBUSTNESS_COLUMNS = ["method", "unit", "retain_fraction", "seed", "simulated_snapshot_id", "simulated_comments",
                      "simulated_commenters", "metric", "k", "value", "n_sources", "status", "reason"]


@contextmanager
def isolated_data_dir(root: Path) -> Iterator[Path]:
    """Temporarily point DATA_DIR at ``root`` (restored even on errors)."""
    old = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(root)
    try:
        yield root
    finally:
        if old is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = old


def read_frames(snapshot_id: str) -> dict[str, pd.DataFrame]:
    """The snapshot's datasets with their exact schema dtypes restored (e.g. list<string> tags)."""
    out = {}
    for n in DATASETS:
        path = snapshots.research_dataset_path(snapshot_id, n)
        out[n] = _conform(get_spec(n), read_dataset(path), path)
    return out


def subsample(comments: pd.DataFrame, fraction: float, seed: int, unit: str = "comments") -> pd.DataFrame:
    """Deterministic subsample keeping ``round(fraction * n)`` comments or commenters (seeded)."""
    if not 0 < fraction <= 1:
        raise ValueError("retain fraction must be in (0, 1]")
    if unit not in UNITS:
        raise ValueError(f"unit must be one of {UNITS}")
    rng = np.random.default_rng(seed)
    if unit == "comments":
        order = comments.sort_values("comment_id").index.to_numpy()
        keep = rng.permutation(order)[: int(round(fraction * len(order)))]
        return comments.loc[sorted(keep)].reset_index(drop=True)
    who = np.array(sorted(comments["author_channel_id"].dropna().unique()))
    kept = set(rng.permutation(who)[: int(round(fraction * len(who)))])
    return comments[comments["author_channel_id"].isin(kept)].reset_index(drop=True)


def simulate(snapshot_id: str, reference: dict[str, pd.DataFrame], methods: Sequence[str],
             fractions: Sequence[float], seeds: Sequence[int], ks: Sequence[int],
             rank_fn: Callable[[str, Sequence[str]], dict[str, pd.DataFrame | None]], unit: str = "comments",
             workdir: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Run every (fraction, seed) simulation; ``reference`` holds the full-data rankings per method and
    ``rank_fn(simulated_snapshot_id, methods)`` ranks the methods on the (isolated) simulated snapshot,
    called once per simulation while its temporary data directory is active."""
    if unit not in UNITS:
        raise ValueError(f"unit must be one of {UNITS}")
    before = snapshots.verify_research_snapshot(snapshot_id)
    if not before.ok:
        raise an.EvaluationError(f"source snapshot {snapshot_id} fails verification: {before.errors}")
    info = snapshots.get_research_snapshot(snapshot_id)
    as_of = gf._snapshot_time(info)
    frames = read_frames(snapshot_id)
    rows, runs = [], []
    for fraction in fractions:
        for seed in seeds:
            sub = subsample(frames["comments"], fraction, seed, unit)
            with tempfile.TemporaryDirectory(prefix="c3eval_", dir=workdir) as tmp, isolated_data_dir(Path(tmp)):
                sim = snapshots.create_research_snapshot(
                    {**frames, "comments": sub}, source="evaluation_simulation", extracted_at=as_of,
                    details={"simulation_of": snapshot_id, "unit": unit, "retain_fraction": fraction, "seed": seed})
                base = {"unit": unit, "retain_fraction": float(fraction), "seed": int(seed),
                        "simulated_snapshot_id": sim.snapshot_id, "simulated_comments": int(len(sub)),
                        "simulated_commenters": int(sub["author_channel_id"].nunique())}
                runs.append(base)
                ranked = rank_fn(sim.snapshot_id, [m for m in methods if m in reference])
                for m in methods:
                    ref = reference.get(m)
                    if ref is None or ref.empty:
                        rows.append({**base, "method": m, "metric": None, "k": None, "value": None, "n_sources": 0,
                                     "status": "unavailable", "reason": "no full-data reference rankings"})
                        continue
                    got = ranked.get(m)
                    if got is None or got.empty:
                        rows.append({**base, "method": m, "metric": None, "k": None, "value": None, "n_sources": 0,
                                     "status": "unavailable", "reason": "method produced no rankings on the simulation"})
                        continue
                    rows += [{**base, "method": m, **r} for r in an.compare_rankings(ref, got, ks)]
                    rows.append({**base, "method": m, **_coverage(ref, got)})
    after = snapshots.verify_research_snapshot(snapshot_id)
    if not after.ok:
        raise an.EvaluationError(f"source snapshot {snapshot_id} changed during simulation: {after.errors}")
    summary = {"unit": unit, "retain_fractions": [float(f) for f in fractions], "seeds": [int(s) for s in seeds],
               "source_comments": int(len(frames["comments"])), "runs": runs, "isolation": "temporary DATA_DIR per run",
               "source_snapshot_verified_before_and_after": True}
    return pd.DataFrame(rows, columns=ROBUSTNESS_COLUMNS), summary


def _coverage(ref: pd.DataFrame, got: pd.DataFrame) -> dict:
    """Share of the full-data pairs with a defined score that still have one under sparsity."""
    key = ["source_channel_id", "destination_channel_id"]
    r = ref.dropna(subset=["score"])[key]
    if r.empty:
        return {"metric": "score_coverage", "k": None, "value": None, "n_sources": 0, "status": "undefined",
                "reason": "no defined full-data scores"}
    g = got.dropna(subset=["score"])[key]
    kept = len(r.merge(g, on=key))
    return {"metric": "score_coverage", "k": None, "value": kept / len(r),
            "n_sources": int(r["source_channel_id"].nunique()), "status": "ok", "reason": None}
