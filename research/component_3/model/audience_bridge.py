"""Component 3 STEP 19: confidence weighting and the Audience Bridge Score (proposed method).

    python -m research.component_3.model.audience_bridge                    # latest research snapshot
    python -m research.component_3.model.audience_bridge --w-diffusion 0.6 --confidence-k 5

For every ordered channel pair (source -> destination, no self pairs) of one research snapshot:

    normalized_diffusion = per-source min-max of the STEP 17 PPR diffusion_score
    normalized_topic     = per-source min-max of the STEP 18 topic_similarity
    base_score           = w_d * normalized_diffusion + w_t * normalized_topic        (w_d + w_t = 1)
    evidence_confidence  = n / (n + k)        n = shared commenters of the pair (STEP 14)
    topic_coverage_conf  = min(coverage_ratio(source), coverage_ratio(destination))   (STEP 18)
    confidence           = evidence_confidence * topic_coverage_conf
    audience_bridge_score = base_score * confidence

PROVISIONAL: the normalization, the confidence components, k and the weights are documented,
configurable defaults chosen for this implementation; they await supervisor confirmation.

A pair whose components cannot be computed gets NULL scores and a ``score_status`` saying why
(never a fabricated 0). The score is a potential audience bridge signal: it does not show
audience migration, subscriber transfer, causality or growth.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.component_3.model import baselines as bl
from research.component_3.model import ppr_diffusion as ppr
from research.component_3.model import topic_similarity as ts
from research.component_3.preprocessing import hetero_graph as hg
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

METHOD_VERSION = "1.0-provisional"
BRIDGE_DIR = "bridge"
RUN_FILE = "bridge_run.json"
SCORES_FILE = "audience_bridge_scores.parquet"
NORMALIZATIONS = ("per_source_minmax",)
FORMULA = {
    "normalized_diffusion": "per-source min-max of diffusion_score over the source's candidate destinations",
    "normalized_topic_similarity": "per-source min-max of topic_similarity over the source's candidate destinations",
    "diffusion_contribution": "w_diffusion * normalized_diffusion",
    "topic_contribution": "w_topic * normalized_topic_similarity",
    "base_score": "diffusion_contribution + topic_contribution",
    "evidence_confidence": "n / (n + confidence_k), n = shared commenters of the pair (STEP 14)",
    "topic_coverage_confidence": "min(coverage_ratio(source), coverage_ratio(destination)), coverage_ratio = "
                                 "usable-text videos / stored videos (STEP 18)",
    "confidence": "evidence_confidence * topic_coverage_confidence",
    "audience_bridge_score": "base_score * confidence",
    "min_max_constant": "if every candidate has the same value: 0.0 when that value is 0 (no signal), else NULL "
                        "(undefined)",
}
SCORE_COLUMNS = {
    "source_channel_id": "string", "destination_channel_id": "string",
    "raw_diffusion_score": "Float64", "normalized_diffusion": "Float64",
    "raw_topic_similarity": "Float64", "normalized_topic_similarity": "Float64",
    "diffusion_contribution": "Float64", "topic_contribution": "Float64", "base_score": "Float64",
    "shared_commenters": "Int64", "evidence_confidence": "Float64",
    "source_topic_coverage": "Float64", "destination_topic_coverage": "Float64",
    "topic_coverage_confidence": "Float64", "confidence": "Float64",
    "audience_bridge_score": "Float64", "rank": "Int64", "score_status": "string",
    "snapshot_id": "string", "experiment_id": "string",
}


class BridgeError(ValueError):
    pass


@dataclass(frozen=True)
class BridgeConfig:
    w_diffusion: float = 0.5
    w_topic: float = 0.5
    normalization: str = "per_source_minmax"
    confidence_k: float = 3.0          # shared commenters at which evidence_confidence = 0.5

    def __post_init__(self):
        for name in ("w_diffusion", "w_topic"):
            v = getattr(self, name)
            if not np.isfinite(v) or v < 0:
                raise BridgeError(f"{name} must be finite and non-negative")
        if not np.isclose(self.w_diffusion + self.w_topic, 1.0, atol=1e-9):
            raise BridgeError("w_diffusion + w_topic must equal 1")
        if self.normalization not in NORMALIZATIONS:
            raise BridgeError(f"normalization must be one of {NORMALIZATIONS}")
        if not np.isfinite(self.confidence_k) or self.confidence_k <= 0:
            raise BridgeError("confidence_k must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BridgeResult:
    snapshot_id: str
    experiment_id: str
    scores: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


# --- scoring ---------------------------------------------------------------------------------

def minmax(values: pd.Series) -> pd.Series:
    """Min-max over defined values; constant -> 0.0 if the constant is 0, else NULL. NULL stays NULL."""
    v = values.astype("Float64")
    d = v.dropna()
    if d.empty:
        return v
    lo, hi = float(d.min()), float(d.max())
    if hi == lo:
        return v.where(v.isna(), 0.0 if hi == 0 else pd.NA).astype("Float64")
    return ((v - lo) / (hi - lo)).astype("Float64")


def score(inp: bl.BaselineInput, diffusion: ppr.DiffusionRun, topic: ts.TopicResult,
          config: BridgeConfig = BridgeConfig()) -> BridgeResult:
    """Combine stored STEP 17 / 18 / 14 outputs of ONE snapshot into the Audience Bridge Score."""
    sid = inp.snapshot_id
    if diffusion.snapshot_id != sid or topic.snapshot_id != sid:
        raise BridgeError(f"component results come from different snapshots "
                          f"(features {sid}, diffusion {diffusion.snapshot_id}, topic {topic.snapshot_id})")
    if diffusion.metadata.get("graph_fingerprint") not in (None, inp.graph.fingerprint()):
        raise BridgeError("diffusion run was computed on a different graph")
    if topic.as_of != inp.as_of:
        raise BridgeError(f"topic as_of {topic.as_of} differs from the feature as_of {inp.as_of}")

    ch = inp.channels
    pairs = pd.DataFrame([(a, b) for a in ch for b in ch if a != b],
                         columns=["source_channel_id", "destination_channel_id"])
    d = diffusion.results[["source_channel_id", "destination_channel_id", "diffusion_score"]]
    t = topic.similarity[["source_channel_id", "destination_channel_id", "topic_similarity"]]
    df = pairs.merge(d, how="left", on=["source_channel_id", "destination_channel_id"]) \
              .merge(t, how="left", on=["source_channel_id", "destination_channel_id"])
    df = df.rename(columns={"diffusion_score": "raw_diffusion_score", "topic_similarity": "raw_topic_similarity"})

    pf = inp.pair_features
    shared = {**{(a, b): n for a, b, n in zip(pf["channel_a"], pf["channel_b"], pf["shared_commenter_count"])},
              **{(b, a): n for a, b, n in zip(pf["channel_a"], pf["channel_b"], pf["shared_commenter_count"])}}
    # pairs absent from channel_pair_features have no shared commenter: an observed zero, not missing
    df["shared_commenters"] = [int(shared.get((a, b), 0)) for a, b in zip(df.source_channel_id, df.destination_channel_id)]
    cov = dict(zip("channel:" + topic.profiles["channel_id"].astype(str),
                   topic.profiles["coverage_ratio"].where(topic.profiles["profile_available"])))
    df["source_topic_coverage"] = df["source_channel_id"].map(cov).astype("Float64")
    df["destination_topic_coverage"] = df["destination_channel_id"].map(cov).astype("Float64")

    g = df.groupby("source_channel_id", sort=True)
    df["normalized_diffusion"] = g["raw_diffusion_score"].transform(minmax).astype("Float64")
    df["normalized_topic_similarity"] = g["raw_topic_similarity"].transform(minmax).astype("Float64")
    df["diffusion_contribution"] = config.w_diffusion * df["normalized_diffusion"]
    df["topic_contribution"] = config.w_topic * df["normalized_topic_similarity"]
    df["base_score"] = df["diffusion_contribution"] + df["topic_contribution"]
    n = df["shared_commenters"].astype(float)
    df["evidence_confidence"] = (n / (n + config.confidence_k)).astype("Float64")
    df["topic_coverage_confidence"] = df[["source_topic_coverage", "destination_topic_coverage"]].min(axis=1, skipna=False)
    df["confidence"] = df["evidence_confidence"] * df["topic_coverage_confidence"]
    df["audience_bridge_score"] = df["base_score"] * df["confidence"]
    df["score_status"] = [_status(r) for r in df.itertuples()]

    df = df.sort_values(["source_channel_id", "audience_bridge_score", "destination_channel_id"],
                        ascending=[True, False, True], na_position="last", kind="stable").reset_index(drop=True)
    df["rank"] = df.groupby("source_channel_id")["audience_bridge_score"].rank(method="first", ascending=False)
    experiment_id = make_experiment_id(inp, diffusion, topic, config)
    df = df.assign(snapshot_id=sid, experiment_id=experiment_id)[list(SCORE_COLUMNS)].astype(SCORE_COLUMNS)

    result = BridgeResult(sid, experiment_id, df)
    result.metadata = {
        "method": "audience_bridge_score", "method_version": METHOD_VERSION, "role": "proposed method",
        "experiment_id": experiment_id, "snapshot_id": sid, "graph_fingerprint": inp.graph.fingerprint(),
        "as_of": inp.as_of.isoformat().replace("+00:00", "Z"), "channels": ch, "config": config.to_dict(),
        "formula": FORMULA, "provisional": "normalization, confidence components, confidence_k and weights are "
                                         "documented defaults awaiting supervisor confirmation",
        "inputs": {"diffusion_experiment_id": diffusion.experiment_id, "topic_experiment_id": topic.experiment_id,
                   "features": "STEP 14 channel_pair_features as of the snapshot"},
        "coverage": {"pairs": int(len(df)), "scored": int(df["audience_bridge_score"].notna().sum()),
                     "status_counts": {k: int(v) for k, v in df["score_status"].value_counts().sort_index().items()}},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "note": "Potential audience bridge signal only; not audience migration, subscriber transfer, causality "
                "or guaranteed growth.",
    }
    result.metadata["validation"] = validate(result)
    return result


def _status(r) -> str:
    missing = [name for name, v in (("diffusion", r.raw_diffusion_score), ("topic", r.raw_topic_similarity),
                                    ("topic coverage", r.topic_coverage_confidence)) if pd.isna(v)]
    if missing:
        return "incomplete: " + ", ".join(missing) + " unavailable"
    if pd.isna(r.normalized_diffusion) or pd.isna(r.normalized_topic_similarity):
        return "incomplete: normalization undefined (constant non-zero values for the source)"
    return "ok"


def make_experiment_id(inp, diffusion, topic, config: BridgeConfig) -> str:
    payload = json.dumps({"snapshot": inp.snapshot_id, "graph": inp.graph.fingerprint(), "config": config.to_dict(),
                          "diffusion": diffusion.experiment_id, "topic": topic.experiment_id,
                          "version": METHOD_VERSION}, sort_keys=True)
    return f"abs-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def run(snapshot_id: str, config: BridgeConfig = BridgeConfig(), *, encoder=None, ppr_config=None,
        topic_config=None, inp: bl.BaselineInput | None = None) -> BridgeResult:
    """Compute the components on the snapshot (same graph, same as_of) and score."""
    inp = inp or bl.load_input(snapshot_id)
    diffusion = ppr.run_diffusion(inp.graph, ppr_config or ppr.PPRConfig())
    topic = ts.run(inp.snapshot_id, topic_config or ts.TopicConfig(), as_of=inp.as_of, encoder=encoder)
    return score(inp, diffusion, topic, config)


def score_channels(ctx) -> tuple[pd.DataFrame, str]:
    """STEP 21 evaluation slot (see evaluation/methods.py)."""
    r = run(ctx.snapshot_id, encoder=ctx.encoder, ppr_config=ctx.ppr_config, topic_config=ctx.topic_config,
            inp=ctx.baseline_input)
    return r.scores, r.experiment_id


# --- validation ------------------------------------------------------------------------------

def validate(result: BridgeResult, atol: float = 1e-9) -> dict[str, Any]:
    s, errors = result.scores, []
    if (s["source_channel_id"] == s["destination_channel_id"]).any():
        errors.append("self pairs present")
    if s.duplicated(["source_channel_id", "destination_channel_id"]).any():
        errors.append("duplicate pairs")
    for col in ("normalized_diffusion", "normalized_topic_similarity", "evidence_confidence",
                "topic_coverage_confidence", "confidence", "base_score", "audience_bridge_score"):
        v = s[col].dropna().astype(float)
        if ((v < -atol) | (v > 1 + atol)).any():
            errors.append(f"{col} outside [0, 1]")
    ok = s[s["score_status"] == "ok"]
    rebuilt = (ok["diffusion_contribution"] + ok["topic_contribution"]) * ok["confidence"]
    if not np.allclose(rebuilt.astype(float), ok["audience_bridge_score"].astype(float), atol=atol):
        errors.append("audience_bridge_score does not equal base_score * confidence")
    if s.loc[s["score_status"] != "ok", "audience_bridge_score"].notna().any():
        errors.append("incomplete pairs carry a score")
    if errors:
        raise BridgeError("audience bridge validation failed: " + "; ".join(errors))
    return {"passed": True, "tolerance": atol}


# --- persistence ---------------------------------------------------------------------------

def bridge_dir(snapshot_id: str, experiment_id: str) -> Path:
    return hg.graph_dir(snapshot_id).parent / BRIDGE_DIR / experiment_id


def save(result: BridgeResult) -> Path:
    target = bridge_dir(result.snapshot_id, result.experiment_id)
    if (target / RUN_FILE).is_file():
        if load(target).scores.equals(result.scores):
            return target
        raise FileExistsError(f"bridge experiment {result.experiment_id} already exists with different scores")
    staging = target.with_name(f".{target.name}.staging")
    write_dataset(result.scores, staging / SCORES_FILE, overwrite=True)
    meta = {**result.metadata, "scores_sha256": _digest(result.scores)}
    (staging / RUN_FILE).write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


def load(directory: Path) -> BridgeResult:
    meta = json.loads((directory / RUN_FILE).read_text(encoding="utf-8"))
    scores = read_dataset(directory / SCORES_FILE).astype(SCORE_COLUMNS)
    if _digest(scores) != meta.get("scores_sha256"):
        raise BridgeError(f"{SCORES_FILE} changed after saving (checksum mismatch)")
    return BridgeResult(meta["snapshot_id"], meta["experiment_id"], scores, meta)


def _digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False, lineterminator="\n").encode()).hexdigest()


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="audience_bridge", description="Component 3 Audience Bridge Score (STEP 19).")
    ap.add_argument("--snapshot", help="research snapshot id (default: latest)")
    ap.add_argument("--w-diffusion", type=float, default=BridgeConfig.w_diffusion,
                    help="diffusion weight; topic weight = 1 - this")
    ap.add_argument("--confidence-k", type=float, default=BridgeConfig.confidence_k)
    ap.add_argument("--topic-backend", choices=["e5", "char_lsa"], default="e5")
    args = ap.parse_args(argv)
    try:
        config = BridgeConfig(w_diffusion=args.w_diffusion, w_topic=1 - args.w_diffusion,
                              confidence_k=args.confidence_k)
        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        r = run(sid, config, topic_config=ts.TopicConfig(backend=args.topic_backend))
        out = save(r)
    except (BridgeError, FileExistsError, snapshots.SnapshotNotFoundError, hg.GraphBuildError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    c = r.metadata["coverage"]
    print(f"Audience Bridge Score {r.experiment_id} on {sid} -> {out}")
    print(f"  pairs {c['pairs']} | scored {c['scored']} | statuses {c['status_counts']}")
    top = r.scores.dropna(subset=["audience_bridge_score"]).nlargest(5, "audience_bridge_score")
    for x in top.itertuples():
        print(f"  {x.source_channel_id} -> {x.destination_channel_id}: {x.audience_bridge_score:.4f} "
              f"(base {x.base_score:.3f} x confidence {x.confidence:.3f})")
    print("  (provisional formula; potential audience bridge signal, not migration or causality)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
