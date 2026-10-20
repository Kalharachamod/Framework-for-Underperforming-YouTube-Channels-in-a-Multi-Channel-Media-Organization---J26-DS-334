# Component 3: Data Pipeline

## Data categories

| Category | What | Where | Mutable? |
|---|---|---|---|
| **Raw data** | API responses as stored rows; collection run logs | Supabase PostgreSQL; `data/raw/collection_runs/*.json` | The database is updated by later collections |
| **Snapshots** | Frozen research copies of channels, videos and comments | `data/snapshots/research/rs-<UTC time>/` (Parquet + manifest with checksums) | **No.** Never modified |
| **Processed data** | Validated, research-ready datasets (commenter participation, channel-pair overlap) | `data/processed/component_3/<snapshot>/*.parquet` | Write-once |
| **Features** | Graph and graph features as of a reference time | `…/<snapshot>/graph/`, `…/<snapshot>/features/asof-<time>/` | Write-once |
| **Experiment outputs** | Topics, embeddings, diffusion, bridge scores, baselines, explanations, evaluation | `…/<snapshot>/<stage>/<experiment-id>/` | Write-once; the ID is a hash of the inputs and configuration |

All of `data/` is git-ignored.

## Steps

1. **Collection:** `python -m shared.data_collection.run_collection --max-videos 50 --snapshot`
   - collects channels, then videos, then comments into Supabase, with quota accounting and retries
   - commenter IDs are pseudonymised before storage
   - writes a run log, with exit code 1 if any item failed
2. **Snapshot creation:** the `--snapshot` flag exports the stored rows into a new `rs-<time>` research snapshot.
   - an existing ID is refused
   - a checksum manifest is written
3. **Preprocessing and validation (STEP 12):** `python -m research.component_3.preprocessing.research_dataset`
   - verifies the checksums
   - runs DuckDB checks: counts, duplicates, missing values, relationships and quality warnings
   - exports the research-ready datasets
4. **Topic run (needed before the graph):** `python -m research.component_3.model.topic_similarity --topics 10`
5. **Graph preparation (STEP 13):** `python -m research.component_3.preprocessing.hetero_graph --topic-run latest`
6. **Feature generation (STEP 14):** `python -m research.component_3.preprocessing.graph_features`
7. **Models, scoring, baselines, evaluation and explanations:** see [component3_reproduction_guide.md](component3_reproduction_guide.md).

## Experiment data selection

- Each stage uses the **latest** research snapshot unless `--snapshot rs-…` is given.
- The dashboard and API default to the latest snapshot and offer a snapshot selector.
- **Reported thesis results** use `rs-20261010T081534Z`. It is the latest **complete** full-scale snapshot, with the full pipeline and a completed evaluation: `eval-60ac93319497`.
- `rs-20261015T174938Z` is newer, but **incomplete**: a network interruption during collection left 718 comments unstored, 26 videos failed and 446 were skipped. It must be labelled as partial if used. See [component3_known_findings_and_limitations.md](component3_known_findings_and_limitations.md).
- Temporal evaluation pairs a snapshot only with an earlier snapshot that has the same channel set and a similar collection depth (ratio ≥ 0.8).

## Reproducibility considerations

- **Inputs:** an analysis is fully determined by the snapshot ID, the salt (`.env`), the configuration and the seeds. Each experiment ID is a hash of these.
- **Determinism:** fixed seeds and single-worker training make metapath2vec, node2vec, PPR, topic similarity, the score and Louvain reproducible. HGT is seeded on CPU.
- **Versions:** library versions are recorded in every experiment manifest. `requirements-lock.txt` pins the exact versions; `requirements.txt` gives minimum versions.
- **Pinned model:** the topic encoder is pinned to a model revision.
- **Raw data:** it is not redistributed (YouTube terms and privacy). Code, configuration and snapshot IDs are.
