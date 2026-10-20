# Component 3: Final System Architecture

Every layer below exists in the repository. Code paths are relative to the repository root.

```
YouTube Data API v3
        ↓
Shared Data Collector                 shared/data_collection/
        ↓
Supabase PostgreSQL                   shared/database/
        ↓
Parquet Snapshots (immutable)         data/snapshots/research/rs-<time>/
        ↓
DuckDB                                research/component_3/preprocessing/research_dataset.py
        ↓
Validation / Privacy                  STEP 12 validation; pseudonymisation at parse time
        ↓
Heterogeneous Graph                   preprocessing/hetero_graph.py (+ graph_features.py)
        ↓
metapath2vec / HGT                    model/metapath2vec.py, model/hgt.py
        ↓
Node Representations                  data/processed/component_3/<snapshot>/embeddings/
        ↓
Personalized PageRank                 model/ppr_diffusion.py
        ↓
Topic Similarity                      model/topic_similarity.py
        ↓
Confidence Weighting                  inside model/audience_bridge.py
        ↓
Audience Bridge Score                 model/audience_bridge.py
        ↓
Ranked Source → Destination Channels  bridge/<abs-id>/audience_bridge_scores.parquet
        ↓
Explainability                        explainability/
        ↓
Evaluation                            evaluation/   (with model/baselines.py: Louvain, node2vec)
        ↓
Backend API (FastAPI, read-only)      backend/  → /api/v1/component-3/*
        ↓
Dashboard (React + Vite)              frontend/src/features/component_3/
```

Topic similarity is computed **before** the graph is finalised, because its KMeans clusters become the graph's `topic` nodes. It is drawn after PPR above only because that is its position in the score.

## Layers

| Layer | Responsibility | Key properties |
|---|---|---|
| **YouTube Data API v3** | Source of public channels, videos and comments | Quota-bounded; API key in `.env` only |
| **Shared data collector** | Maps API resources to records, pseudonymises commenters, retries, logs runs | Shared by all components; run logs in `data/raw/collection_runs/` |
| **Supabase PostgreSQL** | Team database of collected rows | Migrations in `shared/database/migrations/`; credentials in `.env` only |
| **Parquet snapshots** | Frozen copies used for research | Checksummed manifest; never modified; new data creates a new ID |
| **DuckDB** | SQL validation and preparation; read-only analytics workspace | Deterministic reads over Parquet |
| **Validation / privacy** | Research-readiness report; commenter pseudonyms | `anon_` HMAC-SHA256; fails closed without the salt |
| **Heterogeneous graph** | Nodes and edges of section 4.5 of the methodology; descriptive features | Fingerprinted; features as of the snapshot time |
| **metapath2vec / HGT** | Node embeddings (64-dimensional) | Seeded; HGT is the alternative |
| **Personalized PageRank** | Directional reachability per source channel | Converged power iteration |
| **Topic similarity** | Multilingual content profiles and cosine | Pinned E5 model revision |
| **Confidence / ABS** | Per-source normalisation, weighting, confidence gate, ranking | Write-once experiment IDs |
| **Explainability** | Decomposition, evidence, rule-based reasons, sensitivity | Wording excludes migration and causal language |
| **Evaluation** | Agreement, top-k, temporal, sparse, performance | No labels, so consistency only |
| **Backend API** | Read-only JSON over stored Parquet results | No commenter IDs returned; 404 / 422 errors with messages |
| **Dashboard** | Overview, Audience Bridges, Channel Explorer, Pipeline Graph, Graph Intelligence, Neural Models, Topic Intelligence, Baselines & Evaluation, Explainability, Experiments, System Status | Shows stored results only; empty states when an artifact is missing |

See also: [../architecture/](../architecture/), [component3_data_pipeline.md](component3_data_pipeline.md) and [../../backend/README.md](../../backend/README.md).
