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

## Folders
`preprocessing/` · `model/` · `evaluation/` · `notebooks/` · `results/` (git-ignored)
