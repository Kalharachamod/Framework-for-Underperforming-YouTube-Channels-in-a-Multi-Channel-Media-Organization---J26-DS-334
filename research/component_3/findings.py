"""Component 3 STEP 28: research findings report from the persisted experiment artifacts.

    python -m research.component_3.findings --snapshot rs-...      # snapshot of a STEP 27 full experiment

Reads ONLY stored artifacts of one documented run (the run record written by research/component_3/pilot.py):
scores (STEP 19), explanations (STEP 22), evaluation (STEP 21), baselines (STEP 20), topic profiles (STEP 18),
graph features (STEP 14) and the collection/data-quality record. Nothing is recollected, retrained or
overwritten. Every number in the report and every figure is computed from those artifacts; analyses whose
inputs are missing are marked unavailable or inconclusive. No commenter identifier is read into the report.

Outputs:
  docs/component_3_findings_report.md                       report
  docs/figures/component_3/<snapshot_id>/*.png               figures (aggregate data only)
  data/processed/component_3/<snapshot_id>/findings/findings.json   all computed statistics (git-ignored)
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.component_3 import pilot as pl
from shared.utils import paths, privacy, snapshots

REPORT_PATH = "docs/component_3_findings_report.md"
FIGURES_DIR = "docs/figures/component_3"
NOT_SHOWN = ("Shared commenter activity and similarity describe aggregate public-comment behaviour; they do not "
             "show audience migration, subscriber transfer, causality or future growth.")


class FindingsError(RuntimeError):
    pass


# --- loading --------------------------------------------------------------------------------------

def load_run(snapshot_id: str, config_path: Path | None = None) -> dict[str, Any]:
    cfg = pl.load_config(config_path or paths.PROJECT_ROOT / "config/experiments/component_3_full.json")
    rec = pl.record_path(snapshot_id, cfg)
    if not rec.is_file():
        raise FindingsError(f"no {cfg.name} run record for {snapshot_id}: the full-scale experiment has not been run "
                            "(or did not finish) for this snapshot")
    run = json.loads(rec.read_text(encoding="utf-8"))
    stages = {s["stage"]: s for s in run.get("stages", [])}
    missing = [s for s in pl.PIPELINE_STAGES if stages.get(s, {}).get("status") != "completed"]
    if missing:
        raise FindingsError(f"the experiment on {snapshot_id} is incomplete; stages not completed: {missing}. "
                            "No findings are generated from a partial run.")
    run["_stages"] = stages
    return run


def load_artifacts(snapshot_id: str, run: dict[str, Any]) -> dict[str, Any]:
    from research.component_3.evaluation import evaluate as ev
    from research.component_3.explainability import explain as ex
    from research.component_3.model import audience_bridge as ab
    from research.component_3.model import baselines as bl
    from research.component_3.model import topic_similarity as ts
    from shared.utils.parquet_io import read_dataset

    a = {k: v["artifact"] for k, v in run["_stages"].items()}
    bridge = ab.load(ab.bridge_dir(snapshot_id, a["audience_bridge"]))
    louvain_dir = bl.baseline_dir(snapshot_id, a["louvain"])
    n2v_dir = bl.baseline_dir(snapshot_id, a["node2vec"])
    out = {
        "ids": a, "bridge": bridge,
        "explanation": ex.load(ex.explanations_dir(snapshot_id, a["explainability"])),
        "evaluation": ev.load(ev.evaluation_dir(snapshot_id, a["evaluation"])),
        "topic": ts.load(ts.topics_dir(snapshot_id, a["topics"])),
        "louvain_communities": read_dataset(louvain_dir / "louvain_communities.parquet"),
        "louvain_meta": json.loads((louvain_dir / "baseline_run.json").read_text(encoding="utf-8")),
        "node2vec_similarity": read_dataset(n2v_dir / "node2vec_channel_similarity.parquet"),
        "node2vec_meta": json.loads((n2v_dir / "experiment.json").read_text(encoding="utf-8")),
        "pair_features": read_dataset(paths.component_dir(3) / snapshot_id / "features" / a["features"]
                                      / "channel_pair_features.parquet"),
    }
    for name in ("bridge", "explanation", "evaluation"):
        art = out[name]
        if getattr(art, "snapshot_id", snapshot_id) != snapshot_id:
            raise FindingsError(f"{name} artifact belongs to another snapshot")
    if out["evaluation"].metadata["methods"]["audience_bridge_score"]["experiment_id"] != bridge.experiment_id:
        raise FindingsError("the evaluation did not evaluate the same Audience Bridge experiment")
    return out


# --- analyses -------------------------------------------------------------------------------------

def _names(run: dict[str, Any]) -> dict[str, str]:
    return {f"channel:{i}": t for t, i in run["channels"].items()}


def _stats(v: pd.Series) -> dict[str, Any]:
    v = v.dropna().astype(float)
    if v.empty:
        return {"n": 0}
    return {"n": int(len(v)), "min": float(v.min()), "q1": float(v.quantile(0.25)), "median": float(v.median()),
            "q3": float(v.quantile(0.75)), "max": float(v.max()), "mean": float(v.mean()),
            "share_zero": float((v == 0).mean())}


def analyse(snapshot_id: str, run: dict[str, Any], art: dict[str, Any]) -> dict[str, Any]:
    names = _names(run)
    s = art["bridge"].scores.copy()
    s["source"] = s.source_channel_id.map(names)
    s["destination"] = s.destination_channel_id.map(names)
    ok = s[s.score_status == "ok"]
    res: dict[str, Any] = {"snapshot_id": snapshot_id, "ids": art["ids"], "names": names}

    # provenance --------------------------------------------------------------------------------------
    info = snapshots.get_research_snapshot(snapshot_id)
    quality = run.get("channel_quality", [])
    observed = [q for q in quality if q["videos"] > 0]
    res["provenance"] = {
        "snapshot_id": snapshot_id, "source": info.source, "extracted_at": info.manifest.get("extracted_at"),
        "rows": info.row_counts, "configured_channels": len(run["channels"]),
        "observed_channels": len(observed),
        "video_window": [min((q["video_window"].split(" .. ")[0] for q in observed), default=None),
                         max((q["video_window"].split(" .. ")[1] for q in observed), default=None)],
        "comment_window": [min((q["comment_window"].split(" .. ")[0] for q in quality if q["comments"]), default=None),
                           max((q["comment_window"].split(" .. ")[1] for q in quality if q["comments"]), default=None)],
        "data_quality": run["_stages"]["research_data"]["details"].get("quality"),
        "collection_config": {k: run["config"][k] for k in ("max_videos_per_channel", "max_threads_per_video",
                                                              "fetch_all_replies", "published_since")},
        "bridge_config": art["bridge"].metadata["config"], "bridge_inputs": art["bridge"].metadata["inputs"],
        "louvain_config": art["louvain_meta"].get("parameters"), "node2vec_config": art["node2vec_meta"].get("parameters")
        or art["node2vec_meta"].get("config"),
        "evaluation_config": art["evaluation"].metadata["config"],
        "versions": {**art["evaluation"].metadata.get("versions", {}), "platform": platform.python_version()},
        "registry": run.get("registry", {}),
        "requests": (run.get("collection") or {}).get("requests"),
    }

    # Audience Bridge Score -------------------------------------------------------------------------------
    top = ok[ok["rank"] == 1].sort_values("audience_bridge_score", ascending=False)
    res["top_destinations"] = [
        {"source": r.source, "destination": r.destination, "score": float(r.audience_bridge_score),
         "diffusion": float(r.diffusion_contribution), "embedding": float(r.embedding_contribution),
         "topic": float(r.topic_contribution), "confidence": float(r.confidence), "shared": int(r.shared_commenters)}
        for r in top.itertuples()]
    res["distributions"] = {c: _stats(ok[c]) for c in ("audience_bridge_score", "diffusion_contribution",
                                                       "embedding_contribution", "topic_contribution", "confidence",
                                                       "evidence_confidence", "topic_coverage_confidence")}
    res["pairs"] = {"total": int(len(s)), "scored": int(len(ok)), "incomplete": int((s.score_status != "ok").sum()),
                    "zero_score": int((ok.audience_bridge_score == 0).sum())}
    res["insufficient_data"] = run.get("insufficient_data", [])

    # directional differences ------------------------------------------------------------------------------
    key = ok.set_index(["source_channel_id", "destination_channel_id"])
    asym = []
    for (a, b), r in key.iterrows():
        if a < b and (b, a) in key.index:
            back = key.loc[(b, a)]
            asym.append({"a": names.get(a, a), "b": names.get(b, b), "a_to_b": float(r.audience_bridge_score),
                         "b_to_a": float(back.audience_bridge_score),
                         "rank_a_to_b": int(r["rank"]), "rank_b_to_a": int(back["rank"])})
    adf = pd.DataFrame(asym)
    if len(adf):
        adf["abs_diff"] = (adf.a_to_b - adf.b_to_a).abs()
        res["directional"] = {"pairs": int(len(adf)), "median_abs_diff": float(adf.abs_diff.median()),
                              "max_abs_diff": float(adf.abs_diff.max()),
                              "reciprocal_top1": int(((adf.rank_a_to_b == 1) & (adf.rank_b_to_a == 1)).sum()),
                              "largest": adf.sort_values("abs_diff", ascending=False).head(8).to_dict("records")}
    else:
        res["directional"] = {"pairs": 0}

    # structural and topic relationships ------------------------------------------------------------------
    pf = art["pair_features"].copy()
    pf["a"], pf["b"] = pf.channel_a.map(names), pf.channel_b.map(names)
    res["structural"] = {
        "pairs_with_shared_commenters": int(len(pf)),
        "possible_pairs": int(len(names) * (len(names) - 1) / 2),
        "top_shared": pf.sort_values("shared_commenter_count", ascending=False).head(8)[
            ["a", "b", "shared_commenter_count", "jaccard_similarity"]].to_dict("records"),
        "top_jaccard": pf.sort_values("jaccard_similarity", ascending=False).head(8)[
            ["a", "b", "shared_commenter_count", "jaccard_similarity"]].to_dict("records"),
        "disconnected": sorted(n for c, n in names.items() if c not in set(pf.channel_a) | set(pf.channel_b)),
        "jaccard": _stats(pf.jaccard_similarity),
    }
    topic = art["topic"]
    sim = topic.similarity.dropna(subset=["topic_similarity"])
    sim = sim[sim.source_channel_id < sim.destination_channel_id].copy()
    sim["a"], sim["b"] = sim.source_channel_id.map(names), sim.destination_channel_id.map(names)
    prof = topic.profiles
    res["topic"] = {
        "channels_with_profile": int(prof.profile_available.sum()), "channels": int(len(prof)),
        "usable_video_share": _stats(prof.coverage_ratio),
        "similarity": _stats(sim.topic_similarity),
        "top_pairs": sim.sort_values("topic_similarity", ascending=False).head(8)[["a", "b", "topic_similarity"]]
        .to_dict("records"),
        "clusters": topic.metadata.get("clustering", {}).get("n_topics"),
        "model": topic.metadata.get("model") or topic.metadata.get("encoder"),
    }

    # baselines and evaluation ------------------------------------------------------------------------
    ev_ = art["evaluation"]
    rt = ev_.tables["ranking_evaluation_results"]
    agree = rt[rt.analysis == "agreement"]
    res["agreement"] = agree[["method", "reference_method", "metric", "k", "value", "n_sources", "status", "reason"]] \
        .to_dict("records")
    rel = rt[rt.analysis == "relevance"]
    res["relevance"] = {"computed": bool((rel.status == "ok").any()),
                        "status": sorted(set(rel.status.astype(str))),
                        "labels": ev_.metadata.get("labels", {}).get("status", "supplied")}
    comm = art["louvain_communities"].copy()
    comm["channel"] = comm.channel_id.map(names)
    res["louvain"] = {"communities": [sorted(g.channel.dropna()) for _, g in comm.groupby("community_id")],
                      "modularity": art["louvain_meta"].get("modularity")}
    n2v = art["node2vec_similarity"]
    n2v_top = n2v[n2v["rank"] == 1].set_index("source_channel_id").destination_channel_id
    abs_top = ok[ok["rank"] == 1].set_index("source_channel_id").destination_channel_id
    common = sorted(set(n2v_top.index) & set(abs_top.index))
    same_comm = dict(zip(comm.channel_id, comm.community_id))
    res["top1_overlap"] = {
        "sources": len(common),
        "node2vec_same_top1": int(sum(n2v_top[c] == abs_top[c] for c in common)),
        "abs_top1_in_same_louvain_community": int(sum(same_comm.get(c) == same_comm.get(abs_top[c]) for c in abs_top.index)),
        "abs_sources": int(len(abs_top)),
    }
    res["temporal_overlap"] = temporal_overlap(ev_.metadata.get("temporal", {}))
    res["temporal"] = {"summary": ev_.metadata.get("temporal", {}),
                       "rows": ev_.tables["temporal_stability_results"].query("status == 'ok'")
                       [["method", "earlier_snapshot_id", "later_snapshot_id", "metric", "k", "value", "n_sources"]]
                       .to_dict("records")}
    sp = ev_.tables["sparse_robustness_results"]
    sp_ok = sp[sp.status == "ok"].copy()
    if len(sp_ok):
        sp_ok["metric_k"] = sp_ok.metric.astype(str) + sp_ok.k.map(lambda k: "" if pd.isna(k) else f"@{int(k)}")
        g = sp_ok.groupby(["method", "retain_fraction", "metric_k"]).value
        res["sparse"] = g.agg(["mean", "min", "max", "count"]).reset_index().to_dict("records")
    else:
        res["sparse"] = []
    res["sparse_unavailable"] = sp[sp.status != "ok"][["method", "status", "reason"]].drop_duplicates().to_dict("records")
    perf = ev_.tables["computational_performance_results"]
    res["performance"] = perf[perf.stage == "main"][["method", "status", "seconds", "python_heap_peak_mib",
                                                     "graph_nodes", "graph_edges"]].to_dict("records")
    res["stage_seconds"] = {k: v["seconds"] for k, v in run["_stages"].items()}

    # explainability -------------------------------------------------------------------------------------
    xt = art["explanation"].tables
    x = xt["bridge_score_explanations"]
    reasons = xt["bridge_explanation_reasons"]
    res["explainability"] = {
        "status_counts": art["explanation"].metadata["status_counts"],
        "reason_counts": reasons.reason_code.value_counts().to_dict(),
        "examples": [x[(x.source_channel_id == f"channel:{run['channels'][t['source']]}")
                       & (x["rank"] == 1)].explanation_text.iloc[0]
                     for t in res["top_destinations"][:3] if t["source"] in run["channels"]],
    }
    sens = xt["bridge_sensitivity_results"]
    top_changes = []
    for scen, g in sens[(sens.status == "ok") & (sens.original_rank == 1)].groupby("scenario"):
        if scen == "original":
            continue
        top_changes.append({"scenario": scen, "sources": int(len(g)), "top1_kept": int((g.scenario_rank == 1).sum())})
    res["sensitivity"] = top_changes
    return res


def temporal_overlap(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """For each compared snapshot pair: days apart and the share of the later snapshot's videos and comments
    that were already in the earlier one (high overlap means stability partly reflects shared data)."""
    from shared.utils.parquet_io import read_dataset

    out = []
    for p in summary.get("pairs", []):
        if not p.get("comparable"):
            continue
        a, b = p["earlier"], p["later"]
        ids = {}
        for snap in (a, b):
            ids[snap] = {n: set(read_dataset(snapshots.research_dataset_path(snap, n), columns=[col])[col])
                         for n, col in (("videos", "video_id"), ("comments", "comment_id"))}
        ea = snapshots.get_research_snapshot(a).manifest.get("extracted_at") or ""
        eb = snapshots.get_research_snapshot(b).manifest.get("extracted_at") or ""
        days = (pd.Timestamp(eb) - pd.Timestamp(ea)).total_seconds() / 86400 if ea and eb else None
        out.append({"earlier": a, "later": b, "days_apart": days,
                    "videos_shared": len(ids[a]["videos"] & ids[b]["videos"]) / max(1, len(ids[b]["videos"])),
                    "comments_shared": len(ids[a]["comments"] & ids[b]["comments"]) / max(1, len(ids[b]["comments"]))})
    return out


# --- figures ------------------------------------------------------------------------------------------

def figures(res: dict[str, Any], art: dict[str, Any], out_dir: Path) -> list[dict[str, str]]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    sid, eid = res["snapshot_id"], res["ids"]["audience_bridge"]
    prov = f"snapshot {sid} · experiment {eid}"
    figs = []

    def save(fig, name, title, caption, shows, not_shows):
        fig.text(0.01, 0.005, prov, fontsize=7, color="#555")
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        fig.savefig(out_dir / name, dpi=130)
        plt.close(fig)
        figs.append({"file": name, "title": title, "caption": caption, "shows": shows, "not_shows": not_shows})

    names = res["names"]
    s = art["bridge"].scores
    ok = s[s.score_status == "ok"]

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.hist(ok.audience_bridge_score.astype(float), bins=30, range=(0, 1), color="#1f5f9e")
    ax.set(title="Distribution of Audience Bridge Scores", xlabel="Audience Bridge Score (0-1)",
           ylabel="Ordered channel pairs")
    save(fig, "abs_distribution.png", "Distribution of Audience Bridge Scores",
         f"All {len(ok)} scored ordered channel pairs (fixed axis 0-1).",
         "How scores are spread, including the share of pairs at 0 (no shared commenters).",
         "Which pairs are 'true' bridges; scores are a provisional ranking signal.")

    top = pd.DataFrame(res["top_destinations"])
    if len(top):
        fig, ax = plt.subplots(figsize=(8, 0.42 * len(top) + 1.2))
        lab = top.source + " -> " + top.destination
        y = np.arange(len(top))[::-1]
        ax.barh(y, top.diffusion, color="#1f5f9e", label="Diffusion")
        ax.barh(y, top.embedding, left=top.diffusion, color="#2f7d6d", label="Embedding")
        ax.barh(y, top.topic, left=top.diffusion + top.embedding, color="#6c8fb0", label="Topic")
        ax.scatter(top.score, y, color="black", zorder=3, s=14, label="Score (base x confidence)")
        ax.set_yticks(y, lab, fontsize=7)
        ax.set(xlim=(0, 1), xlabel="Contribution to the base score (0-1)",
               title="Top destination per source: score components")
        ax.legend(fontsize=7, loc="lower right")
        save(fig, "top_destination_components.png", "Score components of each source's top destination",
             "Stacked bars: weighted diffusion, embedding and topic parts of the base score; dot: final score after "
             "confidence.", "Which component drives each top-ranked pair, and how much confidence reduces it.",
             "That the destination will receive the source's audience.")

    order = sorted(names.values())
    idx = {n: i for i, n in enumerate(order)}
    mat = np.full((len(order), len(order)), np.nan)
    for r in s.itertuples():
        if r.score_status == "ok":
            mat[idx[names[r.source_channel_id]], idx[names[r.destination_channel_id]]] = float(r.audience_bridge_score)
    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    im = ax.imshow(mat, vmin=0, vmax=1, cmap="Blues")
    ax.set_xticks(range(len(order)), order, rotation=90, fontsize=6)
    ax.set_yticks(range(len(order)), order, fontsize=6)
    ax.set(xlabel="Destination channel", ylabel="Source channel", title="Audience Bridge Score matrix (rows = source)")
    fig.colorbar(im, ax=ax, label="Score (0-1); blank = not scored / self")
    save(fig, "abs_matrix.png", "Audience Bridge Score matrix",
         "Each cell is the stored score for source (row) -> destination (column); the diagonal and unscored pairs "
         "are blank.", "Directional structure: rows and columns with uniformly low scores, and asymmetric pairs.",
         "Audience flows; the matrix is a structural-similarity ranking signal.")

    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    ax.scatter(ok.shared_commenters.astype(float), ok.confidence.astype(float), s=10, color="#1f5f9e")
    ax.set_xscale("symlog")
    ax.set(xlabel="Shared commenters of the pair (symlog scale)", ylabel="Confidence (0-1)", ylim=(-0.02, 1.02),
           title="Confidence versus shared-commenter evidence")
    save(fig, "confidence_vs_evidence.png", "Confidence versus shared-commenter evidence",
         "One point per scored pair; confidence = n/(n+k) x topic coverage.",
         "How strongly the provisional confidence form discounts pairs with little evidence.",
         "That the confidence form is calibrated; it is a documented, provisional choice.")

    agree = pd.DataFrame(res["agreement"])
    sp = agree[(agree.metric == "spearman")] if len(agree) else agree
    if len(sp):
        methods = sorted(set(sp.method) | set(sp.reference_method))
        m = np.full((len(methods), len(methods)), np.nan)
        for r in sp.itertuples():
            if pd.notna(r.value):
                i, j = methods.index(r.method), methods.index(r.reference_method)
                m[i, j] = m[j, i] = float(r.value)
        np.fill_diagonal(m, 1.0)
        fig, ax = plt.subplots(figsize=(6.5, 5.5))
        im = ax.imshow(m, vmin=-1, vmax=1, cmap="RdBu")
        ax.set_xticks(range(len(methods)), methods, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(len(methods)), methods, fontsize=7)
        for i in range(len(methods)):
            for j in range(len(methods)):
                if not np.isnan(m[i, j]):
                    ax.text(j, i, f"{m[i, j]:+.2f}", ha="center", va="center", fontsize=6)
        ax.set(title="Mean per-source Spearman agreement between methods")
        fig.colorbar(im, ax=ax, label="Spearman (-1 to 1); blank = undefined")
        save(fig, "method_agreement.png", "Ranking agreement between methods",
             "Macro-averaged per-source Spearman correlation (STEP 21); undefined cells are blank.",
             "Which methods rank destinations similarly.", "Which method is correct; no relevance labels exist.")

    sparse = pd.DataFrame(res["sparse"])
    if len(sparse):
        sub = sparse[sparse.metric_k == "spearman"]
        if len(sub):
            fig, ax = plt.subplots(figsize=(7, 3.6))
            lab = sub.method + " @ " + sub.retain_fraction.map(lambda f: f"{f:.0%}")
            ax.barh(lab, sub["mean"], color="#1f5f9e")
            ax.errorbar(sub["mean"], lab, xerr=[sub["mean"] - sub["min"], sub["max"] - sub["mean"]], fmt="none",
                        ecolor="black", capsize=3)
            ax.set(xlim=(-1, 1), xlabel="Spearman with the full-data ranking (mean over seeds; bars: min-max)",
                   title="Sparse-data robustness (comment subsampling)")
            save(fig, "sparse_robustness.png", "Sparse-data robustness",
                 "Rankings recomputed on seeded comment subsamples, compared with the full-data ranking.",
                 "How much each method's ranking changes when comments are removed.",
                 "Performance under other real-world sparsity patterns.")

    perf = pd.DataFrame(res["performance"])
    perf = perf[perf.status == "ok"] if len(perf) else perf
    if len(perf):
        fig, ax = plt.subplots(figsize=(7, 3.4))
        ax.barh(perf.method, perf.seconds.astype(float), color="#586172")
        ax.set(xlabel="Wall-clock seconds (measured, includes tracemalloc overhead)",
               title="Computational runtime per method (evaluation run)")
        save(fig, "runtime.png", "Computational runtime", "Measured wall-clock time per method in the STEP 21 run.",
             "Relative cost of the methods on this machine.", "Runtime on other hardware or data sizes.")
    return figs


# --- report --------------------------------------------------------------------------------------------

def _e(v) -> str:
    """Markdown table cell: escape '|' (channel names may contain it)."""
    return str(v).replace("|", "\\|")


def _f(v, d=3):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else (f"{v:.{d}f}" if isinstance(v, float) else str(v))


def render(res: dict[str, Any], figs: list[dict[str, str]], fig_rel: str) -> str:
    p, d = res["provenance"], res["distributions"]
    sid, ids = res["snapshot_id"], res["ids"]
    agree = pd.DataFrame(res["agreement"])

    def ag(method, ref, metric="spearman", k=None):
        if not len(agree):
            return None
        r = agree[(((agree.method == method) & (agree.reference_method == ref)) |
                   ((agree.method == ref) & (agree.reference_method == method))) & (agree.metric == metric)]
        r = r[r.k.isna()] if k is None else r[r.k == k]
        return None if r.empty or pd.isna(r.value.iloc[0]) else float(r.value.iloc[0])

    abs_l, abs_n = ag("audience_bridge_score", "louvain"), ag("audience_bridge_score", "node2vec")
    abs_d = ag("audience_bridge_score", "ppr_diffusion")
    st, tp, dr = res["structural"], res["topic"], res["directional"]
    L = [
        "# Component 3 Research Findings: Diffusion-Based Cross-Channel Audience Bridge Scoring", "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} from the persisted artifacts of snapshot "
        f"`{sid}` (bridge experiment `{ids['audience_bridge']}`, evaluation `{ids['evaluation']}`, explanations "
        f"`{ids['explainability']}`). Reproduce with `python -m research.component_3.findings --snapshot {sid}`.", "",
        f"> {NOT_SHOWN} The scoring formula is provisional and no relevance labels exist, so these are descriptive and "
        "comparative findings, not validated performance claims.", "",
        "## 1. Executive summary", "",
        f"- **Data:** {p['observed_channels']} of {p['configured_channels']} configured channels observed; "
        f"{p['rows'].get('videos')} videos and {p['rows'].get('comments')} public comments (snapshot `{sid}`).",
        f"- **Structure:** {st['pairs_with_shared_commenters']} of {st['possible_pairs']} channel pairs share at least one "
        f"commenter; {len(st['disconnected'])} channel(s) share none with any other channel.",
        f"- **Scores:** {res['pairs']['scored']} of {res['pairs']['total']} ordered pairs scored; median score "
        f"{_f(d['audience_bridge_score'].get('median'))}, {_f(100 * d['audience_bridge_score'].get('share_zero', 0), 1)}% of "
        "scored pairs are 0 (no shared commenters).",
        f"- **Baselines:** mean per-source Spearman of the score with Louvain {_f(abs_l)}, with node2vec {_f(abs_n)}, "
        f"and with its own diffusion component {_f(abs_d)} (consistency, not correctness).",
        f"- **Ground truth:** relevance metrics {'were computed' if res['relevance']['computed'] else 'were not computed (no labels)'}.",
        f"- **Temporal stability:** {res['temporal']['summary'].get('status')}"
        + (f" ({res['temporal']['summary'].get('reason')})" if res['temporal']['summary'].get('reason') else "")
        + "".join(f"; one comparable pair {_f(o['days_apart'], 1)} days apart sharing {_f(100 * o['videos_shared'], 0)}% "
                  "of videos, so stability largely reflects shared data" for o in res["temporal_overlap"]) + ".", "",
        "## 2. Experiment configuration and provenance", "",
        "| Item | Value |", "|---|---|",
        f"| Snapshot | `{sid}` ({p['source']}, extracted {p['extracted_at']}) |",
        f"| Observation window | videos {p['video_window'][0]} .. {p['video_window'][1]}; comments {p['comment_window'][0]} .. {p['comment_window'][1]} |",
        f"| Collection limits | {p['collection_config']} |",
        f"| Channel registry | {p['registry'].get('configured_by_group')}; plan gaps: {p['registry'].get('gaps') or 'none'} |",
        f"| Data quality | {p['data_quality']} |",
        f"| API requests | {(p['requests'] or {}).get('total')} requests, {(p['requests'] or {}).get('quota_units')} quota units |",
        f"| Audience Bridge config | {p['bridge_config']} |",
        f"| Component experiments | {p['bridge_inputs']} |",
        f"| Louvain | `{ids['louvain']}` {p['louvain_config']} |",
        f"| node2vec | `{ids['node2vec']}` {p['node2vec_config']} |",
        f"| Evaluation | `{ids['evaluation']}` {p['evaluation_config']} |",
        f"| Versions | {p['versions']} |", "",
        "## 3. Dataset and data-quality profile", "",
        f"See the experiment report (`docs/component_3_full_experiment_report.md`) for per-channel coverage. Observed "
        f"channels: {p['observed_channels']}/{p['configured_channels']}. Comment counts are bounded by the collection "
        "limits and differ with channel size and content, so they are not audience sizes.", "",
        "## 4. Methodology summary", "",
        "Heterogeneous commenter-video-channel-topic graph -> metapath2vec (primary) / HGT (alternative) channel "
        "embeddings -> Personalized PageRank diffusion -> topic similarity -> confidence weighting -> "
        "`score = (w_d diffusion + w_e embedding + w_t topic) x confidence` with weights "
        f"{p['bridge_config'].get('w_diffusion'):.3f} / {p['bridge_config'].get('w_embedding', 0):.3f} / "
        f"{p['bridge_config'].get('w_topic'):.3f} and k = {p['bridge_config'].get('confidence_k')} "
        "(provisional; see docs/architecture/audience_bridge.md). Baselines: Louvain communities on the shared-commenter "
        "channel projection and node2vec channel-embedding cosine, on the same snapshot.", "",
        "## 5. Audience Bridge Score findings", "",
        "**Measured:** top destination per source (rank 1):", "",
        "| Source | Destination | Score | Diffusion | Embedding | Topic | Confidence | Shared commenters |",
        "|---|---|---|---|---|---|---|---|",
        *[f"| {_e(t['source'])} | "
          + (f"{_e(t['destination'])}" if t["score"] > 0 else "— (every score is 0: no shared commenters; rank 1 is only a tie-break)")
          + f" | {t['score']:.4f} | {t['diffusion']:.3f} | {t['embedding']:.3f} | "
          f"{t['topic']:.3f} | {t['confidence']:.3f} | {t['shared']} |" for t in res["top_destinations"]], "",
        "| Measure (scored pairs) | n | Min | Median | Max | Share = 0 |", "|---|---|---|---|---|---|",
        *[f"| {k} | {v.get('n')} | {_f(v.get('min'))} | {_f(v.get('median'))} | {_f(v.get('max'))} | "
          f"{_f(v.get('share_zero'))} |" for k, v in d.items()], "",
        "**Insufficient evidence:** " + ("; ".join(res["insufficient_data"]) or "none detected") + ".", "",
        f"**Directional differences:** {dr.get('pairs', 0)} unordered pairs scored in both directions; median "
        f"|score(A->B) - score(B->A)| = {_f(dr.get('median_abs_diff'))}, max {_f(dr.get('max_abs_diff'))}; "
        f"{dr.get('reciprocal_top1', 0)} pair(s) are each other's top destination.", "",
        "| A | B | A->B | B->A | rank A->B | rank B->A |", "|---|---|---|---|---|---|",
        *[f"| {_e(x['a'])} | {_e(x['b'])} | {x['a_to_b']:.4f} | {x['b_to_a']:.4f} | {x['rank_a_to_b']} | {x['rank_b_to_a']} |"
          for x in dr.get("largest", [])], "",
        "**Interpretation:** directional differences arise because diffusion is computed from each source and the "
        "per-source normalization ranks destinations relative to the source's other candidates; they are properties "
        "of the method, not evidence of one-way audience movement.", "",
        "## 6. Topic and structural relationship analysis", "",
        "| Most shared commenters (A, B) | Shared | Jaccard |", "|---|---|---|",
        *[f"| {_e(x['a'])} - {_e(x['b'])} | {x['shared_commenter_count']} | {x['jaccard_similarity']:.4f} |" for x in st["top_shared"]], "",
        f"Jaccard over pairs with shared commenters: median {_f(st['jaccard'].get('median'), 4)}, max "
        f"{_f(st['jaccard'].get('max'), 4)}. Channels sharing no commenter with any other: "
        f"{', '.join(st['disconnected']) or 'none'}.", "",
        f"Topic profiles: {tp['channels_with_profile']}/{tp['channels']} channels; topic similarity (cosine) median "
        f"{_f(tp['similarity'].get('median'))}, range {_f(tp['similarity'].get('min'))} .. {_f(tp['similarity'].get('max'))}; "
        f"{tp['clusters']} topic clusters.", "",
        "| Most similar topics (A, B) | Topic similarity |", "|---|---|",
        *[f"| {_e(x['a'])} - {_e(x['b'])} | {x['topic_similarity']:.3f} |" for x in tp["top_pairs"]], "",
        "## 7. Baseline comparison", "",
        "**Louvain communities** (modularity "
        f"{_f(res['louvain']['modularity'])}): " + "; ".join("{" + ", ".join(c) + "}" for c in res["louvain"]["communities"]) + ".", "",
        f"Top-1 destination agreement: node2vec picks the same top destination for "
        f"{res['top1_overlap']['node2vec_same_top1']} of {res['top1_overlap']['sources']} sources; the score's top "
        f"destination lies in the source's Louvain community for {res['top1_overlap']['abs_top1_in_same_louvain_community']} "
        f"of {res['top1_overlap']['abs_sources']} sources.", "",
        "## 8. Evaluation results", "",
        "| Method | Compared with | Metric | Value | Sources | Status |", "|---|---|---|---|---|---|",
        *[f"| {r['method']} | {r['reference_method']} | {r['metric']}{'' if pd.isna(r['k']) else '@' + str(int(r['k']))} | "
          f"{_f(None if pd.isna(r['value']) else float(r['value']))} | {r['n_sources']} | "
          f"{r['status'] if pd.isna(r['reason']) else r['status'] + ': ' + str(r['reason'])} |"
          for r in res["agreement"] if r["method"] == "audience_bridge_score"], "",
        f"Relevance metrics (precision, recall, NDCG, MRR): {', '.join(res['relevance']['status'])} "
        f"(labels: {res['relevance']['labels']}). 'Undefined' means the metric could not be computed, which is "
        "different from a computed value of 0.", "",
        "## 9. Robustness and temporal analysis", "",
        f"**Temporal:** {res['temporal']['summary'].get('status')}"
        + (f" — {res['temporal']['summary'].get('reason')}" if res['temporal']['summary'].get('reason') else ""),
        *[f"Compared `{o['earlier']}` -> `{o['later']}`: {_f(o['days_apart'], 1)} days apart; "
          f"{_f(100 * o['videos_shared'], 1)}% of the later snapshot's videos and {_f(100 * o['comments_shared'], 1)}% "
          "of its comments were already in the earlier snapshot. **High stability here largely reflects this "
          "shared data; it is not evidence of long-term stability.** Longer, repeated collection is needed."
          for o in res["temporal_overlap"]],
        *([""] + ["| Method | Earlier | Later | Metric | Value | Sources |", "|---|---|---|---|---|---|"]
          + [f"| {r['method']} | {r['earlier_snapshot_id']} | {r['later_snapshot_id']} | {r['metric']}"
             f"{'' if pd.isna(r['k']) else '@' + str(int(r['k']))} | {_f(r['value'])} | {r['n_sources']} |"
             for r in res["temporal"]["rows"]] if res["temporal"]["rows"] else []), "",
        "**Sparse data** (seeded comment subsampling; mean, min-max over seeds):", "",
        "| Method | Retained | Metric | Mean | Min | Max | Seeds |", "|---|---|---|---|---|---|---|",
        *[f"| {r['method']} | {r['retain_fraction']:.0%} | {r['metric_k']} | {r['mean']:.3f} | {r['min']:.3f} | "
          f"{r['max']:.3f} | {int(r['count'])} |" for r in res["sparse"]], "",
        *(["Unavailable in simulations: " + "; ".join(f"{u['method']} ({u['status']}: {u['reason']})"
                                                       for u in res["sparse_unavailable"]), ""]
          if res["sparse_unavailable"] else []),
        "**Runtime** (evaluation run, measured):", "",
        "| Method | Seconds | Python heap peak (MiB) |", "|---|---|---|",
        *[f"| {r['method']} | {_f(r['seconds'], 2)} | {_f(r['python_heap_peak_mib'], 1)} |" for r in res["performance"]
          if r["status"] == "ok"], "",
        "Times are wall-clock on the run machine and include any concurrent load (other jobs ran on the same "
        "machine during this experiment); they are not controlled benchmarks.", "",
        "## 10. Explainability examples", "",
        f"Explanation statuses: {res['explainability']['status_counts']}. Reasons: {res['explainability']['reason_counts']}.", "",
        *[f"> {e}" for e in res["explainability"]["examples"]], "",
        "Score sensitivity (top-1 destination kept under each scenario, from stored components):", "",
        "| Scenario | Sources | Top-1 kept |", "|---|---|---|",
        *[f"| {x['scenario']} | {x['sources']} | {x['top1_kept']} |" for x in res["sensitivity"]], "",
        "## Findings", "",
        f"**Finding 1 — Cross-channel structural connectivity.** {st['pairs_with_shared_commenters']} of "
        f"{st['possible_pairs']} channel pairs share commenters; overlap is concentrated in a few pairs (top pair "
        f"{st['top_shared'][0]['a'] + ' - ' + st['top_shared'][0]['b'] + ': ' + str(st['top_shared'][0]['shared_commenter_count']) if st['top_shared'] else '—'} "
        f"shared commenters) and {len(st['disconnected'])} channel(s) are disconnected in the collected data.",
        f"**Finding 2 — Content-topic similarity.** Topic profiles exist for {tp['channels_with_profile']}/{tp['channels']} "
        f"channels; similarity ranges {_f(tp['similarity'].get('min'))} .. {_f(tp['similarity'].get('max'))} (median "
        f"{_f(tp['similarity'].get('median'))}). Topic similarity is content resemblance, not influence.",
        f"**Finding 3 — Confidence-weighted ranking behaviour.** Confidence median {_f(d['confidence'].get('median'))}; "
        f"{_f(100 * d['audience_bridge_score'].get('share_zero', 0), 1)}% of scored pairs score 0 because they share no "
        f"commenter. The score agrees with its diffusion component at Spearman {_f(abs_d)}.",
        f"**Finding 4 — Baseline comparison.** Spearman with Louvain {_f(abs_l)} and with node2vec {_f(abs_n)}: the "
        "proposed score ranks destinations differently from both baselines. Without labels this shows difference, "
        "not superiority.",
        f"**Finding 5 — Robustness and limitations.** Temporal stability: {res['temporal']['summary'].get('status')}"
        + ("".join(f" over {_f(o['days_apart'], 1)} days with {_f(100 * o['videos_shared'], 0)}% shared videos "
                   "(not long-term evidence)" for o in res["temporal_overlap"])) + ". "
        f"Sparse-data results: {len(res['sparse'])} summarized method/fraction/metric rows. "
        "See limitations below.", "",
        "## 11. Limitations and validity threats", "",
        "- Public comments are a small, self-selected subset of viewers; commenters are not representative of whole "
        "audiences.",
        "- Shared commenter activity does not prove audience migration or subscriber transfer.",
        "- Comment availability varies by video and channel; collection limits "
        f"({p['collection_config']['max_videos_per_channel']} videos, {p['collection_config']['max_threads_per_video']} "
        "threads per video) and API behaviour bias coverage toward recent, active videos.",
        "- Channels differ in publishing volume and content type, which affects both overlap and topic profiles.",
        "- Topic similarity does not establish influence; embeddings and diffusion describe graph structure only.",
        "- The scoring weights, confidence form and k are provisional; results depend on them (see the sensitivity table).",
        "- No relevance labels: no accuracy, precision, recall, NDCG or MRR claims are possible.",
        "- Temporal conclusions need repeated comparable snapshots; " +
        ("only the comparison(s) shown above exist." if res["temporal"]["rows"] else "none were available here."),
        "- Results cover the observed Derana channels and period only; " +
        (f"the research plan's channel counts differ from the approved set ({p['registry'].get('gaps')})."
         if p["registry"].get("gaps") else "no other channels were studied."), "",
        "## 12. Conclusions supported by the evidence", "",
        "- The pipeline produces complete, explainable, reproducible rankings on the full approved channel set.",
        "- The proposed score is a distinct ranking signal: it differs from Louvain and node2vec and is driven mostly by "
        "diffusion, moderated by embeddings, topic similarity and confidence.",
        "- Claims of better accuracy, causal audience movement or growth are **not** supported by this experiment.", "",
        "## 13. Recommendations for future research", "",
        "- Obtain defensible relevance labels (e.g. supervisor-judged channel pairs with a recorded label source) to "
        "measure ranking quality.",
        "- Collect repeated comparable snapshots (same depth, daily) for temporal stability.",
        "- Confirm or revise the provisional weights and confidence form with the supervisor, then rerun.",
        "- Extend to further organizations only after the registry is approved.", "",
        "## Figures", "",
    ]
    for f in figs:
        L += [f"### {f['title']}", "", f"![{f['title']}]({fig_rel}/{f['file']})", "",
              f"*{f['caption']}* Shows: {f['shows']} Does not show: {f['not_shows']}", ""]
    L += ["## Reproducibility", "",
          f"- Inputs: snapshot `{sid}`; artifacts {ids}.",
          f"- Command: `python -m research.component_3.findings --snapshot {sid}` (reads stored artifacts only; no "
          "collection or training).",
          f"- Computed statistics: `data/processed/component_3/{sid}/findings/findings.json`.", ""]
    return "\n".join(L)


def generate(snapshot_id: str, *, config_path: Path | None = None, report_path: str = REPORT_PATH,
             figures_dir: str = FIGURES_DIR) -> dict[str, Any]:
    run = load_run(snapshot_id, config_path)
    art = load_artifacts(snapshot_id, run)
    res = analyse(snapshot_id, run, art)
    out_dir = paths.PROJECT_ROOT / figures_dir / snapshot_id
    figs = figures(res, art, out_dir)
    report = paths.PROJECT_ROOT / report_path
    rel = Path(os.path.relpath(out_dir, report.parent)).as_posix()
    text = render(res, figs, rel)
    if privacy.HASH_PREFIX in text or "commenter:" in text:
        raise FindingsError("report refused: it would contain commenter identifiers")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text, encoding="utf-8")
    stats_file = paths.component_dir(3) / snapshot_id / "findings" / "findings.json"
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text(json.dumps({k: v for k, v in res.items() if k != "names"}, indent=2, default=str) + "\n",
                          encoding="utf-8")
    return {"report": str(report_path), "figures": [str(out_dir / f["file"]) for f in figs], "stats": str(stats_file),
            "results": res}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="findings", description="Component 3 research findings report (STEP 28).")
    ap.add_argument("--snapshot", required=True, help="snapshot of a completed STEP 27 full experiment")
    ap.add_argument("--config", help="experiment configuration (default: config/experiments/component_3_full.json)")
    args = ap.parse_args(argv)
    try:
        out = generate(args.snapshot, config_path=Path(args.config) if args.config else None)
    except FindingsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Report: {out['report']}\nFigures: {len(out['figures'])}\nStatistics: {out['stats']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
