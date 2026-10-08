# Component 3 Heterogeneous Research Graph

Code: [`research/component_3/preprocessing/hetero_graph.py`](../../research/component_3/preprocessing/hetero_graph.py) · Tests: [`tests/component_3/test_hetero_graph.py`](../../tests/component_3/test_hetero_graph.py)
Input: a research-ready snapshot ([research_dataset.md](research_dataset.md))

The heterogeneous **commenter–video–channel–topic** graph is the foundation for the proposed Audience Bridge Score framework: metapath2vec / HGT, Personalized PageRank, topic similarity, confidence weighting, baselines and explainability. **This step only builds and validates the graph.** No model is trained and no score is computed.

```
Commenter                          Commenter
    │ comments (weight = #comments)    │
    ▼                                  └──── participates_in ────▶ Channel
  Video                                       (derived; weight = #comments on the channel)
    │ belongs_to (weight = 1)
    ▼
 Channel                           Video ── has_topic ──▶ Topic   (schema ready, empty until topic modelling)
```

## Building

```powershell
python -m research.component_3.preprocessing.hetero_graph                 # latest research snapshot
python -m research.component_3.preprocessing.hetero_graph --snapshot rs-20261008T093922Z
```

- **Input:** the research snapshot's Parquet files, queried with DuckDB. There's no YouTube access.
- **Refusal:** a snapshot that isn't **research-ready** (STEP 12) is refused with `GraphBuildError`.
- **Method:** all aggregation is DuckDB SQL; Python only assembles and validates the tables.
- **Sparse:** only observed relationships become edges. No dense commenter × channel matrix is ever created.

## Node types

| Type | ID | Attributes |
|---|---|---|
| `channel` | `channel:<channel_id>` | `label` (name), `published_at` (created), `subscriber_count`, `view_count`, `video_count` |
| `video` | `video:<video_id>` | `label` (title), `channel_id`, `published_at`, `duration_seconds`, `view_count`, `like_count`, `comment_count` |
| `commenter` | `commenter:<pseudonym>` | none beyond the ID (minimal by design) |
| `topic` | `topic:<topic_id>` | `label`, supplied by the later topic-modelling stage; **empty now** |

All nodes share one table, `graph_nodes`, with `node_id`, `node_type`, `key` (the ID within its type), and nullable attribute columns.

## Edge types and weights

| Relation | Source → target | Derived? | `weight` | Other attributes |
|---|---|---|---|---|
| `comments` | commenter → video | no | **Number of comments** (top-level + replies) by the commenter on the video; one edge per pair, not one per comment | `comment_count`, `reply_count`, `first_at`, `last_at` (first and last comment time) |
| `belongs_to` | video → channel | no | **1.0** (structural) | none |
| `participates_in` | commenter → channel | **yes** | **Sum of the commenter's `comments` weights** on that channel's videos | `comment_count`, `reply_count`, `video_count`, `first_at`, `last_at` (first and last interaction) |
| `has_topic` | video → topic | no | Topic weight in [0, 1] from the topic stage (**no topics yet**) | none |

- `participates_in` is **derived** from `comments` + `belongs_to`, using the video's channel. It's marked `derived = true` and isn't an independent behavioural event.
- To avoid double counting, algorithms that walk commenter → video → channel should leave it out: `to_networkx(include_derived=False)`.
- No confidence weighting, topic similarity or PageRank is applied. These are transparent baseline weights.
- Features and `ln(1 + comment_count)` interaction weights are added by STEP 14 ([graph_features.md](graph_features.md)).

## Artifact (serialization)

`data/processed/component_3/<snapshot_id>/graph/` (git-ignored):

| File | Contents |
|---|---|
| `graph_nodes.parquet` | One row per node, sorted by type (channel, video, commenter, topic) then `node_id` |
| `graph_edges.parquet` | One row per edge: `source`, `target`, `relation`, `source_type`, `target_type`, `derived`, `weight`, attributes; sorted by relation, then source, then target |
| `graph_manifest.json` | Graph schema version, snapshot ID, node and relation types, **weight definitions**, statistics, content **fingerprint** |

- The graph is written once per snapshot: an identical rebuild is accepted, a different graph is refused.
- `load_graph(path)` reloads it, checks the fingerprint (detecting any edited file), and re-validates.
- `graph.to_networkx()` gives an in-memory `networkx.DiGraph` with `node_type` and `relation` attributes, for traversal and later algorithms. Parquet stays the canonical format.

## Determinism

- **IDs** are built from the stored IDs: no random IDs, no object addresses.
- **Aggregation** is SQL `GROUP BY`.
- **Sorting** is explicit.
- **The fingerprint** is a SHA-256 of the canonical tables.

The same snapshot always produces the same graph and fingerprint, and identical data in another snapshot produces the same fingerprint (a test checks this).

## Validation (`validate_graph`, never repairs)

Each of these is a failure:
- duplicate node IDs
- unknown node or edge types
- IDs not of the form `<type>:<key>`
- edges referencing missing nodes or connecting the wrong node types
- the wrong `derived` flag
- duplicate edges
- self-loops
- negative or missing weights
- `has_topic` weights outside [0, 1]
- a video without exactly one `belongs_to` edge to an existing channel
- `participates_in` edges that **don't exactly equal** the aggregation of `comments` through `belongs_to` (pairs, weights, video counts, first and last times)
- any commenter key that isn't a pseudonym

Topic nodes and edges may be empty.

## Statistics (descriptive only)

The manifest records:
- node counts per type and edge counts per relation
- total nodes, and total edges with and without derived edges
- unique commenters, videos and channels
- commenters on 2+ channels
- the number of channel pairs that share commenters, and the top pairs with their shared-commenter counts

These are descriptive graph statistics. **They aren't Audience Bridge Scores.**

## Privacy and interpretation

- Commenter nodes use **only the pseudonym** (`commenter:anon_…`). Raw YouTube commenter IDs, names, emails, demographics and subscription status aren't present, and validation rejects a non-pseudonym commenter.
- Commenter overlap between channels is an **observable interaction signal**. It doesn't prove audience migration, subscription, identity or causality.
