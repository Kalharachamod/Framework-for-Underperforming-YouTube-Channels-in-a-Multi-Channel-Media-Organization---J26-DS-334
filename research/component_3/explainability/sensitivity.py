"""Score sensitivity analysis: recompute the Audience Bridge Score from STORED component values under
controlled changes and report score and rank changes.

This is score sensitivity, NOT causal inference: removing a component shows how much the
score formula relies on it, not that the component causes audience behaviour. Production scores
are never modified; every scenario is stored as a separate configuration. Only the stored
components of the scored snapshot are used (no recomputation from data, no future information).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

SENSITIVITY_COLUMNS = {
    "scenario": "string", "scenario_config": "string", "source_channel_id": "string",
    "destination_channel_id": "string", "original_score": "Float64", "original_rank": "Int64",
    "scenario_score": "Float64", "scenario_rank": "Int64", "score_delta": "Float64", "rank_change": "Int64",
    "status": "string",
}


def scenarios(w_diffusion: float, w_topic: float, alternative_weights: tuple[float, ...]) -> list[dict]:
    """The original configuration plus controlled variations (weights always sum to 1)."""
    out = [{"scenario": "original", "w_diffusion": w_diffusion, "w_topic": w_topic, "diffusion": True,
            "topic": True, "confidence": True},
           {"scenario": "diffusion_removed", "w_diffusion": w_diffusion, "w_topic": w_topic, "diffusion": False,
            "topic": True, "confidence": True},
           {"scenario": "topic_removed", "w_diffusion": w_diffusion, "w_topic": w_topic, "diffusion": True,
            "topic": False, "confidence": True},
           {"scenario": "confidence_removed", "w_diffusion": w_diffusion, "w_topic": w_topic, "diffusion": True,
            "topic": True, "confidence": False}]
    for wd in alternative_weights:
        if not 0 <= wd <= 1:
            raise ValueError("alternative diffusion weights must be in [0, 1]")
        if np.isclose(wd, w_diffusion):
            continue
        out.append({"scenario": f"weights_wd{wd:g}_wt{1 - wd:g}", "w_diffusion": float(wd), "w_topic": float(1 - wd),
                    "diffusion": True, "topic": True, "confidence": True})
    return out


def rescore(scores: pd.DataFrame, s: dict) -> pd.Series:
    nd = scores["normalized_diffusion"].astype("Float64") if s["diffusion"] else 0.0
    nt = scores["normalized_topic_similarity"].astype("Float64") if s["topic"] else 0.0
    base = s["w_diffusion"] * nd + s["w_topic"] * nt
    out = base * (scores["confidence"].astype("Float64") if s["confidence"] else 1.0)
    return pd.Series(out, index=scores.index, dtype="Float64").where(scores["score_status"] == "ok")


def rank_within_source(scores: pd.DataFrame, values: pd.Series) -> pd.Series:
    """Rank 1 = highest per source; ties broken by destination id; NULL score -> no rank."""
    tmp = pd.DataFrame({"s": scores["source_channel_id"], "d": scores["destination_channel_id"],
                        "v": values.astype("Float64")}, index=scores.index)
    tmp = tmp.sort_values(["s", "v", "d"], ascending=[True, False, True], na_position="last", kind="stable")
    tmp["r"] = tmp.groupby("s")["v"].rank(method="first", ascending=False)
    return tmp["r"].reindex(scores.index).astype("Int64")


def analyse(scores: pd.DataFrame, w_diffusion: float, w_topic: float,
            alternative_weights: tuple[float, ...] = (0.0, 0.25, 0.75, 1.0)) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=list(SENSITIVITY_COLUMNS)).astype(SENSITIVITY_COLUMNS)
    original, original_rank = scores["audience_bridge_score"].astype("Float64"), scores["rank"].astype("Int64")
    frames = []
    for s in scenarios(w_diffusion, w_topic, alternative_weights):
        val = rescore(scores, s)
        rank = rank_within_source(scores, val)
        cfg = {k: v for k, v in s.items() if k != "scenario"}
        frames.append(pd.DataFrame({
            "scenario": s["scenario"], "scenario_config": json.dumps(cfg, sort_keys=True),
            "source_channel_id": scores["source_channel_id"], "destination_channel_id": scores["destination_channel_id"],
            "original_score": original, "original_rank": original_rank, "scenario_score": val, "scenario_rank": rank,
            "score_delta": val - original, "rank_change": original_rank - rank,   # > 0 = moved up
            "status": np.where(scores["score_status"] == "ok", "ok", "not_computed: incomplete score components"),
        }))
    df = pd.concat(frames, ignore_index=True)
    return df[list(SENSITIVITY_COLUMNS)].astype(SENSITIVITY_COLUMNS)
