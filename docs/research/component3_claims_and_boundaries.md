# Component 3: Claims and Boundaries

## Safe claims (supported by the implementation and results)

| Claim | Evidence |
|---|---|
| The system identifies **potential** cross-channel audience bridges from public interaction and content evidence | Pipeline STEP 12–19; 306 scored pairs in `abs-7cf3eab938ad` |
| The framework integrates graph structure, diffusion, semantic similarity and evidence quality | Three-part base score × confidence ([component3_final_methodology.md](component3_final_methodology.md) §4.12) |
| The system produces a **directional** Audience Bridge Score | Source-personalised PPR and per-source normalisation; up to 0.160 difference between A→B and B→A |
| The approach is evaluated against Louvain and node2vec baselines | `eval-60ac93319497`: Spearman 0.330 (Louvain) and −0.286 (node2vec) |
| The framework provides interpretable score components | Decomposition reconstructs every score exactly (error 0); 306 complete explanations |
| On the evaluated data, the score's ranking is more stable under 50 % comment subsampling than Louvain or node2vec | Spearman 0.814 vs 0.506 / 0.631 (2 seeds) |
| The pipeline is reproducible from a snapshot, configuration and seeds | Content-addressed experiment IDs; STEP 34 re-runs |
| The system can keep potential-bridge estimates current with an unattended nightly pipeline over a same-period rolling window | `research.c3_live_runs`; first full run `live-20261020T215831Z` (18 channels, 0 collection failures) |

Always state the scope with these claims: one snapshot, 18 Derana channels, no labels.

## Unsupported claims (prohibited)

| Do not claim | Why |
|---|---|
| Actual audience migration | No movement is observed; a snapshot shows who commented where |
| Subscriber transfer | Per-user subscriptions are not observed |
| Causal influence | No intervention or counterfactual |
| Guaranteed growth, or any forecast | The score is not a forecast |
| Guaranteed recommendation success | Acting on rankings was not evaluated |
| Demographic identification | None is inferred or stored |
| Private audience behaviour | Only public comments are used |
| Complete representation of all YouTube viewers | Commenters are a self-selected subset; collection is bounded |
| Accuracy, correctness or "validated" performance | No ground-truth labels |
| Novelty of individual techniques (PPR, metapath2vec, HGT, node2vec, Louvain, E5, shrinkage confidence, heterogeneous graphs, directional audience relations) | All are established ([component3_novelty_threat_analysis.md](component3_novelty_threat_analysis.md)) |
| "First", "first-ever", "unique", "novel algorithm", "no previous work" | Not supported by a non-systematic search |
| That HGT is an effective channel representation here | Channel vectors collapsed (Finding 3) |
| That the score identifies bridges a simple shared-commenter count would miss | On this data it closely follows the count (≈0.8 among evidence pairs) and changes the top bridge for only 3–4 of 13 channels (Finding 6) |
| Long-term stability | One comparable snapshot pair, 1.5 days apart |
| That nightly score changes show audiences changing, or that live results are thesis results | Consecutive 90-day windows overlap by 89 days; changes mostly reflect new and late comments. Live runs are monitoring output, not evaluated |

## Preferred terminology

Use these terms:
- "potential audience bridge"
- "cross-channel audience affinity"
- "Bridge Score"
- "evidence strength"
- "observed interaction evidence"
- "potential destination"
- "shared public commenters"

Avoid these:
- "audience migration"
- "audience transfer"
- "subscriber movement"
- "guaranteed growth"
- "predicted subscriber transfer"
- "shared audience" (use "shared commenters")
