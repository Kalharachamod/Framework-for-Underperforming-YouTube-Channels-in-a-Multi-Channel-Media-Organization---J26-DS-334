# Component 3: Methodology Traceability

*STEP 33, final methodology audit.* This document traces every Component 3 stage from data collection to the dashboard. Each claim was checked against the code (`research/component_3/`) and the current artefacts on 2026-10-15.

## 1. Pipeline trace

| # | Stage | Code | Input | Output | Deterministic / versioned by |
|---|---|---|---|---|---|
| 1 | YouTube collection | `shared/data_collection/` | YouTube Data API v3 (public channels, videos, comments) | Supabase rows + immutable Parquet snapshot `rs-<UTC time>` | Snapshot ID; collection settings stored in the snapshot manifest |
| 2 | Pseudonymisation | `shared/` parsers | raw comment author IDs | `anon_` + HMAC-SHA256(salt, id) | Salt from `.env` only; fails closed without it |
| 3 | Research dataset (STEP 12) | `preprocessing/research_dataset.py` | snapshot Parquet | DuckDB validation, commenter participation, channel-pair overlap | Snapshot ID + validation report |
| 4 | Heterogeneous graph (STEP 13) | `preprocessing/hetero_graph.py` | research dataset | nodes: channel, video, commenter, (topic); edges: `comments`, `belongs_to`, derived `participates_in`, (`has_topic`) | Graph fingerprint in the manifest |
| 5 | Graph features (STEP 14) | `preprocessing/graph_features.py` | graph, `as_of` | node/edge/pair features, `ln(1+comments)` edge weights | `as_of` cut-off (no future rows) |
| 6 | metapath2vec, primary (STEP 15) | `model/metapath2vec.py` | graph | node embeddings (dim 64) | seed 42, 1 worker, CRC32 hash, `m2v-<hash>` |
| 7 | HGT, alternative (STEP 16) | `model/hgt.py` | graph | node embeddings, link-prediction metrics | seed 42, temporal split, `hgt-<hash>` |
| 8 | PPR diffusion (STEP 17) | `model/ppr_diffusion.py` | graph | `diffusion_score(source → destination)` | α 0.85, tol 1e-10, `ppr-<hash>` |
| 9 | Topic similarity (STEP 18) | `model/topic_similarity.py` | video titles + descriptions, `as_of` | channel profiles, symmetric cosine, coverage; optional `has_topic` edges | e5-small at a pinned revision, experiment ID over snapshot + `as_of` + config + encoder |
| 10 | Audience Bridge Score (STEP 19) | `model/audience_bridge.py` | outputs of 6/7, 8, 9 + shared-commenter counts | per-source ranked `audience_bridge_score`, `score_status` | method 2.0, `BridgeConfig`, experiment ID over all input IDs |
| 11 | Baselines (STEP 20) | `model/baselines.py` | graph | Louvain same-community, node2vec cosine | seed 42, library version recorded |
| 12 | Evaluation (STEP 21) | `evaluation/` | standard ranking tables from 8–11 | agreement, top-k, temporal stability, sparse robustness, performance | `eval-<hash>`, fixed sparse seeds (CLI default 0/1/2) |
| 13 | Explainability (STEP 22) | `explainability/` | ABS run + evidence | decomposition, evidence, reasons, sensitivity | derived from the ABS run ID |
| 14 | API + dashboard | `backend/`, `frontend/` | Parquet results via DuckDB (read-only) | aggregate JSON, pages | read-only; no commenter IDs leave the API |

Every arrow in the table was confirmed in code: each stage reads the previous stage's artefacts by snapshot or experiment ID, and every result directory is write-once.

## 2. Research objective alignment

| Objective | Implemented by | Evidence | Status |
|---|---|---|---|
| Model channels, videos, commenters and topics as one heterogeneous graph | STEP 13 | graph manifest, node/edge counts | Met |
| Learn type-aware representations | STEP 15 (primary), STEP 16 (alternative) | embeddings, metapath coverage, HGT link-prediction metrics | Met |
| Measure multi-hop audience reachability from a source channel | STEP 17 PPR | `diffusion_score`, `reachable` | Met |
| Measure content similarity across Sinhala / Tamil / English | STEP 18 | profiles, coverage, similarity | Met |
| Combine signals into a directional, evidence-weighted bridge ranking | STEP 19 | ABS run, `score_status`, ranks | Met |
| Explain every score | STEP 22 | decomposition sums to the score; rule-based reasons | Met |
| Compare with established baselines | STEP 20/21 | Louvain, node2vec, agreement tables | Met |
| Assess stability and robustness | STEP 21 | temporal (1 comparable pair), sparse (2 seeded runs at 50 % retention, 60 result rows) | Met, limited by data |
| Assess ranking correctness | STEP 21 relevance metrics | requires a labels file | **Not met: no ground-truth labels exist** |
| Periodic (weekly) recomputation | planned | none | **Not implemented** (manual runs) |

## 3. Data-to-method traceability and leakage

| Method | Data it uses | Time control | Leakage assessment |
|---|---|---|---|
| Graph features | comments, videos up to `as_of` | SQL filter on `as_of` | None: no rows after `as_of` |
| metapath2vec | all graph edges of the snapshot (transductive) | snapshot boundary | No target is predicted, so there is no train/test leakage. Embeddings describe the snapshot only. |
| HGT | `comments` edges | temporal split by first comment time; features fitted on the training graph as of the boundary; validation edges removed from message passing | Guarded. Random fallback is recorded when warm validation edges < 20. Current run is temporal. |
| PPR | `comments` + `belongs_to` (topic and `participates_in` excluded by default) | snapshot boundary | No target; excluding `participates_in` avoids counting the same commenter–channel evidence twice |
| Topic similarity | titles + first 1000 description characters, videos published up to `as_of` | `as_of > snapshot` is rejected | None |
| ABS | outputs above + shared-commenter count | same snapshot | The shared-commenter count is used in confidence and is also partly visible to PPR. This is **deliberate double use of overlap evidence** (one as reachability, one as support), documented, not leakage. |
| Evaluation agreement | rankings of the same snapshot | — | Not a correctness test; no labels involved |
| Temporal stability | two snapshots, same channels, depth ratio ≥ 0.8 | later snapshot extracted later | No information flows from the later snapshot into the earlier ranking |
| Sparse robustness | subsampled comments / commenters, fixed seeds | `as_of` unchanged | Controlled simulation |

**Finding:** no leakage path was found. The one shared signal (commenter overlap feeding both diffusion and confidence) is a design choice and is stated as a limitation in [component3_methodology_freeze.md](component3_methodology_freeze.md).
