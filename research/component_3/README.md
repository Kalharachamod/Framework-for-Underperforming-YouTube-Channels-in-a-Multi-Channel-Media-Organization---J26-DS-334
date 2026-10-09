# Component 3

**Diffusion-Based Cross-Channel Audience Bridge Scoring**
Owner: Koonara K M K C (IT23200760)

## Planned modules
- Heterogeneous commenter-video-channel-topic graph (commenter IDs hashed)
- Node embeddings: metapath2vec (primary), lightweight HGT (alternative)
- Personalized PageRank diffusion from the target channel
- Audience Bridge Score: diffusion + topic similarity + confidence weighting, with explanations
- Baselines: Louvain, node2vec; weekly snapshot recomputation

## Implemented
- `preprocessing/research_dataset.py`: research snapshot → DuckDB → validation → research-ready datasets (commenter participation, channel-pair overlap). See [docs/architecture/research_dataset.md](../../docs/architecture/research_dataset.md).
- `preprocessing/hetero_graph.py`: heterogeneous commenter–video–channel(–topic) graph from a research-ready snapshot (Parquet nodes/edges + manifest). See [docs/architecture/hetero_graph.md](../../docs/architecture/hetero_graph.md).
- `preprocessing/graph_features.py`: descriptive node / edge / channel-pair features and transparent `ln(1 + comments)` edge weights, computed as of a reference time (no leakage). See [docs/architecture/graph_features.md](../../docs/architecture/graph_features.md).
- `model/metapath2vec.py`: primary representation learning (meta-path-guided walks + skip-gram), reproducible node embeddings. See [docs/architecture/metapath2vec.md](../../docs/architecture/metapath2vec.md).
- `model/hgt.py`: HGT alternative graph learning (type-specific features, HGTConv, link-prediction objective, temporal split with documented fallback). See [docs/architecture/hgt.md](../../docs/architecture/hgt.md).
- `model/ppr_diffusion.py`: Personalized PageRank diffusion from each source channel over the heterogeneous graph (channel-to-channel `diffusion_score`). See [docs/architecture/ppr_diffusion.md](../../docs/architecture/ppr_diffusion.md).
- `model/topic_similarity.py`: multilingual content-semantic channel profiles and symmetric topic similarity (optional topic clustering → graph topic nodes). See [docs/architecture/topic_similarity.md](../../docs/architecture/topic_similarity.md).
- `model/baselines.py`: comparison baselines (not the proposed method): Louvain communities on a channel projection of shared commenters, and type-agnostic node2vec channel similarity. See [docs/architecture/baselines.md](../../docs/architecture/baselines.md).
- `evaluation/`: research evaluation framework comparing the proposed method (Audience Bridge Score slot; components PPR diffusion and topic similarity) with the baselines: label-based ranking quality, method agreement, top-k, temporal stability, sparse-data robustness and measured performance. See [docs/architecture/evaluation.md](../../docs/architecture/evaluation.md).

## Folders
`preprocessing/` · `model/` · `evaluation/` · `notebooks/` · `results/` (git-ignored)
