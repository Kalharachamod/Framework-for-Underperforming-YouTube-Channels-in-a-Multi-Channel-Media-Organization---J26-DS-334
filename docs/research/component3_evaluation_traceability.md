# Component 3: Evaluation Traceability

*STEP 33, §10–§13.* This document audits the score's mathematics, the baselines and the evaluation design, and records what each evaluation result can and cannot support.

## 10. Audience Bridge Score: mathematical audit

Implemented formula (method 2.0, `model/audience_bridge.py`):

```
norm_x     = per-source min-max of x over that source's destinations
base_score = w_d·norm_diffusion + w_e·norm_embedding + w_t·norm_topic      (defaults 1/3 each)
ABS        = base_score × confidence                                         ∈ [0, 1)
rank       = per source, descending score, ties broken by destination ID
```

| Check | Result |
|---|---|
| Weights must be non-negative and sum to 1 | Enforced in `BridgeConfig`; invalid values raise |
| k > 0 | Enforced |
| Range | base ∈ [0, 1], confidence ∈ [0, 1), so ABS ∈ [0, 1). A score of 1 is impossible by design |
| Min-max, constant column | all 0 → 0.0; constant non-zero → NULL (no ordering information); NULL stays NULL |
| Missing component | score NULL with a `score_status` explaining which input is missing. It is **never** silently 0 |
| n = 0 shared commenters | confidence 0 → ABS 0 (observed zero) |
| Clipping | only `np.clip` of cosine to [-1, 1], a floating-point guard |
| Ties | stable sort by score then destination ID; `rank(method="first")` → deterministic |
| Additivity for explanations | the decomposition `w_i·norm_i·confidence` sums exactly to ABS |

Numeric edge-case check (run during this audit):

| Case | Result |
|---|---|
| zero diffusion, other components 1, n = 10, coverage 1 | base 0.333, confidence 0.769, ABS 0.256 |
| n = 0 | ABS 0 |
| very large n, all components 1 | ABS → 1.0 (limit, never reached) |
| n = 1 | confidence 0.25 |

**Verdict: no mathematical error.** The formula is unchanged.

**Interpretive limitation:** because normalisation is per source, ABS values are **relative within one source's ranking**. Comparing raw scores across different sources (as the Overview's "Top bridges" list does) is a convenience view, not a calibrated cross-source comparison.

## 11. Baselines

| Baseline | Definition | Fairness check |
|---|---|---|
| Louvain | Communities on a Jaccard channel projection of shared commenters; resolution 1.0, seed 42; score = 1 if same community, else 0 | Uses the same commenter evidence as ABS, so it is a fair "overlap only" baseline. It is binary, so rank agreement with it is coarse |
| node2vec | Type-agnostic random walks (p = q = 1), dim 64, weighted; channel cosine | Same graph, same dimension as metapath2vec, so it isolates the effect of type-aware metapaths |

Both are baselines only and are never presented as the proposed method.

## 12. Evaluation design and current results

| Evaluation | What it measures | Current result | Can claim | Cannot claim |
|---|---|---|---|---|
| Relevance metrics (P@k, NDCG …) | correctness against labels | **not run: no labels file** | — | accuracy, correctness |
| Agreement (Spearman, Kendall τ-b, top-k Jaccard) | similarity between rankings | Spearman vs Louvain 0.330, vs node2vec −0.286, vs PPR component 0.809 | ABS is related to, but not the same as, overlap communities; it differs from type-agnostic structure | that higher or lower agreement is "better" |
| Top-k | list overlap | reported per method | which destinations change between methods | superiority |
| Temporal stability | rank stability across comparable snapshots | 35 comparisons, `rs-20261008T191612Z` vs `rs-20261010T081534Z` | stability over about 1.5 days | long-term stability, growth, migration |
| Sparse robustness | rank stability under subsampling (CLI default: retain 0.75/0.5/0.25 × seeds 0/1/2; `eval-60ac93319497` used retain 0.5 × seeds 0/1, i.e. 2 runs) | 2 runs, 60 result rows; mean Spearman of the score 0.814 at 50 % retained | sensitivity to evidence loss | real-world robustness to different channel sets |
| Performance | runtime / memory | measured | feasibility on this sample | scalability to large graphs |

## 13. Temporal audit

- The snapshot pair `rs-20261008T093922Z` vs `rs-20261008T191612Z` is correctly rejected (depth ratio about 0.2 < 0.8).
- The 3-channel pilot `rs-20261010T072201Z` is skipped because its channel set differs.
- The comparable pair `rs-20261008T191612Z` → `rs-20261010T081534Z` has 18 channels and equal depth. 851 videos in both; comments grew from 10,256 to 10,823.
- One comparable pair over a short window is **weak temporal evidence**. More repeated collection with the same settings is needed before stability is claimed in general.
- HGT's temporal split is internal to one snapshot and is a different concept from cross-snapshot stability.
