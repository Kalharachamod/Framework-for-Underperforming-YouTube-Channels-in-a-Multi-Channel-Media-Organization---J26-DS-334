# Component 3 Full-Scale Multi-Channel Experiment (STEP 27)

Run: 2026-10-10T11:12:49+00:00 to 2026-10-11T06:09:24+00:00 (UTC) · Snapshot: `rs-20261010T081534Z`

> Pilot results validate the pipeline on a small real sample. They do not show audience migration, causal influence, subscriber transfer or future growth, and three channels are too few for general conclusions.

## Configuration

| Setting | Value |
|---|---|
| Channels | 18: TV Derana (owned), Ada Derana (owned), FM Derana (owned), Derana Shorts (owned), Ada Derana News Channel (owned), Ada Derana Education (owned), Derana City Of Music (owned), Derana 60 Plus (owned), Ada Derana Sports (owned), Ada Derana Biz (owned), Ada Derana World News (owned), TV Derana LIVE (owned), Derana Little Star (owned), Ada Derana Tamil (owned), Ada Derana News Channel | English (owned), Dream Star (owned), Lokaya Saha Lokayo (owned), Pulse.lk (owned) |
| Channel note | The team decided on the Derana-only channel set (18 confirmed owned channels, no competitor group); the plan's 16 owned + 41 competitor channels are reported as a registry gap, not invented. |
| Videos per channel (max) | 50 |
| Comment threads per video (max) | 100 (all replies fetched: True) |
| Observation window | newest videos, no date limit |
| Retries / timeout | 3 retries, 30.0 s |
| Quota cap | 3000 units |
| Topic clusters / seed | 10 / 42 |
| Sparse simulations | fractions (0.5,), seeds (0, 1) |

## Preflight

| Check | Status | Detail |
|---|---|---|
| environment variables | pass | YOUTUBE_API_KEY: set, COMMENTER_HASH_SALT: set, SUPABASE_DB_URL: set |
| YouTube Data API v3 client | pass | client configured (key present, not a placeholder) |
| channel ids | pass | 18 selected from configuration ({'owned': 18}) |
| channel registry vs research plan | warn | competitor: plan 41, configured 0; owned: plan 16, configured 18 (missing channels are not invented; the run uses the configured set) |
| shared database (read-only) | pass | reachable; 18 of 18 selected channels already stored |
| output directories | pass | data directory writable |
| disk space | pass | 22.4 GB free (minimum 2.0 GB) |
| pipeline dependencies | pass | all importable |
| commenter pseudonymization | pass | salt configured; ids are HMAC-SHA256 pseudonyms |
| existing snapshots intact | pass | 4 research snapshot(s) verified |
| new snapshot, no overwrite | pass | a new rs-<timestamp> id is created; existing ids are refused by create_research_snapshot |
| quota estimate | pass | upper bound 1523 units (cap 3000) |
| storage estimate | pass | about 0.07 GB, scaled from pilot rs-20261010T072201Z (3.7 MB for 45 videos) |

Quota estimate (upper bound): 1523 units {'channels.list': 2, 'playlistItems.list': 18, 'videos.list': 18, 'commentThreads.list': 900, 'comments.list': 585}.

## Collection (YouTube Data API v3)

| Measure | Value |
|---|---|
| API requests | 606 (554 succeeded, 52 failed, 1 retries) |
| Quota units used | 605 |
| Requests by endpoint | {'channels.list': 2, 'commentThreads.list': 508, 'comments.list': 60, 'playlistItems.list': 18, 'videos.list': 18} |
| Channels collected | 18 of 18 |
| Videos collected | 851 (new 93, updated 758, unchanged 0) |
| Comments collected | 10823 (8947 top-level, 1876 replies) |
| Videos with zero public comments | 344 |
| Videos with comments disabled | 51 |
| Videos without a public comment count | 51 |
| Collection failures | channels none; videos none; comments none |
| Pilot snapshot rows | {'channels': 18, 'videos': 851, 'comments': 10823} |
| Collection time | 1165.56 s |

## Channel registry

| Measure | Value |
|---|---|
| Configured channels | 18 {'owned': 18} |
| Selected for this run | 18 (groups ['owned', 'competitor']) |
| Research plan | {'competitor': 41, 'owned': 16} |
| Gaps | {'competitor': {'expected': 41, 'configured': 0}, 'owned': {'expected': 16, 'configured': 18}} |
| Duplicate / invalid ids | none / none |

## Data quality by channel

Comment counts are bounded by the collection limits (videos per channel, threads per video) and differ with channel size and content, so commenter counts are not comparable as audience sizes.

| Channel | Group | Videos | With comments | Zero public comments | Count hidden | Comments | Top-level | Unique commenters | Stored / public | Video window | Comment window |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Ada Derana Sports | owned | 50 | 38 | 12 | 0 | 1814 | 1284 | 1301 | 0.739 | 2026-02-14 .. 2026-09-21 | 2026-02-14 .. 2026-10-04 |
| Dream Star | owned | 50 | 48 | 2 | 0 | 1524 | 1317 | 1049 | 0.776 | 2026-01-18 .. 2026-10-05 | 2026-01-18 .. 2026-10-10 |
| TV Derana | owned | 50 | 34 | 16 | 0 | 1431 | 1065 | 944 | 0.779 | 2026-10-07 .. 2026-10-10 | 2026-10-07 .. 2026-10-10 |
| Derana Little Star | owned | 50 | 49 | 1 | 0 | 1339 | 1212 | 834 | 0.956 | 2026-08-15 .. 2026-09-16 | 2026-08-15 .. 2026-10-09 |
| Ada Derana | owned | 50 | 38 | 12 | 0 | 1244 | 1011 | 928 | 0.422 | 2026-10-09 .. 2026-10-10 | 2026-10-09 .. 2026-10-10 |
| Derana 60 Plus | owned | 50 | 45 | 5 | 0 | 915 | 783 | 417 | 0.865 | 2026-03-29 .. 2026-09-11 | 2026-03-29 .. 2026-10-03 |
| FM Derana | owned | 50 | 42 | 8 | 0 | 906 | 731 | 615 | 0.65 | 2026-07-24 .. 2026-10-08 | 2026-07-24 .. 2026-10-10 |
| Derana City Of Music | owned | 50 | 48 | 2 | 0 | 694 | 656 | 548 | 0.99 | 2022-03-06 .. 2022-06-05 | 2022-03-07 .. 2026-08-01 |
| Lokaya Saha Lokayo | owned | 50 | 33 | 16 | 1 | 384 | 364 | 364 | 0.705 | 2025-05-02 .. 2026-10-08 | 2025-05-24 .. 2026-10-09 |
| TV Derana LIVE | owned | 50 | 29 | 21 | 0 | 291 | 263 | 261 | 0.556 | 2026-07-10 .. 2026-10-07 | 2026-07-12 .. 2026-10-10 |
| Ada Derana Education | owned | 50 | 14 | 36 | 0 | 128 | 123 | 125 | 0.928 | 2026-08-08 .. 2026-10-09 | 2026-08-18 .. 2026-10-09 |
| Ada Derana News Channel | owned | 50 | 21 | 29 | 0 | 116 | 104 | 103 | 1.0 | 2026-09-23 .. 2026-10-09 | 2026-09-23 .. 2026-10-09 |
| Derana Shorts | owned | 50 | 9 | 41 | 0 | 24 | 24 | 23 | 1.0 | 2026-06-25 .. 2026-10-01 | 2026-06-26 .. 2026-09-08 |
| Ada Derana Biz | owned | 50 | 4 | 46 | 0 | 9 | 6 | 9 | 1.0 | 2025-12-18 .. 2026-09-24 | 2025-12-31 .. 2026-03-12 |
| Ada Derana Tamil | owned | 50 | 2 | 48 | 0 | 2 | 2 | 2 | 1.0 | 2026-09-30 .. 2026-10-09 | 2026-10-05 .. 2026-10-09 |
| Pulse.lk | owned | 50 | 2 | 48 | 0 | 2 | 2 | 2 | 1.0 | 2026-09-09 .. 2026-10-10 | 2026-09-14 .. 2026-10-09 |
| Ada Derana News Channel \| English | owned | 50 | 0 | 0 | 50 | 0 | 0 | 0 | — | 2026-09-22 .. 2026-10-09 | — |
| Ada Derana World News | owned | 1 | 0 | 1 | 0 | 0 | 0 | 0 | — | 2025-10-07 .. 2025-10-07 | — |

## Difference from the controlled pilot

| Measure | Pilot | This run |
|---|---|---|
| Snapshot rows | {'channels': 3, 'videos': 45, 'comments': 862} | {'channels': 18, 'videos': 851, 'comments': 10823} |
| Quota units | 50 | 605 |
| Depth (videos, threads) | [15, 50] | [50, 100] |

## Pipeline stages

| Stage | Status | Time (s) | Artifact | Details |
|---|---|---|---|---|
| research_data | completed | 1.39 | — | {"quality": "VALID_WITH_WARNINGS", "counts": {"channels": 18, "videos": 851, "comments": 10823, "top_level_comments": 8947, "replies": 1876, "unique_commenters": 7336}, "commenters_on_multiple_channels": 175} |
| topics | completed | 80.19 | `top-6bf1e474f003` | {"videos": 851, "usable_videos": 851, "channels_with_profile": "18/18", "clusters": 10} |
| graph | completed | 6.72 | `ba6f77f20f19fc59` | {"node_counts": {"channel": 18, "video": 851, "commenter": 7336, "topic": 10}, "edge_counts": {"comments": 9044, "belongs_to": 851, "participates_in": 7525, "has_topic": 851}, "commenters_on_multiple_channels": 175} |
| features | completed | 6.49 | `asof-20261010T081519Z` | {"channel_pairs_with_shared_commenters": 41} |
| metapath2vec | completed | 1.64 | `m2v-996c59079f77` | {"embedded_nodes": 8215, "metapaths_used": ["CVC", "CVChVC", "ChVCVCh", "VChV", "VTV"], "metapaths_skipped": []} |
| hgt | completed | 1.63 | `hgt-c132bac52fc0` | {"embedded_nodes": 8215, "reused": true, "split": "temporal"} |
| ppr_diffusion | completed | 1.07 | `ppr-528039331d78` | {"sources": 18, "skipped_sources": 0, "reachable_pairs": 156, "pairs": 306} |
| audience_bridge | completed | 9.44 | `abs-7cf3eab938ad` | {"pairs": 306, "scored": 306, "status_counts": {"ok": 306}} |
| louvain | completed | 8.51 | `louvain-df378406c68c` | {"communities": 8, "modularity": 0.1929633991740573, "isolated_channels": 5} |
| node2vec | completed | 512.32 | `node2vec-421e71b0a640` | {"embedded_nodes": 8205} |
| explainability | completed | 17.79 | `xpl-3baba8a75699` | {"status_counts": {"complete": 306}} |
| evaluation | completed | 67504.14 | `eval-60ac93319497` | {"methods": {"audience_bridge_score": "ok", "ppr_diffusion": "ok", "topic_similarity": "ok", "metapath2vec_similarity": "ok", "hgt_similarity": "ok", "louvain": "ok", "node2vec": "ok"}, "labels": "none supplied", "temporal": "ok", "sparse_runs": 2} |

## Research validity checks

| Check | Status | Detail |
|---|---|---|
| scored channels are pilot channels | pass | 18 source channels |
| no self pairs | pass | source != destination |
| scores finite and in [0, 1] | pass | 306 scores, 306 confidence values |
| decomposition matches the formula | pass | max reconstruction error 0.0e+00 |
| missing evidence not scored as zero | pass | 0 incomplete pair(s) carry no score |
| baselines use the same snapshot and graph | pass | same graph: ['louvain', 'node2vec'] |
| topic profiles from the pilot channels' videos | pass | 18/18 channels with a profile |
| relevance metrics not reported without labels | pass | no labels supplied |
| temporal evaluation reported honestly | pass | None |
| artifact provenance | pass | all artifacts reference the pilot snapshot |
| no commenter identifiers in derived artifacts | pass | scanned scores, explanations, evaluation, diffusion and baselines |
| existing snapshots unchanged | pass | 4 earlier snapshot(s) verified |

## Audience Bridge Score results (top destination per source)

| Source | Destination | Score | Diffusion | Embedding | Topic | Confidence | Shared commenters |
|---|---|---|---|---|---|---|---|
| Ada Derana Tamil | Ada Derana | 0.0000 | 0.0000 | 0.1849 | 0.3333 | 0.0000 | 0 |
| Ada Derana | Ada Derana Sports | 0.8595 | 0.3333 | 0.3333 | 0.3156 | 0.8750 | 21 |
| Ada Derana Sports | Ada Derana | 0.8715 | 0.3333 | 0.3293 | 0.3333 | 0.8750 | 21 |
| Derana Little Star | Dream Star | 0.8976 | 0.3333 | 0.3333 | 0.3057 | 0.9231 | 36 |
| FM Derana | Ada Derana Sports | 0.4654 | 0.1877 | 0.2628 | 0.2941 | 0.6250 | 5 |
| TV Derana | Dream Star | 0.5017 | 0.0892 | 0.3093 | 0.2285 | 0.8000 | 12 |
| Ada Derana Biz | Ada Derana Sports | 0.2193 | 0.3333 | 0.2486 | 0.2952 | 0.2500 | 1 |
| Ada Derana Education | Ada Derana Sports | 0.3322 | 0.3333 | 0.2245 | 0.2727 | 0.4000 | 2 |
| Pulse.lk | Ada Derana Tamil | 0.0000 | 0.0000 | 0.2755 | 0.1571 | 0.0000 | 0 |
| Ada Derana News Channel | Ada Derana Sports | 0.3364 | 0.3333 | 0.2257 | 0.2820 | 0.4000 | 2 |
| Lokaya Saha Lokayo | Ada Derana | 0.2511 | 0.1058 | 0.2659 | 0.2559 | 0.4000 | 2 |
| Derana 60 Plus | Dream Star | 0.8408 | 0.3333 | 0.3333 | 0.2675 | 0.9000 | 27 |
| Derana Shorts | Ada Derana Tamil | 0.0000 | 0.0000 | 0.2859 | 0.2551 | 0.0000 | 0 |
| TV Derana LIVE | Dream Star | 0.6347 | 0.3333 | 0.2951 | 0.2442 | 0.7273 | 8 |
| Ada Derana World News | Ada Derana Tamil | 0.0000 | 0.0000 | 0.2188 | 0.1567 | 0.0000 | 0 |
| Derana City Of Music | Lokaya Saha Lokayo | 0.1966 | 0.3333 | 0.1892 | 0.2638 | 0.2500 | 1 |
| Dream Star | Derana 60 Plus | 0.8855 | 0.3333 | 0.3333 | 0.3172 | 0.9000 | 27 |
| Ada Derana News Channel \| English | Ada Derana Tamil | 0.0000 | 0.0000 | 0.2315 | 0.2214 | 0.0000 | 0 |

## Score component and confidence distributions (scored pairs)

| Measure | Pairs | Min | Median | P90 | Max | Share = 0 |
|---|---|---|---|---|---|---|
| audience_bridge_score | 306 | 0.0 | 0.0 | 0.3146 | 0.8976 | 0.732 |
| diffusion_contribution | 306 | 0.0 | 0.0001 | 0.148 | 0.3333 | 0.49 |
| embedding_contribution | 306 | 0.0 | 0.1745 | 0.2953 | 0.3333 | 0.059 |
| topic_contribution | 306 | 0.0 | 0.265 | 0.319 | 0.3333 | 0.059 |
| confidence | 306 | 0.0 | 0.0 | 0.5 | 0.9231 | 0.732 |
| evidence_confidence | 306 | 0.0 | 0.0 | 0.5 | 0.9231 | 0.732 |
| topic_coverage_confidence | 306 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| shared_commenters | 306 | 0.0 | 0.0 | 3.0 | 36.0 | 0.732 |

## Channels affected by insufficient data

- Ada Derana Tamil: shares no commenter with any other channel, so every score is 0
- Ada Derana Biz: fewer than k shared commenters with every other channel (low confidence)
- Ada Derana Education: fewer than k shared commenters with every other channel (low confidence)
- Pulse.lk: shares no commenter with any other channel, so every score is 0
- Ada Derana News Channel: fewer than k shared commenters with every other channel (low confidence)
- Derana Shorts: shares no commenter with any other channel, so every score is 0
- Ada Derana World News: shares no commenter with any other channel, so every score is 0
- Derana City Of Music: fewer than k shared commenters with every other channel (low confidence)
- Ada Derana News Channel | English: shares no commenter with any other channel, so every score is 0

## Evaluation

| Comparison | Metric | Value | Sources | Status / reason |
|---|---|---|---|---|
| audience_bridge_score vs ppr_diffusion | spearman | +0.809 | 13 | ok |
| audience_bridge_score vs ppr_diffusion | kendall | +0.711 | 13 | ok |
| audience_bridge_score vs ppr_diffusion | topk_jaccard@1 | +0.833 | 18 | ok |
| audience_bridge_score vs ppr_diffusion | topk_jaccard@3 | +0.789 | 18 | ok |
| audience_bridge_score vs ppr_diffusion | topk_jaccard@5 | +0.788 | 18 | ok |
| audience_bridge_score vs topic_similarity | spearman | +0.294 | 13 | ok |
| audience_bridge_score vs topic_similarity | kendall | +0.227 | 13 | ok |
| audience_bridge_score vs topic_similarity | topk_jaccard@1 | +0.111 | 18 | ok |
| audience_bridge_score vs topic_similarity | topk_jaccard@3 | +0.189 | 18 | ok |
| audience_bridge_score vs topic_similarity | topk_jaccard@5 | +0.266 | 18 | ok |
| audience_bridge_score vs metapath2vec_similarity | spearman | +0.406 | 13 | ok |
| audience_bridge_score vs metapath2vec_similarity | kendall | +0.326 | 13 | ok |
| audience_bridge_score vs metapath2vec_similarity | topk_jaccard@1 | +0.222 | 18 | ok |
| audience_bridge_score vs metapath2vec_similarity | topk_jaccard@3 | +0.344 | 18 | ok |
| audience_bridge_score vs metapath2vec_similarity | topk_jaccard@5 | +0.377 | 18 | ok |
| audience_bridge_score vs hgt_similarity | spearman | +0.182 | 13 | ok |
| audience_bridge_score vs hgt_similarity | kendall | +0.131 | 13 | ok |
| audience_bridge_score vs hgt_similarity | topk_jaccard@1 | +0.111 | 18 | ok |
| audience_bridge_score vs hgt_similarity | topk_jaccard@3 | +0.161 | 18 | ok |
| audience_bridge_score vs hgt_similarity | topk_jaccard@5 | +0.224 | 18 | ok |
| audience_bridge_score vs louvain | spearman | +0.330 | 13 | ok |
| audience_bridge_score vs louvain | kendall | +0.308 | 13 | ok |
| audience_bridge_score vs louvain | topk_jaccard@1 | +0.444 | 18 | ok |
| audience_bridge_score vs louvain | topk_jaccard@3 | +0.461 | 18 | ok |
| audience_bridge_score vs louvain | topk_jaccard@5 | +0.513 | 18 | ok |
| audience_bridge_score vs node2vec | spearman | -0.286 | 13 | ok |
| audience_bridge_score vs node2vec | kendall | -0.219 | 13 | ok |
| audience_bridge_score vs node2vec | topk_jaccard@1 | +0.111 | 18 | ok |
| audience_bridge_score vs node2vec | topk_jaccard@3 | +0.056 | 18 | ok |
| audience_bridge_score vs node2vec | topk_jaccard@5 | +0.065 | 18 | ok |

## Errors, warnings and limitations

- No relevance labels: ranking quality (precision, recall, NDCG, MRR) is not computed.
- Temporal stability: ok. Comparable snapshots are judged on channel set and collection depth only; other collection differences (e.g. reply fetching) are not detected automatically.
- Channel registry: the research plan names 41 competitor channel(s), the configuration has 0; missing channels were not invented or substituted.
- Channel registry: the research plan names 16 owned channel(s), the configuration has 18; missing channels were not invented or substituted.
- This snapshot becomes the newest research snapshot, so commands and the dashboard default to it; select another snapshot explicitly where needed.
- This report comes from a pipeline rerun on the existing pilot snapshot (collection run started 2026-10-10T07:53:46+00:00); no new API calls were made. Stage times are from the rerun.
- Shared-commenter evidence per channel pair: max 36, median 0 (confidence k = 3). 

**Recommendation:** complete: all stages and validity checks passed; results are ready for analysis within the stated limitations (no relevance labels, provisional formula)
