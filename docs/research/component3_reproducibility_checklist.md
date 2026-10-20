# Component 3: Reproducibility Checklist

*STEP 33, §14.* Checked against the code on 2026-10-15.

| Item | Status | Where |
|---|---|---|
| Immutable input snapshots with IDs | ✅ | `rs-<UTC time>` Parquet snapshots |
| Data validation before modelling | ✅ | STEP 12 DuckDB validation report |
| Graph fingerprint checked by downstream stages | ✅ | STEP 13 manifest |
| `as_of` cut-off for time-dependent stages | ✅ | graph features, topic similarity (future `as_of` rejected) |
| Fixed seeds | ✅ | metapath2vec 42, HGT 42, Louvain 42, node2vec 42, sparse robustness 0/1/2 |
| Deterministic embedding training | ✅ | metapath2vec / node2vec: 1 worker + CRC32 hash |
| Deterministic tie-breaking | ✅ | ABS rank by score, then destination ID |
| Content-addressed experiment IDs | ✅ | `m2v-`, `hgt-`, `ppr-`, topic, ABS, Louvain, node2vec, `eval-` hashes of inputs + config |
| Write-once results | ✅ | an existing experiment directory is never overwritten (tested) |
| Configuration stored with results | ✅ | `experiment.json` / manifest per run |
| Library versions stored with results | ✅ | Python, numpy, pandas, gensim, torch, torch_geometric, networkx versions in manifests |
| Pinned pretrained model | ✅ | `intfloat/multilingual-e5-small` at a pinned revision |
| Pinned dependency versions | ⚠️ Partial | `requirements.txt` uses `>=` lower bounds. Exact versions are recorded per run, but a fresh install may differ. Recommended: export a lock file (`pip freeze`) for the thesis appendix |
| Secrets outside the repo | ✅ | `.env` only (API key, Supabase, `COMMENTER_HASH_SALT`) |
| Pseudonymisation reproducible | ✅ | same salt → same `anon_` IDs; different salt → unlinkable |
| Tests without external services | ✅ | no real YouTube API or production Supabase in tests |
| Hyperparameters tuned? | ❌ (by design) | all defaults are documented and untuned; stated as a limitation |
| HGT bit-exact across hardware | ⚠️ | seeded on CPU; GPU or different torch builds may give small numeric differences |
| Raw data redistributable | ❌ | YouTube terms and privacy: data is not shared; the pipeline and snapshot IDs are |

**To reproduce a run:** use the same snapshot, the same `.env` salt and the same configuration. The pipeline then produces the same experiment IDs. A matching ID means the inputs and configuration are identical.
