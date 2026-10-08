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

## Folders
`preprocessing/` · `model/` · `evaluation/` · `notebooks/` · `results/` (git-ignored)
