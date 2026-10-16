"""Component 3 research views for the dashboard: graph intelligence, topic similarity, all scored bridge
pairs and the run (experiment) browser.

Read-only. Everything is read from stored artifacts (run metadata JSON and Parquet results); nothing is
recomputed or estimated. Only aggregates leave this module: node and edge counts, degree histograms
(counts of nodes per degree bin), channel-level values and run configuration. No node identifier of a
commenter or video is returned.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from backend.database.component_3_artifacts import (BRIDGE_DIR, BRIDGE_RUN, DIFFUSION_DIR, EVALUATION_DIR,
                                                    EVALUATION_META, EXPLANATION_META, EXPLANATIONS_DIR,
                                                    FEATURES_DIR, GRAPH_DIR, TOPICS_DIR, BASELINES_DIR,
                                                    Component3Store)
from backend.services.component_3.service import ArtifactUnavailable, Component3Service, _clean, _public, _ts, _v

# degree bins for the histogram (upper bounds, inclusive); the last bin is open-ended
DEGREE_BINS = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, 500), (501, None)]

# run folders: (kind folder, id prefix, metadata file, readable method, pipeline step)
RUN_KINDS = [
    (DIFFUSION_DIR, "ppr", "diffusion_run.json", "Personalized PageRank", "STEP 17"),
    (TOPICS_DIR, "top", "topic_run.json", "Topic similarity", "STEP 18"),
    ("embeddings", "m2v", "experiment.json", "metapath2vec", "STEP 15"),
    ("embeddings", "hgt", "experiment.json", "HGT", "STEP 16"),
    (BASELINES_DIR, "louvain", "baseline_run.json", "Louvain baseline", "STEP 20"),
    (BASELINES_DIR, "node2vec", "experiment.json", "node2vec baseline", "STEP 20"),
    (BRIDGE_DIR, "abs", BRIDGE_RUN, "Audience Bridge Score", "STEP 19"),
    (EXPLANATIONS_DIR, "xpl", EXPLANATION_META, "Explainability", "STEP 22"),
    (EVALUATION_DIR, "eval", EVALUATION_META, "Evaluation", "STEP 21"),
]
BRIDGE_COLUMNS = ["source_channel_id", "destination_channel_id", "rank", "audience_bridge_score", "base_score",
                  "diffusion_contribution", "embedding_contribution", "topic_contribution", "confidence",
                  "evidence_confidence", "topic_coverage_confidence", "shared_commenters", "score_status", "raw_topic_similarity"]


def _scalar(v: Any) -> str | float | int | bool | None:
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return v[:120]
    if isinstance(v, list):
        if all(isinstance(x, dict) and "name" in x for x in v):
            return ", ".join(str(x["name"]) for x in v)[:120]
        if all(isinstance(x, (str, int, float, bool)) for x in v):
            return ", ".join(str(x) for x in v)[:120]
        return f"{len(v)} items"
    if isinstance(v, dict):
        return f"{len(v)} entries" if v else "none"
    return str(v)[:120]


def _config(meta: dict[str, Any], limit: int = 14) -> dict[str, Any]:
    """Top-level configuration of a run as display scalars (never data rows)."""
    cfg = meta.get("config")
    if not isinstance(cfg, dict):
        return {}
    return {k: _scalar(v) for k, v in list(cfg.items())[:limit]}


def _passed(meta: dict[str, Any]) -> bool | None:
    val = meta.get("validation")
    return bool(val.get("passed")) if isinstance(val, dict) and "passed" in val else None


class ResearchViewsService:
    def __init__(self, base: Component3Service):
        self.base = base
        self.store: Component3Store = base.store

    def channel_icons(self) -> dict[str, Any]:
        """Public channel profile-image URLs saved by ``research.component_3.preprocessing.channel_icons``.
        Presentation metadata only. Entries with an invalid channel id or a non-allowed image host are dropped,
        so the dashboard only loads images from YouTube's image hosts. A missing file gives an empty list."""
        from urllib.parse import urlparse
        from research.component_3.preprocessing.channel_icons import ALLOWED_HOSTS, icons_path, is_channel_id
        data = self.store.read_json(icons_path()) or {}
        items = []
        for cid, url in sorted((data.get("items") or {}).items()):
            parsed = urlparse(url) if isinstance(url, str) else None
            if is_channel_id(cid) and parsed and parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS:
                items.append({"channel_id": cid, "icon_url": url})
        return _clean({"fetched_at": _ts(data.get("fetched_at")), "items": items,
                       "note": "Public channel profile images from YouTube; shown for recognition only."})

    def _names(self, sid: str) -> dict[str, str | None]:
        ch = self.store.query(self.store.snapshot_dataset(sid, "channels"), ["channel_id", "channel_name"])
        return dict(zip(ch["channel_id"].astype(str), ch["channel_name"]))

    def _latest(self, sid: str, kind: str, prefix: str, meta_file: str) -> dict[str, Any] | None:
        runs = self.store.runs(sid, kind, prefix, meta_file)
        return runs[-1] if runs else None

    # --- graph intelligence -------------------------------------------------------------------------

    def graph_summary(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        sid = snap.snapshot_id
        gdir = self.store.processed_dir(sid) / GRAPH_DIR
        manifest = self.store.read_json(gdir / "graph_manifest.json")
        if manifest is None:
            raise ArtifactUnavailable(f"the heterogeneous graph (STEP 13) has not been built for snapshot {sid}")
        stats = manifest.get("statistics", {})
        defs = manifest.get("weight_definitions", {})
        relations = [{"relation": name, "source_type": r.get("source_type"), "target_type": r.get("target_type"),
                      "derived": bool(r.get("derived")), "edges": stats.get("edge_counts", {}).get(name),
                      "weight_definition": defs.get(name)}
                     for name, r in manifest.get("relations", {}).items()]

        # degree histogram per node type over observed (non-derived) edges: counts only, no node ids
        rows = self.store.aggregate("""
            WITH e AS (SELECT source AS node, source_type AS t FROM edges WHERE NOT derived
                       UNION ALL SELECT target, target_type FROM edges WHERE NOT derived),
                 d AS (SELECT t, node, count(*) AS degree FROM e GROUP BY t, node)
            SELECT t AS node_type, degree, count(*) AS nodes FROM d GROUP BY 1, 2 ORDER BY 1, 2
        """, {"edges": gdir / "graph_edges.parquet"})
        degree = []
        node_counts = stats.get("node_counts", {})
        observed = {str(t): grp for t, grp in rows.groupby("node_type")}
        for t in sorted(set(node_counts) | set(observed)):
            grp = observed.get(t)
            hist = Counter()
            total, weighted, mx = 0, 0, 0
            pairs = zip(grp["degree"].astype(int), grp["nodes"].astype(int)) if grp is not None else []
            for deg, n in pairs:
                total += n
                weighted += deg * n
                mx = max(mx, deg)
                for lo, hi in DEGREE_BINS:
                    if deg >= lo and (hi is None or deg <= hi):
                        hist[(lo, hi)] += n
                        break
            # nodes without any observed edge (e.g. a channel with no stored video) have degree 0
            isolated = max(0, int(node_counts.get(t, total)) - total)
            hist[(0, 0)] += isolated
            total += isolated
            degree.append({"node_type": str(t), "nodes": total, "mean_degree": weighted / total if total else None,
                           "max_degree": mx,
                           "bins": [{"label": f"{lo}" if lo == hi else (f"{lo}+" if hi is None else f"{lo}–{hi}"),
                                     "nodes": hist.get((lo, hi), 0)} for lo, hi in DEGREE_BINS]})

        # channel connectivity and connected components of the shared-commenter channel graph
        names = self._names(sid)
        overlap = self.store.processed_dir(sid) / "channel_pair_overlap.parquet"
        partners: dict[str, set[str]] = {c: set() for c in names}
        shared: Counter = Counter()
        if overlap.is_file():
            pf = self.store.query(overlap, ["channel_a", "channel_b", "shared_commenters"])
            for a, b, n in zip(pf["channel_a"], pf["channel_b"], pf["shared_commenters"]):
                a, b = _public(str(a)), _public(str(b))
                if int(n) > 0:
                    partners.setdefault(a, set()).add(b)
                    partners.setdefault(b, set()).add(a)
                    shared[a] += int(n)
                    shared[b] += int(n)
        seen: set[str] = set()
        components = []
        for c in sorted(partners):
            if c in seen:
                continue
            stack, comp = [c], []
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                comp.append(x)
                stack.extend(partners.get(x, ()))
            components.append(len(comp))
        channels = sorted(({"channel_id": c, "channel_name": names.get(c), "connected_channels": len(p),
                            "shared_commenters_summed": shared.get(c, 0)} for c, p in partners.items()),
                          key=lambda r: (-r["connected_channels"], -r["shared_commenters_summed"], r["channel_id"]))

        reps = []
        for prefix, label in (("m2v", "metapath2vec"), ("hgt", "HGT")):
            m = self._latest(sid, "embeddings", prefix, "experiment.json")
            if m is None:
                reps.append({"method": label, "status": "missing"})
                continue
            val, cov = m.get("validation", {}), m.get("coverage", {})
            reps.append({"method": label, "status": "available", "experiment_id": m.get("experiment_id"),
                         "created_at": _ts(m.get("created_at")), "role": m.get("role", "primary" if prefix == "m2v" else None),
                         "dimensions": val.get("dimensions"), "coverage_ratio": cov.get("coverage_ratio"),
                         "validation_passed": _passed(m), "config": _config(m, 8)})

        d = self._latest(sid, DIFFUSION_DIR, "ppr", "diffusion_run.json")
        diffusion: dict[str, Any] = {"status": "missing"}
        if d is not None:
            conv = d.get("convergence", {}) or {}
            iters = [c.get("iterations") for c in conv.values() if isinstance(c, dict) and c.get("iterations") is not None]
            resid = [c.get("residual") for c in conv.values() if isinstance(c, dict) and c.get("residual") is not None]
            cfg = d.get("config", {})
            dg = d.get("diffusion_graph", {})
            diffusion = {"status": "available", "experiment_id": d.get("experiment_id"), "created_at": _ts(d.get("created_at")),
                         "alpha": cfg.get("alpha"), "tolerance": cfg.get("tolerance"), "max_iterations": cfg.get("max_iterations"),
                         "directionality": cfg.get("directionality"), "include_topic_edges": cfg.get("include_topic_edges"),
                         "include_derived_participation": cfg.get("include_derived_participation"),
                         "sources": len(conv), "converged_sources": sum(1 for c in conv.values() if isinstance(c, dict) and c.get("converged")),
                         "iterations_max": max(iters) if iters else None, "residual_max": max(resid) if resid else None,
                         "graph_nodes": dg.get("nodes"), "graph_edges": dg.get("edges"),
                         "validation_passed": _passed(d)}

        return _clean({
            "snapshot_id": sid, "built_at": _ts(manifest.get("built_at")),
            "node_counts": stats.get("node_counts", {}), "edge_counts": stats.get("edge_counts", {}),
            "total_nodes": stats.get("total_nodes"), "total_edges": stats.get("total_edges"),
            "total_edges_excluding_derived": stats.get("total_edges_excluding_derived"),
            "commenters_on_multiple_channels": stats.get("commenters_on_multiple_channels"),
            "channel_pairs_with_shared_commenters": stats.get("channel_pairs_with_shared_commenters"),
            "relations": relations, "degree_distribution": degree, "channel_connectivity": channels,
            "connected_components": sorted(components, reverse=True), "representations": reps, "diffusion": diffusion,
            "note": "Descriptive graph statistics and stored run settings; shared commenters are interaction "
                    "signals, not audience migration."})

    # --- topic similarity ----------------------------------------------------------------------------

    def topic_similarity(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        sid = snap.snapshot_id
        run = self._latest(sid, TOPICS_DIR, "top", "topic_run.json")
        if run is None:
            raise ArtifactUnavailable(f"no topic similarity run (STEP 18) exists for snapshot {sid}")
        names = self._names(sid)
        sim = self.store.query(run["_dir"] / "channel_topic_similarity.parquet",
                               ["source_channel_id", "destination_channel_id", "topic_similarity", "both_profiles_available"])
        prof_path = run["_dir"] / "channel_semantic_profiles.parquet"
        profiles = {}
        if prof_path.is_file():
            pf = self.store.query(prof_path, ["channel_id", "total_videos", "usable_videos", "coverage_ratio", "profile_available"])
            profiles = {_public(str(r.channel_id)): r for r in pf.itertuples()}
        channels = [{"channel_id": c, "channel_name": n,
                     "profile_available": bool(profiles[c].profile_available) if c in profiles else False,
                     "usable_videos": _v(profiles[c].usable_videos) if c in profiles else None,
                     "coverage_ratio": _v(profiles[c].coverage_ratio) if c in profiles else None}
                    for c, n in sorted(names.items(), key=lambda kv: (kv[1] or kv[0]))]
        cells = [{"source_channel_id": _public(str(r.source_channel_id)), "destination_channel_id": _public(str(r.destination_channel_id)),
                  "topic_similarity": _v(r.topic_similarity) if bool(r.both_profiles_available) else None}
                 for r in sim.itertuples() if str(r.source_channel_id) != str(r.destination_channel_id)]
        model = run.get("model", {}) if isinstance(run.get("model"), dict) else {}
        clustering = run.get("clustering", {}) if isinstance(run.get("clustering"), dict) else {}
        return _clean({"snapshot_id": sid, "experiment_id": run.get("experiment_id"), "created_at": _ts(run.get("created_at")),
                       "model": model.get("name"), "n_topics": clustering.get("n_topics"),
                       "channels": channels, "cells": cells,
                       "note": "Topic similarity is the cosine similarity of channel content profiles (video titles and "
                               "descriptions); it measures content similarity only, not audience overlap."})

    # --- all scored pairs ----------------------------------------------------------------------------

    def bridge_pairs(self, snapshot_id: str | None, experiment_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        run = self.base._experiment(snap, experiment_id)
        path = run["_dir"] / "audience_bridge_scores.parquet"
        df = self.store.query(path, BRIDGE_COLUMNS, where="source_channel_id <> destination_channel_id",
                              order_by="audience_bridge_score DESC NULLS LAST, source_channel_id, destination_channel_id",
                              limit=10000)
        names = self._names(snap.snapshot_id)
        items = []
        for r in df.itertuples():
            s, d = _public(str(r.source_channel_id)), _public(str(r.destination_channel_id))
            items.append({"source_channel_id": s, "source_channel_name": names.get(s),
                          "destination_channel_id": d, "destination_channel_name": names.get(d),
                          "rank": _v(r.rank), "audience_bridge_score": _v(r.audience_bridge_score), "base_score": _v(r.base_score),
                          "diffusion_component": _v(r.diffusion_contribution), "embedding_component": _v(r.embedding_contribution),
                          "topic_component": _v(r.topic_contribution), "confidence_component": _v(r.confidence),
                          "evidence_confidence": _v(r.evidence_confidence), "topic_coverage_confidence": _v(r.topic_coverage_confidence),
                          "shared_commenters": _v(r.shared_commenters), "score_status": str(r.score_status),
                          "topic_similarity": _v(r.raw_topic_similarity)})
        return _clean({"snapshot_id": snap.snapshot_id, "experiment_id": run["experiment_id"], "items": items,
                       "note": "Stored Audience Bridge Scores (provisional formula), ordered by score; rank is the "
                               "per-source rank from the scoring run. Nothing is recalculated."})

    # --- run browser ---------------------------------------------------------------------------------

    def runs(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self.base._snapshot(snapshot_id)
        sid = snap.snapshot_id
        pdir = self.store.processed_dir(sid)
        items = []
        g = self.store.read_json(pdir / GRAPH_DIR / "graph_manifest.json")
        if g is not None:
            st = g.get("statistics", {})
            items.append({"run_id": "graph", "kind": GRAPH_DIR, "method": "Heterogeneous graph", "step": "STEP 13",
                          "created_at": _ts(g.get("built_at")), "validation_passed": None,
                          "config": {"schema_version": g.get("graph_schema_version"), "nodes": st.get("total_nodes"),
                                     "edges": st.get("total_edges")}})
        fdir = pdir / FEATURES_DIR
        if fdir.is_dir():
            for d in sorted(x for x in fdir.iterdir() if x.is_dir() and x.name.startswith("asof-")):
                m = self.store.read_json(d / "feature_manifest.json")
                if m is not None:
                    items.append({"run_id": d.name, "kind": FEATURES_DIR, "method": "Graph features", "step": "STEP 14",
                                  "created_at": _ts(m.get("created_at") or m.get("built_at")), "validation_passed": _passed(m),
                                  "config": _config(m, 8)})
        for kind, prefix, meta_file, label, step in RUN_KINDS:
            for m in self.store.runs(sid, kind, prefix, meta_file):
                # the folder name is the run's own id (explanation and evaluation metadata also name the scoring run)
                items.append({"run_id": m["_dir"].name, "kind": kind, "method": label, "step": step,
                              "created_at": _ts(m.get("created_at")), "validation_passed": _passed(m), "config": _config(m)})
        items.sort(key=lambda r: (str(r["created_at"] or ""), r["run_id"]), reverse=True)
        return _clean({"snapshot_id": sid, "snapshot_created_at": snap.created_at, "snapshot_extracted_at": snap.extracted_at,
                       "row_counts": snap.row_counts, "items": items,
                       "note": "Stored research runs of this snapshot with their recorded configuration (read-only)."})

    # --- neural models (HGT, metapath2vec) ------------------------------------------------------------

    def neural_models(self, snapshot_id: str | None) -> dict[str, Any]:
        """Stored settings and training records of the graph neural models. Aggregates only: per-epoch
        losses and metrics, walk counts per metapath, feature names per node type."""
        snap = self.base._snapshot(snapshot_id)
        sid = snap.snapshot_id

        def num(v: Any) -> float | None:
            try:
                return None if v is None else float(v)
            except (TypeError, ValueError):
                return None

        hgt_meta = self._latest(sid, "embeddings", "hgt", "experiment.json")
        hgt: dict[str, Any] = {"status": "missing"}
        if hgt_meta is not None:
            tr = hgt_meta.get("training", {}) or {}
            history = [{"epoch": int(h.get("epoch", i + 1)), "train_loss": num(h.get("train_loss")),
                        "valid_loss": num(h.get("valid_loss")), "valid_roc_auc": num(h.get("valid_roc_auc")),
                        "valid_average_precision": num(h.get("valid_average_precision"))}
                       for i, h in enumerate(tr.get("history", []) or []) if isinstance(h, dict)]
            split = hgt_meta.get("split", {}) or {}
            nf = hgt_meta.get("node_features", {}) or {}
            hgt = {"status": "available", "experiment_id": hgt_meta.get("experiment_id"),
                   "created_at": _ts(hgt_meta.get("created_at")), "role": hgt_meta.get("role"),
                   "config": _config(hgt_meta, 14), "objective": str(hgt_meta.get("objective", ""))[:200] or None,
                   "negative_sampling": {k: _scalar(v) for k, v in (hgt_meta.get("negative_sampling", {}) or {}).items()},
                   "split": {"kind": split.get("kind"), "train_edges": num(split.get("train_edges")),
                             "validation_edges": num(split.get("validation_edges")), "cutoff": _ts(split.get("cutoff"))},
                   "node_features": {str(k): [str(x) for x in v] for k, v in nf.items() if isinstance(v, list)},
                   "history": history, "duration_seconds": num(tr.get("duration_seconds")),
                   "dimensions": (hgt_meta.get("validation", {}) or {}).get("dimensions"),
                   "coverage_ratio": (hgt_meta.get("coverage", {}) or {}).get("coverage_ratio"),
                   "validation_passed": _passed(hgt_meta)}

        m2v_meta = self._latest(sid, "embeddings", "m2v", "experiment.json")
        m2v: dict[str, Any] = {"status": "missing"}
        if m2v_meta is not None:
            cfg = m2v_meta.get("config", {}) or {}
            paths = {str(p.get("name")): p for p in cfg.get("metapaths", []) if isinstance(p, dict)}
            walks = (m2v_meta.get("walks", {}) or {})
            per = []
            for name, w in (walks.get("per_metapath", {}) or {}).items():
                p = paths.get(str(name), {})
                per.append({"metapath": str(name), "node_types": [str(t) for t in p.get("node_types", [])],
                            "start_nodes": num(w.get("start_nodes")), "walks": num(w.get("walks")), "truncated": num(w.get("truncated"))})
            tr = m2v_meta.get("training", {}) or {}
            m2v = {"status": "available", "experiment_id": m2v_meta.get("experiment_id"),
                   "created_at": _ts(m2v_meta.get("created_at")), "config": _config(m2v_meta, 14),
                   "metapaths": per, "total_walks": num(walks.get("total_walks")), "mean_walk_length": num(walks.get("mean_walk_length")),
                   "training": {k: _scalar(v) for k, v in tr.items()},
                   "dimensions": (m2v_meta.get("validation", {}) or {}).get("dimensions"),
                   "coverage_ratio": (m2v_meta.get("coverage", {}) or {}).get("coverage_ratio"),
                   "validation_passed": _passed(m2v_meta)}
        return _clean({"snapshot_id": sid, "hgt": hgt, "metapath2vec": m2v,
                       "note": "Graph representation models of the score's embedding component. Records are read from "
                               "the stored runs; nothing is retrained. Embedding similarity reflects graph structure only."})

    # --- snapshot comparison ----------------------------------------------------------------------------

    def compare(self, snapshot_id: str | None, base_snapshot_id: str) -> dict[str, Any]:
        """Stored scores of the latest scoring run of two snapshots, joined per directed pair. Comparison is
        allowed only when both snapshots have a scoring run and the same channel set, and the base snapshot
        is older. Differences are plain subtractions of stored values; nothing is rescored."""
        cur = self.base._snapshot(snapshot_id)
        base = self.base._snapshot(base_snapshot_id)

        def run_info(snap):
            runs = self.store.runs(snap.snapshot_id, BRIDGE_DIR, "abs", BRIDGE_RUN)
            if not runs:
                return None
            m = runs[-1]
            cfg = m.get("config", {}) or {}
            return m, {"snapshot_id": snap.snapshot_id, "experiment_id": m.get("experiment_id"), "created_at": _ts(m.get("created_at")),
                       "method_version": m.get("method_version"), "w_diffusion": cfg.get("w_diffusion"),
                       "w_embedding": cfg.get("w_embedding"), "w_topic": cfg.get("w_topic"),
                       "embedding_source": cfg.get("embedding_source")}

        out: dict[str, Any] = {"compatible": False, "reason": None, "base": None, "current": None,
                               "same_configuration": None, "items": [],
                               "note": "Changes are differences of stored values between two scoring runs (current minus "
                                       "previous). They describe how the research signal changed, not audience movement."}
        if base.snapshot_id == cur.snapshot_id:
            out["reason"] = "Select two different snapshots."
            return _clean(out)
        if base.as_of >= cur.as_of:
            out["reason"] = "The previous snapshot must be older than the current snapshot."
            return _clean(out)
        bi, ci = run_info(base), run_info(cur)
        if bi is None or ci is None:
            out["reason"] = "Both snapshots need a stored Audience Bridge Score run."
            return _clean(out)
        out["base"], out["current"] = bi[1], ci[1]
        if set(self._names(base.snapshot_id)) != set(self._names(cur.snapshot_id)):
            out["reason"] = "The snapshots cover different channel sets, so their rankings are not comparable."
            return _clean(out)
        keys = ("method_version", "w_diffusion", "w_embedding", "w_topic", "embedding_source")
        out["same_configuration"] = all(bi[1].get(k) == ci[1].get(k) for k in keys)
        cols = ["source_channel_id", "destination_channel_id", "audience_bridge_score", "rank", "confidence",
                "diffusion_contribution", "raw_topic_similarity"]
        frames = {}
        for tag, (m, _) in (("b", bi), ("c", ci)):
            df = self.store.query(m["_dir"] / "audience_bridge_scores.parquet", cols, where="source_channel_id <> destination_channel_id")
            frames[tag] = {(str(r.source_channel_id), str(r.destination_channel_id)): r for r in df.itertuples()}
        names = self._names(cur.snapshot_id)

        def diff(a, b):
            return None if a is None or b is None else b - a

        items = []
        for key in sorted(set(frames["b"]) | set(frames["c"])):
            rb, rc = frames["b"].get(key), frames["c"].get(key)
            get = lambda r, f: None if r is None else _v(getattr(r, f))
            s, d = _public(key[0]), _public(key[1])
            row = {"source_channel_id": s, "source_channel_name": names.get(s),
                   "destination_channel_id": d, "destination_channel_name": names.get(d)}
            for field, name in (("audience_bridge_score", "score"), ("rank", "rank"), ("confidence", "confidence"),
                                ("diffusion_contribution", "diffusion"), ("raw_topic_similarity", "topic_similarity")):
                pv, cv = get(rb, field), get(rc, field)
                row[f"previous_{name}"], row[f"current_{name}"], row[f"{name}_change"] = pv, cv, diff(pv, cv)
            items.append(row)
        items.sort(key=lambda r: (-(abs(r["score_change"]) if r["score_change"] is not None else -1), r["source_channel_id"], r["destination_channel_id"]))
        out.update({"compatible": True, "items": items})
        return _clean(out)
