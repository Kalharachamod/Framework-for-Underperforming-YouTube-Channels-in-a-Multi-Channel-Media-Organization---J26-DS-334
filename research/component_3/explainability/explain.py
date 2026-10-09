"""Component 3 STEP 22: evidence-based explanations of the Audience Bridge Score.

    python -m research.component_3.explainability.explain                    # latest bridge run
    python -m research.component_3.explainability.explain --bridge-dir <path to bridge/abs-...>

For every scored source -> destination pair (no self pairs) of ONE STEP 19 experiment:
* score decomposition from the stored components and the experiment's own weights, rebuilt and
  checked against the stored score within ``reconstruction_tolerance``;
* aggregate, privacy-safe evidence (evidence.py) with zero / missing / insufficient coverage kept apart;
* structured reasons chosen by documented, configurable criteria (``ExplainConfig``);
* ranking context within the same source, snapshot and experiment;
* score sensitivity scenarios (sensitivity.py).

A score explanation says why the method produced a score; it is not empirical evaluation (STEP 21),
and nothing here shows audience migration, subscriber transfer, causality or growth.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.component_3.evaluation import evaluate as ev
from research.component_3.explainability import evidence as evd
from research.component_3.explainability import sensitivity as sens
from research.component_3.model import audience_bridge as ab
from research.component_3.model import baselines as bl
from research.component_3.preprocessing import hetero_graph as hg
from shared.utils import privacy, snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

EXPLAIN_VERSION = "1.0"
EXPLANATIONS_DIR = "explanations"
METADATA_FILE = "explanation_run_metadata.json"
NOTE = ("These explanations describe why the scoring method produced each score, using the available "
        "aggregate evidence. They are not empirical validation and do not show audience migration, subscriber "
        "transfer, causality, future growth or business outcomes.")

EXPLANATION_COLUMNS = {
    "source_channel_id": "string", "source_channel_name": "string", "destination_channel_id": "string",
    "destination_channel_name": "string", "rank": "Int64", "candidate_destinations": "Int64",
    "scored_destinations": "Int64", "score_percentile": "Float64", "audience_bridge_score": "Float64",
    "raw_diffusion_score": "Float64", "normalized_diffusion": "Float64", "raw_topic_similarity": "Float64",
    "normalized_topic_similarity": "Float64", "w_diffusion": "Float64", "w_topic": "Float64",
    "diffusion_contribution": "Float64", "topic_contribution": "Float64", "diffusion_share_of_base": "Float64",
    "base_score": "Float64", "shared_commenters": "Int64", "evidence_confidence": "Float64",
    "topic_coverage_confidence": "Float64", "confidence": "Float64", "reconstructed_score": "Float64",
    "reconstruction_error": "Float64", "next_higher_destination": "string", "next_higher_score": "Float64",
    "next_lower_destination": "string", "next_lower_score": "Float64", "top_competitors": "string",
    "reason_codes": "string", "explanation_text": "string", "uncertainty_notes": "string",
    "explanation_status": "string", "snapshot_id": "string", "experiment_id": "string",
    "explanation_config_id": "string", "created_at": "datetime64[us, UTC]",
}
REASON_COLUMNS = {"source_channel_id": "string", "destination_channel_id": "string", "reason_code": "string",
                  "reason_text": "string", "criterion": "string", "value": "Float64", "threshold": "Float64"}
VOLATILE_COLUMNS = ("created_at",)


class ExplainError(ValueError):
    pass


@dataclass(frozen=True)
class ExplainConfig:
    """Centralized reason criteria. None disables a label (the value is still reported)."""

    reconstruction_tolerance: float = 1e-9      # float64 rounding of a 3-step product
    strong_relative_fraction: float = 0.25      # top quartile of the source's candidates by that component
    limited_topic_coverage_below: float = 1.0   # any video without usable text -> profile is partial
    min_temporal_active_days: int = 2           # one day cannot show repeated activity
    consistent_temporal_active_days: int | None = None   # no defensible default: disabled
    broad_video_coverage: float | None = None             # no defensible default: disabled
    alternative_weights: tuple[float, ...] = (0.0, 0.25, 0.75, 1.0)
    competitors: int = 3

    def __post_init__(self):
        if not 0 < self.strong_relative_fraction <= 1:
            raise ExplainError("strong_relative_fraction must be in (0, 1]")
        if self.reconstruction_tolerance <= 0:
            raise ExplainError("reconstruction_tolerance must be positive")
        if self.broad_video_coverage is not None and not 0 < self.broad_video_coverage <= 1:
            raise ExplainError("broad_video_coverage must be in (0, 1]")
        if self.min_temporal_active_days < 1 or (self.consistent_temporal_active_days or 1) < 1:
            raise ExplainError("active-day criteria must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def config_id(self) -> str:
        payload = json.dumps({"config": self.to_dict(), "version": EXPLAIN_VERSION}, sort_keys=True)
        return f"xcfg-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


RATIONALE = {
    "reconstruction_tolerance": "absolute float64 tolerance for (w_d*n_d + w_t*n_t) * (n/(n+k)) * coverage",
    "strong_relative_fraction": "relative, per-source criterion: the component value is > 0 and ranks in the top "
                                "ceil(fraction * candidates) of the source's candidates (top quartile by convention)",
    "strong_shared_commenters": "n >= confidence_k of the scoring experiment, i.e. evidence_confidence >= 0.5 "
                                "(the half-saturation point of the scoring's own confidence definition)",
    "limited_topic_coverage_below": "topic profiles built from fewer than all stored videos are partial",
    "min_temporal_active_days": "activity on a single day cannot show repeated (temporal) support",
    "consistent_temporal_active_days": "disabled by default: no defensible absolute threshold; value and relative "
                                       "position are reported instead",
    "broad_video_coverage": "disabled by default: no defensible absolute threshold; value is reported instead",
}


@dataclass
class ExplanationResult:
    explanation_id: str
    snapshot_id: str
    experiment_id: str
    tables: dict[str, pd.DataFrame]
    metadata: dict[str, Any] = field(default_factory=dict)


# --- main entry -------------------------------------------------------------------------------

def explain(bridge: ab.BridgeResult, config: ExplainConfig = ExplainConfig(),
            inp: bl.BaselineInput | None = None) -> ExplanationResult:
    check_provenance(bridge)
    inp = inp or bl.load_input(bridge.snapshot_id)
    _check_inputs(bridge, inp)
    scores = bridge.scores[bridge.scores["source_channel_id"] != bridge.scores["destination_channel_id"]]
    scores = scores.reset_index(drop=True)
    w_d, w_t = float(bridge.metadata["config"]["w_diffusion"]), float(bridge.metadata["config"]["w_topic"])
    k = float(bridge.metadata["config"]["confidence_k"])
    config_id = config.config_id()
    created = pd.Timestamp(datetime.now(timezone.utc).replace(microsecond=0))

    evidence = evd.build_evidence(scores, bridge.snapshot_id, inp.as_of, inp.graph)
    names = _channel_names(bridge.snapshot_id)
    ctx = ranking_context(scores, config.competitors)
    rebuilt = reconstruct(scores, w_d, w_t, k)
    ev_by = evidence.set_index(["source_channel_id", "destination_channel_id"])
    component_ranks = _component_ranks(scores)
    eval_ctx = evaluation_context(bridge)

    rows, reason_rows = [], []
    for i, r in scores.iterrows():
        key = (r.source_channel_id, r.destination_channel_id)
        e = ev_by.loc[key]
        reasons = select_reasons(r, e, component_ranks.loc[i], k, config)
        status = ("incomplete" if r.score_status != "ok" else
                  "reconstruction_mismatch" if not (rebuilt.loc[i, "error"] <= config.reconstruction_tolerance)
                  else "complete")
        notes = uncertainty_notes(r, e, status, eval_ctx, k)
        base = r.base_score
        share = (r.diffusion_contribution / base) if status != "incomplete" and pd.notna(base) and base > 0 else pd.NA
        c = ctx.loc[i]
        rows.append({
            "source_channel_id": key[0], "source_channel_name": names.get(key[0]), "destination_channel_id": key[1],
            "destination_channel_name": names.get(key[1]), "rank": r["rank"], **c.to_dict(),
            "audience_bridge_score": r.audience_bridge_score, "raw_diffusion_score": r.raw_diffusion_score,
            "normalized_diffusion": r.normalized_diffusion, "raw_topic_similarity": r.raw_topic_similarity,
            "normalized_topic_similarity": r.normalized_topic_similarity, "w_diffusion": w_d, "w_topic": w_t,
            "diffusion_contribution": r.diffusion_contribution, "topic_contribution": r.topic_contribution,
            "diffusion_share_of_base": share, "base_score": base, "shared_commenters": r.shared_commenters,
            "evidence_confidence": r.evidence_confidence, "topic_coverage_confidence": r.topic_coverage_confidence,
            "confidence": r.confidence, "reconstructed_score": rebuilt.loc[i, "score"],
            "reconstruction_error": rebuilt.loc[i, "error"], "reason_codes": ";".join(x["reason_code"] for x in reasons),
            "explanation_text": explanation_text(r, c, reasons, names, status, share),
            "uncertainty_notes": "; ".join(notes), "explanation_status": status,
            "snapshot_id": bridge.snapshot_id, "experiment_id": bridge.experiment_id,
            "explanation_config_id": config_id, "created_at": created,
        })
        reason_rows += [{"source_channel_id": key[0], "destination_channel_id": key[1], **x} for x in reasons]

    explanations = _typed(pd.DataFrame(rows, columns=list(EXPLANATION_COLUMNS)), EXPLANATION_COLUMNS)
    reasons_df = _typed(pd.DataFrame(reason_rows, columns=list(REASON_COLUMNS)), REASON_COLUMNS)
    sensitivity = sens.analyse(scores, w_d, w_t, config.alternative_weights)
    prov = {"snapshot_id": bridge.snapshot_id, "experiment_id": bridge.experiment_id,
            "explanation_config_id": config_id}
    tables = {
        "bridge_score_explanations": explanations,
        "bridge_explanation_reasons": reasons_df.assign(**prov),
        "bridge_evidence_summaries": evidence.assign(experiment_id=bridge.experiment_id,
                                                     explanation_config_id=config_id),
        "bridge_sensitivity_results": sensitivity.assign(**prov),
    }
    explanation_id = "xpl-" + hashlib.sha256(json.dumps(
        {"experiment": bridge.experiment_id, "config": config_id}, sort_keys=True).encode()).hexdigest()[:12]
    metadata = {
        "explanation_id": explanation_id, "explain_version": EXPLAIN_VERSION, "snapshot_id": bridge.snapshot_id,
        "experiment_id": bridge.experiment_id, "explanation_config_id": config_id, "config": config.to_dict(),
        "criteria_rationale": RATIONALE, "scoring_config": bridge.metadata["config"],
        "scoring_inputs": bridge.metadata.get("inputs"), "graph_fingerprint": inp.graph.fingerprint(),
        "as_of": inp.as_of.isoformat().replace("+00:00", "Z"),
        "status_counts": {k_: int(v) for k_, v in explanations["explanation_status"].value_counts().sort_index().items()},
        "evaluation_context": eval_ctx,
        "sensitivity_note": "Score sensitivity analysis recomputed from stored components only; not causal inference.",
        "evidence_states": {"observed": "evidence exists", "zero": "both channels observed, value is 0",
                            "insufficient_coverage": "a channel has no stored videos or commenters",
                            "missing": "required input not available"},
        "privacy": "aggregate counts only; no raw or pseudonymized commenter identifiers in any output",
        "interpretation": NOTE, "created_at": created.isoformat().replace("+00:00", "Z"),
    }
    result = ExplanationResult(explanation_id, bridge.snapshot_id, bridge.experiment_id, tables, metadata)
    result.metadata["validation"] = validate(result, config)
    return result


# --- provenance -------------------------------------------------------------------------------

def check_provenance(bridge: ab.BridgeResult) -> None:
    s = bridge.scores
    sids, eids = set(s["snapshot_id"].dropna()), set(s["experiment_id"].dropna())
    if len(sids) > 1 or len(eids) > 1:
        raise ExplainError("score table mixes snapshots or experiments: incompatible scores cannot be ranked together")
    if s.empty:
        return
    if sids != {bridge.snapshot_id} or eids != {bridge.experiment_id}:
        raise ExplainError("score rows do not belong to the bridge result's snapshot / experiment")


def _check_inputs(bridge: ab.BridgeResult, inp: bl.BaselineInput) -> None:
    if inp.snapshot_id != bridge.snapshot_id:
        raise ExplainError(f"evidence snapshot {inp.snapshot_id} differs from the scored snapshot {bridge.snapshot_id}")
    if bridge.metadata.get("graph_fingerprint") not in (None, inp.graph.fingerprint()):
        raise ExplainError("evidence graph differs from the graph the scores were computed on")
    if bridge.metadata.get("as_of") not in (None, inp.as_of.isoformat().replace("+00:00", "Z")):
        raise ExplainError("evidence as_of differs from the scored as_of")


# --- decomposition ------------------------------------------------------------------------------

def reconstruct(scores: pd.DataFrame, w_d: float, w_t: float, k: float) -> pd.DataFrame:
    """Rebuild every score from its stored inputs with the experiment's weights (no stored intermediates)."""
    n = scores["shared_commenters"].astype("Float64")
    conf = (n / (n + k)) * scores["topic_coverage_confidence"].astype("Float64")
    base = w_d * scores["normalized_diffusion"].astype("Float64") + \
        w_t * scores["normalized_topic_similarity"].astype("Float64")
    rebuilt = (base * conf).astype("Float64")
    error = (rebuilt - scores["audience_bridge_score"].astype("Float64")).abs()
    return pd.DataFrame({"score": rebuilt, "error": error.astype("Float64")}, index=scores.index)


# --- ranking context ------------------------------------------------------------------------------

def ranking_context(scores: pd.DataFrame, competitors: int = 3) -> pd.DataFrame:
    cols = ["candidate_destinations", "scored_destinations", "score_percentile", "next_higher_destination",
            "next_higher_score", "next_lower_destination", "next_lower_score", "top_competitors"]
    out = pd.DataFrame(index=scores.index, columns=cols, dtype=object)
    for _, g in scores.groupby("source_channel_id", sort=True):
        ranked = g.dropna(subset=["rank"]).sort_values("rank")
        ids, vals = ranked["destination_channel_id"].tolist(), ranked["audience_bridge_score"].astype(float).tolist()
        for i, r in g.iterrows():
            out.at[i, "candidate_destinations"] = len(g)
            out.at[i, "scored_destinations"] = len(ranked)
            others = [{"destination_channel_id": d, "score": round(v, 12), "rank": j + 1}
                      for j, (d, v) in enumerate(zip(ids, vals)) if d != r.destination_channel_id][:competitors]
            out.at[i, "top_competitors"] = json.dumps(others)
            if pd.isna(r["rank"]):
                continue
            pos = int(r["rank"]) - 1
            below = sum(1 for v in vals if v < vals[pos])
            out.at[i, "score_percentile"] = below / (len(vals) - 1) if len(vals) > 1 else None
            if pos > 0:
                out.at[i, "next_higher_destination"], out.at[i, "next_higher_score"] = ids[pos - 1], vals[pos - 1]
            if pos + 1 < len(ids):
                out.at[i, "next_lower_destination"], out.at[i, "next_lower_score"] = ids[pos + 1], vals[pos + 1]
    return out


def _component_ranks(scores: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=scores.index)
    for col in ("normalized_diffusion", "normalized_topic_similarity"):
        out[col] = scores.groupby("source_channel_id")[col].rank(method="min", ascending=False)
        out[col + "_n"] = scores.groupby("source_channel_id")[col].transform("count")
    return out


# --- reasons and uncertainty -----------------------------------------------------------------

def select_reasons(r, e, ranks, k: float, cfg: ExplainConfig) -> list[dict]:
    out = []

    def add(code, text, criterion, value=None, threshold=None):
        out.append({"reason_code": code, "reason_text": text, "criterion": criterion,
                    "value": None if value is None or pd.isna(value) else float(value),
                    "threshold": None if threshold is None else float(threshold)})

    for col, code, label in (("normalized_diffusion", "strong_structural_connectivity", "structural connectivity "
                              "(PPR diffusion)"), ("normalized_topic_similarity", "high_topic_similarity",
                                                  "topic similarity")):
        n, rk, v = ranks[col + "_n"], ranks[col], r[col]
        if pd.notna(v) and v > 0 and n and pd.notna(rk):
            cut = math.ceil(cfg.strong_relative_fraction * n)
            if rk <= cut:
                add(code, f"Strong {label}: ranks {int(rk)} of {int(n)} candidates for this source.",
                    f"value > 0 and per-source rank <= ceil({cfg.strong_relative_fraction:g} * candidates)", rk, cut)

    shared = e["shared_commenters"]
    if e["shared_commenter_state"] == evd.OBSERVED:
        if shared >= k:
            add("strong_shared_commenter_evidence", f"{int(shared)} shared commenters (at least k = {k:g}).",
                "shared_commenters >= confidence_k", shared, k)
        else:
            add("low_confidence_sparse_evidence", f"Only {int(shared)} shared commenter(s), fewer than k = {k:g}; "
                "confidence is reduced.", "0 < shared_commenters < confidence_k", shared, k)
    elif e["shared_commenter_state"] == evd.ZERO:
        add("no_shared_commenter_evidence", "No commenter was observed on both channels, so confidence and the "
            "score are 0 by definition.", "shared_commenters == 0 with both channels observed", 0.0)

    if cfg.broad_video_coverage is not None and e["video_coverage_state"] == evd.OBSERVED:
        cov = min(e["source_video_coverage"], e["destination_video_coverage"])
        if pd.notna(cov) and cov >= cfg.broad_video_coverage:
            add("broad_video_coverage", f"Shared commenters appear on at least {cov:.0%} of each channel's stored "
                "videos.", "min(video coverage) >= broad_video_coverage", cov, cfg.broad_video_coverage)

    if e["temporal_state"] == evd.OBSERVED:
        days = e["shared_active_days"]
        if days < cfg.min_temporal_active_days:
            add("insufficient_temporal_evidence", f"Shared-commenter activity falls on {int(days)} day(s) only.",
                "shared_active_days < min_temporal_active_days", days, cfg.min_temporal_active_days)
        elif cfg.consistent_temporal_active_days is not None and days >= cfg.consistent_temporal_active_days:
            add("consistent_temporal_support", f"Shared-commenter activity spans {int(days)} distinct days.",
                "shared_active_days >= consistent_temporal_active_days", days, cfg.consistent_temporal_active_days)

    cov = r.topic_coverage_confidence
    if pd.notna(cov) and cov < cfg.limited_topic_coverage_below:
        add("limited_topic_coverage", f"Topic profiles use {cov:.0%} of the stored videos (the rest lack usable "
            "text).", "topic_coverage_confidence < limited_topic_coverage_below", cov,
            cfg.limited_topic_coverage_below)

    if r.score_status != "ok" or evd.INSUFFICIENT in (e["shared_commenter_state"], e["video_coverage_state"]):
        add("insufficient_evidence", "Insufficient evidence for a reliable interpretation"
            + (f" ({r.score_status})." if r.score_status != "ok" else " (a channel has no stored videos or commenters)."),
            "score incomplete or a channel lacks observation coverage")
    return out


def uncertainty_notes(r, e, status: str, eval_ctx: dict, k: float) -> list[str]:
    notes = []
    if status == "incomplete":
        notes.append(f"score not decomposed: {r.score_status}")
    if status == "reconstruction_mismatch":
        notes.append("stored score does not match its reconstruction; treat as unreliable")
    if e["shared_commenter_state"] == evd.INSUFFICIENT:
        notes.append("absence of shared commenters is not informative: a channel has no observed commenters")
    elif e["shared_commenter_state"] == evd.OBSERVED and e["shared_commenters"] < k:
        notes.append(f"few shared commenters ({int(e['shared_commenters'])}); small changes in data can move this score")
    if e["topic_state"] == evd.MISSING:
        notes.append("topic evidence missing (no topic profile for a channel)")
    if e["temporal_state"] == evd.OBSERVED and e["shared_active_days"] < 2:
        notes.append("temporal evidence comes from a single day")
    if not eval_ctx.get("abs_labelled_evaluation"):
        notes.append("no labelled evaluation of this experiment: the score is not empirically validated")
    return notes


def explanation_text(r, c, reasons: list[dict], names: dict, status: str, share) -> str:
    src = names.get(r.source_channel_id) or r.source_channel_id
    dst = names.get(r.destination_channel_id) or r.destination_channel_id
    if status == "incomplete":
        return f"{src} -> {dst}: no score ({r.score_status}). " + " ".join(x["reason_text"] for x in reasons)
    head = (f"{src} -> {dst}: rank {int(r['rank'])} of {int(c['scored_destinations'])} scored destinations; "
            f"Audience Bridge Score {r.audience_bridge_score:.4f} = (diffusion {r.diffusion_contribution:.4f} + "
            f"topic {r.topic_contribution:.4f}) x confidence {r.confidence:.4f}.")
    if pd.notna(share):
        head += f" Diffusion provides {share:.0%} of the base score."
    return " ".join([head, *(x["reason_text"] for x in reasons)])


def evaluation_context(bridge: ab.BridgeResult) -> dict[str, Any]:
    """STEP 21 evaluations on this snapshot that include this exact experiment (context only)."""
    root = ev.evaluation_dir(bridge.snapshot_id, "x").parent
    found = []
    for d in sorted(root.glob("eval-*")) if root.is_dir() else []:
        try:
            m = json.loads((d / ev.METADATA_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        a = m.get("methods", {}).get("audience_bridge_score", {})
        if a.get("experiment_id") == bridge.experiment_id:
            found.append({"evaluation_id": m["evaluation_id"], "labels": m.get("labels", {}).get("status", "supplied")})
    labelled = any(f["labels"] == "supplied" for f in found)
    return {"evaluations_of_this_experiment": found, "abs_labelled_evaluation": labelled,
            "note": ("no STEP 21 evaluation of this experiment found" if not found else
                     "STEP 21 evaluation exists" + ("" if labelled else " but without relevance labels (agreement "
                                                                       "and robustness only)"))
                    + "; a score explanation is not an empirical evaluation"}


# --- validation ----------------------------------------------------------------------------

def validate(result: ExplanationResult, config: ExplainConfig) -> dict[str, Any]:
    errors = []
    x = result.tables["bridge_score_explanations"]
    if (x["source_channel_id"] == x["destination_channel_id"]).any():
        errors.append("self-channel explanations present")
    if x.duplicated(["source_channel_id", "destination_channel_id"]).any():
        errors.append("duplicate explanations")
    done = x[x["explanation_status"] == "complete"]
    if (done["reconstruction_error"].astype(float) > config.reconstruction_tolerance).any():
        errors.append("complete explanation exceeds the reconstruction tolerance")
    for name, df in result.tables.items():
        if "snapshot_id" in df and len(df) and set(df["snapshot_id"].dropna()) != {result.snapshot_id}:
            errors.append(f"{name}: wrong snapshot provenance")
        if "experiment_id" in df and len(df) and set(df["experiment_id"].dropna()) != {result.experiment_id}:
            errors.append(f"{name}: wrong experiment provenance")
        leaks = _identifier_leaks(df)
        if leaks:
            errors.append(f"{name}: commenter identifiers in column(s) {leaks}")
    if errors:
        raise ExplainError("explanation validation failed: " + "; ".join(errors))
    return {"passed": True, "reconstruction_tolerance": config.reconstruction_tolerance,
            "complete": int(len(done)), "privacy_check": "no raw or pseudonymized commenter ids"}


def _identifier_leaks(df: pd.DataFrame) -> list[str]:
    """Columns containing pseudonyms (anon_...) or raw-looking channel ids that are not graph channel ids."""
    bad = []
    for c in df.columns:
        if not (df[c].dtype == object or str(df[c].dtype).startswith("string")):
            continue
        vals = df[c].dropna().astype(str)
        if vals.str.contains(privacy.HASH_PREFIX, regex=False).any() or vals.str.contains("commenter:", regex=False).any():
            bad.append(c)
    return bad


# --- persistence ---------------------------------------------------------------------------

def explanations_dir(snapshot_id: str, explanation_id: str) -> Path:
    return hg.graph_dir(snapshot_id).parent / EXPLANATIONS_DIR / explanation_id


def save(result: ExplanationResult) -> Path:
    """Write once; a rerun with identical content (apart from created_at) keeps the existing folder."""
    target = explanations_dir(result.snapshot_id, result.explanation_id)
    stable = {n: digest(df.drop(columns=list(VOLATILE_COLUMNS), errors="ignore")) for n, df in result.tables.items()}
    if (target / METADATA_FILE).is_file():
        if json.loads((target / METADATA_FILE).read_text(encoding="utf-8")).get("deterministic_sha256") == stable:
            return target
        raise FileExistsError(f"explanation run {result.explanation_id} already exists with different content")
    staging = target.with_name(f".{target.name}.staging")
    for name, df in result.tables.items():
        write_dataset(df, staging / f"{name}.parquet", overwrite=True)
    meta = {**result.metadata, "table_sha256": {n: digest(df) for n, df in result.tables.items()},
            "deterministic_sha256": stable}
    (staging / METADATA_FILE).write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


def load(directory: Path) -> ExplanationResult:
    meta = json.loads((directory / METADATA_FILE).read_text(encoding="utf-8"))
    tables = {n: read_dataset(directory / f"{n}.parquet") for n in meta["table_sha256"]}
    tables["bridge_score_explanations"] = _typed(tables["bridge_score_explanations"], EXPLANATION_COLUMNS)
    for n, df in tables.items():
        if digest(df.drop(columns=list(VOLATILE_COLUMNS), errors="ignore")) != meta["deterministic_sha256"][n]:
            raise ExplainError(f"{n}.parquet changed after saving (checksum mismatch)")
    return ExplanationResult(meta["explanation_id"], meta["snapshot_id"], meta["experiment_id"], tables, meta)


def digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False, lineterminator="\n").encode()).hexdigest()


# --- helpers ---------------------------------------------------------------------------------

def _typed(df: pd.DataFrame, cols: dict[str, str]) -> pd.DataFrame:
    df = df.astype(object).where(df.notna(), None)
    return df.astype(cols).reset_index(drop=True)


def _channel_names(snapshot_id: str) -> dict[str, str]:
    ch = read_dataset(snapshots.research_dataset_path(snapshot_id, "channels"), columns=["channel_id", "channel_name"])
    return dict(zip("channel:" + ch["channel_id"].astype(str), ch["channel_name"].astype(str)))


def latest_bridge_dir(snapshot_id: str) -> Path:
    root = ab.bridge_dir(snapshot_id, "x").parent
    runs = sorted((d for d in root.glob("abs-*") if (d / ab.RUN_FILE).is_file()),
                  key=lambda d: json.loads((d / ab.RUN_FILE).read_text(encoding="utf-8"))["created_at"]) \
        if root.is_dir() else []
    if not runs:
        raise ExplainError(f"no Audience Bridge Score run for {snapshot_id}; run "
                           "python -m research.component_3.model.audience_bridge first")
    return runs[-1]


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="explain", description="Component 3 Audience Bridge explanations (STEP 22).")
    ap.add_argument("--snapshot", help="research snapshot id (default: latest)")
    ap.add_argument("--bridge-dir", help="a saved bridge/abs-... folder (default: latest run of the snapshot)")
    ap.add_argument("--show", type=int, default=5, help="print the top N explanations")
    args = ap.parse_args(argv)
    try:
        if args.bridge_dir:
            bridge = ab.load(Path(args.bridge_dir))
        else:
            sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
            bridge = ab.load(latest_bridge_dir(sid))
        result = explain(bridge)
        out = save(result)
    except (ExplainError, ab.BridgeError, FileExistsError, snapshots.SnapshotNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    m = result.metadata
    print(f"Explanations {result.explanation_id} for {result.experiment_id} on {result.snapshot_id} -> {out}")
    print(f"  statuses {m['status_counts']} | {m['evaluation_context']['note']}")
    x = result.tables["bridge_score_explanations"]
    for t in x.dropna(subset=["audience_bridge_score"]).nlargest(args.show, "audience_bridge_score").itertuples():
        print(f"  - {t.explanation_text}")
    print(f"  ({NOTE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
