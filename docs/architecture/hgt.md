# HGT: Alternative Heterogeneous Graph Learning (Component 3)

Code: [`research/component_3/model/hgt.py`](../../research/component_3/model/hgt.py) · Tests: [`tests/component_3/test_hgt.py`](../../tests/component_3/test_hgt.py)

```
Heterogeneous graph (STEP 13)
   ├── metapath2vec  →  PRIMARY embeddings       (STEP 15)
   └── HGT           →  ALTERNATIVE embeddings   (this step)
```

## Why HGT is included

HGT (Heterogeneous Graph Transformer) learns **type-aware attention** over the graph: separate parameters for each node type and each relation. It's included to test **empirically** whether a learned graph-transformer representation is useful for the same cross-channel audience problem as metapath2vec.

**metapath2vec remains the primary method.** HGT is an alternative. Neither is assumed better, and the comparison must be empirical. Neither method, and no embedding similarity, proves audience migration, causality, subscriber movement, conversion or influence.

```powershell
python -m research.component_3.model.hgt                                    # latest snapshot
python -m research.component_3.model.hgt --hidden 64 --layers 2 --heads 2 --epochs 50 --seed 7
```

**Libraries:**
- PyTorch (CPU build is enough) and PyTorch Geometric (`HGTConv`) are the only deep-learning framework. Install with `pip install torch --index-url https://download.pytorch.org/whl/cpu`.
- `networkx` and `gensim` stay as they are, for the graph adapter and metapath2vec.

## Graph input

- **The same STEP 13 graph** as metapath2vec: the same snapshot, node IDs and relations, checked via the graph fingerprint.
- **Converted** to a sparse `torch_geometric.data.HeteroData`, with no dense adjacency matrices.

| Node type | Present |
|---|---|
| `commenter`, `video`, `channel` | Yes |
| `topic` | Only when topic nodes exist (none yet; never fabricated) |

| Relation (message passing) | Notes |
|---|---|
| `commenter –comments→ video` + reverse | **Training edges only** during training |
| `video –belongs_to→ channel` + reverse | Structural |
| `video –has_topic→ topic` + reverse | When topics exist |
| `participates_in` | **Not used**: it's derived, and would leak held-out comment edges |

## Node features (type-specific, explicit missing values)

Each type has its own feature vector and its own linear input projection to the hidden size. Unrelated features are never concatenated across types.

| Type | Features |
|---|---|
| channel | log1p of observed subscribers, views and public video count; age (years), all from STEP 14 public metrics; log1p of stored videos |
| video | log1p of observed views, likes and public comment count; age (years), from STEP 14; log1p of distinct commenters (training edges) |
| commenter | log1p of videos commented on, of total comment weight, and of channels, **from training edges only** (every commenter attribute comes from comments, so STEP 14 commenter features would leak) |

- **Missing values:** each public feature is value + **missing-indicator**, with 0 when missing. Nothing is silently imputed as a real 0.
- **Standardization** (z-score per type) is fitted on the **training graph only**.
- **Public metrics** are taken from STEP 14 **as of the training boundary**. Metrics collected after the boundary are NULL and flagged, so no future information is used.

**Edge features:** PyG's `HGTConv` has no edge-attribute input. The relation type is modelled by relation-specific attention. Comment weights can optionally weight the positive loss (`positive_weighting="log1p_comments"`, off by default). No confidence weighting is applied.

## Learning objective

**Self-supervised link prediction** on the observed behavioural relation **commenter –comments→ video**:
- Embeddings: type projections → `layers × HGTConv` (ReLU and dropout between layers).
- Score: the **dot product** of commenter and video embeddings.
- Loss: binary cross-entropy of observed (positive) edges vs negative edges.

No Audience Bridge labels or future outcomes are used. They don't exist, and using them would be leakage.

## Negative sampling (type-respecting)

- For each positive (commenter, video), sample `negatives_per_positive` random **videos** for the same commenter. The relation is commenter → video, so negatives always have the right types.
- Negatives that are **any known positive edge** (training or validation) are resampled.
- Sampling is seeded (`numpy.random.default_rng(seed)`). Fixed validation negatives are drawn once.

## Training / validation split

1. **Temporal (preferred):** edges are ordered by their first comment time, and the newest `validation_fraction` (20%) is held out. Validation keeps only **warm** edges, whose commenter and video already appear in training, because a cold-start node has nothing learned to evaluate.
2. **Fallback:** with fewer than `min_validation_edges` (20) warm edges, a **seeded random edge split** is used. It's recorded as `random_edge_split_fallback` with the reason, and it's **not a temporal evaluation**.

**On the current real data** (snapshot `rs-20261008T093922Z`), only **2 warm post-cutoff edges** exist, because almost all later edges come from commenters never seen before. The fallback is therefore used, leaving 1,137 training and 22 validation edges. Most random-split candidates are dropped too, since most commenters have a single edge. A real temporal evaluation needs repeated collection of the same channels over time.

## Hyperparameters (defaults; lightweight, not tuned)

| Parameter | Default |
|---|---|
| Hidden / embedding dimension | 64 |
| HGT layers | 2 |
| Attention heads | 2 |
| Dropout | 0.2 |
| Learning rate (Adam) | 0.005 |
| Weight decay | 1e-4 |
| Epochs (full batch) | 50 |
| Negatives per positive | 5 |
| Validation fraction | 0.2 |
| Seed | 42 |

## Reproducibility

- **Determinism:** `torch.manual_seed(seed)`, deterministic algorithms enabled, one CPU thread during training, seeded NumPy for splits and negatives, sorted node indices. The same graph, configuration and seed give the same embeddings and training history (tested).
- **Experiment ID:** `hgt-<sha256(graph fingerprint + configuration)>`.

## Output (shared format with metapath2vec)

`data/processed/component_3/<snapshot_id>/embeddings/<hgt-…>/` (git-ignored):

| File | Contents |
|---|---|
| `embeddings.parquet` | `node_id`, `node_type`, `snapshot_id`, `experiment_id`, `model_type` (= `HGT`), `embedding` |
| `embeddings.npy` | Matrix, same row order |
| `experiment.json` | Configuration, versions, objective, negative sampling, split (kind, reason, boundary, counts), message-passing and feature descriptions, per-epoch metrics, duration, coverage, validation |
| `model.pt` | Checkpoint: `state_dict` + configuration + experiment and snapshot IDs (no secrets) |

**Final embeddings** are computed for **every** node by running the trained model on the **full snapshot graph**: all comment edges, and features as of the snapshot, standardized with the training statistics.

## Training metrics

Recorded per epoch:
- training loss
- validation loss
- validation **ROC-AUC**
- validation **Average Precision** for held-out edges vs fixed negatives

Training duration is recorded too. These measure the **link-prediction objective only**. They're not evidence of research success, and with the random fallback they aren't temporal-generalization results.

## Comparability with metapath2vec

| | metapath2vec | HGT |
|---|---|---|
| Snapshot, graph, node universe | Same (graph fingerprint recorded) | Same |
| Uses `participates_in` | No | No |
| Signal | Co-occurrence in meta-path walks | Supervised link prediction with attention |
| Node features | None (structure only) | Public metrics + training-edge degrees |
| Nodes embedded | Nodes visited by walks (an isolated channel gets none) | **All** nodes (features + type projection) |
| Hyperparameters | Walks / window / skip-gram | Layers / heads / dropout / optimizer |

Hyperparameters are intentionally **not** forced to match, since the architectures differ. A fair later comparison should use the same snapshot, the common node set and the same evaluation subset.

## Exploratory similarity

`hgt_similarity_exploratory()` returns cosine nearest channels, labelled **"HGT embedding similarity — exploratory"**. It isn't an Audience Bridge Score, a ranking or a recommendation.

## Limitations

- **Small, sparse sample:** about 0.7% video coverage, few shared commenters, and mostly cold-start later edges. Link-prediction metrics on it are unstable.
- **No real temporal validation yet:** the random fallback is used on the current data.
- **No edge attributes** in `HGTConv`, and **no topic semantics** yet.
- **Default hyperparameters**, untuned.
