# Component 3: Integration Test Results

*STEP 34, run on 2026-10-15/16.* The plan is in [component3_end_to_end_test_plan.md](component3_end_to_end_test_plan.md).

**Data used:**
- pilot snapshot `rs-20261010T072201Z`: stage re-runs
- main snapshot `rs-20261010T081534Z`: API and results
- newest snapshot `rs-20261015T174938Z`: live collection, pipeline and dashboard
- synthetic data: the offline integration test

No extra YouTube API calls were made for testing. Production Supabase was not queried by the tests.

| Stage | Status | Evidence | Issues |
|---|---|---|---|
| Data collection | PASS (with data issue) | User-run collection on 2026-10-15: 18/18 channels and 851 videos collected. Failures were listed per item and the run exited with code 1 | Network outage: 26 videos failed, 446 skipped, 718 comments not stored (Finding 2). The failure was reported, not silent |
| Storage | PASS | Supabase rows were exported to a new immutable snapshot with checksums; `verify_research_snapshot` OK; DuckDB views queryable; repeated counts deterministic. The offline test passes the collector → PostgreSQL → Parquet path | — |
| Validation | PASS | Pilot: `research_ready`, `VALID`, 0 duplicate comment IDs, 0 null timestamps, 0 non-pseudonymised commenter IDs, all relationships resolve. Newest: `VALID_WITH_WARNINGS` (likes > views on 4 videos; 133 comments dated before their video) | Missing comments cannot be detected structurally |
| Graph | PASS | 4 node types and 4 relations; 0 self-loops; 0 duplicate edges; 0 isolated nodes; 0 negative weights; fingerprint equals the saved one. Newest: 10 topic nodes, 1,136 `has_topic` edges | Empty values in edge attributes are "not applicable" by relation (for example `video_count` on `comments`) |
| Graph features | PASS | 4 tables identical to saved; 0 inf; 0 negative values; 0 null IDs | Empty values are type-specific "not applicable" columns, never filled with 0 |
| metapath2vec | PASS | 766/766 nodes embedded (pilot) and 12,672/12,672 (newest); dimension 64; 0 NaN/inf; all 5 metapaths; bit-identical re-run | — |
| HGT | PASS (negative result) | Runs and is reproducible (difference 0.0); finite. Pilot used a recorded random fallback (1 warm edge < 20). Newest snapshot: temporal split, 96 validation edges, ROC-AUC 0.946 | Channel embeddings collapse (cosine median 0.978–0.989) (Finding 3) |
| PageRank | PASS | 0 self pairs; 0 negative; unreachable destinations exactly 0; α 0.85; every source converged (146 iterations, residual < 1e-10, mass 1.0); identical re-run | — |
| Topic similarity | PASS | 10 clusters; values in [-1, 1]; symmetric; identical re-run; pinned encoder | Raw cosine is compressed (0.78–0.98) |
| Confidence | PASS | Range [0, 0.923] on the main snapshot (< 1); confidence = evidence × coverage recomputed exactly (difference 0) | Uses shared commenters and topic coverage only. Interaction, coverage and temporal evidence are explanation-only by design. Popularity bias documented |
| Audience Bridge Score | PASS | score = base × confidence (difference 0); base = Σ w·norm (difference 0); ranks monotone per source; all 23 output columns present, including `snapshot_id` and `experiment_id`; identical re-run | Three-part formula (the two-part form is an ablation). Zero-evidence sources show ranks (Finding 4) |
| Louvain | PASS | Re-run identical to saved; metadata stored. Newest: 8 communities, modularity 0.209 | — |
| node2vec | PASS | Bit-identical vectors; similarity identical to saved; 0 NaN | Slowest method (Finding 1) |
| Evaluation | PASS | Pilot re-run: all 7 methods `ok`, labels "none supplied", temporal `ok`, 2 sparse runs, 5 tables. Main run `eval-60ac93319497` complete | 18.75 h recorded runtime, dominated by one outlier step. Temporal pairs use every snapshot in the store. ID changed with code version 1.1 (explained) |
| Explainability | PASS | 4 tables identical to saved (except `created_at`); no migration or causal wording; no commenter IDs; decomposition exact | — |
| Backend | PASS | 60 API calls over latest + main snapshots: all endpoints 200 with valid input, at most 276 ms, no `anon_` or `commenter:` IDs in any response. Errors are clear: missing snapshot 404, unknown channel 404, self pair 422, invalid table 422, bad paging or limit 422, unknown route 404. Missing evaluation returns an empty list | — |
| Dashboard | PASS | `tsc` clean, vitest 48/48, production build OK; no mock data in app code. Headless screenshots of Overview, Bridges, Explainability, Evaluation, Graph and Topics show real data; direction is explicit; empty states are correct ("No evaluation has been run for this snapshot") | Zero-evidence rank display (Finding 4); mixed column semantics in the Bridges table, with tooltips (Finding 5) |
| Reproducibility | PASS | See [component3_reproducibility_test_results.md](component3_reproducibility_test_results.md) | No lock file (lower-bound requirements) |

## Error handling

| Case | Result |
|---|---|
| Missing snapshot (all stage CLIs) | Exit code 1 with "research snapshot … does not exist"; no artifacts written |
| No bridge run for explanations | Exit code 1 with an instruction to run the score first |
| Invalid weights (sum ≠ 1) | Exit code 1, "w_diffusion + w_embedding + w_topic must equal 1" |
| Empty graph, missing topic, missing embedding, corrupted data, baseline failure | Covered by unit tests in `tests/component_3/*`. Missing components give NULL with a `score_status`, never 0 |
| API unavailable / frontend timeout | Covered by frontend tests ("API Connected" indicator and error states) |
| Write-once conflict | `FileExistsError` "already exists with different results" |

## Automated suites

| Suite | Result |
|---|---|
| `tests/integration/test_component3_end_to_end.py` (offline, synthetic) | 2 passed |
| `tests/backend` + `tests/component_3` | 317 passed. The 2 failures in the full run were environment issues (disk 0.2 GB free; MemoryError while loading the model). Both pass after freeing disk space (pilot 21/21; topic tests pass) |
| Frontend | `tsc -b` clean; vitest 48/48; build OK |

## Failure classification and fixes

| Issue | Class | Action |
|---|---|---|
| Full disk caused test failures and likely the 718 `storage_error` comments | A: environment | The user freed disk space; tests re-run and pass |
| Network outage during collection | A / C: environment / data | Documented; snapshot marked incomplete |
| Pipeline run without `--topics 10` / `--topic-run` (graph without topics) | B: configuration | Derived artifacts deleted and rebuilt in the correct order; the reproduction guide documents the order |
| Evaluation ID differs from the saved pilot run | B: version | Explained (evaluation version 1.1); no change needed |
| HGT channel collapse | F: methodological | **Documented, not changed** (alternative method only) |
| Zero-evidence ranks; column semantics | E: presentation | Documented; UI unchanged |

No code was changed in STEP 34.

## Readiness

**READY WITH MINOR TECHNICAL ISSUES.** The research pipeline works end to end and reproduces exactly. The remaining issues are minor engineering or data issues and are documented:
- incomplete newest snapshot
- evaluation runtime
- zero-evidence rank display
- missing lock file
