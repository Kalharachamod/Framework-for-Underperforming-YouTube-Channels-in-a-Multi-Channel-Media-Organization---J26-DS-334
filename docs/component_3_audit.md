# Component 3 End-to-End Audit (STEP 25)

Audit date: 2026-10-10 · Branch: `component-3` · Scope: Diffusion-Based Cross-Channel Audience Bridge Scoring, from data collection to the React dashboard.

Every item below is backed by code inspection, a test run or a command run during this audit. Results produced from synthetic test data are pipeline checks, **not research findings**.

## 1. Status of each part

| # | Part | Status | Evidence |
|---|---|---|---|
| 1 | YouTube Data API v3 client and collectors | Implemented and tested | Mocked-transport tests (`tests/shared/test_*collector.py`, `test_youtube_client.py`). Real collection has run: 18 channels, 851 videos, 10,256 comments |
| 2 | Supabase research data layer | Implemented and tested | Repository and migrations tested against a throwaway local PostgreSQL. Tests never use production Supabase |
| 3 | Parquet snapshots | Implemented and tested | Both real research snapshots pass checksum verification (see §4) |
| 4 | DuckDB analytical layer | Implemented and tested | `test_duckdb_query.py`, `test_research_dataset.py`, plus the API's bounded queries |
| 5 | Schemas and validation | Implemented and tested | `test_schemas.py`, `test_quality.py` |
| 6 | Research snapshot and preparation | Implemented and tested | The end-to-end test asserts a `VALID`, research-ready snapshot |
| 7 | Heterogeneous graph | Implemented and tested (topic layer added after the audit) | `hetero_graph --topic-run latest` now builds the graph with topic nodes from a clustered topic run. The real snapshots still have graphs without topics until they're rebuilt |
| 8 | Graph features and edge weighting | Implemented and tested | `test_graph_features.py` |
| 9 | metapath2vec (primary) | Implemented and tested, **integrated after the audit** | Its channel-embedding similarity is now the score's embedding part (default source) |
| 10 | HGT (alternative) | Implemented and tested, **integrated after the audit** | Selectable embedding source (`--embedding-source hgt`), and evaluated on its own as `hgt_similarity` |
| 11 | Personalized PageRank | Implemented and tested | `test_ppr_diffusion.py`. A real run exists |
| 12 | Topic similarity | Implemented and tested | Tests use a fake encoder. Real runs use e5, which needs a one-time model download |
| 13 | Confidence weighting and Audience Bridge Score | Implemented and tested, **provisional formula** | `test_audience_bridge.py`. Real run: 306 of 306 pairs scored |
| 14 | Louvain baseline | Implemented and tested | No real-data artifact saved yet: evaluation runs Louvain without persisting it |
| 15 | node2vec baseline | Implemented and tested | Same as Louvain |
| 16 | Evaluation framework | Implemented and tested | A real run exists (`--skip-sparse`). No relevance labels, temporal data insufficient, sparse simulations not yet run on real data |
| 17 | Explainability | Implemented and tested | Real run: 306 of 306 explanations complete, all within the reconstruction tolerance |
| 18 | FastAPI backend | Implemented and tested | 21 API tests. Started with uvicorn and served the real artifacts |
| 19 | React dashboard | Implemented and tested | 26 frontend tests and a clean production build. Not visually inspected by the auditor (see §7) |
| 20 | Tests, docs and environment | Implemented, with two discrepancies fixed | See §3 |

**Blocked:** nothing is blocked by missing dependencies on this machine. Database tests and the end-to-end test need PostgreSQL server tools (`initdb`/`pg_ctl`). Without them, pytest reports those tests as **skipped**, never as passed.

## 2. End-to-end data flow

`tests/integration/test_component3_end_to_end.py` runs on synthetic data and executes every stage with real project code. It records each stage and asserts that all 12 ran:

1. **Collectors to database:** collector record mapping, with commenter IDs pseudonymized before they're persisted, into the PostgreSQL research schema.
2. **Parquet snapshots:** two research snapshots, an earlier and a later one.
3. **DuckDB preparation:** the snapshot validates as research-ready.
4. **Graph and features.**
5. **metapath2vec and HGT.**
6. **PPR, topic similarity and the Audience Bridge Score:** the score is computed from the *saved* PPR and topic artifacts, and it equals the in-memory result.
7. **Louvain and node2vec, saved.**
8. **Evaluation:** temporal comparison of the two snapshots and one seeded sparse simulation.
9. **Explanations:** these link to the evaluation of the same experiment.
10. **FastAPI:** all nine artifact types are reported as available, and the stored scores come back unchanged.
11. **Dashboard contract:** every API response has exactly the fields declared in `frontend/src/features/component_3/types.ts`.
12. **Privacy scan:** of every artifact and every response.

These identifiers and conventions were checked across stages:
- **Channel IDs:** `UC…` in the database and API, and `channel:UC…` inside graph artifacts. The API converts between them.
- **Timestamps:** UTC timestamps throughout (database round-trip tested). The API returns ISO 8601.
- **Run identifiers:** snapshot IDs (`rs-…`) and experiment IDs (`ppr-`, `top-`, `abs-`, `louvain-`, `node2vec-`, `eval-`, `xpl-`) are propagated and echoed by every API response.
- **Missing values:** a missing value is NULL, never 0.
- **Folder names:** the API's artifact folder names are checked against the research modules' own constants by a test.

## 3. Defects found and fixed in this audit

| Defect | Fix |
|---|---|
| `README.md` said "Backend and frontend run instructions will be added" | Replaced with the actual uvicorn and `npm run dev` commands |
| The runbook's analysis pipeline stopped at topic similarity | Added the Audience Bridge Score, baselines, explanations and evaluation commands |
| No offline test covered the whole chain | Added `tests/integration/test_component3_end_to_end.py`. It includes a test that compares the TypeScript and Pydantic contracts |

No code defect showed up between stages: the end-to-end test passed on its first run. The scoring formula wasn't changed. The end-to-end test asserts `score = (diffusion + topic) × confidence` to within 1e-12, and the STEP 19 validation checks the same.

## 4. Data integrity and privacy

- **Snapshots:** they're immutable. Both real snapshots verified against their checksums:
  - `rs-20261008T093922Z`: 18 channels, 171 videos, 1,695 comments
  - `rs-20261008T191612Z`: 18 channels, 851 videos, 10,256 comments

  Artifacts are write-once: a rerun with different content is refused.
- **Duplicates and keys:** handled by upserts with history tables. Foreign keys are enforced (tested: a video needs its channel, a comment needs its video).
- **Pseudonymization:** a scan of all 54 Parquet files under `data/` found **0** commenter values that aren't pseudonyms. Derived outputs (scores, explanations, evaluation, diffusion) contain **no** pseudonyms at all. The collection log contains no commenter fields. The API and the dashboard client both refuse pseudonyms in responses.
- **Secrets:** no API key, salt or JWT pattern appears in tracked files or in the full git history. The only database-URL match is the placeholder in `.env.example`. Both `.env.example` files hold placeholders only.
- **Data sources:** only public YouTube Data API v3 data is used. There's no BigQuery usage in the code or docs, and no account or demographic data.
- **Open item:** the 30-day YouTube API retention policy is still undecided, awaiting the supervisor.

## 5. Research-methodology risks

1. **Resolved after the audit (2026-10-10, option 1):** the score is now `(w_d·diffusion + w_e·embedding + w_t·topic) × confidence`, with metapath2vec as the primary and HGT as the alternative embedding source, and ablations in STEP 21 and 22. Original finding: **the representation-learning output wasn't used by the score.** The proposal's chain is graph → metapath2vec/HGT → PPR → topic → confidence → score. In the code, PPR runs on the graph's edges, and the score combines PPR, topic similarity and confidence. **The metapath2vec and HGT embeddings are trained and saved but not consumed.** This needs a design decision before real experiments, for example:
   - use embedding similarity to weight PPR transitions
   - add it as a further score component
   - or document the embeddings as an analysis-only output

   It was not changed here, because that would alter the method.
2. **Resolved after the audit:** topic nodes can now be built into the graph (`--topic-run`), and metapath2vec uses the `VTV` metapath when they exist. PageRank excludes topic edges by default, so topic isn't counted twice. Original finding: **topic nodes were missing from the graph.** Topic similarity enters the score directly, so the "commenter–video–channel–topic" graph currently has no topic layer.
3. **The scoring formula is provisional.** Normalization, the confidence form (`n/(n+k)` × topic coverage), `k = 3` and the 0.5/0.5 weights await confirmation. On real data, the score agrees with PPR alone at Spearman 0.83, meaning diffusion dominates the rankings.
4. **Ranking quality can't be measured yet:** there are no relevance labels. Agreement and robustness show consistency, not correctness.
5. **No temporal evaluation yet.** The two real snapshots differ in collection depth (about 10 vs 50 videos per channel) and are correctly marked non-comparable.
6. **Five of the 18 channels share no commenters** with any other channel in the collected data, so all their scores are 0. Comment sampling (up to 100 threads per video) limits the overlap evidence.
7. **Nothing claims** migration, transfer, causality or growth. Each layer carries this statement.

## 6. Reproducibility

- **Seeds and IDs:** fixed seeds and configuration-hash experiment IDs at every stage. Reproducibility tests exist for every component. metapath2vec is also tested across processes, using a single worker and CRC32 hashing.
- **No future data:** features, topics and scores use the snapshot's `as_of` time.
- **Robustness simulations** run in temporary data folders. The source snapshot is checksum-verified before and after (tested, including in the end-to-end test).
- **Known nondeterminism:**
  - HGT on other hardware or library versions may differ slightly. It's reproducible on the same CPU setup (tested).
  - Wall-clock timings vary between runs by nature, so they're excluded from the write-once comparisons.

## 7. Tests executed during this audit

| Suite | Result |
|---|---|
| Python, full (`python -m pytest`), including the new integration tests | 807 passed, 0 failed, 0 skipped (wall time 6 h 24 min this run; earlier full runs took 12–19 min, so the machine was likely asleep or busy) |
| Offline end-to-end integration (`tests/integration`) | 2 passed (about 93 s) |
| Frontend unit and component tests (`npm test`) | 26 passed |
| Frontend production build (`npm run build`) | Succeeded |
| Real-data checks | Both snapshots verified, the 54-file privacy scan was clean, and the API was started with uvicorn and served the real artifacts |

**Not verified by the auditor:** the dashboard's look at desktop, tablet and phone widths. No browser was available to the audit tooling. The user ran the UI locally.

## 8. Remaining work before real-data experiments

1. **Rebuild the real snapshot's artifacts with the topic layer and the embedding part:** topic clusters → graph with topics → features → metapath2vec and HGT → PageRank → score → baselines → explanations → evaluation. Choose and report the number of topic clusters.
2. **Confirm the provisional STEP 19 settings** (weights, `k`, confidence form) with the supervisor, then rerun scoring.
3. **Collect repeatedly with fixed settings** (`--max-videos 50`, daily) to build comparable snapshots for temporal stability.
4. **Create defensible relevance labels,** e.g. supervisor-judged channel pairs with a recorded `label_source`, if ranking quality is to be reported.
5. **Run and save the baselines on real data** (`python -m research.component_3.model.baselines louvain` and `node2vec`), and run the full evaluation, including sparse-data simulations.
6. **Decide the data retention policy.**
