"""Component 3 research evaluation (STEP 21): proposed method vs baselines.

    python -m research.component_3.evaluation.evaluate                       # latest research snapshot
    python -m research.component_3.evaluation.evaluate --labels labels.csv --k 1 3 5
    python -m research.component_3.evaluation.evaluate --topic-backend char_lsa --skip-sparse

Methods (see methods.py): audience_bridge_score (proposed; a slot until STEP 19 exists),
ppr_diffusion and topic_similarity (components of the proposed method), louvain and node2vec
(baselines). Analyses:

* ranking quality: Precision@k, Recall@k, NDCG@k, MRR **only with explicit relevance labels**;
  without labels they are not computed and method agreement (Spearman, Kendall tau-b, top-k
  Jaccard) is reported instead. Agreement is consistency between methods, not accuracy.
* top-k: per-source top-k lists, distinct destinations, boundary ties.
* temporal stability across comparable research snapshots ("insufficient temporal data" otherwise).
* sparse-data robustness: seeded subsampling simulations in isolated temporary data directories.
* computational performance: measured wall-clock time and traced Python-heap peak, nothing estimated.

Artifacts: data/processed/component_3/<snapshot_id>/evaluation/<evaluation_id>/ (write-once).
No result shows audience migration, causality or growth.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.component_3.evaluation import analysis as an
from research.component_3.evaluation import methods as me
from research.component_3.evaluation import robustness as rb
from research.component_3.evaluation import temporal as tp
from research.component_3.model import baselines as bl
from research.component_3.preprocessing import hetero_graph as hg
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

EVALUATION_DIR = "evaluation"
EVALUATION_VERSION = "1.0"
METADATA_FILE = "evaluation_run_metadata.json"
COMPARISON_NOTE = ("Agreement and stability measure consistency between rankings, not correctness. "
                   "No result shows audience migration, audience transfer, causality or growth.")
ABS_NOTE = "Audience Bridge Score (STEP 19) is not yet available; the proposed method's slot is reported as unavailable."

RANKING_EVAL_COLUMNS = ["analysis", "method", "reference_method", "metric", "k", "value", "n_sources", "status",
                        "reason"]
PERFORMANCE_COLUMNS = ["stage", "method", "context", "run_snapshot_id", "status", "seconds", "python_heap_peak_mib",
                       "graph_nodes", "graph_edges", "channels", "retain_fraction", "seed"]
TABLE_DTYPES = {"k": "Int64", "value": "Float64", "n_sources": "Int64", "seconds": "Float64",
                "python_heap_peak_mib": "Float64", "graph_nodes": "Int64", "graph_edges": "Int64",
                "channels": "Int64", "retain_fraction": "Float64", "seed": "Int64", "rank": "Int64",
                "score": "Float64", "tied": "boolean", "comparable": "boolean", "simulated_comments": "Int64",
                "simulated_commenters": "Int64"}
CORRELATIONS = {"spearman", "kendall"}
UNIT_INTERVAL = {"topk_jaccard", "precision_at_k", "recall_at_k", "ndcg_at_k", "mrr", "score_coverage",
                 "topk_boundary_tie_share"}
VOLATILE_COLUMNS = ("simulated_snapshot_id",)   # simulated snapshot ids carry their creation time
DETERMINISTIC_TABLES = ("ranking_evaluation_results", "top_k_evaluation_results", "temporal_stability_results",
                        "sparse_robustness_results")
MEMORY_NOTE = ("python_heap_peak_mib = peak of allocations traced by tracemalloc (Python objects and NumPy "
               "buffers) during the stage; memory allocated by native libraries that bypass the Python allocator "
               "(e.g. parts of gensim, PyTorch) is not included. Times include tracemalloc overhead.")


@dataclass(frozen=True)
class EvaluationConfig:
    methods: tuple[str, ...] = tuple(me.METHODS)
    ks: tuple[int, ...] = (1, 3, 5)
    labels_path: str | None = None
    run_temporal: bool = True
    temporal_snapshots: tuple[str, ...] | None = None        # None = all research snapshots
    min_depth_ratio: float = 0.8
    run_sparse: bool = True
    sparse_unit: str = "comments"
    sparse_fractions: tuple[float, ...] = (0.75, 0.5, 0.25)
    sparse_seeds: tuple[int, ...] = (0, 1, 2)
    sparse_methods: tuple[str, ...] = ("audience_bridge_score", "ppr_diffusion", "louvain", "node2vec")

    def __post_init__(self):
        unknown = sorted((set(self.methods) | set(self.sparse_methods)) - set(me.METHODS))
        if unknown:
            raise an.EvaluationError(f"unknown method(s) {unknown}; available {sorted(me.METHODS)}")
        if not self.ks or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in self.ks):
            raise an.EvaluationError("k values must be positive integers")
        if not 0 < self.min_depth_ratio <= 1:
            raise an.EvaluationError("min_depth_ratio must be in (0, 1]")
        if any(not 0 < f <= 1 for f in self.sparse_fractions):
            raise an.EvaluationError("sparse retain fractions must be in (0, 1]")
        if self.sparse_unit not in rb.UNITS:
            raise an.EvaluationError(f"sparse_unit must be one of {rb.UNITS}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationResult:
    evaluation_id: str
    snapshot_id: str
    tables: dict[str, pd.DataFrame]
    metadata: dict[str, Any] = field(default_factory=dict)


class _Runner:
    """Runs methods per snapshot, caching rankings and recording performance rows."""

    def __init__(self, encoder, method_configs: dict[str, Any]):
        self.encoder, self.configs = encoder, method_configs
        self.cache: dict[tuple[str, str], me.MethodRun] = {}
        self.performance: list[dict] = []

    def context(self, snapshot_id: str, stage: str, extra: dict) -> me.MethodContext:
        t0 = time.perf_counter()
        inp = bl.load_input(snapshot_id)
        self.performance.append({"stage": stage, "method": "input_preparation", "context": "graph + features as of "
                                 "the snapshot", "run_snapshot_id": snapshot_id, "status": "ok",
                                 "seconds": round(time.perf_counter() - t0, 4), "python_heap_peak_mib": None,
                                 **_graph_size(inp), **extra})
        return me.MethodContext(snapshot_id, inp, encoder=self.encoder, **self.configs)

    def run(self, ctx: me.MethodContext, methods, stage: str, extra: dict, cache: bool = True) -> dict[str, me.MethodRun]:
        out = {}
        for m in methods:
            key = (ctx.snapshot_id, m)
            if cache and key in self.cache:
                out[m] = self.cache[key]
                continue
            r = me.run_method(m, ctx)
            errors = me.validate_rankings(r.rankings) if r.status == "ok" else []
            if errors:
                raise an.EvaluationError(f"{m} rankings failed validation: {errors}")
            self.performance.append({"stage": stage, "method": m, "context": "method run", "run_snapshot_id":
                                     ctx.snapshot_id, "status": r.status,
                                     "seconds": r.seconds if r.status == "ok" else None,
                                     "python_heap_peak_mib": r.python_peak_mib if r.status == "ok" else None,
                                     **_graph_size(ctx.baseline_input), **extra})
            if cache:
                self.cache[key] = r
            out[m] = r
        return out


def evaluate(snapshot_id: str, config: EvaluationConfig = EvaluationConfig(), *, encoder=None,
             node2vec_config=None, louvain_config=None, ppr_config=None, topic_config=None) -> EvaluationResult:
    info = snapshots.get_research_snapshot(snapshot_id)
    configs = {"node2vec_config": node2vec_config, "louvain_config": louvain_config, "ppr_config": ppr_config,
               "topic_config": topic_config}
    runner = _Runner(encoder, configs)
    ks = tuple(sorted(set(config.ks)))
    started = time.perf_counter()

    # 1. every method on the evaluated snapshot
    ctx = runner.context(info.snapshot_id, "main", {"retain_fraction": None, "seed": None})
    inp = ctx.baseline_input
    runs = runner.run(ctx, config.methods, "main", {"retain_fraction": None, "seed": None})
    ok = {m: r for m, r in runs.items() if r.status == "ok"}
    rankings = {m: r.rankings for m, r in ok.items()}

    # 2. ranking quality (labels only) + agreement + top-k
    labels, label_sha = (an.load_labels(config.labels_path, inp.channels) if config.labels_path else (None, None))
    rows = []
    for m, r in runs.items():
        if r.status != "ok":
            rows.append(_row("method_status", m, None, {"metric": None, "k": None, "value": None, "n_sources": 0,
                                                         "status": r.status, "reason": r.reason}))
        elif labels is None:
            rows.append(_row("relevance", m, None, {"metric": None, "k": None, "value": None, "n_sources": 0,
                                                     "status": "not_computed",
                                                     "reason": "no explicit relevance labels supplied; relevance "
                                                               "metrics are not computed (agreement reported instead)"}))
        else:
            rows += [_row("relevance", m, None, x) for x in an.relevance_metrics(r.rankings, labels, ks)]
    for a, b in combinations([m for m in config.methods if m in ok], 2):
        rows += [_row("agreement", a, b, x) for x in an.compare_rankings(rankings[a], rankings[b], ks)]
    for m in rankings:
        rows += [_row("top_k_summary", m, None, x) for x in an.top_k_summary(rankings[m], ks)]
    ranking_eval = pd.DataFrame(rows, columns=RANKING_EVAL_COLUMNS)
    top_k = pd.concat([an.top_k_table(rankings[m], ks) for m in rankings], ignore_index=True) if rankings \
        else an.top_k_table(me._empty(), ks)

    # 3. temporal stability
    if config.run_temporal:
        sids = list(config.temporal_snapshots or [s.snapshot_id for s in snapshots.list_research_snapshots()])
        if info.snapshot_id not in sids:
            sids.append(info.snapshot_id)

        def rank_at(sid: str, method: str):
            if (sid, method) not in runner.cache:
                c = ctx if sid == info.snapshot_id else runner.context(sid, "temporal", {"retain_fraction": None,
                                                                                         "seed": None})
                runner.run(c, [m for m in config.methods if (sid, m) not in runner.cache], "temporal",
                           {"retain_fraction": None, "seed": None})
            r = runner.cache[(sid, method)]
            return r.rankings if r.status == "ok" else None

        temporal, temporal_summary = tp.stability(sids, list(config.methods), ks, rank_at, config.min_depth_ratio)
    else:
        temporal, temporal_summary = pd.DataFrame(columns=tp.TEMPORAL_COLUMNS), {"status": "skipped"}

    # 4. sparse-data robustness (isolated simulations)
    sparse_methods = [m for m in config.sparse_methods if m in config.methods]
    if config.run_sparse and sparse_methods:
        def rank_sim(sid: str, methods) -> dict[str, pd.DataFrame | None]:
            extra = current.copy()
            c = runner.context(sid, "sparse_simulation", extra)
            res = runner.run(c, methods, "sparse_simulation", extra, cache=False)
            return {m: r.rankings if r.status == "ok" else None for m, r in res.items()}

        current: dict = {}
        sparse_rows, sparse_summary = [], None
        for fraction in config.sparse_fractions:
            for seed in config.sparse_seeds:
                current.update(retain_fraction=float(fraction), seed=int(seed))
                df, summ = rb.simulate(info.snapshot_id, {m: rankings[m] for m in sparse_methods if m in rankings},
                                       sparse_methods, [fraction], [seed], ks, rank_sim, config.sparse_unit)
                sparse_rows.append(df)
                sparse_summary = summ if sparse_summary is None else {**sparse_summary,
                                                                      "runs": sparse_summary["runs"] + summ["runs"]}
        sparse = pd.concat(sparse_rows, ignore_index=True)
        sparse_summary.update(retain_fractions=list(config.sparse_fractions), seeds=list(config.sparse_seeds))
        sparse_summary["unchanged_by_design"] = {
            m: "topic similarity depends only on video text, which comment subsampling does not change"
            for m in config.methods if m == "topic_similarity" and m not in sparse_methods}
    else:
        sparse, sparse_summary = pd.DataFrame(columns=rb.ROBUSTNESS_COLUMNS), {"status": "skipped"}

    performance = pd.DataFrame(runner.performance, columns=PERFORMANCE_COLUMNS)

    # 5. identity + metadata
    experiments = {m: r.experiment_id for m, r in runs.items()}
    evaluation_id = make_evaluation_id(info.snapshot_id, inp.graph.fingerprint(), config, label_sha, experiments,
                                       configs)
    tables = {
        "ranking_evaluation_results": ranking_eval,
        "top_k_evaluation_results": top_k,
        "temporal_stability_results": temporal,
        "sparse_robustness_results": sparse,
        "computational_performance_results": performance,
    }
    tables = {name: _finish(df, info.snapshot_id, evaluation_id) for name, df in tables.items()}
    abs_run = runs.get("audience_bridge_score")
    metadata = {
        "evaluation_id": evaluation_id, "evaluation_version": EVALUATION_VERSION, "snapshot_id": info.snapshot_id,
        "graph_fingerprint": inp.graph.fingerprint(), "as_of": inp.as_of.isoformat().replace("+00:00", "Z"),
        "channels": inp.channels, "config": config.to_dict(),
        "method_configs": {k: (asdict(v) if v is not None else "module default") for k, v in configs.items()},
        "methods": {m: {"status": r.status, "role": _role(m), "experiment_id": r.experiment_id, "reason": r.reason,
                        "details": r.details} for m, r in runs.items()},
        "proposed_method": {"method": "audience_bridge_score",
                            "status": abs_run.status if abs_run else "not requested",
                            "note": ABS_NOTE if (abs_run is None or abs_run.status != "ok") else None},
        "labels": ({"path": str(config.labels_path), "sha256": label_sha, "rows": int(len(labels)),
                    "sources": sorted(set(labels["label_source"].astype(str))),
                    "unlabelled_destinations": "treated as not relevant for labelled sources"}
                   if labels is not None else {"status": "none supplied",
                                               "consequence": "relevance metrics not computed"}),
        "temporal": temporal_summary, "sparse_robustness": sparse_summary,
        "performance": {"memory_note": MEMORY_NOTE, "total_seconds": round(time.perf_counter() - started, 4),
                        "platform": platform.platform(), "processor": platform.processor() or None,
                        "cpu_count": os.cpu_count()},
        "interpretation": COMPARISON_NOTE,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "versions": _versions(),
    }
    result = EvaluationResult(evaluation_id, info.snapshot_id, tables, metadata)
    result.metadata["validation"] = validate(result)
    return result


def make_evaluation_id(snapshot_id, fingerprint, config, label_sha, experiments, configs) -> str:
    payload = json.dumps({"snapshot": snapshot_id, "graph": fingerprint, "config": config.to_dict(),
                          "labels": label_sha, "experiments": experiments, "version": EVALUATION_VERSION,
                          "method_configs": {k: asdict(v) if v is not None else None for k, v in configs.items()}},
                         sort_keys=True, default=str)
    return f"eval-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


# --- validation ------------------------------------------------------------------------------

def validate(result: EvaluationResult) -> dict[str, Any]:
    errors = []
    expected = {"ranking_evaluation_results": RANKING_EVAL_COLUMNS, "top_k_evaluation_results": an.TOP_K_COLUMNS,
                "temporal_stability_results": tp.TEMPORAL_COLUMNS, "sparse_robustness_results": rb.ROBUSTNESS_COLUMNS,
                "computational_performance_results": PERFORMANCE_COLUMNS}
    for name, cols in expected.items():
        df = result.tables.get(name)
        if df is None:
            errors.append(f"{name}: missing")
            continue
        if list(df.columns) != ["evaluation_id", "snapshot_id", *cols]:
            errors.append(f"{name}: unexpected columns")
            continue
        if (df["evaluation_id"] != result.evaluation_id).any():
            errors.append(f"{name}: rows from another evaluation")
        if "value" in df:
            v = df["value"].astype("float64")
            if np.isinf(v).any():
                errors.append(f"{name}: infinite values")
            ok = df["status"] == "ok"
            if v[ok].isna().any() or v[~ok].notna().any():
                errors.append(f"{name}: value must be set exactly when status is ok")
            corr, unit = df["metric"].isin(CORRELATIONS), df["metric"].isin(UNIT_INTERVAL)
            if ((v[corr] < -1 - 1e-9) | (v[corr] > 1 + 1e-9)).any():
                errors.append(f"{name}: correlation outside [-1, 1]")
            if ((v[unit] < -1e-9) | (v[unit] > 1 + 1e-9)).any():
                errors.append(f"{name}: metric outside [0, 1]")
    tk = result.tables.get("top_k_evaluation_results")
    if tk is not None and len(tk) and (tk["source_channel_id"] == tk["destination_channel_id"]).any():
        errors.append("top-k contains self pairs")
    perf = result.tables.get("computational_performance_results")
    if perf is not None and len(perf) and (perf["seconds"].dropna() < 0).any():
        errors.append("negative timings")
    if errors:
        raise an.EvaluationError("evaluation validation failed: " + "; ".join(errors))
    return {"passed": True}


# --- persistence ---------------------------------------------------------------------------

def evaluation_dir(snapshot_id: str, evaluation_id: str) -> Path:
    return hg.graph_dir(snapshot_id).parent / EVALUATION_DIR / evaluation_id


def save(result: EvaluationResult) -> Path:
    """Write once. An existing run with identical deterministic tables is kept as is (timings and
    simulated snapshot ids differ between runs by nature); different results under the same id are refused."""
    target = evaluation_dir(result.snapshot_id, result.evaluation_id)
    digests = {n: digest(result.tables[n]) for n in result.tables}
    stable = {n: digest(result.tables[n].drop(columns=list(VOLATILE_COLUMNS), errors="ignore"))
              for n in DETERMINISTIC_TABLES}
    if (target / METADATA_FILE).is_file():
        existing = json.loads((target / METADATA_FILE).read_text(encoding="utf-8")).get("deterministic_sha256", {})
        if existing == stable:
            return target
        raise FileExistsError(f"evaluation {result.evaluation_id} already exists with different results")
    staging = target.with_name(f".{target.name}.staging")
    for name, df in result.tables.items():
        write_dataset(df, staging / f"{name}.parquet", overwrite=True)
    meta = {**result.metadata, "table_sha256": digests, "deterministic_sha256": stable}
    (staging / METADATA_FILE).write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


def load(directory: Path) -> EvaluationResult:
    meta = json.loads((directory / METADATA_FILE).read_text(encoding="utf-8"))
    tables = {n: _types(read_dataset(directory / f"{n}.parquet")) for n in meta["table_sha256"]}
    for n, df in tables.items():
        if digest(df) != meta["table_sha256"][n]:
            raise an.EvaluationError(f"{n}.parquet changed after saving (checksum mismatch)")
    return EvaluationResult(meta["evaluation_id"], meta["snapshot_id"], tables, meta)


def digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False, lineterminator="\n").encode()).hexdigest()


# --- helpers ---------------------------------------------------------------------------------

def _row(analysis: str, method: str, reference: str | None, values: dict) -> dict:
    return {"analysis": analysis, "method": method, "reference_method": reference, **values}


def _role(method: str) -> str:
    return ("proposed method" if method in me.PROPOSED else
            "component of proposed method" if method in me.PROPOSED_COMPONENTS else "baseline")


def _graph_size(inp) -> dict:
    return {"graph_nodes": int(len(inp.graph.nodes)), "graph_edges": int(len(inp.graph.edges)),
            "channels": int(len(inp.channels))}


def _types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if c in TABLE_DTYPES:
            df[c] = df[c].astype(TABLE_DTYPES[c])
        elif df[c].dtype == object or str(df[c].dtype).startswith("string"):
            df[c] = df[c].astype("string")
    return df


def _finish(df: pd.DataFrame, snapshot_id: str, evaluation_id: str) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    df.insert(0, "snapshot_id", snapshot_id)
    df.insert(0, "evaluation_id", evaluation_id)
    df = df.astype(object).where(df.notna(), None)
    return _types(df)


def _versions() -> dict[str, str]:
    import networkx
    import scipy

    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__, "networkx": networkx.__version__}


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="evaluate", description="Component 3 research evaluation (STEP 21).")
    ap.add_argument("--snapshot", help="research snapshot id (default: latest)")
    ap.add_argument("--methods", nargs="+", choices=sorted(me.METHODS), default=list(me.METHODS))
    ap.add_argument("--k", nargs="+", type=int, default=[1, 3, 5])
    ap.add_argument("--labels", help="explicit relevance labels (CSV/Parquet): source_channel_id, "
                                     "destination_channel_id, relevance, label_source")
    ap.add_argument("--topic-backend", choices=["e5", "char_lsa"], default="e5")
    ap.add_argument("--skip-temporal", action="store_true")
    ap.add_argument("--skip-sparse", action="store_true")
    ap.add_argument("--sparse-unit", choices=rb.UNITS, default="comments")
    ap.add_argument("--sparse-fractions", nargs="+", type=float, default=[0.75, 0.5, 0.25])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    args = ap.parse_args(argv)
    try:
        from research.component_3.model import topic_similarity as ts

        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        config = EvaluationConfig(methods=tuple(args.methods), ks=tuple(args.k), labels_path=args.labels,
                                  run_temporal=not args.skip_temporal, run_sparse=not args.skip_sparse,
                                  sparse_unit=args.sparse_unit, sparse_fractions=tuple(args.sparse_fractions),
                                  sparse_seeds=tuple(args.seeds))
        result = evaluate(sid, config, topic_config=ts.TopicConfig(backend=args.topic_backend))
        out = save(result)
    except (an.EvaluationError, FileExistsError, snapshots.SnapshotNotFoundError, hg.GraphBuildError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    m = result.metadata
    print(f"Evaluation {result.evaluation_id} on {sid} -> {out}")
    for name, info in m["methods"].items():
        print(f"  {name:<22} {info['role']:<30} {info['status']}" + (f" ({info['reason']})" if info["reason"] else ""))
    if m["proposed_method"]["note"]:
        print(f"  NOTE: {m['proposed_method']['note']}")
    print(f"  labels: {m['labels'].get('status', 'supplied')} | temporal: {m['temporal'].get('status')}"
          + (f" ({m['temporal'].get('reason')})" if m["temporal"].get("reason") else "")
          + f" | sparse runs: {len(m['sparse_robustness'].get('runs', []))}")
    agree = result.tables["ranking_evaluation_results"]
    agree = agree[(agree["analysis"] == "agreement") & (agree["metric"] == "spearman")]
    for r in agree.itertuples():
        val = "undefined" if pd.isna(r.value) else f"{r.value:+.3f} over {r.n_sources} sources"
        print(f"  spearman {r.method} vs {r.reference_method}: {val}")
    print(f"  ({COMPARISON_NOTE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
