# metapath2vec: Primary Representation Learning (Component 3)

Code: [`research/component_3/model/metapath2vec.py`](../../research/component_3/model/metapath2vec.py) · Tests: [`tests/component_3/test_metapath2vec.py`](../../tests/component_3/test_metapath2vec.py)
Input: the STEP 13 graph ([hetero_graph.md](hetero_graph.md)); weights consistent with STEP 14 ([graph_features.md](graph_features.md))

```
Heterogeneous graph → graph features → [metapath2vec] → node embeddings
  → (later) diffusion + topic similarity + confidence → Audience Bridge Score
```

## Why metapath2vec

The graph is **heterogeneous**: commenters, videos and channels mean different things. Ordinary (homogeneous) random walks ignore those types. metapath2vec instead restricts walks to **meta-paths**, typed patterns such as commenter → video → commenter. It then learns embeddings with skip-gram, so nodes that occur in similar typed contexts get similar vectors.

It's the proposal's **primary** representation method. HGT is a later alternative, and node2vec and Louvain are later baselines. The code is kept isolated so they can be compared fairly.

metapath2vec itself isn't the research novelty. The contribution is the full framework: heterogeneous audience and content graph + type-aware representation + diffusion + topic similarity + confidence weighting → **Audience Bridge Score**.

## Meta-paths

Walks **repeat** a meta-path, so each starts and ends with the same node type. The one-way commenter → video → channel is therefore used in its symmetric form.

| Name | Node types (relations) | Why it's used |
|---|---|---|
| `CVC` | commenter –comments– video –comments– commenter | Commenters who comment on the same videos |
| `CVChVC` | commenter → video → channel → video → commenter | Commenter-to-channel structure (symmetric form of Commenter → Video → Channel) |
| `ChVCVCh` | channel → video → commenter → video → channel | Cross-channel connectivity through shared commenter participation |
| `VChV` | video –belongs_to– channel –belongs_to– video | Videos in the same channel context |
| `VTV` (later) | video –has_topic– topic –has_topic– video | Videos sharing a topic; **usable only once topic nodes exist** |

- **Configurable:** meta-paths are set through `Config(metapaths=...)`. The set is deliberately small rather than every possible path.
- **Validation before training:** each meta-path must have valid node types and relations, relations that connect the stated types, and a repeatable (cyclic) form. Its node types and relations must also be **present in the graph**.
- **Unusable paths are skipped and reported**, for example `VTV` before topic modelling, never filled with fabricated data.
- **The derived `participates_in` edges are never walked**, so commenter → video → channel evidence isn't counted twice.

## Walk strategy

- Walks start at **every** node of the meta-path's first type, `walks_per_node` times each, in sorted order.
- Every step must follow the meta-path's next relation to a node of the next type, over real STEP 13 edges in **either direction**.
- **Transition probabilities:**
  - `uniform` (default; classic metapath2vec)
  - `log1p_comments`: comment edges weighted `ln(1 + comment_count)`, the STEP 14 interaction weight
- A walk stops early at a dead end, for example a channel without stored videos. One-node walks are dropped. Counts of walks and truncations per meta-path are recorded.
- **Randomness** comes only from `numpy.random.default_rng(seed)`, with sorted neighbour lists. The same graph, configuration and seed always give the same walks.

## Training (skip-gram with negative sampling)

The walks are sentences for `gensim.Word2Vec`, a mature implementation, run in skip-gram mode with negative sampling. The heterogeneous sampling above is our own explicit code.

| Hyperparameter | Default | Config field |
|---|---|---|
| Embedding dimension | 64 | `dimensions` |
| Walks per start node | 10 | `walks_per_node` |
| Walk length (nodes) | 40 | `walk_length` |
| Context window | 5 | `window` |
| Negative samples | 5 | `negative` |
| Epochs | 5 | `epochs` |
| Learning rate (linear decay) | 0.025 → 0.0001 | `learning_rate`, `min_learning_rate` |
| Random seed | 42 | `seed` |

These are practical defaults for a small research graph, not tuned values. Larger settings, such as the paper's 1,000 walks of length 100, can be passed via the configuration or command line.

```powershell
python -m research.component_3.model.metapath2vec                                   # latest snapshot
python -m research.component_3.model.metapath2vec --dim 128 --walks-per-node 20 --seed 7 --weights log1p_comments
```

## Reproducibility

- **Training:** a single worker thread, a fixed seed, and a **deterministic CRC32 hash** in place of Python's per-process randomized `hash()`. Repeated runs, **including separate processes**, give identical vectors (tested).
- **Experiment ID:** `m2v-<sha256(graph fingerprint + configuration)>`. The same snapshot graph and configuration always give the same ID.
- **One snapshot per experiment:** each experiment uses exactly one snapshot, recorded in every artifact. Multiple snapshots are never mixed implicitly, which keeps later temporal-stability comparisons possible.

## Output

`data/processed/component_3/<snapshot_id>/embeddings/<experiment_id>/` (git-ignored):

| File | Contents |
|---|---|
| `embeddings.parquet` | `node_id`, `node_type`, `snapshot_id`, `experiment_id`, `embedding` (list of floats). Readable and reloadable |
| `embeddings.npy` | float32 matrix for numerical work. Rows follow the Parquet rows |
| `experiment.json` | Full configuration and meta-paths, hyperparameters, seed, software versions, `created_at`, graph fingerprint, walk statistics, coverage, validation result, vector checksum |

- Saved once: re-saving the same experiment is accepted only if the vectors match.
- `load_embeddings()` checks the checksum and that the two files agree, with no retraining.
- **Node types are preserved:** `result.of_type("commenter" | "video" | "channel")`.

## Coverage and validation

- **Coverage** is reported per node type. A node gets **no embedding only if no usable meta-path walk visits it**, for example a channel without stored videos, or topic nodes before topic modelling.
- **Validation** checks:
  - the expected shape and dimension
  - no NaN or infinite values
  - every embedded node exists in the graph with the same type
  - no duplicates
  - commenter IDs are pseudonyms
  - an optional minimum coverage
- **Sanity checks:** `nearest_neighbours()` (cosine), and `channel_similarity_exploratory()`, labelled **"Embedding similarity — exploratory"**. These are not evaluation, scores, rankings or recommendations.

## Limitations

- **Structural only:** embeddings reflect the **structure of the observed sample**. With low collection coverage (STEP 14: about 0.7% of videos per channel) and few shared commenters, they're dominated by within-channel structure.
- **No topics yet:** topic semantics aren't included until the topic-modelling stage.
- **Not tuned:** hyperparameters are defaults, not tuned values.

metapath2vec captures **graph-based structural relationships**. It does **not** prove audience migration, causality, subscriber movement, influence or conversion. Commenters appear only as pseudonyms.
