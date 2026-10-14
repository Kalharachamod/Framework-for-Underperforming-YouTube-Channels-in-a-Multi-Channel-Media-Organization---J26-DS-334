"""Score sensitivity analysis: recompute the Audience Bridge Score from STORED component values under
controlled changes and report score and rank changes.

This is score sensitivity, NOT causal inference: removing a component shows how much the score
formula relies on it, not that the component causes audience behaviour. Production scores are
never modified; every scenario is stored as a separate configuration. Only the stored components
of the scored snapshot are used (no recomputation from data, no future information).
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
COMPONENTS = ("diffusion", "embedding", "topic")
NORMALIZED = {"diffusion": "normalized_diffusion", "embedding": "normalized_embedding_similarity",
              "topic": "normalized_topic_similarity"}

Weights = tuple[float, float, float]   # (w_diffusion, w_embedding, w_topic)


def scenarios(weights: Weights, alternative_weights: tuple[Weights, ...] = ()) -> list[dict]:
    """The original configuration plus controlled variations (alternative weights always sum to 1).
    Components with weight 0 in the original configuration have no 'removed' scenario."""
    w = dict(zip(COMPONENTS, (float(x) for x in weights)))
    keep = {c: True for c in COMPONENTS}
    out = [{"scenario": "original", "weights": w, "use": keep, "confidence": True}]
    for c in COMPONENTS:
        if w[c] > 0:
            out.append({"scenario": f"{c}_removed", "weights": w, "use": {**keep, c: False}, "confidence": True})
    out.append({"scenario": "confidence_removed", "weights": w, "use": keep, "confidence": False})
    for alt in alternative_weights:
        if len(alt) != 3 or any(not 0 <= x <= 1 for x in alt) or not np.isclose(sum(alt), 1.0):
            raise ValueError("alternative weights must be (w_diffusion, w_embedding, w_topic) in [0, 1] summing to 1")
        if np.allclose(alt, weights):
            continue
        name = "weights_" + "_".join(f"{c[0]}{x:g}" for c, x in zip(COMPONENTS, alt))
        out.append({"scenario": name, "weights": dict(zip(COMPONENTS, map(float, alt))), "use": keep,
                    "confidence": True})
    return out


def rescore(scores: pd.DataFrame, s: dict) -> pd.Series:
    """Recompute from the stored normalized components. A component that is needed (weight > 0 and in
    use) but not stored for a pair gives NULL; it is never treated as 0."""
    base = pd.Series(0.0, index=scores.index, dtype="Float64")
    for c in COMPONENTS:
        if s["use"][c] and s["weights"][c] > 0:
            base = base + s["weights"][c] * scores[NORMALIZED[c]].astype("Float64")
    out = base * (scores["confidence"].astype("Float64") if s["confidence"] else 1.0)
    return pd.Series(out, index=scores.index, dtype="Float64").where(scores["score_status"] == "ok")


def rank_within_source(scores: pd.DataFrame, values: pd.Series) -> pd.Series:
    """Rank 1 = highest per source; ties broken by destination id; NULL score -> no rank."""
    tmp = pd.DataFrame({"s": scores["source_channel_id"], "d": scores["destination_channel_id"],
                        "v": values.astype("Float64")}, index=scores.index)
    tmp = tmp.sort_values(["s", "v", "d"], ascending=[True, False, True], na_position="last", kind="stable")
    tmp["r"] = tmp.groupby("s")["v"].rank(method="first", ascending=False)
    return tmp["r"].reindex(scores.index).astype("Int64")


def analyse(scores: pd.DataFrame, weights: Weights, alternative_weights: tuple[Weights, ...] = ()) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=list(SENSITIVITY_COLUMNS)).astype(SENSITIVITY_COLUMNS)
    original, original_rank = scores["audience_bridge_score"].astype("Float64"), scores["rank"].astype("Int64")
    frames = []
    for s in scenarios(weights, alternative_weights):
        val = rescore(scores, s)
        rank = rank_within_source(scores, val)
        cfg = {"weights": s["weights"], "components_used": s["use"], "confidence": s["confidence"]}
        status = np.where(scores["score_status"] != "ok", "not_computed: incomplete score components",
                          np.where(val.isna(), "not_computed: a required component is not stored", "ok"))
        frames.append(pd.DataFrame({
            "scenario": s["scenario"], "scenario_config": json.dumps(cfg, sort_keys=True),
            "source_channel_id": scores["source_channel_id"], "destination_channel_id": scores["destination_channel_id"],
            "original_score": original, "original_rank": original_rank, "scenario_score": val, "scenario_rank": rank,
            "score_delta": val - original, "rank_change": original_rank - rank,   # > 0 = moved up
            "status": status,
        }))
    df = pd.concat(frames, ignore_index=True)
    return df[list(SENSITIVITY_COLUMNS)].astype(SENSITIVITY_COLUMNS)
