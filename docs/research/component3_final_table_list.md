# Component 3: Recommended Thesis Tables

Every table below is supported by stored data. The source column points to where the numbers already are.

| # | Table | Source |
|---|---|---|
| 1 | Dataset summary (channels, videos, comments, commenters, coverage per channel) | [final_results §8.1](component3_final_results.md); per-channel table in `docs/component_3_full_experiment_report.md` |
| 2 | Graph statistics (node and edge counts, overlapping pairs) | [final_results §8.2](component3_final_results.md) |
| 3 | Model configuration (metapath2vec, HGT, PPR, topic) | [experimental_setup](component3_experimental_setup.md) |
| 4 | Audience Bridge Score components (variable, meaning, range, symmetric or directional) | [final_methodology §4.11–4.12](component3_final_methodology.md) |
| 5 | Baseline configuration (Louvain, node2vec) | [experimental_setup](component3_experimental_setup.md) |
| 6 | Evaluation metrics (what each measures and what it cannot show) | [evaluation_traceability §12](component3_evaluation_traceability.md) |
| 7 | Proposed method vs baselines (Spearman, Kendall, top-k Jaccard) | [final_results §8.10](component3_final_results.md) |
| 8 | Robustness results (temporal and sparse) | [final_results §8.12–8.13](component3_final_results.md) |
| 9 | Computational performance (with the outlier note) | [final_results §8.14](component3_final_results.md) |
| 10 | Limitations | [limitations](component3_limitations.md) |
| 11 | Top destination per source | [final_results §8.7](component3_final_results.md) |
| 12 | Sensitivity of the top-1 destination (component removal and weights) | `docs/component_3_findings_report.md` §10 |
| 13 | Novelty classification (A–D) | [novelty_threat_analysis](component3_novelty_threat_analysis.md) |

There is **no table of accuracy, precision or NDCG**: no labels exist, and none should be reported.
