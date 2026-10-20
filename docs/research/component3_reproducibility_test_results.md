# Component 3: Reproducibility Test Results

*STEP 34, run on 2026-10-16.*

**Method:**
- Every stage was run **twice in memory** on the pilot snapshot `rs-20261010T072201Z` (3 channels, 45 videos, 862 comments).
- Each run used the stored pilot configuration (seed 42, 10 topics) and the same `.env` salt.
- Each output was compared (a) between the two runs and (b) with the artifact saved on 2026-10-10.
- Nothing was written to the project and no API calls were made.

The script was a temporary test harness that calls `research.component_3` functions directly. It is not part of the repository.

| Stage | Experiment ID (re-run = saved?) | Run 1 vs run 2 | Re-run vs saved artifact |
|---|---|---|---|
| Snapshot integrity | `rs-20261010T072201Z` | checksums OK | — |
| Topic similarity | `top-ae433bb1c3bb` (yes) | identical | identical |
| Graph | fingerprint equal (yes) | identical | identical |
| Graph features (4 tables) | `asof-20261010T072200Z` (yes) | — | identical (all 4 tables) |
| metapath2vec | `m2v-1cdd65e00974` (yes) | **bit-identical** vectors | **bit-identical** |
| HGT | `hgt-fa5dda2690ad` (yes) | max abs diff 0.0 | max abs diff 0.0 |
| PPR diffusion | `ppr-701d81ec03fa` (yes) | identical | identical |
| Audience Bridge Score | `abs-0d80cd37d57c` (yes) | identical | identical |
| Louvain | `louvain-bf68c16727f4` (yes) | identical | identical |
| node2vec | `node2vec-e7604c385711` (yes) | **bit-identical** vectors | identical similarity |
| Explainability | `xpl-f75609f82ada` (yes) | identical | identical except the `created_at` timestamp |
| Evaluation | `eval-7606eb79e6ef` (saved: `eval-b770fba998e1`) | — | **different ID, expected:** see below |

## Which outputs should be identical

- **Bit-identical:**
  - metapath2vec and node2vec (seeded, 1 worker, CRC32 hash)
  - PPR and topic similarity (deterministic algorithms, pinned encoder revision)
  - the score, Louvain (seeded), the graph, features and explanation tables
- **Identical on the same machine and library build:** HGT (seeded CPU training). Here it was exactly identical. On different hardware or torch builds, small floating-point differences are possible. They are not expected to change rankings, but this was not tested.
- **Never identical:** timestamps (`created_at`) and measured runtimes and memory.

## Evaluation ID difference (explained, not a defect)

- **Cause:** the saved pilot evaluation was produced by evaluation code **version 1.0** (10 Oct). The code is now **version 1.1** (commit `e7185f3`, 11 Oct: "pair snapshots with the latest earlier snapshot of the same channels"). The version is part of the evaluation ID by design, so the ID changes.
- **Inputs are unchanged:** all seven method experiment IDs used inside the evaluation equal the saved ones.
- **Temporal status also changed:** the old version reported `insufficient_temporal_data`; the re-run reports `ok`. The temporal analysis covers **all comparable snapshot pairs in the store**, not only the evaluated snapshot (`temporal_snapshots = None`). Newer 18-channel snapshots now provide a comparable pair.
- **Recommendation:** when reporting temporal stability, cite the snapshot pair, or pass `temporal_snapshots` explicitly. This keeps the incomplete `rs-20261015T174938Z` out of temporal pairs.

## Score and ranking stability

- Score, base, confidence and rank columns are identical across runs.
- Ranks are monotone per source, and ties are broken deterministically by destination ID.

## Verdict

**PASS.** Every deterministic stage reproduces exactly, both between runs and against the artifacts saved six days earlier. The evaluation ID change is caused by a documented code-version bump.
