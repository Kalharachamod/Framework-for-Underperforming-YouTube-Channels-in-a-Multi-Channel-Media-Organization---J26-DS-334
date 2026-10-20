# Component 3: Known Findings from Final Integration Testing

These findings come from STEP 34 (end-to-end integration testing). Each one cites its evidence. None of them changes the frozen methodology.

## Finding 1: Evaluation runtime

**Classification:** performance / computational limitation, not a software bug.

**Observation:** the full evaluation `eval-60ac93319497` recorded **67,504 s (about 18.75 h)** of wall-clock time.

**Evidence** (`computational_performance_results.parquet`):

| Phase | Recorded seconds |
|---|---|
| Main run (all 7 methods) | 1,703 |
| Temporal re-run on the earlier snapshot | 991 |
| Sparse simulation, seed 0 | 64,232, of which **62,287 s is one metapath2vec step** |
| Sparse simulation, seed 1 | 544, with the same metapath2vec step taking 52 s |

**Interpretation:**
- Sparse-data robustness re-runs the score, PPR, metapath2vec, Louvain and node2vec on every subsample. HGT and topic similarity are not part of the sparse runs.
- This repeated retraining is the systematic cost. node2vec is the slowest method in every phase (349–1,817 s), followed by the score (114–147 s, including topic encoding).
- **Most of the 18.75 h, however, is a single outlier.** One metapath2vec retraining took 62,287 s, while the identical step for the other seed took 52 s.
- The cause was not recorded. The findings report notes concurrent jobs on the same machine, and a suspended or overloaded machine is the likely explanation, but this is **not verified**.
- Without the outlier, the evaluation took about 5,200 s (about 1.4 h).

**Confirmation (16 Oct):** the evaluation of the newest snapshot (`eval-09420b1535eb`) ran the CLI default of 9 sparse runs (3 retain levels × 3 seeds) in **9,124 s (about 2.5 h)**. Its longest single step was 771 s (node2vec), with no outlier. This supports the view that the 18.75 h was a one-off anomaly, not the normal cost.

**Mechanism observed (16 Oct):** a dashboard completion job on a quick-analysis snapshot recorded 24,706 s for one node2vec run. The machine was asleep for most of it: Windows logged Kernel-Power event 42 (entering sleep) at 15:53 and a resume at 22:38 local time. The job's actual compute was about 11 minutes. This shows how system sleep inflates wall-clock timings. It does not prove the cause of the 10 Oct outlier, which was not recorded.

**Consequence:**
- Evaluation cost grows with the number of sparse settings. The CLI default of 3 retain levels × 3 seeds means 9 re-runs.
- Long runs should be kept on an awake, otherwise idle machine. `--skip-sparse` gives a quick evaluation without robustness results.
- No methodology change was made.

## Finding 2: Incomplete snapshot

**Classification:** data issue (incomplete collection).

- Snapshot `rs-20261015T174938Z` was collected while the network connection failed (`getaddrinfo failed`), with the system disk nearly full.
- **Collection log:**
  - Comments: 1,136 videos requested, 598 processed, 26 failed, 446 skipped, 66 with comments disabled; **718 comments failed storage** (`storage_error`).
  - The run ended with exit code 1 ("some items failed").
- The snapshot still passed structural validation (`research_ready`, `VALID_WITH_WARNINGS`), because missing comments are not detectable as malformed records.
- **It must not be treated as a complete dataset.** The reported thesis results use the complete snapshot `rs-20261010T081534Z`.
- If `rs-20261015T174938Z` results are shown, they must be labelled as coming from a partial collection.

## Finding 3: HGT channel-representation collapse

**Classification:** experimental / model limitation (a negative result).

**Evidence:** pairwise cosine similarity between the 18 channel embeddings.

| Snapshot | HGT | metapath2vec |
|---|---|---|
| `rs-20261010T081534Z` | 0.901 to 1.000, median 0.978; 30 % of pairs > 0.99 | 0.198 to 0.564, median 0.411 |
| `rs-20261015T174938Z` | 0.956 to 1.000, median 0.989; 44 % of pairs > 0.99 | 0.259 to 0.573, median 0.428 |

- Under the tested configuration (2 layers, 64 hidden units, 50 epochs, commenter→video link prediction), HGT does **not** sufficiently distinguish channels.
- A plausible reason is that the training objective optimises commenter–video links, never channel separation. With few channels and heavy message passing through shared video nodes, the channel vectors converge.
- The validation loss on the main snapshot (2.771) was far above the training loss (0.456), with ROC-AUC 0.859. This is consistent with a model that fits edges but does not generalise into channel-level structure.
- **The primary Audience Bridge Score uses metapath2vec, so this does not invalidate the main pipeline.** HGT stays the documented alternative, and this negative result is reported.

## Finding 4: Zero-evidence channel rankings

**Classification:** presentation / interpretation issue. The formula is correct.

- A source channel that shares no commenters with any other channel gets confidence 0, so every score is 0 for all 17 destinations. In the main snapshot, five channels are in this state (section 8.1 of [component3_final_results.md](component3_final_results.md)).
- Ties are broken deterministically by destination ID, so these channels still show **numerical ranks 1–17**.
- **Where this is already handled:**
  - The findings report writes "every score is 0: no shared commenters; rank 1 is only a tie-break".
  - The explanations carry the reason `no_shared_commenter_evidence`.
- **Where it is not:** the dashboard ranking views still display these rows with ranks.
- **Recommendation** (not implemented in this documentation step): show "No bridge evidence" instead of a rank when a source's scores are all 0.

## Finding 5: Bridges table column semantics

**Classification:** documentation of existing presentation.

In the Audience Bridges ranking table:
- **"Diffusion"** shows the **weighted diffusion component**, w_d × normalised PPR, in [0, 1/3] with default weights.
- **"Topic sim."** shows the **raw cosine topic similarity**, roughly 0.78–0.98 in this data, unweighted and unnormalised.

Both columns have tooltips stating this ("Diffusion component (weight × normalised Personalized PageRank)" and "Raw cosine similarity of the two content profiles (symmetric)"). The values are correct. Readers must not compare the two columns directly. Values were not changed.

## Finding 6: The score closely follows a simple overlap count

**Classification:** research finding / limitation (no code defect).

**Evidence:** comparison of the Audience Bridge Score with a simple-overlap baseline (rank destinations by shared commenters):

| Comparison with the simple-overlap baseline | Derana main (`abs-7cf3eab938ad`) | Derana newest, partial (`abs-ba1203506d95`) |
|---|---|---|
| Spearman, all pairs (13 sources with a defined ranking) | 0.989 | 0.984 |
| Mean per-source Spearman, **only pairs that share commenters** (11 sources) | **0.84** (min 0.50) | **0.78** (min −0.13) |
| Top-1 Jaccard | 0.833 | 0.778 |
| Sources whose top destination differs | **3 of 13** | **4 of 13** |

**Interpretation:**
- The agreement over all pairs (≈0.99) is inflated because both methods score every pair without shared commenters as 0.
- Among pairs with evidence, the score mostly follows the count (≈0.8) but changes the top bridge for about a quarter to a third of channels.
- With the current sparse data (most evidence pairs share only 1–3 commenters), the evidence-based confidence dominates the ranking. The diffusion, embedding and topic components mainly refine the order of closely matched pairs.
- **Consequence:** the thesis must not claim that the score finds bridges a simple count cannot. The defensible claims are that it gives a graded, explained ranking, separates tied counts, and adds content and structure; its added value over counting is **modest on this data** and should be re-tested on larger, same-period collections and against expert labels.

## Other integration observations (STEP 34)

- **Error responses:** a self pair (source = destination) returns HTTP 422 "self pairs are not scored". A malformed channel ID returns 404 "not part of research snapshot". Both are clear and safe.
- **Missing evaluation:** when a snapshot has no evaluation yet, the API returns an empty list and the dashboard shows "No evaluation has been run for this snapshot". This is correct empty-state behaviour.
