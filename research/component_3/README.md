# Component 3

**Diffusion-Based Cross-Channel Audience Bridge Scoring**
Owner: Koonara K M K C (IT23200760)

## Original module plan (all implemented except weekly recomputation; see Implemented)
- Heterogeneous commenter-video-channel-topic graph (commenter IDs hashed)
- Node embeddings: metapath2vec (primary), lightweight HGT (alternative)
- Personalized PageRank diffusion from the target channel
- Audience Bridge Score: diffusion + embedding similarity + topic similarity, multiplied by confidence, with explanations
- Baselines: Louvain, node2vec; weekly snapshot recomputation (planned, not implemented: snapshots are collected and scored manually)

## Implemented
- `preprocessing/research_dataset.py`: research snapshot → DuckDB → validation → research-ready datasets (commenter participation, channel-pair overlap). See [docs/architecture/research_dataset.md](../../docs/architecture/research_dataset.md).
- `preprocessing/hetero_graph.py`: heterogeneous commenter–video–channel(–topic) graph from a research-ready snapshot (Parquet nodes/edges + manifest). See [docs/architecture/hetero_graph.md](../../docs/architecture/hetero_graph.md).
- `preprocessing/graph_features.py`: descriptive node / edge / channel-pair features and transparent `ln(1 + comments)` edge weights, computed as of a reference time (no leakage). See [docs/architecture/graph_features.md](../../docs/architecture/graph_features.md).
- `model/metapath2vec.py`: primary representation learning (meta-path-guided walks + skip-gram), reproducible node embeddings. See [docs/architecture/metapath2vec.md](../../docs/architecture/metapath2vec.md).
- `model/hgt.py`: HGT alternative graph learning (type-specific features, HGTConv, link-prediction objective, temporal split with documented fallback). See [docs/architecture/hgt.md](../../docs/architecture/hgt.md).
- `model/ppr_diffusion.py`: Personalized PageRank diffusion from each source channel over the heterogeneous graph (channel-to-channel `diffusion_score`). See [docs/architecture/ppr_diffusion.md](../../docs/architecture/ppr_diffusion.md).
- `model/topic_similarity.py`: multilingual content-semantic channel profiles and symmetric topic similarity (optional topic clustering → graph topic nodes). See [docs/architecture/topic_similarity.md](../../docs/architecture/topic_similarity.md).
- `model/baselines.py`: comparison baselines (not the proposed method): Louvain communities on a channel projection of shared commenters, and type-agnostic node2vec channel similarity. See [docs/architecture/baselines.md](../../docs/architecture/baselines.md).
- `model/audience_bridge.py`: the proposed Audience Bridge Score: per-source normalized PPR diffusion, channel-embedding similarity (metapath2vec by default, HGT optional) and topic similarity, weighted and multiplied by confidence (shared-commenter evidence and topic coverage). Provisional, configurable defaults. See [docs/architecture/audience_bridge.md](../../docs/architecture/audience_bridge.md).
- `evaluation/`: research evaluation framework comparing the proposed method (Audience Bridge Score and its components PPR diffusion, metapath2vec / HGT similarity and topic similarity) with the baselines: label-based ranking quality, method agreement, top-k, temporal stability, sparse-data robustness and measured performance. See [docs/architecture/evaluation.md](../../docs/architecture/evaluation.md).
- `explainability/`: evidence-based explanations of every Audience Bridge Score: score decomposition, aggregate evidence, rule-based reasons, ranking context and score sensitivity. See [docs/architecture/explainability.md](../../docs/architecture/explainability.md).
- `analysis.py`: quick analysis of **any** organization from the dashboard ("Analyze Organization"): fresh small-sample collection, an organization-only snapshot and the pipeline up to the Audience Bridge Score (HGT, node2vec and the evaluation are skipped). Exploratory; separate from the Derana research dataset. See [docs/architecture/org_analysis.md](../../docs/architecture/org_analysis.md).

## Research documentation
Final research package: [docs/research/component3_documentation_index.md](../../docs/research/component3_documentation_index.md).

## Folders
`preprocessing/` · `model/` · `evaluation/` · `notebooks/` · `results/` (git-ignored)
