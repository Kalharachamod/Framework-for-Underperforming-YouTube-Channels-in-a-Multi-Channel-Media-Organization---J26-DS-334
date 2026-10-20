# Component 3: Final Results

**Source:** snapshot `rs-20261010T081534Z`, the latest complete full-scale snapshot. The artifacts are listed in [component3_experimental_setup.md](component3_experimental_setup.md).

**Provenance:** every number comes from the stored artifacts, via `docs/component_3_findings_report.md` (reproduce with `python -m research.component_3.findings --snapshot rs-20261010T081534Z`) or a direct read of the artifacts.

> These results describe aggregate public-comment behaviour and method consistency. They do not show audience migration, subscriber transfer, causality or growth, and without relevance labels they are not accuracy results.

## 8.1 Dataset Summary

| Measure | Value |
|---|---|
| Channels | 18 of 18 observed |
| Videos | 851 |
| Comments | 10,823 (8,947 top-level, 1,876 replies) |
| Unique commenters | 7,336; 175 on 2 or more channels |
| Videos with zero public comments / comments disabled | 344 / 51 |
| Channels sharing no commenter with any other | 5 (Ada Derana Tamil, Pulse.lk, Derana Shorts, Ada Derana World News, Ada Derana News Channel \| English) |

## 8.2 Graph Statistics

| Measure | Value |
|---|---|
| Nodes | 8,215: channel 18, video 851, commenter 7,336, topic 10 |
| Edges | 18,271: comments 9,044, belongs_to 851, participates_in 7,525, has_topic 851 |
| Channel pairs sharing commenters | 41 of 153 unordered pairs; maximum 36 shared (Derana Little Star – Dream Star); median 0 |
| Jaccard over overlapping pairs | median 0.0018, maximum 0.0195 |

## 8.3 Representation Learning Results

| Model | Result |
|---|---|
| metapath2vec `m2v-996c59079f77` | 8,215 / 8,215 nodes embedded; all 5 metapaths used; channel–channel cosine 0.198 to 0.564 (median 0.411) |
| HGT `hgt-c132bac52fc0` | temporal split, 41 validation edges; final epoch: training loss 0.456, validation loss 2.771, validation ROC-AUC 0.859, validation AP 0.423 |
| HGT channel vectors | channel–channel cosine 0.901 to 1.000 (median 0.978). **The channels are barely separated.** See Finding 3 in [component3_known_findings_and_limitations.md](component3_known_findings_and_limitations.md) |

## 8.4 Diffusion Results

PPR `ppr-528039331d78` covers 18 sources and 306 ordered pairs. It converged for every source. 156 of 306 pairs are reachable; the other 150 score exactly 0.

## 8.5 Topic Similarity Results

- Profiles for 18 of 18 channels; 851 of 851 videos have usable text.
- 10 topic clusters.
- Cosine median 0.935, range 0.781 to 0.983. Most similar pair: TV Derana – TV Derana LIVE (0.983).
- The raw values are compressed into a narrow band, typical of E5 embeddings. Per-source normalisation spreads them out.

## 8.6 Confidence Results

| Measure (306 pairs) | Minimum | Median | P90 | Maximum | Share = 0 |
|---|---|---|---|---|---|
| confidence | 0.000 | 0.000 | 0.500 | 0.923 | 73.2 % |
| evidence_confidence | 0.000 | 0.000 | 0.500 | 0.923 | 73.2 % |
| topic_coverage_confidence | 1.000 | 1.000 | 1.000 | 1.000 | 0 % |
| shared commenters | 0 | 0 | 3 | 36 | 73.2 % |

Topic coverage was complete, so in this snapshot confidence equals evidence confidence.

## 8.7 Audience Bridge Score Results

- All 306 of 306 ordered pairs were scored (`ok`).
- Score median 0.000; P90 0.315; maximum 0.898.
- 73.2 % of pairs score 0 because they share no commenters.
- Reconstruction error of the decomposition: 0.

| Source | Top destination | Score | Diffusion | Embedding | Topic | Confidence | Shared |
|---|---|---|---|---|---|---|---|
| Derana Little Star | Dream Star | 0.8976 | 0.333 | 0.333 | 0.306 | 0.923 | 36 |
| Dream Star | Derana 60 Plus | 0.8855 | 0.333 | 0.333 | 0.317 | 0.900 | 27 |
| Ada Derana Sports | Ada Derana | 0.8715 | 0.333 | 0.329 | 0.333 | 0.875 | 21 |
| Ada Derana | Ada Derana Sports | 0.8595 | 0.333 | 0.333 | 0.316 | 0.875 | 21 |
| Derana 60 Plus | Dream Star | 0.8408 | 0.333 | 0.333 | 0.268 | 0.900 | 27 |
| TV Derana LIVE | Dream Star | 0.6347 | 0.333 | 0.295 | 0.244 | 0.727 | 8 |
| TV Derana | Dream Star | 0.5017 | 0.089 | 0.309 | 0.229 | 0.800 | 12 |
| FM Derana | Ada Derana Sports | 0.4654 | 0.188 | 0.263 | 0.294 | 0.625 | 5 |

The diffusion, embedding and topic columns are weighted contributions, w × normalised value. The five zero-evidence channels have **no bridge evidence**: every score is 0, and their "rank 1" is only a tie-break (Finding 4).

**Directionality:**
- 153 unordered pairs are scored in both directions.
- The median of |score(A→B) − score(B→A)| is 0.000; the maximum is 0.160 (TV Derana LIVE ↔ Dream Star: 0.635 vs 0.474).
- 2 pairs are each other's top destination.

## 8.8 Louvain Results

`louvain-df378406c68c` found 8 communities with modularity 0.193; 5 channels are isolated.

| Community | Channels |
|---|---|
| 1 | Ada Derana, Ada Derana Biz, Ada Derana Sports, Derana City Of Music, Lokaya Saha Lokayo |
| 2 | Ada Derana Education, Ada Derana News Channel, FM Derana, TV Derana, TV Derana LIVE |
| 3 | Derana 60 Plus, Derana Little Star, Dream Star |
| 4–8 | The 5 isolated channels, each a singleton |

## 8.9 node2vec Results

`node2vec-421e71b0a640` embedded 8,205 nodes (no topic nodes; the walks are type-agnostic) and produced channel cosine for 306 pairs.

## 8.10 Proposed Method vs Baselines

The table shows mean per-source agreement with the Audience Bridge Score. Spearman and Kendall are over 13 sources with defined rankings; top-k is over 18 sources.

| Compared with | Spearman | Kendall | Top-1 Jaccard | Top-3 Jaccard | Top-5 Jaccard |
|---|---|---|---|---|---|
| PPR diffusion (component) | 0.809 | 0.711 | 0.833 | 0.789 | 0.788 |
| metapath2vec similarity (component) | 0.406 | 0.326 | 0.222 | 0.344 | 0.377 |
| Louvain (baseline) | 0.330 | 0.308 | 0.444 | 0.461 | 0.513 |
| topic similarity (component) | 0.294 | 0.227 | 0.111 | 0.189 | 0.266 |
| HGT similarity (alternative) | 0.182 | 0.131 | 0.111 | 0.161 | 0.224 |
| node2vec (baseline) | −0.286 | −0.219 | 0.111 | 0.056 | 0.065 |

**Interpretation:**
- The score is driven mostly by diffusion. It is weakly related to Louvain communities and inversely related to node2vec.
- This shows that the methods produce **different** rankings, not that any one of them is better.
- Top-1 agreement: for 8 of 18 sources, the score's top destination lies in the source's Louvain community. node2vec picks the same top destination for only 2 of 18 sources.

## 8.11 Ranking Results

- **Relevance metrics** (precision, recall, NDCG, MRR): **not computed**, because no labels were supplied.
- **Sensitivity of the top-1 destination** (18 sources): it is kept by 9 sources when confidence is removed, 16 without diffusion, 15 without embeddings, 17 without topic, and 13 with topic only. Confidence has the largest effect.
- **Explanation statuses:** 306 complete.
- **Reason counts:**

  | Reason | Count |
  |---|---|
  | no shared-commenter evidence | 158 |
  | high topic similarity | 90 |
  | strong embedding similarity | 90 |
  | insufficient evidence | 66 |
  | strong structural connectivity | 65 |
  | low-confidence sparse evidence | 42 |
  | strong shared-commenter evidence | 40 |

## 8.12 Temporal Results

The comparison is `rs-20261008T191612Z` → `rs-20261010T081534Z`: 1.5 days apart, sharing 87.3 % of the later snapshot's videos and 75.4 % of its comments.

| Method | Spearman | Kendall | Top-1 | Top-3 | Top-5 |
|---|---|---|---|---|---|
| Audience Bridge Score | 0.946 | 0.901 | 0.944 | 0.844 | 0.894 |
| PPR diffusion | 0.969 | 0.913 | 0.944 | 0.889 | 0.857 |
| topic similarity | 0.993 | 0.971 | 1.000 | 0.972 | 0.944 |
| metapath2vec | 0.622 | 0.484 | 0.500 | 0.417 | 0.509 |
| HGT | 0.756 | 0.581 | 0.444 | 0.400 | 0.556 |
| Louvain | 0.791 | 0.791 | 0.722 | 0.694 | 0.778 |
| node2vec | 0.588 | 0.427 | 0.111 | 0.267 | 0.455 |

High stability here largely reflects the shared data. It is **not** evidence of long-term stability.

## 8.13 Sparse-Data Results

Comment subsampling at 50 % retention, seeds 0 and 1. The table compares each method's subsampled ranking with its full-data ranking (mean, with min–max).

| Method | Spearman | Kendall | Top-1 | Top-5 | Score coverage |
|---|---|---|---|---|---|
| Audience Bridge Score | 0.814 (0.811–0.816) | 0.742 | 0.722 | 0.769 | 1.000 |
| PPR diffusion | 0.903 (0.899–0.908) | 0.791 | 0.750 | 0.718 | 1.000 |
| node2vec | 0.631 (0.625–0.637) | 0.469 | 0.139 | 0.423 | 1.000 |
| Louvain | 0.506 (0.491–0.521) | 0.506 | 0.667 | 0.604 | 1.000 |
| metapath2vec | 0.096 (−0.027–0.219) | 0.076 | 0.222 | 0.230 | 1.000 |

The score is more stable under halved evidence than either baseline. metapath2vec similarity alone is unstable when evidence is halved.

## 8.14 Computational Results

Wall-clock seconds, as measured in `eval-60ac93319497`, on a machine with concurrent load:

| Method | Main run | Temporal run | Sparse seed 0 | Sparse seed 1 |
|---|---|---|---|---|
| Input preparation | 7.9 | 7.4 | 2.6 | 4.2 |
| Audience Bridge Score (incl. topic encoding) | 146.8 | 139.0 | 114.1 | 134.1 |
| PPR diffusion | 13.0 | 14.1 | 3.3 | 3.2 |
| topic similarity | 105.4 | 86.0 | — | — |
| metapath2vec similarity | 13.1 | 2.8 | **62,287.4** | 52.1 |
| HGT similarity | 13.1 | 3.1 | — | — |
| Louvain | 12.2 | 3.4 | 7.7 | 1.6 |
| node2vec | 1,391.4 | 735.5 | 1,817.1 | 348.6 |
| **Total recorded** | | | | **67,504 s** |

The 62,287 s entry is a single outlier: the identical step with seed 1 took 52 s. Excluding it, the evaluation took about 5,200 s. node2vec is the consistently slowest method. See Finding 1.

**Python heap peak:** 633 MiB for the score and topic runs (E5 encoder); 56 MiB or less for the others.

## 8.15 Supplementary: newest snapshot (partial collection)

These results use `rs-20261015T174938Z`, evaluation `eval-09420b1535eb` (CLI defaults: 3 retain levels × 3 seeds = 9 sparse runs).

> **This snapshot is incomplete:** 718 comments were not stored and 26 videos failed (Finding 2). The results are supplementary, are labelled as partial, and do not replace the main results above.

**Data and graph:**
- 18 channels, 1,136 videos, 18,323 comments and 11,508 commenters (329 on 2 or more channels)
- 47 overlapping channel pairs
- graph of 12,672 nodes and 29,375 edges

**Agreement:** Spearman of the score with PPR 0.845, metapath2vec 0.430, topic 0.364, Louvain 0.388, HGT 0.193 and node2vec −0.372. This is the same pattern as the main results.

**Temporal stability** (mean per-source Spearman):

| Method | 191612Z → 081534Z (1.5 days, complete) | 081534Z → 174938Z (5.4 days, later snapshot partial) |
|---|---|---|
| Audience Bridge Score | 0.946 | 0.888 |
| PPR diffusion | 0.969 | 0.946 |
| topic similarity | 0.993 | 0.992 |
| Louvain | 0.791 | 0.791 |
| HGT | 0.756 | 0.668 |
| metapath2vec | 0.622 | 0.504 |
| node2vec | 0.588 | 0.559 |

The second pair is longer and has less shared data, and the score's stability drops from 0.946 to 0.888. Because the later snapshot is partial, the drop cannot be attributed to time alone.

**Sparse-data robustness** (mean Spearman vs the full-data ranking, 3 seeds):

| Method | 75 % retained | 50 % | 25 % |
|---|---|---|---|
| PPR diffusion | 0.936 | 0.907 | 0.836 |
| Audience Bridge Score | 0.887 | 0.823 | 0.675 |
| node2vec | 0.589 | 0.599 | 0.577 |
| Louvain | 0.428 | 0.362 | 0.197 |
| metapath2vec | 0.417 | 0.230 | 0.096 |

The score degrades gradually and stays above both baselines at every level.

**Runtime:** 9,124 s in total (main 1,022 s, temporal 830 s, sparse 7,197 s). The largest single step was node2vec at 771 s; no outlier occurred. Explanations: `xpl-9ca69e2cd234`, 306 complete.
