"""Component 3 API business logic: selects snapshots / experiments, validates identifiers and
filters, and shapes stored research artifacts into response payloads.

Nothing is recomputed: scores come from STEP 19 artifacts, explanations from STEP 22, evaluation
from STEP 21. A missing artifact is reported as unavailable, never filled in.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from backend.database.component_3_artifacts import (BASELINES_DIR, BRIDGE_DIR, BRIDGE_RUN, DIFFUSION_DIR,
                                                     EVALUATION_DIR, EVALUATION_META, EXPLANATION_META,
                                                     EXPLANATIONS_DIR, FEATURES_DIR, GRAPH_DIR, TOPICS_DIR,
                                                     Component3Store, SnapshotMissing, SnapshotRef)

CHANNEL_ID = re.compile(r"^(channel:)?([A-Za-z0-9_-]{2,64})$")
SNAPSHOT_ID = re.compile(r"^rs-\d{8}T\d{6}Z$")
EXPERIMENT_ID = re.compile(r"^abs-[0-9a-f]{12}$")
EVALUATION_ID = re.compile(r"^eval-[0-9a-f]{12}$")
FILTER_VALUE = re.compile(r"^[a-z0-9_]{1,64}$")
PSEUDONYM = "anon_"
INTERPRETATION = ("Audience Bridge Scores are potential audience bridge signals from a provisional formula; they "
                  "do not show audience migration, subscriber transfer, causality or growth.")
FORMULA = "audience_bridge_score = (diffusion_component + topic_component) x confidence_component"
EVAL_TABLES = {"ranking": "ranking_evaluation_results", "top_k": "top_k_evaluation_results",
               "temporal_stability": "temporal_stability_results", "sparse_robustness": "sparse_robustness_results",
               "performance": "computational_performance_results"}
EVAL_NOTE = ("Evaluation results as stored by STEP 21. Agreement and stability measure consistency between "
             "rankings, not correctness; relevance metrics exist only when explicit labels were supplied.")


class NotFound(LookupError):
    code = "not_found"


class ArtifactUnavailable(LookupError):
    code = "artifact_unavailable"


class InvalidParameter(ValueError):
    code = "invalid_parameter"


class Component3Service:
    def __init__(self, store: Component3Store | None = None):
        self.store = store or Component3Store()

    # --- shared selection ------------------------------------------------------------------------

    def _snapshot(self, snapshot_id: str | None) -> SnapshotRef:
        if snapshot_id is not None and not SNAPSHOT_ID.fullmatch(snapshot_id):
            raise InvalidParameter("snapshot_id must look like rs-YYYYMMDDTHHMMSSZ")
        try:
            return self.store.snapshot(snapshot_id)
        except SnapshotMissing as exc:
            raise NotFound(str(exc)) from None

    @staticmethod
    def channel_node(channel_id: str) -> str:
        m = CHANNEL_ID.fullmatch(channel_id or "")
        if not m:
            raise InvalidParameter("channel_id must be a YouTube channel id (letters, digits, '_' or '-')")
        return "channel:" + m.group(2)

    def _channels(self, snap: SnapshotRef) -> pd.DataFrame:
        df = self.store.query(self.store.snapshot_dataset(snap.snapshot_id, "channels"),
                              ["channel_id", "channel_name", "subscriber_count", "view_count", "video_count",
                               "description", "published_at"], order_by="channel_id")
        df["node_id"] = "channel:" + df["channel_id"].astype(str)
        return df

    def _require_channel(self, snap: SnapshotRef, node: str) -> pd.Series:
        ch = self._channels(snap)
        hit = ch[ch["node_id"] == node]
        if hit.empty:
            raise NotFound(f"channel {_public(node)} is not part of research snapshot {snap.snapshot_id}")
        return hit.iloc[0]

    def _node_features(self, snap: SnapshotRef) -> pd.DataFrame | None:
        path = self.store.features_dir(snap) / "graph_node_features.parquet"
        if not path.is_file():
            return None
        return self.store.query(path, where="node_type = 'channel'")

    # --- status ----------------------------------------------------------------------------------

    def research_status(self, snapshot_id: str | None) -> dict[str, Any]:
        snaps = self.store.list_snapshots()
        summary = [{"snapshot_id": s.snapshot_id, "created_at": s.created_at, "extracted_at": s.extracted_at,
                    "channels": s.row_counts.get("channels", 0), "videos": s.row_counts.get("videos", 0),
                    "comments": s.row_counts.get("comments", 0)} for s in snaps]
        if not snaps:
            if snapshot_id is not None:
                raise NotFound(f"research snapshot {snapshot_id} does not exist")
            return {"research_data": "missing", "snapshots": [], "latest_snapshot_id": None, "snapshot_id": None,
                    "artifacts": [], "note": "No research snapshot exists yet; run the collection pipeline first."}
        snap = self._snapshot(snapshot_id)
        sid, st = snap.snapshot_id, self.store
        graph_ok = (st.processed_dir(sid) / GRAPH_DIR / "graph_manifest.json").is_file()
        features_ok = (st.features_dir(snap) / "feature_manifest.json").is_file()
        artifacts = [
            _status("heterogeneous_graph", 1 if graph_ok else 0, None, "STEP 13"),
            _status("graph_features", st.count_dirs(sid, FEATURES_DIR, "asof-"),
                    st.features_dir(snap).name if features_ok else None,
                    "STEP 14; features as of the snapshot time" + ("" if features_ok else " are missing")),
            _status("ppr_diffusion", *self._latest_dir(sid, DIFFUSION_DIR, "ppr"), "STEP 17"),
            _status("topic_similarity", *self._latest_dir(sid, TOPICS_DIR, "top"), "STEP 18"),
            _status("baseline_louvain", *self._latest_dir(sid, BASELINES_DIR, "louvain"), "STEP 20"),
            _status("baseline_node2vec", *self._latest_dir(sid, BASELINES_DIR, "node2vec"), "STEP 20"),
            _status("audience_bridge_scores", *self._latest_run(sid, BRIDGE_DIR, "abs", BRIDGE_RUN),
                    "STEP 19 (provisional formula)"),
            _status("explanations", *self._latest_run(sid, EXPLANATIONS_DIR, "xpl", EXPLANATION_META), "STEP 22"),
            _status("evaluations", *self._latest_run(sid, EVALUATION_DIR, "eval", EVALUATION_META), "STEP 21"),
        ]
        return {"research_data": "available", "snapshots": summary, "latest_snapshot_id": snaps[-1].snapshot_id,
                "snapshot_id": sid, "artifacts": artifacts,
                "note": "Each artifact is reported separately; a healthy API does not imply that all artifacts exist."}

    def _latest_dir(self, sid: str, kind: str, prefix: str) -> tuple[int, str | None]:
        root = self.store.processed_dir(sid) / kind
        names = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name.startswith(prefix + "-")) \
            if root.is_dir() else []
        return len(names), (names[-1] if names else None)

    def _latest_run(self, sid: str, kind: str, prefix: str, meta: str) -> tuple[int, str | None]:
        runs = self.store.runs(sid, kind, prefix, meta)
        return len(runs), (runs[-1]["_dir"].name if runs else None)

    # --- channels ---------------------------------------------------------------------------------

    def list_channels(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self._snapshot(snapshot_id)
        ch = self._channels(snap)
        feats = self._node_features(snap)
        f = feats.set_index("node_id") if feats is not None else None
        items = []
        for r in ch.itertuples():
            row = f.loc[r.node_id] if f is not None and r.node_id in f.index else None
            items.append({"channel_id": r.channel_id, "channel_name": _v(r.channel_name),
                          "observed_subscriber_count": _v(r.subscriber_count),
                          "stored_video_count": _v(row["stored_video_count"]) if row is not None else None,
                          "unique_commenter_count": _v(row["unique_commenter_count"]) if row is not None else None,
                          "comment_count": _v(row["comment_count"]) if row is not None else None})
        return _clean({"snapshot_id": snap.snapshot_id, "features_status": "available" if f is not None else "missing",
                       "items": items, "total": len(items)})

    def channel_detail(self, channel_id: str, snapshot_id: str | None) -> dict[str, Any]:
        snap = self._snapshot(snapshot_id)
        node = self.channel_node(channel_id)
        meta = self._require_channel(snap, node)
        feats = self._node_features(snap)
        row = None
        if feats is not None:
            hit = feats[feats["node_id"] == node]
            row = hit.iloc[0] if len(hit) else None
        g = (lambda c: _v(row[c]) if row is not None else None)
        return _clean({
            "snapshot_id": snap.snapshot_id, "features_status": "available" if feats is not None else "missing",
            "as_of": snap.as_of if feats is not None else None, "channel_id": _public(node),
            "channel_name": _v(meta["channel_name"]), "description": _v(meta["description"]),
            "published_at": _v(meta["published_at"]), "observed_subscriber_count": g("observed_subscriber_count"),
            "observed_view_count": g("observed_view_count"), "observed_api_video_count": g("observed_api_video_count"),
            "stored_video_count": g("stored_video_count"), "unique_commenter_count": g("unique_commenter_count"),
            "comment_count": g("comment_count"), "reply_count": g("reply_count"),
            "avg_comments_per_video": g("avg_comments_per_video"), "active_commenter_count": g("active_commenter_count"),
            "first_interaction_at": g("first_interaction_at"), "last_interaction_at": g("last_interaction_at"),
            "active_days": g("active_days"), "collection_coverage": g("collection_coverage"),
        })

    def channel_pairs(self, channel_id: str, snapshot_id: str | None, limit: int, offset: int) -> dict[str, Any]:
        snap = self._snapshot(snapshot_id)
        node = self.channel_node(channel_id)
        self._require_channel(snap, node)
        path = self.store.features_dir(snap) / "channel_pair_features.parquet"
        if not path.is_file():
            raise ArtifactUnavailable(f"graph features (STEP 14) are not available for snapshot {snap.snapshot_id}")
        pf = self.store.query(path, ["channel_a", "channel_b", "shared_commenter_count", "jaccard_similarity",
                                     "directional_overlap_a_to_b", "directional_overlap_b_to_a"],
                              where="(channel_a = ? OR channel_b = ?) AND channel_a <> channel_b", params=[node, node])
        names = dict(zip(self._channels(snap)["node_id"], self._channels(snap)["channel_name"]))
        rows = []
        for r in pf.itertuples():
            fwd = r.channel_a == node
            other = r.channel_b if fwd else r.channel_a
            rows.append({"source_channel_id": _public(node), "destination_channel_id": _public(other),
                         "destination_channel_name": _v(names.get(other)), "shared_commenters": int(r.shared_commenter_count),
                         "jaccard_similarity": _v(r.jaccard_similarity),
                         "directional_overlap_source_to_destination": _v(r.directional_overlap_a_to_b if fwd
                                                                         else r.directional_overlap_b_to_a)})
        rows.sort(key=lambda x: (-x["shared_commenters"], x["destination_channel_id"]))
        return _clean({"snapshot_id": snap.snapshot_id, "source_channel_id": _public(node), "total": len(rows),
                       "limit": limit, "offset": offset, "items": rows[offset:offset + limit],
                       "note": "Pairs with at least one shared commenter (STEP 14); counts are aggregates. Pairs "
                               "not listed share no commenter."})

    # --- audience bridge ---------------------------------------------------------------------------

    def bridge_experiments(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self._snapshot(snapshot_id)
        sid = snap.snapshot_id
        expl = self.store.runs(sid, EXPLANATIONS_DIR, "xpl", EXPLANATION_META)
        evals = self.store.runs(sid, EVALUATION_DIR, "eval", EVALUATION_META)
        items = []
        for m in reversed(self.store.runs(sid, BRIDGE_DIR, "abs", BRIDGE_RUN)):
            eid, cfg, cov = m["experiment_id"], m.get("config", {}), m.get("coverage", {})
            items.append({
                "experiment_id": eid, "snapshot_id": sid, "created_at": _ts(m.get("created_at")),
                "method_version": m.get("method_version"), "provisional": bool(m.get("provisional")),
                "w_diffusion": float(cfg.get("w_diffusion")), "w_topic": float(cfg.get("w_topic")),
                "confidence_k": float(cfg.get("confidence_k")), "pairs": cov.get("pairs"),
                "scored_pairs": cov.get("scored"),
                "explanation_ids": [x["explanation_id"] for x in expl if x.get("experiment_id") == eid],
                "evaluation_ids": [x["evaluation_id"] for x in evals
                                   if x.get("methods", {}).get("audience_bridge_score", {}).get("experiment_id") == eid],
            })
        return _clean({"snapshot_id": sid, "items": items})

    def _experiment(self, snap: SnapshotRef, experiment_id: str | None) -> dict[str, Any]:
        if experiment_id is not None and not EXPERIMENT_ID.fullmatch(experiment_id):
            raise InvalidParameter("experiment_id must look like abs-<12 hex digits>")
        runs = self.store.runs(snap.snapshot_id, BRIDGE_DIR, "abs", BRIDGE_RUN)
        if not runs:
            raise ArtifactUnavailable(f"no Audience Bridge Score run (STEP 19) exists for snapshot {snap.snapshot_id}")
        if experiment_id is None:
            return runs[-1]
        for m in runs:
            if m["experiment_id"] == experiment_id:
                return m
        raise NotFound(f"experiment {experiment_id} does not exist for snapshot {snap.snapshot_id}")

    def bridge_ranking(self, source: str, snapshot_id: str | None, experiment_id: str | None, limit: int,
                       offset: int, include_unscored: bool) -> dict[str, Any]:
        snap = self._snapshot(snapshot_id)
        node = self.channel_node(source)
        meta = self._require_channel(snap, node)
        run = self._experiment(snap, experiment_id)
        path = run["_dir"] / "audience_bridge_scores.parquet"
        where = "source_channel_id = ? AND destination_channel_id <> source_channel_id"
        if not include_unscored:
            where += " AND audience_bridge_score IS NOT NULL"
        total = self.store.count(path, where, [node])
        df = self.store.query(path, ["destination_channel_id", "rank", "audience_bridge_score",
                                     "diffusion_contribution", "topic_contribution", "confidence", "base_score",
                                     "score_status"], where, [node],
                              order_by="rank ASC NULLS LAST, destination_channel_id", limit=limit, offset=offset)
        names = dict(zip(self._channels(snap)["node_id"], self._channels(snap)["channel_name"]))
        items = [{"rank": _v(r.rank), "destination_channel_id": _public(r.destination_channel_id),
                  "destination_channel_name": _v(names.get(r.destination_channel_id)),
                  "audience_bridge_score": _v(r.audience_bridge_score), "diffusion_component": _v(r.diffusion_contribution),
                  "topic_component": _v(r.topic_contribution), "confidence_component": _v(r.confidence),
                  "base_score": _v(r.base_score), "score_status": str(r.score_status)} for r in df.itertuples()]
        return _clean({"snapshot_id": snap.snapshot_id, "experiment_id": run["experiment_id"],
                       "source_channel_id": _public(node), "source_channel_name": _v(meta["channel_name"]),
                       "include_unscored": include_unscored, "total": total, "limit": limit, "offset": offset,
                       "items": items, "note": INTERPRETATION})

    def bridge_pair(self, source: str, destination: str, snapshot_id: str | None,
                    experiment_id: str | None) -> dict[str, Any]:
        snap = self._snapshot(snapshot_id)
        src, dst = self.channel_node(source), self.channel_node(destination)
        if src == dst:
            raise InvalidParameter("source and destination must be different channels (self pairs are not scored)")
        src_meta, dst_meta = self._require_channel(snap, src), self._require_channel(snap, dst)
        run = self._experiment(snap, experiment_id)
        eid, cfg = run["experiment_id"], run.get("config", {})
        s = self.store.query(run["_dir"] / "audience_bridge_scores.parquet",
                             where="source_channel_id = ? AND destination_channel_id = ?", params=[src, dst])
        if s.empty:
            raise NotFound(f"pair {_public(src)} -> {_public(dst)} is not in experiment {eid}")
        r = s.iloc[0]
        breakdown = {
            "raw_diffusion_score": _v(r["raw_diffusion_score"]), "normalized_diffusion": _v(r["normalized_diffusion"]),
            "raw_topic_similarity": _v(r["raw_topic_similarity"]),
            "normalized_topic_similarity": _v(r["normalized_topic_similarity"]),
            "w_diffusion": float(cfg["w_diffusion"]), "w_topic": float(cfg["w_topic"]),
            "diffusion_component": _v(r["diffusion_contribution"]), "topic_component": _v(r["topic_contribution"]),
            "base_score": _v(r["base_score"]), "shared_commenters": _v(r["shared_commenters"]),
            "evidence_confidence": _v(r["evidence_confidence"]),
            "topic_coverage_confidence": _v(r["topic_coverage_confidence"]), "confidence_component": _v(r["confidence"]),
            "formula": FORMULA,
        }
        out = {"snapshot_id": snap.snapshot_id, "experiment_id": eid, "source_channel_id": _public(src),
               "source_channel_name": _v(src_meta["channel_name"]), "destination_channel_id": _public(dst),
               "destination_channel_name": _v(dst_meta["channel_name"]), "rank": _v(r["rank"]),
               "audience_bridge_score": _v(r["audience_bridge_score"]), "score_status": str(r["score_status"]),
               "score_breakdown": breakdown, "note": INTERPRETATION, **self._explanation(snap, eid, src, dst)}
        return _clean(out)

    def _explanation(self, snap: SnapshotRef, eid: str, src: str, dst: str) -> dict[str, Any]:
        none = {"explanation_status": "unavailable", "explanation_id": None, "explanation_config_id": None,
                "explanation_outcome": None, "explanation_text": None, "evidence_summary": None,
                "explanation_reasons": [], "uncertainty_notes": [], "ranking_context": None}
        runs = [m for m in self.store.runs(snap.snapshot_id, EXPLANATIONS_DIR, "xpl", EXPLANATION_META)
                if m.get("experiment_id") == eid]
        if not runs:
            return {**none, "explanation_detail": f"no explanation artifact (STEP 22) exists for experiment {eid}; "
                                                  "run python -m research.component_3.explainability.explain"}
        run = runs[-1]
        d, params, where = run["_dir"], [src, dst], "source_channel_id = ? AND destination_channel_id = ?"
        try:
            x = self.store.query(d / "bridge_score_explanations.parquet", where=where, params=params)
            ev = self.store.query(d / "bridge_evidence_summaries.parquet", where=where, params=params)
            rs = self.store.query(d / "bridge_explanation_reasons.parquet",
                                  ["reason_code", "reason_text", "criterion", "value", "threshold"], where, params)
        except FileNotFoundError:
            return {**none, "explanation_detail": f"explanation run {run['explanation_id']} is incomplete on disk"}
        if x.empty:
            return {**none, "explanation_detail": "the explanation artifact has no row for this pair"}
        e, xr = (ev.iloc[0] if len(ev) else None), x.iloc[0]
        evidence = None if e is None else {k: _v(e[k]) for k in (
            "shared_commenters", "shared_commenter_state", "jaccard_similarity",
            "directional_overlap_source_to_destination", "shared_comments_on_source", "shared_comments_on_destination",
            "shared_videos_on_source", "shared_videos_on_destination", "source_video_coverage",
            "destination_video_coverage", "video_coverage_state", "shared_active_days", "shared_first_comment_at",
            "shared_last_comment_at", "temporal_state", "topic_similarity", "topic_state")}
        notes = [n for n in str(_v(xr["uncertainty_notes"]) or "").split("; ") if n]
        return {"explanation_status": "available", "explanation_detail": None,
                "explanation_id": run["explanation_id"], "explanation_config_id": _v(xr["explanation_config_id"]),
                "explanation_outcome": _v(xr["explanation_status"]), "explanation_text": _v(xr["explanation_text"]),
                "evidence_summary": evidence,
                "explanation_reasons": [{k: _v(v) for k, v in rr.items()} for rr in rs.to_dict("records")],
                "uncertainty_notes": notes,
                "ranking_context": {
                    "candidate_destinations": _v(xr["candidate_destinations"]),
                    "scored_destinations": _v(xr["scored_destinations"]), "score_percentile": _v(xr["score_percentile"]),
                    "next_higher_destination_id": _public(_v(xr["next_higher_destination"])),
                    "next_higher_score": _v(xr["next_higher_score"]),
                    "next_lower_destination_id": _public(_v(xr["next_lower_destination"])),
                    "next_lower_score": _v(xr["next_lower_score"])}}

    # --- evaluation -------------------------------------------------------------------------------

    def evaluation_runs(self, snapshot_id: str | None) -> dict[str, Any]:
        snap = self._snapshot(snapshot_id)
        items = []
        for m in reversed(self.store.runs(snap.snapshot_id, EVALUATION_DIR, "eval", EVALUATION_META)):
            methods = {k: str(v.get("status")) for k, v in m.get("methods", {}).items()}
            items.append({"evaluation_id": m["evaluation_id"], "snapshot_id": snap.snapshot_id,
                          "created_at": _ts(m.get("created_at")), "methods": methods,
                          "audience_bridge_experiment_id": m.get("methods", {}).get("audience_bridge_score", {})
                          .get("experiment_id"),
                          "labels_status": m.get("labels", {}).get("status", "supplied"),
                          "temporal_status": m.get("temporal", {}).get("status"),
                          "sparse_runs": len(m.get("sparse_robustness", {}).get("runs", []))})
        return _clean({"snapshot_id": snap.snapshot_id, "items": items})

    def _evaluation(self, evaluation_id: str, snapshot_id: str | None) -> tuple[SnapshotRef, dict[str, Any]]:
        if not EVALUATION_ID.fullmatch(evaluation_id or ""):
            raise InvalidParameter("evaluation_id must look like eval-<12 hex digits>")
        candidates = [self._snapshot(snapshot_id)] if snapshot_id else list(reversed(self.store.list_snapshots()))
        for snap in candidates:
            for m in self.store.runs(snap.snapshot_id, EVALUATION_DIR, "eval", EVALUATION_META):
                if m["evaluation_id"] == evaluation_id:
                    return snap, m
        if not any(self.store.runs(s.snapshot_id, EVALUATION_DIR, "eval", EVALUATION_META) for s in candidates):
            raise ArtifactUnavailable("no evaluation (STEP 21) has been run yet"
                                      + (f" for snapshot {snapshot_id}" if snapshot_id else ""))
        raise NotFound(f"evaluation {evaluation_id} does not exist")

    def evaluation_rows(self, evaluation_id: str, table: str, snapshot_id: str | None, method: str | None,
                        metric: str | None, limit: int, offset: int) -> dict[str, Any]:
        snap, meta = self._evaluation(evaluation_id, snapshot_id)
        if table not in EVAL_TABLES:
            raise InvalidParameter(f"table must be one of {sorted(EVAL_TABLES)}")
        path = meta["_dir"] / f"{EVAL_TABLES[table]}.parquet"
        if not path.is_file():
            raise ArtifactUnavailable(f"table {table} is missing from evaluation {evaluation_id}")
        cols = self.store.columns(path)
        where, params = [], []
        if method is not None:
            known = set(meta.get("methods", {})) | ({"input_preparation"} if table == "performance" else set())
            if not FILTER_VALUE.fullmatch(method) or method not in known:
                raise InvalidParameter(f"method must be one of {sorted(known)}")
            where.append("method = ?")
            params.append(method)
        if metric is not None:
            if "metric" not in cols:
                raise InvalidParameter(f"table {table} has no metric column; the metric filter is not supported")
            if not FILTER_VALUE.fullmatch(metric):
                raise InvalidParameter("metric must contain only lowercase letters, digits and '_'")
            where.append("metric = ?")
            params.append(metric)
        w = " AND ".join(where)
        total = self.store.count(path, w, params)
        df = self.store.query(path, where=w, params=params, limit=limit, offset=offset)
        items = [{k: _v(v) for k, v in rec.items()} for rec in df.to_dict("records")]
        for it in items:
            for k in ("source_channel_id", "destination_channel_id"):
                if k in it:
                    it[k] = _public(it[k])
        return _clean({"evaluation_id": evaluation_id, "snapshot_id": snap.snapshot_id, "table": table, "columns": cols,
                       "total": total, "limit": limit, "offset": offset, "items": items, "note": EVAL_NOTE})

    def evaluation_metadata(self, evaluation_id: str, snapshot_id: str | None) -> dict[str, Any]:
        snap, m = self._evaluation(evaluation_id, snapshot_id)
        config = {k: v for k, v in m.get("config", {}).items() if k != "labels_path"}
        labels = {k: v for k, v in m.get("labels", {}).items() if k != "path"}       # no local file paths
        perf = {k: v for k, v in m.get("performance", {}).items() if k in ("memory_note", "total_seconds", "cpu_count")}
        temporal = {k: v for k, v in m.get("temporal", {}).items() if k in ("status", "reason", "comparable_pairs",
                                                                            "min_depth_ratio")}
        sparse = {k: v for k, v in m.get("sparse_robustness", {}).items()
                  if k in ("status", "unit", "retain_fractions", "seeds", "source_comments")}
        if "runs" in m.get("sparse_robustness", {}):
            sparse["runs"] = len(m["sparse_robustness"]["runs"])
        methods = {k: {"status": v.get("status"), "role": v.get("role"), "experiment_id": v.get("experiment_id"),
                       "reason": v.get("reason")} for k, v in m.get("methods", {}).items()}
        return _clean({"evaluation_id": m["evaluation_id"], "snapshot_id": snap.snapshot_id,
                       "created_at": _ts(m.get("created_at")), "graph_fingerprint": m.get("graph_fingerprint"),
                       "as_of": _ts(m.get("as_of")), "config": _flat(config), "methods": methods,
                       "proposed_method": m.get("proposed_method", {}), "labels": _flat(labels),
                       "temporal": temporal, "sparse_robustness": sparse, "performance": perf,
                       "interpretation": m.get("interpretation"), "versions": m.get("versions", {})})


# --- helpers ---------------------------------------------------------------------------------

def _status(name: str, count: int, latest: str | None, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "available" if count else "missing", "count": count, "latest_id": latest,
            "detail": detail}


def _public(node: str | None) -> str | None:
    return None if node is None else str(node).removeprefix("channel:")


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc) if value else None


def _v(value: Any) -> Any:
    """Plain JSON-able Python value; NaN / NA / NaT -> None."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _flat(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (json.dumps(v, sort_keys=True) if isinstance(v, dict) else v) for k, v in d.items()}


def _clean(payload: Any) -> Any:
    """Last line of defence: refuse to return anything that looks like a commenter pseudonym."""
    def walk(x):
        if isinstance(x, str):
            if PSEUDONYM in x or "commenter:" in x:
                raise IdentifierLeak()
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    walk(payload)
    return payload


class IdentifierLeak(RuntimeError):
    """Raised (and answered as a generic 500) if a response would contain commenter identifiers."""
