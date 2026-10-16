# Component 3 Controlled Real-Data Pilot (STEP 26)

Run: 2026-10-10T07:39:19+00:00 to 2026-10-10T07:49:00+00:00 (UTC) · Snapshot: `rs-20261010T072201Z`

> Pilot results validate the pipeline on a small real sample. They do not show audience migration, causal influence, subscriber transfer or future growth, and three channels are too few for general conclusions.

## Configuration

| Setting | Value |
|---|---|
| Channels | TV Derana (`UCRDDfbYPHX_GUJ4lcQYTc8A`), Dream Star (`UCs8gVM6lPhRZk3L_zZmedpw`), Derana City Of Music (`UCrZs77rjxjbn_BMaSccMXnQ`) |
| Channel note | eTunes is not in the approved Derana channel set; Derana City Of Music is the music-profile substitute. |
| Videos per channel (max) | 15 |
| Comment threads per video (max) | 50 (all replies fetched: False) |
| Observation window | newest videos, no date limit |
| Retries / timeout | 3 retries, 30.0 s |
| Quota cap | 500 units |
| Topic clusters / seed | 10 / 42 |
| Sparse simulations | fractions (0.5,), seeds (0, 1) |

## Preflight

| Check | Status | Detail |
|---|---|---|
| environment variables | pass | YOUTUBE_API_KEY: set, COMMENTER_HASH_SALT: set, SUPABASE_DB_URL: set |
| YouTube Data API v3 client | pass | client configured (key present, not a placeholder) |
| channel ids | pass | 3 resolved from configuration |
| shared database (read-only) | pass | reachable; 3 of 3 pilot channels already stored |
| output directories | pass | data directory writable |
| disk space | pass | 23.0 GB free (minimum 1.0 GB) |
| pipeline dependencies | pass | all importable |
| commenter pseudonymization | pass | salt configured; ids are HMAC-SHA256 pseudonyms |
| existing snapshots intact | pass | 3 research snapshot(s) verified |
| new snapshot, no overwrite | pass | a new rs-<timestamp> id is created; existing ids are refused by create_research_snapshot |
| quota estimate | pass | upper bound 53 units (cap 500) |

Quota estimate (upper bound): 53 units {'channels.list': 2, 'playlistItems.list': 3, 'videos.list': 3, 'commentThreads.list': 45, 'comments.list': 0}.

## Collection (YouTube Data API v3)

| Measure | Value |
|---|---|
| API requests | 50 (50 succeeded, 0 failed, 0 retries) |
| Quota units used | 50 |
| Requests by endpoint | {'channels.list': 2, 'commentThreads.list': 42, 'playlistItems.list': 3, 'videos.list': 3} |
| Channels collected | 3 of 3 |
| Videos collected | 45 (new 15, updated 30, unchanged 0) |
| Comments collected | 862 (789 top-level, 73 replies) |
| Videos with zero public comments | 3 |
| Videos with comments disabled | 0 |
| Videos without a public comment count | 0 |
| Collection failures | channels none; videos none; comments none |
| Pilot snapshot rows | {'channels': 3, 'videos': 45, 'comments': 862} |
| Collection time | 97.19 s |

## Pipeline stages

| Stage | Status | Time (s) | Artifact | Details |
|---|---|---|---|---|
| research_data | completed | 3.78 | — | {"quality": "VALID", "counts": {"channels": 3, "videos": 45, "comments": 862, "top_level_comments": 789, "replies": 73, "unique_commenters": 708}, "commenters_on_multiple_channels": 1} |
| topics | completed | 137.89 | `top-ae433bb1c3bb` | {"videos": 45, "usable_videos": 45, "channels_with_profile": "3/3", "clusters": 10} |
| graph | completed | 13.23 | `1ca246a1d945140f` | {"node_counts": {"channel": 3, "video": 45, "commenter": 708, "topic": 10}, "edge_counts": {"comments": 763, "belongs_to": 45, "participates_in": 709, "has_topic": 45}, "commenters_on_multiple_channels": 1} |
| features | completed | 7.25 | `asof-20261010T072200Z` | {"channel_pairs_with_shared_commenters": 1} |
| metapath2vec | completed | 50.04 | `m2v-1cdd65e00974` | {"embedded_nodes": 766, "metapaths_used": ["CVC", "CVChVC", "ChVCVCh", "VChV", "VTV"], "metapaths_skipped": []} |
| hgt | completed | 4.02 | `hgt-fa5dda2690ad` | {"embedded_nodes": 766, "split": "random_edge_split_fallback"} |
| ppr_diffusion | completed | 0.13 | `ppr-701d81ec03fa` | {"sources": 3, "skipped_sources": 0, "reachable_pairs": 2, "pairs": 6} |
| audience_bridge | completed | 0.49 | `abs-0d80cd37d57c` | {"pairs": 6, "scored": 6, "status_counts": {"ok": 6}} |
| louvain | completed | 0.34 | `louvain-bf68c16727f4` | {"communities": 2, "modularity": 0.0, "isolated_channels": 1} |
| node2vec | completed | 6.93 | `node2vec-e7604c385711` | {"embedded_nodes": 756} |
| explainability | completed | 0.64 | `xpl-f75609f82ada` | {"status_counts": {"complete": 6}} |
| evaluation | completed | 180.39 | `eval-b770fba998e1` | {"methods": {"audience_bridge_score": "ok", "ppr_diffusion": "ok", "topic_similarity": "ok", "metapath2vec_similarity": "ok", "hgt_similarity": "ok", "louvain": "ok", "node2vec": "ok"}, "labels": "none supplied", "temporal": "insufficient_temporal_data", "sparse_runs": 2} |

## Research validity checks

| Check | Status | Detail |
|---|---|---|
| scored channels are pilot channels | pass | 3 source channels |
| no self pairs | pass | source != destination |
| scores finite and in [0, 1] | pass | 6 scores, 6 confidence values |
| decomposition matches the formula | pass | max reconstruction error 0.0e+00 |
| missing evidence not scored as zero | pass | 0 incomplete pair(s) carry no score |
| baselines use the same snapshot and graph | pass | same graph: ['louvain', 'node2vec'] |
| topic profiles from the pilot channels' videos | pass | 3/3 channels with a profile |
| relevance metrics not reported without labels | pass | no labels supplied |
| temporal evaluation reported honestly | pass | no consecutive pair of snapshots has comparable observation windows |
| artifact provenance | pass | all artifacts reference the pilot snapshot |
| no commenter identifiers in derived artifacts | pass | scanned scores, explanations, evaluation, diffusion and baselines |
| existing snapshots unchanged | pass | 3 earlier snapshot(s) verified |

## Audience Bridge Score results (top destination per source)

| Source | Destination | Score | Diffusion | Embedding | Topic | Confidence | Shared commenters |
|---|---|---|---|---|---|---|---|
| TV Derana | Dream Star | 0.0833 | 0.3333 | 0.0000 | 0.0000 | 0.2500 | 1 |
| Derana City Of Music | TV Derana | 0.0000 | 0.0000 | 0.3333 | 0.3333 | 0.0000 | 0 |
| Dream Star | TV Derana | 0.1667 | 0.3333 | 0.0000 | 0.3333 | 0.2500 | 1 |

## Evaluation

| Comparison | Metric | Value | Sources | Status / reason |
|---|---|---|---|---|
| audience_bridge_score vs ppr_diffusion | spearman | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs ppr_diffusion | kendall | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs ppr_diffusion | topk_jaccard@1 | +1.000 | 3 | ok |
| audience_bridge_score vs ppr_diffusion | topk_jaccard@3 | +1.000 | 3 | ok |
| audience_bridge_score vs ppr_diffusion | topk_jaccard@5 | +1.000 | 3 | ok |
| audience_bridge_score vs topic_similarity | spearman | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs topic_similarity | kendall | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs topic_similarity | topk_jaccard@1 | +0.667 | 3 | ok |
| audience_bridge_score vs topic_similarity | topk_jaccard@3 | +1.000 | 3 | ok |
| audience_bridge_score vs topic_similarity | topk_jaccard@5 | +1.000 | 3 | ok |
| audience_bridge_score vs metapath2vec_similarity | spearman | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs metapath2vec_similarity | kendall | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs metapath2vec_similarity | topk_jaccard@1 | +0.333 | 3 | ok |
| audience_bridge_score vs metapath2vec_similarity | topk_jaccard@3 | +1.000 | 3 | ok |
| audience_bridge_score vs metapath2vec_similarity | topk_jaccard@5 | +1.000 | 3 | ok |
| audience_bridge_score vs hgt_similarity | spearman | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs hgt_similarity | kendall | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs hgt_similarity | topk_jaccard@1 | +0.000 | 3 | ok |
| audience_bridge_score vs hgt_similarity | topk_jaccard@3 | +1.000 | 3 | ok |
| audience_bridge_score vs hgt_similarity | topk_jaccard@5 | +1.000 | 3 | ok |
| audience_bridge_score vs louvain | spearman | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs louvain | kendall | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs louvain | topk_jaccard@1 | +1.000 | 3 | ok |
| audience_bridge_score vs louvain | topk_jaccard@3 | +1.000 | 3 | ok |
| audience_bridge_score vs louvain | topk_jaccard@5 | +1.000 | 3 | ok |
| audience_bridge_score vs node2vec | spearman | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs node2vec | kendall | — | 0 | undefined: fewer than 3 common items with defined scores |
| audience_bridge_score vs node2vec | topk_jaccard@1 | +0.333 | 3 | ok |
| audience_bridge_score vs node2vec | topk_jaccard@3 | +1.000 | 3 | ok |
| audience_bridge_score vs node2vec | topk_jaccard@5 | +1.000 | 3 | ok |

## Errors, warnings and limitations

- Small sample: 3 channels give 6 ordered pairs and 2 candidate destinations per source; rank correlations need at least 3 shared destinations per source, so they are undefined here.
- No relevance labels: ranking quality (precision, recall, NDCG, MRR) is not computed.
- Single pilot snapshot: temporal stability cannot be evaluated.
- The pilot snapshot becomes the newest research snapshot, so commands and the dashboard default to it until the next full collection; select the full snapshot explicitly where needed.
- This report comes from a pipeline rerun on the existing pilot snapshot (collection run started 2026-10-10T07:33:56+00:00); no new API calls were made. Stage times are from the rerun.
- Top-k overlap for k >= 2 is trivially 1, because each source has only 2 candidate destinations.
- Shared-commenter evidence per channel pair: max 1, median 0 (confidence k = 3). This is below k for every pair, so scores are small and say little about audience bridges at this collection depth.

**Recommendation:** pipeline validated: scale to the full approved channel set, but at the full collection depth (e.g. 50 videos, 100 threads per video); the pilot depth yields too little shared-commenter evidence for research conclusions
