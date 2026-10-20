# Component 3: Final Methodology

This document describes the methodology in academic order. Implementation details are in `docs/architecture/*.md`, and the audit trail is in [component3_methodology_freeze.md](component3_methodology_freeze.md). The methodology is **frozen** (method version 2.0).

## 4.1 Data Source

The data source is the **YouTube Data API v3** (official API, public resources only). The following endpoints are used:
- `channels.list`
- `playlistItems.list`
- `videos.list`
- `commentThreads.list`
- `comments.list`

No private YouTube Studio analytics are used.

## 4.2 Data Collection

| Entity | Collected | Limits used for the research runs |
|---|---|---|
| Channels | metadata and public statistics for the 18 approved Derana channels | — |
| Videos | newest uploads per channel: title, description, publication time, public statistics | up to 50 per channel |
| Comments | public top-level comments and replies | up to 100 threads per video, all replies |
| Commenter identifiers | the public author channel ID, **pseudonymised at parse time** (see 4.4) | — |

Collection is quota-bounded and retried on transient errors. Failures are recorded per item, never silently dropped.

## 4.3 Data Storage

| Layer | Technology | Role |
|---|---|---|
| Shared research database | Supabase PostgreSQL | Team-wide store of collected rows (`shared/database/`) |
| Research snapshots | Parquet + manifest with SHA-256 checksums | Immutable `rs-<UTC time>` copies; each analysis reads exactly one snapshot |
| Analytical engine | DuckDB | SQL validation and preparation over the Parquet files; read-only workspace views |

## 4.4 Data Processing

- **Pseudonymisation:** commenter ID → `anon_` + HMAC-SHA256(secret salt, ID). This is applied before storage. The pipeline fails closed without the salt.
- **Snapshot management:** snapshots are immutable and checksum-verified before every analysis. Results are stored per snapshot and experiment ID, and are write-once.
- **Validation (STEP 12):**
  - required fields
  - duplicates
  - missing values
  - referential integrity (video → channel, comment → video / channel, reply → parent)
  - data-quality warnings (for example, more likes than views, or comments dated before their video)

  A snapshot must be `research_ready` to be analysed.
- **Feature extraction (STEP 14):** described in 4.6, computed **as of** a reference time, so no later data leaks in.

## 4.5 Heterogeneous Graph

| Node type | Meaning |
|---|---|
| `commenter` | a pseudonymous public commenter account |
| `video` | a collected video |
| `channel` | a research channel |
| `topic` | a KMeans cluster of video text embeddings (10 clusters; present only when a topic run is attached) |

| Edge | Direction | Meaning | Weight |
|---|---|---|---|
| `comments` | commenter → video | the commenter wrote public comment(s) on the video | number of comments |
| `belongs_to` | video → channel | the video was published by the channel | structural (1) |
| `participates_in` | commenter → channel | **derived**: the commenter commented on at least one of the channel's videos | number of comments |
| `has_topic` | video → topic | the video's text falls in the topic cluster | 1.0 (hard assignment) |

The graph has no self-loops or duplicate edges, and it carries a fingerprint that every downstream stage checks.

## 4.6 Graph Feature Engineering

These are descriptive features, computed as of the snapshot time:

| Table | Main features |
|---|---|
| `channel_pair_features` | `shared_commenter_count`, unique commenters per channel, `union_commenter_count`, `jaccard_similarity`, `directional_overlap_a_to_b` / `b_to_a`, `overlap_ratio` |
| `commenter_channel_features` | `video_count`, `comment_count`, `reply_count`, first / last interaction, `active_span_days`, `interaction_weight` = ln(1 + comments) |
| `graph_edge_features` | comment / reply / video counts, time span, `interaction_weight`, `channel_share` |
| `graph_node_features` | per-node counts, observed public statistics (views, likes, subscribers as published), activity and recency measures, `collection_coverage`, `interaction_support_count` |

## 4.7 metapath2vec (primary representation)

- **Role:** learns type-aware node embeddings. The **channel–channel cosine** is the embedding component of the score.
- **Metapaths** (C = commenter, V = video, Ch = channel, T = topic):
  - `CVC` (co-commenting)
  - `CVChVC`
  - `ChVCVCh` (channel–audience–channel)
  - `VChV`
  - `VTV` (topic)
- **Configuration:**
  - dimension 64
  - 10 walks per node, walk length 40, uniform transitions
  - skip-gram window 5, 5 negative samples, 5 epochs
  - seed 42, 1 worker (deterministic)
- The derived `participates_in` edges are never walked.

## 4.8 HGT (alternative representation)

- **Role:** an alternative, attention-based heterogeneous GNN. It can replace metapath2vec as the embedding component (`--embedding-source hgt`). **It is not the primary method.**
- **Configuration:** hidden 64, 2 layers, 2 heads, dropout 0.2; Adam (lr 0.005, weight decay 1e-4); 50 epochs; 5 negatives per positive; seed 42.
- **Training objective:** link prediction on `commenter → video`.
- **Temporal split:** the newest 20 % of edges are held out, keeping warm nodes only. A random fallback is used if there are fewer than 20 validation edges. Node features are fitted on the training graph only.

## 4.9 Personalized PageRank (directional diffusion)

- **Restart and settings:** a random walk with restart to the **source** channel; damping α = 0.85, tolerance 1e-10, at most 1000 iterations.
- **Edges:** relation-aware edges in both directions, with weight-proportional transitions. Topic edges and derived `participates_in` edges are excluded by default.
- **Score:** `diffusion_score(s → d)` is the stationary probability mass on destination channel `d`.
- **Direction:** the score is directional because the walk restarts at `s`, so PPR(s → d) ≠ PPR(d → s).
- **Output rules:** self pairs are excluded. Unreachable destinations score exactly 0 (`reachable = false`).

## 4.10 Topic Similarity

- **Text:** each video's title plus the first 1000 description characters.
- **Encoder:** `intfloat/multilingual-e5-small`, pinned at revision `614241f6…`, which produces 384-dimensional vectors and covers Sinhala, Tamil and English. Text with fewer than 3 letters is marked `insufficient_text`.
- **Channel profile:** the L2-normalised mean of its usable video vectors.
- **Similarity:** the cosine of two profiles. It is **symmetric**, with a raw range of [-1, 1]. It is NULL when a channel has no profile.
- **Coverage:** `coverage_ratio` is the share of a channel's videos with usable text.

## 4.11 Confidence Weighting

```
evidence_confidence       = n / (n + k)        n = shared public commenters of the pair, k = 3
topic_coverage_confidence = min(coverage(source), coverage(destination))
confidence                = evidence_confidence × topic_coverage_confidence          ∈ [0, 1)
```

- **Confidence is a gate:** with n = 0, confidence is 0, so the score is 0. Content similarity alone can never create a bridge.
- **Prior work:** the form `n/(n+k)` is the established shrinkage family (Bell & Koren 2007).
- **What is not in the confidence:** interaction counts, video coverage and temporal support are reported as **explanation evidence only**.

## 4.12 Audience Bridge Score

**Exact implemented formula (method 2.0):**

```
norm_x(s, d) = (x(s, d) − min_d' x(s, d')) / (max_d' x(s, d') − min_d' x(s, d'))      per source s

base_score(s → d) = w_d · norm_diffusion(s → d)
                  + w_e · norm_embedding_similarity(s, d)
                  + w_t · norm_topic_similarity(s, d)

AudienceBridgeScore(s → d) = base_score(s → d) × confidence(s, d)
```

| Variable | Meaning |
|---|---|
| `w_d, w_e, w_t` | weights, non-negative and summing to 1. Default 1/3 each; these are provisional, documented defaults |
| `norm_*` | per-source min-max normalisation. All-zero columns → 0. A constant non-zero column → NULL (no ordering information) |
| `confidence` | see 4.11 |
| ranking | per source, by descending score; ties broken by destination ID, so the order is deterministic |

**Formula note.** Some planning briefs quote a **two-part** form: `w_d·diffusion + w_t·topic`. The implemented and frozen method is **three-part**. The two-part form is reproduced exactly as an ablation with `--weights 0.5 0 0.5 --embedding-source none`.

**Properties:**
- **Range:** the score lies in [0, 1) and can never reach 1.
- **Missing input:** a pair with a missing component gets a NULL score with a `score_status`. It is never silently scored 0.
- **Direction:** only diffusion and per-source normalisation are directional. Embedding similarity, topic similarity and confidence are symmetric.

## 4.13 Baselines

| Baseline | Definition | Why it is used |
|---|---|---|
| **Louvain** | Communities on the Jaccard shared-commenter channel projection (resolution 1.0, seed 42). Score = 1 if the destination is in the source's community, else 0 | The established "overlap community" view: are bridges just communities? |
| **node2vec** | Type-agnostic random-walk embeddings (p = q = 1, dimension 64, weighted, seed 42); channel cosine | The established homogeneous-embedding view. It isolates the value of type-aware metapaths and of the full score |

## 4.14 Evaluation

There are no ground-truth relevance labels, so the evaluation measures **consistency, not correctness**:

1. **Method agreement:** per-source Spearman, Kendall τ-b and top-k Jaccard (k = 1, 3, 5) between the score and each baseline and component.
2. **Top-k comparison** of destinations.
3. **Temporal stability:** rank stability between comparable snapshots, meaning the same channel set and a collection-depth ratio ≥ 0.8.
4. **Sparse-data robustness:** seeded comment subsampling; ranking compared with the full-data ranking.
5. **Computational performance:** wall-clock time and Python heap peak for each method.
6. **Sensitivity (STEP 22):** whether the top-1 destination survives component removal and changes to the weights.

Relevance metrics (precision@k, NDCG, MRR) are implemented, but they are computed only when a labels file is supplied. None exists.
