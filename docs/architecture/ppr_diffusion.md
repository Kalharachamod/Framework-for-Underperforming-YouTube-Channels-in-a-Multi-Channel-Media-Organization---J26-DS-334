# Personalized PageRank Diffusion (Component 3)

Code: [`research/component_3/model/ppr_diffusion.py`](../../research/component_3/model/ppr_diffusion.py) · Tests: [`tests/component_3/test_ppr_diffusion.py`](../../tests/component_3/test_ppr_diffusion.py)

```
Heterogeneous graph → features → metapath2vec / HGT → [Personalized PageRank diffusion]
  → (later) topic similarity → confidence weighting → Audience Bridge Score
```

## Why Personalized PageRank

Personalized PageRank (PPR) measures how probability mass that keeps **restarting at a source** spreads through the graph. Personalized on a **source channel**, it gives each other channel a **diffusion score**: a *graph-based reach / structural connectivity signal* through the observed commenter–video–channel interactions. It's the diffusion component of the proposed framework, and a **potential audience bridge signal**.

PPR produces a **graph diffusion / connectivity signal** only. It does **not** prove audience migration, causality, subscriber movement, conversion or guaranteed growth. `diffusion_score` is **not** the Audience Bridge Score, and it's computed independently of the metapath2vec and HGT embeddings.

```powershell
python -m research.component_3.model.ppr_diffusion                         # every eligible source channel
python -m research.component_3.model.ppr_diffusion --source UC... --alpha 0.85
```

## Diffusion graph (from the STEP 13 graph)

It's built from the **same STEP 13 graph**: its node IDs, types, relations and weights. Every node type takes part; nothing is flattened into a channel overlap matrix.

| Relation | Forward (observed) | Reverse | Weight |
|---|---|---|---|
| `comments` | commenter → video | video → commenter (`derived_diffusion_edge`) | `ln(1 + comment_count)` (STEP 14 `interaction_weight`) |
| `belongs_to` | video → channel | channel → video (`derived_diffusion_edge`) | 1.0 |
| `has_topic` | video → topic | topic → video | Topic weight (once topics exist) |
| `participates_in` | **excluded by default** | | It's derived from `comments` + `belongs_to`, so including it would count the same evidence twice (`include_derived_participation=True` to add it) |

**Direction: relation-aware bidirectional.** Observed edges point commenter → video → channel. A walk could then never leave a channel, so every observed edge also gets a reverse edge, kept with its relation and direction and labelled `derived_diffusion_edge`. This choice is explicit in the configuration, not a library default.

**Relation-specific weights:** `relation_weights=(("comments:reverse", 0.5), ...)` scales one relation and direction. A weight of 0 removes it.

## Transition probabilities

- **`weight_proportional`** (default): P(i → j) = w(i, j) / Σₖ w(i, k), over i's outgoing diffusion edges.
- **`relation_balanced`** (type-aware alternative): each (relation, direction) group at a node gets an equal share, then w / Σw within the group. For example, a video sends ½ to its channel and ½ spread across its commenters.

Each row of the sparse transition matrix sums to 1. Rows of **dangling** nodes, with no outgoing edges (such as a channel without stored videos), sum to 0.

## Personalized PageRank

```
r = (1 − α) · p  +  α · ( Pᵀ r  +  d · p ),      d = mass currently on dangling nodes
```

| Setting | Default | Notes |
|---|---|---|
| `alpha` (damping) | 0.85 | Probability of following an edge; 1 − α restarts at the source. Configurable, must be in (0, 1) |
| `tolerance` | 1e-10 | Stop when ‖rₜ − rₜ₋₁‖₁ < tolerance |
| `max_iterations` | 1000 | Stops safely; `converged = false` is recorded if not reached |
| `personalization` | `source_channel` | All mass on the source channel node. Alternative: `source_channel_videos` (uniform over its videos) |

- **Computation:** sparse power iteration (SciPy CSR); no dense N × N matrix is ever built.
- **Mass:** total mass stays 1.
- **Dangling nodes:** their mass is **returned to the personalization vector**, i.e. the source.
- **Disconnected channels:** with this formulation a channel with **no path** from the source gets **exactly 0** and `reachable = false`. Nothing is fabricated.

## Source-channel analysis

For **each** source channel, by default every channel with outgoing transitions (channels without stored videos are skipped, with the reason recorded):
1. Build the personalization vector.
2. Run PPR on the full heterogeneous graph.
3. Take the scores of the **channel nodes**.
4. Remove the source (`include_source=False`, the default for cross-channel analysis; `True` keeps it as `is_source`).
5. Rank destinations by `diffusion_score`, breaking ties by channel ID.

Each source is computed and stored **independently**; nothing is collapsed into one score.

## Output

`data/processed/component_3/<snapshot_id>/diffusion/<ppr-…>/` (git-ignored):

`channel_diffusion.parquet`: one row per (source, destination) channel:

| Column | Meaning |
|---|---|
| `source_channel_id`, `destination_channel_id` | Channel node IDs (`channel:<id>`) |
| `diffusion_score` | **Raw** PPR mass on the destination channel node (probability-like; not rescaled) |
| `normalized_destination_share` | `diffusion_score / Σ` over this source's destinations. Clearly labelled; it sums to 1 per source |
| `rank` | 1 = highest diffusion score for this source |
| `reachable` | A path from the source exists in the diffusion graph |
| `is_source` | Only when the source is included |
| `snapshot_id`, `experiment_id` | Provenance |

No min-max scaling is applied. Raw scores are small because mass also sits on videos, commenters and the source.

`diffusion_run.json`:
- the experiment ID, snapshot ID and graph fingerprint
- the graph schema and **edge-weighting version**
- the full configuration: α, tolerance, max iterations, directionality, transition rule, personalization, self-channel handling, relation weights
- the creation time and software versions
- diffusion-graph statistics, including counts of observed and derived edges, and the dangling-node handling
- per-source convergence (converged, iterations, residual, total mass)
- skipped sources, validation, and a results checksum

The experiment ID `ppr-<hash(graph fingerprint + configuration)>` is deterministic.

## Validation

Each of these fails the run:
- transition rows that don't sum to 1 (excluding dangling rows)
- negative probabilities
- unknown source or destination channels
- non-finite or negative scores
- PageRank mass ≠ 1 per source
- duplicate (source, destination) rows
- the source present when it should be excluded
- mass on unreachable destinations
- non-channel IDs in the channel results

Ordering is deterministic. The output contains only channel IDs, so no commenter identifiers appear.

## Temporal use

Each run uses **one** research snapshot's graph, recorded via `snapshot_id` and the graph fingerprint. Historical runs use the graph of a historical snapshot; snapshots are never mixed. This allows later temporal-stability experiments.

## Limitations

- **Sample dependence:** scores reflect the **observed sample**. With low collection coverage and few shared commenters, most mass stays inside the source channel, and cross-channel scores are tiny or exactly 0 (unreachable).
- **Parameter sensitivity:** results depend on α, the transition rule and the relation weights. These are documented defaults, not tuned values.
- **No topics yet:** topic similarity and confidence weighting aren't included; that happens in later steps.
