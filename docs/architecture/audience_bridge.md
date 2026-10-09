# Component 3 Audience Bridge Score (STEP 19)

Code: [`research/component_3/model/audience_bridge.py`](../../research/component_3/model/audience_bridge.py) · Tests: [`tests/component_3/test_audience_bridge.py`](../../tests/component_3/test_audience_bridge.py)

```powershell
python -m research.component_3.model.audience_bridge                       # latest research snapshot
python -m research.component_3.model.audience_bridge --w-diffusion 0.6 --confidence-k 5
```

> **Provisional formula.** The overall structure (a weighted diffusion and topic base, multiplied by confidence) follows the research design. The normalization, the confidence components, `k` and the default weights are **documented, configurable choices made for this implementation**. They await supervisor confirmation, and changing them changes the `experiment_id`.

## Formula

For every ordered channel pair source → destination of one research snapshot (self pairs excluded):

```
normalized_diffusion        = per-source min-max of diffusion_score                    (STEP 17 PPR)
normalized_topic_similarity = per-source min-max of topic_similarity                   (STEP 18)
diffusion_contribution      = w_diffusion × normalized_diffusion
topic_contribution          = w_topic × normalized_topic_similarity
base_score                  = diffusion_contribution + topic_contribution              (w_diffusion + w_topic = 1)
evidence_confidence         = n / (n + k)        n = shared commenters of the pair     (STEP 14)
topic_coverage_confidence   = min(coverage_ratio(source), coverage_ratio(destination)) (STEP 18)
confidence                  = evidence_confidence × topic_coverage_confidence
audience_bridge_score       = base_score × confidence                                  range [0, 1]
```

| Choice | Default | Why |
|---|---|---|
| Normalization | per-source min-max | Rankings are per source, so values are compared among the same source's candidates; diffusion and topic land on the same [0, 1] scale. |
| Weights | `w_diffusion = w_topic = 0.5` | No prior evidence favours either component; equal weights are the neutral default. |
| Evidence confidence | `n / (n + k)`, `k = 3` | Grows with shared commenters and saturates toward 1; `k` is the count at which confidence is 0.5. |
| Topic coverage | min of both channels' usable-text share | A topic profile built from part of a channel's videos is less reliable. |
| Combining confidence | product | Each component is in [0, 1]; weak evidence on either side lowers confidence. |

**Consequences to be aware of:**
- A pair with **no shared commenters** gets confidence 0 and a score of 0, however similar the topics are. This is an observed zero, not missing data.
- When every candidate of a source has the same value, min-max is undefined. If that value is 0 (no signal), the result is 0.0; otherwise it's NULL.

## Missing components

A pair whose diffusion, topic similarity or topic coverage is unavailable gets **NULL scores, no rank**, and a `score_status` such as `incomplete: topic, topic coverage unavailable`. A missing score is never filled with 0. Typical cases:
- A channel with no stored videos can't be a diffusion source.
- A channel with no usable text has no topic profile.

## Inputs, provenance and output

- **Inputs:** one snapshot's STEP 13 graph and STEP 14 pair features, PPR diffusion and topic similarity, all computed on the **same graph and `as_of`**. Components from different snapshots, graphs or `as_of` are refused.
- **Location:** `data/processed/component_3/<snapshot_id>/bridge/<abs-…>/`, written once and checksum-verified on load.
  - `audience_bridge_scores.parquet` holds every component, contribution, confidence part, the score, `rank`, `score_status`, `snapshot_id` and `experiment_id`.
  - `bridge_run.json` records the config, formula, input experiment IDs, coverage and validation.
- **Validation:**
  - every value lies in [0, 1]
  - `score = (diffusion_contribution + topic_contribution) × confidence` within 1e-9
  - there are no self pairs or duplicates
  - incomplete pairs carry no score
- **Evaluation:** STEP 21 evaluates the score through `score_channels(ctx)`. STEP 22 explains it.

**Interpretation:** the score is a *potential audience bridge signal*. It doesn't show audience migration, subscriber transfer, causality or growth.
