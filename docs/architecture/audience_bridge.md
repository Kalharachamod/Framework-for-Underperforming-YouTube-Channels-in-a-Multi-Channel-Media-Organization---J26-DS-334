# Component 3 Audience Bridge Score (STEP 19)

Code: [`research/component_3/model/audience_bridge.py`](../../research/component_3/model/audience_bridge.py) · Tests: [`tests/component_3/test_audience_bridge.py`](../../tests/component_3/test_audience_bridge.py)

```powershell
python -m research.component_3.model.audience_bridge                                   # latest snapshot, metapath2vec
python -m research.component_3.model.audience_bridge --embedding-source hgt            # HGT as the embedding source
python -m research.component_3.model.audience_bridge --weights 0.5 0 0.5 --embedding-source none   # ablation: no embeddings
```

> **Provisional formula.** The structure (a weighted diffusion, embedding and topic base, multiplied by confidence) follows the research design. The team decided to include the embedding part on 2026-10-10 ("option 1"). The normalization, the confidence components, `k` and the default weights are **documented, configurable choices** that await supervisor confirmation. Changing any of them changes the `experiment_id`.

## Formula

For every ordered channel pair source → destination of one research snapshot (self pairs excluded):

```
normalized_diffusion            = per-source min-max of diffusion_score                         (STEP 17 PPR)
normalized_embedding_similarity = per-source min-max of cos(e_source, e_destination)            (STEP 15 metapath2vec;
                                                                                                 STEP 16 HGT alternative)
normalized_topic_similarity     = per-source min-max of topic_similarity                        (STEP 18)
base_score                      = w_d × diffusion + w_e × embedding + w_t × topic (normalized)  (w_d + w_e + w_t = 1)
evidence_confidence             = n / (n + k)        n = shared commenters of the pair          (STEP 14)
topic_coverage_confidence       = min(coverage_ratio(source), coverage_ratio(destination))      (STEP 18)
confidence                      = evidence_confidence × topic_coverage_confidence
audience_bridge_score           = base_score × confidence                                       range [0, 1]
```

| Choice | Default | Why |
|---|---|---|
| Normalization | per-source min-max | Rankings are per source, so values are compared among the same source's candidates, and all three parts land on the same [0, 1] scale. |
| Weights | `w_d = w_e = w_t = 1/3` | No prior evidence favours any part; equal weights are the neutral default. STEP 22 sensitivity analysis shows how rankings change under other weights. |
| Embedding source | `metapath2vec` (primary); `hgt` selectable | Matches the proposal's primary and alternative methods, so the two can be compared on the same slot. |
| Evidence confidence | `n / (n + k)`, `k = 3` | Grows with shared commenters and saturates toward 1; `k` is the count at which confidence is 0.5. |
| Topic coverage | min of both channels' usable-text share | A topic profile built from part of a channel's videos is less reliable. |
| Combining confidence | product | Each component is in [0, 1]; weak evidence on either side lowers confidence. |

**Why embedding similarity is a separate part:** it measures *learned* graph proximity (from metapath2vec or HGT walks and message passing), while diffusion measures random-walk reachability from the source. Keeping the parts additive means each one's contribution is visible in explanations and can be removed in ablations:
- the full score
- without embeddings (`--weights 0.5 0 0.5 --embedding-source none`)
- with HGT instead of metapath2vec

**Embeddings used:**
- **Reuse first:** `run()` reuses the latest **saved** embeddings of the configured source trained on **exactly the same graph** (fingerprint match). Otherwise it trains them, seeded. The embedding experiment ID is recorded in `inputs`.
- **Mismatches are refused:** embeddings from another snapshot, graph or method.

**Consequences to be aware of:**
- A pair with **no shared commenters** gets confidence 0 and a score of 0, however similar its topics or embeddings are. This is an observed zero, not missing data.
- When every candidate of a source has the same value, min-max is undefined. If that value is 0 (no signal), the result is 0.0; otherwise it's NULL.
- **Topic edges don't enter PageRank by default** (see [ppr_diffusion.md](ppr_diffusion.md)), so topic content isn't counted twice.

## Missing components

A pair whose diffusion, embedding (when `w_e > 0`), topic similarity or topic coverage is unavailable gets **NULL scores, no rank**, and a `score_status` such as `incomplete: embedding, topic unavailable`. A missing score is never filled with 0. Typical cases:
- A channel with no stored videos can't be a diffusion source.
- A channel no walk visits has no embedding.
- A channel with no usable text has no topic profile.

## Inputs, provenance and output

- **Inputs:** one snapshot's STEP 13 graph and STEP 14 pair features, PPR diffusion, channel embeddings and topic similarity, all from the **same graph and `as_of`**.
- **Location:** `data/processed/component_3/<snapshot_id>/bridge/<abs-…>/`, written once and checksum-verified on load.
  - `audience_bridge_scores.parquet` holds every raw and normalized component, the three contributions, the confidence parts, the score, `rank`, `score_status`, `snapshot_id` and `experiment_id`.
  - `bridge_run.json` records the config (weights, `embedding_source`, `k`), the formula, the input experiment IDs (diffusion, topic, embeddings), coverage and validation.
- **Earlier runs:** runs saved before the embedding part (method 1.x) still load. They are read as `w_embedding = 0` with an embedding contribution of 0, and their scores are unchanged.
- **Validation:**
  - every value lies in [0, 1]
  - `score = (diffusion + embedding + topic contributions) × confidence` within 1e-9
  - there are no self pairs or duplicates
  - incomplete pairs carry no score
- **Evaluation:** STEP 21 evaluates the score (`audience_bridge_score`) and each embedding on its own (`metapath2vec_similarity`, `hgt_similarity`). STEP 22 explains it.

**Interpretation:** the score is a *potential audience bridge signal*. It doesn't show audience migration, subscriber transfer, causality or growth.
