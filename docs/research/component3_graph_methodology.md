# Component 3: Graph Methodology (audit)

*STEP 33, §4–§9.* This document audits the graph and every graph-based method against the code. Full technical descriptions are in `docs/architecture/`.

## 4. Heterogeneous graph (STEP 13)

| Element | Definition | Audit |
|---|---|---|
| Node types | `channel`, `video`, `commenter` (pseudonymised `anon_…`), `topic` (only when STEP 18 clusters were written) | Topic nodes are never fabricated |
| `commenter –comments→ video` | weight = number of comments | Primary interaction relation |
| `video –belongs_to→ channel` | structural | One channel per video |
| `commenter –participates_in→ channel` | **derived** from the two above | Excluded from PPR and from metapath2vec walks, so the same evidence is not counted twice |
| `video –has_topic→ topic` | KMeans cluster of the video text embedding | Excluded from PPR by default (topic similarity already carries content) |
| Edge weight (features) | `ln(1 + comments)` | Transparent, monotone |
| Current size | 18 channels, 851 videos, 10,823 comments (`rs-20261010T081534Z`) | Small sample; see limitations |

**Verdict:** the schema is correct and consistent across STEP 13–22 (the same graph fingerprint is checked by downstream stages).

## 5. metapath2vec (primary representation)

- **Metapaths:** CVC, CVChVC, ChVCVCh, VChV, VTV (C = commenter, V = video, Ch = channel, T = topic). All are symmetric, which skip-gram training requires.
- **Settings:** dimension 64, 10 walks per node, length 40, window 5, 5 negatives, 5 epochs, learning rate 0.025 → 0.0001, seed 42.
- **Determinism:** 1 worker and a CRC32 hash function, so repeated runs give identical vectors.
- **Use in ABS:** channel–channel cosine, min-max normalised per source.
- **Audit:** correct. Known limitation: embeddings reflect the observed sample structure and are untuned defaults.

## 6. HGT (alternative representation)

- **Architecture:** hidden 64, 2 layers, 2 heads, dropout 0.2; Adam (lr 0.005, weight decay 1e-4); 50 epochs; 5 negatives per positive.
- **Objective:** link prediction on `commenter → video`.
- **Split:** temporal (newest 20 % of edges, warm nodes only), with a recorded random fallback. The current run is temporal: 7,235 training edges, 41 validation edges, cut-off 2026-10-09T00:19:58Z.
- **Leakage guard:** node features are fitted on the training graph as of the boundary, and validation edges are removed from message passing.
- **Audit:** correct and not the primary method. Validation metrics rest on 41 edges and are noisy.
- **Negative result (STEP 34):** HGT channel embeddings are nearly identical (channel–channel cosine 0.901–1.000, median 0.978; metapath2vec: 0.198–0.564). HGT does not separate channels under this configuration. See [component3_known_findings_and_limitations.md](component3_known_findings_and_limitations.md), Finding 3.

## 7. Personalized PageRank (diffusion)

- **Parameters:** α = 0.85, tolerance 1e-10, at most 1000 iterations.
- **Personalisation:** the **source** channel node. The score of a destination is the stationary mass on that destination's channel node, so the direction is source → destination.
- **Edges:** relation-aware with reverse edges; transitions are proportional to weight.
- **Excluded by default:** topic edges and derived `participates_in` edges.
- **Dangling mass** returns to the source, so total mass is conserved.
- **Output:** the source is excluded from its own results. Unreachable destinations get exactly 0 with `reachable = false`.
- **Audit:** mathematically correct (personalised power iteration with restart). Tests cover independent sources and a dangling source.

## 8. Topic similarity

- **Encoder:** `intfloat/multilingual-e5-small` at a pinned revision, 384 dimensions.
- **Input:** title + first 1000 characters of the description. Text with fewer than 3 letters is marked `insufficient_text`.
- **Profiles:** each channel profile is the L2-normalised mean of its video vectors.
- **Similarity:** cosine, symmetric, raw range [-1, 1]. NULL when either channel has no profile.
- **Coverage:** `coverage_ratio` = share of a channel's videos with usable text.
- **Time:** respects `as_of`.
- **Exploratory baseline:** `char_lsa`.
- **Audit:** correct. Content similarity is symmetric by construction and is never sufficient on its own (see §9).

## 9. Confidence

```
evidence_confidence       = n / (n + k)          n = shared public commenters, k = 3
topic_coverage_confidence = min(coverage_src, coverage_dst)
confidence                = evidence_confidence × topic_coverage_confidence      ∈ [0, 1)
```

- `n = 0` gives confidence 0, so the score is an **observed zero**. Content similarity alone cannot create a bridge.
- The factor is the established shrinkage family (Bell & Koren 2007); see [component3_novelty_threat_analysis.md](component3_novelty_threat_analysis.md).
- It saturates quickly: n = 1 → 0.25, n = 3 → 0.5, n = 36 → 0.92.
- It uses **absolute** counts, so larger channels tend to get higher confidence (popularity bias). This is documented as a limitation and is not corrected in the frozen method.
- Interaction counts, video coverage and temporal support are **explanation evidence only** (STEP 22). They are not part of the confidence.
