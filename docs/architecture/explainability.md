# Component 3 Explainability Framework (STEP 22)

Code: [`research/component_3/explainability/`](../../research/component_3/explainability/) · Tests: [`tests/component_3/test_explainability.py`](../../tests/component_3/test_explainability.py)

```powershell
python -m research.component_3.model.audience_bridge          # 1. score (STEP 19), saved under bridge/
python -m research.component_3.explainability.explain         # 2. explain the latest bridge run of the latest snapshot
python -m research.component_3.explainability.explain --bridge-dir <bridge/abs-... folder>
```

> **This framework explains the behaviour of the scoring method using the available evidence.** It doesn't prove audience migration, causality, subscriber transfer, future growth or business outcomes. A **score explanation** (why the method produced a score) is not an **empirical evaluation** (how the method performs, STEP 21).

## Objectives

For each scored source → destination pair, the framework explains:
- the score and its diffusion and topic contributions
- the confidence adjustment
- the supporting evidence
- the limitations of that evidence

Everything comes from stored results and features of the **same snapshot, `as_of` and experiment**.

## Score decomposition

The decomposition uses the STEP 19 experiment's own weights and `k`, read from `bridge_run.json`. No separate weights are introduced.

```
diffusion_contribution = w_d × normalized_diffusion
embedding_contribution = w_e × normalized_embedding_similarity   (0 when the experiment has w_e = 0)
topic_contribution     = w_t × normalized_topic_similarity
base_score             = diffusion_contribution + embedding_contribution + topic_contribution
audience_bridge_score  = base_score × confidence,  confidence = n/(n+k) × topic coverage
```

Each part's share of the base score is recorded (`diffusion_share_of_base`, `embedding_share_of_base`, `topic_share_of_base`), together with the experiment's `embedding_source`.

Every score is **rebuilt from its stored inputs**, and `reconstruction_error` is recorded. The `explanation_status` is one of:

| Status | Meaning |
|---|---|
| `complete` | the score was reconstructed within `reconstruction_tolerance` (1e-9, float64 rounding) |
| `reconstruction_mismatch` | the stored score doesn't match its inputs; flagged, never "fixed" |
| `incomplete` | the score has missing components; no decomposition is fabricated |

`diffusion_share_of_base` is the share of the base score that comes from diffusion. It's NULL when the base is 0.

## Evidence sources

`evidence.py` builds aggregate evidence for each ordered pair:

| Evidence | Source |
|---|---|
| Shared commenters, Jaccard, directional overlap | STEP 14 `channel_pair_features` |
| Stored videos, unique commenters, comments per channel | STEP 14 `graph_node_features` |
| Interaction counts, video coverage and temporal support of the shared commenters | DuckDB aggregate over the snapshot's comments up to `as_of`: comments and distinct videos on each channel, distinct active days, first and last comment, span |
| Topic similarity and topic coverage | the STEP 19 score row, which comes from STEP 18 |
| Channel-embedding similarity (raw cosine) | the STEP 19 score row (metapath2vec or HGT) |

Every evidence group has a **state**, and the states are never treated as interchangeable:

| State | Meaning |
|---|---|
| `observed` | the evidence exists (value > 0) |
| `zero` | both channels were observed with commenters, and the value is 0 |
| `insufficient_coverage` | a channel has no stored videos or commenters, so absence tells us nothing |
| `missing` | the required input isn't available (e.g. no topic profile, or no embedding for a channel) |
| `not_used` | the experiment has no embedding part (`w_e = 0`), so embedding evidence doesn't apply |

## Reason rules (`ExplainConfig`)

| Reason code | Rule | Default and rationale |
|---|---|---|
| `strong_structural_connectivity` | normalized diffusion > 0 and per-source rank ≤ ceil(fraction × candidates) | fraction 0.25: a relative, per-source top-quartile convention |
| `strong_embedding_similarity` | the same rule on normalized embedding similarity (only when `w_e > 0`) | as above |
| `high_topic_similarity` | the same rule on normalized topic similarity | as above |
| `strong_shared_commenter_evidence` | shared commenters ≥ the experiment's `k` | the half-saturation point of the scoring's own confidence |
| `low_confidence_sparse_evidence` | 0 < shared commenters < `k` | as above |
| `no_shared_commenter_evidence` | shared commenters = 0, both channels observed | the score is 0 by definition |
| `broad_video_coverage` | min(video coverage) ≥ threshold | **disabled** (no defensible threshold); the value is still reported |
| `consistent_temporal_support` | shared active days ≥ threshold | **disabled** (no defensible threshold); the value is still reported |
| `insufficient_temporal_evidence` | shared active days < `min_temporal_active_days` | 2: a single day can't show repeated activity |
| `limited_topic_coverage` | topic coverage < `limited_topic_coverage_below` | 1.0: any video without usable text makes the profile partial |
| `insufficient_evidence` | incomplete score, or a channel lacks observation coverage | none (a direct check) |

Every criterion, value and threshold is stored in `bridge_explanation_reasons`, and the rationales are recorded in the run metadata. Changing the criteria changes the `explanation_config_id`.

## Uncertainty reporting

`uncertainty_notes` lists, per pair, the caveats that apply:
- the score is incomplete or doesn't match its reconstruction
- the shared-commenter evidence is uninformative or comes from only a few commenters
- topic evidence is missing
- the temporal evidence comes from a single day
- there's no labelled STEP 21 evaluation of this experiment

The STEP 21 link is found by scanning saved evaluations for this `experiment_id`, and the result is recorded in `evaluation_context`.

## Ranking context

Each explanation includes:
- the rank
- candidate and scored destination counts
- the score percentile among the source's scored destinations
- the next higher and next lower destinations and their scores
- the top competing destinations, as a JSON list

Context is computed **within one source, snapshot and experiment only**. A score table that mixes snapshots or experiments is refused as incompatible, and so is evidence from a different snapshot, graph or `as_of`. Self pairs are excluded everywhere.

## Sensitivity analysis

`sensitivity.py` recomputes scores **only from the stored component values** under these scenarios:
- `original`
- `diffusion_removed`, `embedding_removed` and `topic_removed` (that contribution set to 0, the weights unchanged; only for parts with a weight above 0)
- `confidence_removed`
- alternative weights `(w_d, w_e, w_t)`: the corners `(1,0,0)`, `(0,1,0)`, `(0,0,1)` and edge midpoints `(½,½,0)`, `(½,0,½)`, `(0,½,½)` of the weight simplex

A scenario that needs a part the experiment didn't store (e.g. embedding weights for a run without embeddings) is reported as `not_computed`, never treated as 0.

Each scenario is stored separately, with its configuration, score, rank, `score_delta` and `rank_change` (> 0 means the destination moved up). Ties are broken by destination ID.

Production scores are never changed. This is **score sensitivity, not causal inference**: removing a component shows how much the formula relies on it, not that it causes audience behaviour.

## Privacy

- **Pseudonyms stay inside the database:** they're used only within the DuckDB aggregation, and outputs contain counts only.
- **No individual data:** there are no commenter histories, and nothing about identity, demographics or interests.
- **Validation guard:** validation refuses any table containing a pseudonym (`anon_…`) or a commenter node ID.
- **Channel names:** names of the public channels are included.

## Artifacts and provenance

`data/processed/component_3/<snapshot_id>/explanations/<xpl-…>/` holds:

| File | Content |
|---|---|
| `bridge_score_explanations.parquet` | one row per pair: decomposition, reconstruction, ranking context, `reason_codes`, `explanation_text`, `uncertainty_notes`, `explanation_status` |
| `bridge_explanation_reasons.parquet` | normalized reasons: code, text, criterion, value, threshold |
| `bridge_evidence_summaries.parquet` | the evidence values and their states |
| `bridge_sensitivity_results.parquet` | one row per scenario and pair |
| `explanation_run_metadata.json` | config, criteria rationale, scoring config and inputs, evaluation context, checksums |

How the artifacts behave:
- **Provenance:** every table carries `snapshot_id`, `experiment_id` and `explanation_config_id`.
- **Nested values** are stored in normalized form: reasons as their own table, competitors as JSON text.
- **Write-once:** a rerun differing only in `created_at` keeps the existing folder, and loading verifies the checksums.

## Known limitations

- **The STEP 19 formula is provisional,** and so are the explanations built on it.
- **Reason thresholds are conventions.** The relative top quartile and `k` follow from the scoring; the others are disabled until a defensible value exists.
- **Temporal support is descriptive:** active days and span within one snapshot, not trends across snapshots.
- **No empirical validation is implied.** Without relevance labels, STEP 21 reports agreement and robustness only.
