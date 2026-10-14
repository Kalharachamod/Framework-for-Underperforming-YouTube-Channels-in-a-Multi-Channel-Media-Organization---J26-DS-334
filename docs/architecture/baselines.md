# Component 3 Baselines: Louvain and node2vec

Code: [`research/component_3/model/baselines.py`](../../research/component_3/model/baselines.py) · Tests: [`tests/component_3/test_baselines.py`](../../tests/component_3/test_baselines.py)

> **These are baseline comparison methods, not the proposed research contribution.** The proposed method is: heterogeneous graph → metapath2vec / HGT → Personalized PageRank → topic similarity → confidence weighting → **Audience Bridge Score**. The baselines exist so STEP 21 can test, empirically, whether the proposed framework adds value over established graph methods. No evaluation metrics are computed here.

```powershell
python -m research.component_3.model.baselines louvain                      # latest research snapshot
python -m research.component_3.model.baselines node2vec --dim 64 --p 1 --q 1
```

## Fair inputs (shared by both baselines)

`load_input(snapshot_id)` gives each baseline **the same inputs as the proposed method**:
- **Snapshot:** the same research snapshot (STEP 12) and the **same STEP 13 graph**, checked via the graph fingerprint.
- **Features:** STEP 14 features computed **as of the snapshot extraction time**, so no future data is used.
- **Channels:** the same channel set, all graph channels (the 18 confirmed Derana channels).

Each run records, in its metadata:
- the snapshot ID and graph fingerprint
- `as_of`
- the channel set
- the graph projection method and the edge-weight definition
- the seed and all parameters
- the creation time and library versions
- the `experiment_id`: `louvain-…` or `node2vec-…`, a hash of the graph and configuration, never hard-coded

**Unavoidable differences:**
- Louvain sees only the channel-level projection, since community detection on channels needs a channel graph.
- node2vec ignores node types, deliberately, as the conventional counterpart to type-aware metapath2vec and HGT.

## Louvain (structural community baseline)

**What it does:** Louvain finds groups of nodes with many internal, strongly weighted connections, by greedily maximizing **modularity**.

**Why it's included:** it's a simple, widely used structural method. If channels connected by shared commenters form communities, being in the same community is a basic **community association** signal for the proposed scores to beat.

### Projection (heterogeneous graph → channel graph)

```
commenter --comments--> video --belongs_to--> channel        (STEP 13)
        ⇒  channels A and B are linked if they share ≥ 1 commenter (STEP 14 channel_pair_features)
```

- **Nodes:** every channel, including channels with no shared commenters (these stay isolated).
- **Edges:** undirected, one per observed pair with at least one shared commenter. Pairs are never invented.
- **Edge weight** (`projection_weight`), taken from STEP 14 rather than invented:

| Option | Definition | Effect |
|---|---|---|
| `jaccard` (**default**) | \|A ∩ B\| / \|A ∪ B\| of the commenter sets | Size-normalized: large channels don't dominate just because they're large |
| `shared_commenters` | \|A ∩ B\| | Raw evidence; favours large channels |
| `log1p_shared` | ln(1 + \|A ∩ B\|) | Dampens very large counts |

- **Algorithm:** `networkx.community.louvain_communities(weight, resolution, threshold, seed)`, with nodes inserted in sorted order. It's deterministic for a fixed seed.
- **Community IDs** `c00, c01, …` are ordered by size, then by the smallest member ID. Isolated channels become singleton communities, flagged `is_isolated`.

### Output

| Artifact | Columns |
|---|---|
| `louvain_communities.parquet` | `channel_id`, `community_id`, `community_size`, `is_isolated`, `snapshot_id`, `experiment_id` |
| `louvain_channel_relationships.parquet` | Ordered pairs (no self pairs): `source_channel_id`, `destination_channel_id`, `same_community`, `community_relationship`, `shared_commenters`, `projection_weight`, `snapshot_id`, `experiment_id` |

`community_relationship` is a **documented binary indicator**: 1.0 for the same community, 0.0 otherwise. It is **not** a graded similarity score, and community IDs are never used as numbers. Modularity is recorded in `baseline_run.json`.

**Interpretation:** same community means *structural community association* through shared commenter participation. Louvain community membership does **not** prove audience migration, audience transfer, causality or future growth.

**Limitations:**
- Communities are a coarse, all-or-nothing signal.
- Results depend on the resolution parameter and the weight choice.
- With few channels (18) and sparse overlap, many channels end up as singletons.

## node2vec (conventional graph-embedding baseline)

**What it does:** node2vec samples **biased random walks** controlled by a return parameter `p` and an in-out parameter `q`, then learns embeddings with skip-gram.

**Why it's included:** it's the standard *type-agnostic* counterpart of metapath2vec. Comparing them shows whether type-aware learning (metapath2vec, HGT) helps.

### Graph representation

- **The same observed STEP 13 edges as metapath2vec** (`comments`, `belongs_to`), treated as **undirected** with node types ignored.
- **`participates_in` is excluded**, since it's derived, exactly as for metapath2vec.
- **Weights** (`weighted=True`): comments edges use `ln(1 + comment_count)`, the STEP 14 interaction weight; `belongs_to` uses 1.0. Duplicate edges would be merged by summing.
- **Walks** are second-order: from `cur` (having come from `prev`), the unnormalized probability of a neighbour `x` is `w(cur, x) × {1/p if x = prev; 1 if x is a neighbour of prev; 1/q otherwise}`. Walks start from every node in sorted order and are seeded with `numpy.random.default_rng(seed)`.
- **Training** is identical to metapath2vec for fairness: gensim Word2Vec, skip-gram with negative sampling, 1 worker, a deterministic CRC32 hash and a fixed seed. The output is reproducible (tested).

### Channel similarity

```
raw_node2vec_similarity(A, B)        = cos(e_A, e_B) = (e_A · e_B) / (‖e_A‖ ‖e_B‖)     range [−1, 1]
normalized_node2vec_similarity(A, B) = (raw + 1) / 2                                     range [0, 1]
```

- **Normalization** is a linear, order-preserving map, **not clipping**. The raw value is always kept.
- **Symmetric:** cosine similarity is symmetric. Rows are stored for **ordered** pairs (`source → destination`) only so the format matches the proposed method's outputs. This doesn't make the measure directional.
- **Self pairs are excluded.** `rank` is per source, by raw similarity descending, with ties broken by `destination_channel_id`.
- **Channels without an embedding** get NULL similarity and no rank. This happens when a channel has no edges, such as one with no stored videos, so no walk visits it.

### Output

`baselines/<node2vec-…>/` uses the shared embedding format:
- `embeddings.parquet` (`model_type = node2vec`), `embeddings.npy` and `experiment.json`
- `node2vec_channel_similarity.parquet`: `source_channel_id`, `destination_channel_id`, `raw_node2vec_similarity`, `normalized_node2vec_similarity`, `rank`, `snapshot_id`, `experiment_id`

**Interpretation:** node2vec similarity represents **structural graph proximity**. It doesn't mean guaranteed audience movement, audience transfer, growth or any business outcome.

**Limitations:**
- Ignores node types, by design.
- Sensitive to p, q and walk settings, which are defaults, not tuned values.
- With sparse cross-channel commenting, channel embeddings mostly reflect within-channel structure.

## Parameters and defaults

| Louvain | Default |
|---|---|
| `projection_weight` | `jaccard` |
| `resolution` | 1.0 |
| `threshold` | 1e-7 |
| `seed` | 42 |

| node2vec | Default |
|---|---|
| `dimensions` | 64 |
| `walk_length` | 40 |
| `walks_per_node` | 10 |
| `window` | 5 |
| `p` | 1.0 |
| `q` | 1.0 |
| `negative` | 5 |
| `epochs` | 5 |
| `weighted` | true |
| `seed` | 42 |

These are standard defaults (p = q = 1 gives uniform walks), consistent with the metapath2vec settings, not tuned values. Invalid values are rejected: resolution ≤ 0, p or q ≤ 0, dimensions, walks or epochs < 1, walk length < 2.

## Artifacts and reproducibility

- **Location:** `data/processed/component_3/<snapshot_id>/baselines/<experiment_id>/`, git-ignored and written once per experiment.
- **Contents:** every artifact carries `snapshot_id` and `experiment_id`.
- **Privacy:** outputs contain channel IDs and pseudonymized node IDs only, never raw commenter IDs.
- **Determinism:** the same snapshot, configuration and seed give identical results for both baselines (tested). No known library nondeterminism remains, given a single training thread and the deterministic hash.
