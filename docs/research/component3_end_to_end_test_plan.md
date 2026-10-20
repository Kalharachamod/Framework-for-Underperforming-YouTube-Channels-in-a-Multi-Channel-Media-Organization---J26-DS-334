# Component 3: End-to-End Test Plan

*STEP 34.* This plan covers the frozen Component 3 pipeline (see [component3_methodology_freeze.md](component3_methodology_freeze.md)). It uses the existing entry points only.

## Entry points

| Layer | Entry point |
|---|---|
| Collection | `python -m shared.data_collection.run_collection --max-videos 50 --snapshot` |
| Pipeline (all stages, one snapshot) | `research.component_3.pilot.run_pipeline(snapshot_id, config)`; CLI `python -m research.component_3.pilot --config … --snapshot rs-…` (resume, no API calls) |
| Individual stages | `python -m research.component_3.<preprocessing\|model\|evaluation\|explainability>.<module>` (see the root README) |
| Baselines | `python -m research.component_3.model.baselines louvain` and `… node2vec` |
| API | `python -m uvicorn backend.main:app --port 8000`, routes under `/api/v1/component-3` |
| Dashboard | `cd frontend; npm run dev` (port 5173) |
| Automated tests | `pytest tests/backend tests/component_3 tests/integration`; `cd frontend; npx tsc -b; npx vitest run` |

## Test data

Two snapshots are used, so that no new YouTube API calls are needed:
- **`rs-20261010T072201Z`** (3-channel pilot: 45 videos, 862 comments) for full stage re-runs and reproducibility. It is small and has every artifact saved.
- **The latest snapshot**, for the API and dashboard checks on real research data.
- **Synthetic offline data** in `tests/integration/test_component3_end_to_end.py` covers collector → PostgreSQL → Parquet → every stage → FastAPI → frontend contracts.

## Stage checks

| # | Stage | Input | Command / function | Expected output | Validation condition | Failure condition |
|---|---|---|---|---|---|---|
| 1 | Data collection | YouTube API, `.env` key | `run_collection` | rows in Supabase + run log | per-stage counts; failed items listed | silent drop of failed items; secrets printed |
| 2 | Data storage | collected rows | Supabase → snapshot export | Parquet datasets + manifest with checksums | `verify_research_snapshot().ok` | checksum mismatch; missing dataset |
| 3 | Data snapshot | Supabase tables | `create_research_snapshot` | immutable `rs-<time>` directory | manifest ID = directory name | existing snapshot modified |
| 4 | Data validation | snapshot | `research_dataset.prepare(export=False, save_report=False)` | report: counts, duplicates, missing values, relationships | `research_ready`, 0 duplicates, all FK relationships resolve, commenter IDs `anon_…` | malformed records accepted without an error or warning |
| 5 | Graph construction | snapshot + topic run | `hetero_graph.build_graph(topics=…)` | nodes / edges / manifest | 4 node types (topic when a topic run exists), 4 relations, 0 self-loops, 0 duplicates, fingerprint stable | empty graph; topic nodes missing despite a topic run |
| 6 | Graph features | graph, `as_of` | `graph_features.build_features` | 4 feature tables | no NaN / inf, no negative counts, no null IDs | NaN or inf; rows after `as_of` |
| 7 | metapath2vec | graph | `metapath2vec.train(Config(seed=42))` | (n_nodes × 64) vectors | count = graph nodes, finite, re-run bit-identical | missing nodes; non-determinism |
| 8 | HGT | graph | `hgt.train(HGTConfig(seed=42))` | (n_nodes × 64) vectors + split metadata | finite; temporal split or recorded fallback | NaN; unrecorded split |
| 9 | PageRank | graph | `ppr_diffusion.run_diffusion` | `source_channel_id, destination_channel_id, diffusion_score, reachable` | converged; no self pairs; ≥ 0; unreachable → exactly 0 | negative scores; self pairs; non-convergence |
| 10 | Topic similarity | snapshot, `as_of` | `topic_similarity.run(TopicConfig(n_topics=10))` | profiles, symmetric similarity, clusters | values in [-1, 1], symmetric, identical on re-run | values out of range; missing profile scored as 0 |
| 11 | Confidence | shared commenters, coverage | inside `audience_bridge.score` | `evidence_confidence`, `topic_coverage_confidence`, `confidence` | 0 ≤ c < 1; c = evidence × coverage | c ≥ 1; negative |
| 12 | Audience Bridge Score | PPR, m2v, topic, input | `audience_bridge.score(…, BridgeConfig())` | scored pairs with `score_status` | score = base × confidence; base = Σ wᵢ·normᵢ; ranks monotone per source; no self pairs; deterministic | incomplete components scored as 0; ties ordered randomly |
| 13 | Louvain | baseline input | `baselines.run_louvain(LouvainConfig(seed=42))` | communities + relationships | re-run identical | non-determinism |
| 14 | node2vec | baseline input | `baselines.run_node2vec(Node2VecConfig(seed=42))` | embeddings + channel similarity | finite; re-run bit-identical | NaN |
| 15 | Evaluation | snapshot | `evaluate.evaluate` | ranking, top-k, temporal, sparse, performance tables | every method `ok`; labels `not_provided`; temporal pairs only when comparable | mixed snapshots; missing method silently dropped |
| 16 | Explainability | bridge result | `explain.explain` | decomposition, evidence, reasons, sensitivity | contributions sum to the score; no migration / causal wording; no commenter IDs | reasons claiming migration or causality |
| 17 | Backend API | Parquet results | all `/api/v1/component-3` GET routes | JSON per schema | HTTP 200 on valid input, < 1 s, no `anon_` IDs | 500 errors; ID leakage |
| 18 | Dashboard | API | Vite app, headless Chrome screenshots + vitest | pages with real data | real data, empty states when artifacts are missing, direction visible | mock data shown as real; blank page |
| 19 | Reproducibility | same snapshot + config + seeds | each stage twice + compare with the saved artifact | identical tables / vectors | identical except HGT (tolerance) and timings | different experiment ID for identical inputs |
| 20 | Error handling | invalid inputs | API error cases, CLI with a missing snapshot, unit tests | 404 / 422 with a message; CLI exit code ≠ 0 | clear error, no partial artifacts | 500; silent zero results |
