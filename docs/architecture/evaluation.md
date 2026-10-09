# Component 3 Research Evaluation Framework

Code: [`research/component_3/evaluation/`](../../research/component_3/evaluation/) · Tests: [`tests/component_3/test_evaluation.py`](../../tests/component_3/test_evaluation.py)

```powershell
python -m research.component_3.evaluation.evaluate                                  # latest research snapshot
python -m research.component_3.evaluation.evaluate --labels labels.csv --k 1 3 5
python -m research.component_3.evaluation.evaluate --topic-backend char_lsa --skip-sparse
```

> **The Audience Bridge Score (STEP 19) isn't available yet.** The framework has a ready slot for it. Until it exists, the proposed method is reported as `unavailable`, and its components (PPR diffusion and topic similarity) are evaluated with the baselines. No ABS formula is invented here.

## Methods compared

| Method | Role | Signal (higher = stronger) |
|---|---|---|
| `audience_bridge_score` | proposed method | slot: needs `research/component_3/model/audience_bridge.py` with `score_channels(ctx) -> (table with audience_bridge_score, experiment_id)` |
| `ppr_diffusion` | component of proposed method | STEP 17 `diffusion_score` (directional) |
| `topic_similarity` | component of proposed method | STEP 18 `topic_similarity` (symmetric) |
| `louvain` | baseline | STEP 20 same-community indicator (binary, many ties) |
| `node2vec` | baseline | STEP 20 raw cosine similarity |

Each adapter in `methods.py` turns its method's output into one **standard ranking table**:
- **Columns:** `method`, `role`, `signal_type`, `source_channel_id`, `destination_channel_id`, `score`, `rank`, `tied`, `snapshot_id`, `experiment_id`.
- **Excluded pairs:** self pairs and channels outside the snapshot are removed.
- **Undefined scores** are NULL and never 0. They get no rank.
- **Ranks** run per source, ties broken by destination ID. `tied` marks equal scores.

Every method sees the same snapshot, graph and features, computed as of the snapshot extraction time (`as_of`), so no future data is used.

## Analyses

| Analysis | When it runs | Output |
|---|---|---|
| **Ranking quality**: Precision@k, Recall@k, NDCG@k, MRR | **Only with an explicit label file** (`--labels`) | `ranking_evaluation_results` (`analysis = relevance`) |
| **Method agreement**: Spearman, Kendall tau-b, top-k Jaccard | Always, for every pair of available methods | `analysis = agreement` |
| **Top-k** | Always | `top_k_evaluation_results`, plus `analysis = top_k_summary` |
| **Temporal stability** | Comparable research snapshots exist | `temporal_stability_results` |
| **Sparse-data robustness** | Always, unless `--skip-sparse` | `sparse_robustness_results` |
| **Computational performance** | Always (measured) | `computational_performance_results` |

**Labels.** The file is CSV or Parquet with the columns `source_channel_id`, `destination_channel_id`, `relevance` (≥ 0) and `label_source`, which is required and records where each judgement came from.
- **Refused:** missing columns, an empty `label_source`, negative or non-numeric relevance, unknown channels, self pairs and duplicates.
- **Relevance:** a destination is relevant when its relevance is above 0. NDCG uses the graded value as gain.
- **Unlabelled destinations** of a labelled source count as not relevant.
- **Without labels**, relevance metrics are recorded as `not_computed`; no accuracy is claimed.
- **Circularity:** labels derived from shared-commenter counts would favour the Louvain projection, so avoid them.

**Agreement and stability.** Per source, both rankings are compared over the destinations where both have defined scores. The results are then macro-averaged over sources; `n_sources` says how many sources contributed.
- **Ties:** Spearman uses average ranks and Kendall uses tau-b, so Louvain's binary ties are handled.
- **Undefined:** fewer than 3 common items, or a constant ranking, gives NULL with a reason.

Agreement is consistency between methods, **not correctness**.

**Top-k.** For each source, the top-k list is recorded. `boundary_tie_at_k` marks the cases where top-k membership depends on the tie-break rule.
- `topk_distinct_destinations`: how many destinations appear across all sources' top-k lists. A low value means a few hubs dominate.
- `topk_boundary_tie_share`: the share of sources whose k-th and (k+1)-th scores tie.

**Temporal stability.** Two consecutive snapshots are compared only when all of these hold:
- they have the same channel set
- they have a similar collection depth: the ratio of median stored videos per channel is at least `min_depth_ratio` (0.8)
- their data differs
- the later one was extracted later

Otherwise the pair is recorded as `not_comparable` with the reason. If no pair is comparable, every method gets `insufficient_temporal_data`. The current real snapshots (`rs-20261008T093922Z` with about 10 videos per channel and `rs-20261008T191612Z` with about 50) are **not comparable observation windows**. Real temporal evaluation needs repeated daily collection with the same settings.

**Sparse-data robustness.** These are controlled simulations:
- **Subsampling:** comments, or whole commenters (`--sparse-unit commenters`), are subsampled at each retain fraction (default 0.75 / 0.5 / 0.25) with fixed seeds (default 0 / 1 / 2). Channels, videos and `as_of` stay unchanged.
- **Isolation:** each simulation writes its snapshot, graph and features into its **own temporary data directory**, which is deleted afterwards. The source snapshot is checksum-verified before and after, and production data is never written.
- **Results:** agreement with the full-data ranking (Spearman, Kendall, top-k Jaccard) and `score_coverage`, the share of full-data scored pairs still scored.
- **Topic similarity is excluded by default:** it depends only on video text, which comment subsampling doesn't change.

**Performance.** These are measured values; none are estimated:
- **Time:** wall-clock time per stage (`time.perf_counter`).
- **Memory:** `python_heap_peak_mib` is the tracemalloc peak. It covers Python objects and NumPy buffers but **not** native allocations that bypass Python, such as parts of gensim and PyTorch. Timings include tracemalloc overhead.
- **Also recorded:** input preparation time, graph size and the platform. Unavailable methods have NULL timings.

## Artifacts

`data/processed/component_3/<snapshot_id>/evaluation/<evaluation_id>/` (git-ignored) holds:
- `ranking_evaluation_results.parquet`
- `top_k_evaluation_results.parquet`
- `temporal_stability_results.parquet`
- `sparse_robustness_results.parquet`
- `computational_performance_results.parquet`
- `evaluation_run_metadata.json`

How the artifacts behave:
- **Row identity:** every row carries `evaluation_id` and `snapshot_id`.
- **The ID:** `evaluation_id` (`eval-…`) hashes the snapshot, graph fingerprint, configuration, label checksum, method experiment IDs and method configurations.
- **The metadata** records:
  - each method's status and role, plus the ABS note
  - label provenance
  - temporal comparability verdicts and the simulation runs
  - the memory note, versions and validation result
- **Write-once:** a rerun with identical deterministic results keeps the existing folder. Timings and simulated snapshot IDs are allowed to differ. Different results under the same ID are refused.
- **Tampering:** loading checks every table against its stored checksum.
- **Validation** checks the standard columns, that `value` is set exactly when `status = ok`, that correlations lie in [−1, 1] and the other metrics in [0, 1], that there are no self pairs in top-k and no negative timings.

## Interpretation

None of these results shows audience migration, audience transfer, causality, subscriber movement or growth. They show how the methods' structural and topical channel rankings relate to each other, to explicit labels when supplied, over time, and under sparser data.
