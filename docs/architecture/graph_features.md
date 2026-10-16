# Component 3 Graph Features and Edge Weighting

Code: [`research/component_3/preprocessing/graph_features.py`](../../research/component_3/preprocessing/graph_features.py) · Tests: [`tests/component_3/test_graph_features.py`](../../tests/component_3/test_graph_features.py)
Builds on: [hetero_graph.md](hetero_graph.md) (STEP 13 graph) · [research_dataset.md](research_dataset.md) (STEP 12 snapshot)

```
Research-ready data → Heterogeneous graph → [THIS STEP] features + transparent weights
  → metapath2vec / HGT → Personalized PageRank → topic similarity → confidence weighting → Audience Bridge Score
```

> **Descriptive features, not research model scores.** Nothing here is a diffusion score, topic similarity, a confidence weight or an Audience Bridge Score. Those aren't implemented yet.

```powershell
python -m research.component_3.preprocessing.graph_features                          # as of the snapshot's extraction time
python -m research.component_3.preprocessing.graph_features --as-of 2026-10-01T00:00:00Z
```

## How features are computed

- **Input:** the STEP 13 graph (loaded, or built if missing) and the snapshot's **event-level** data, queried with DuckDB SQL. There's no YouTube access and no Python loop over comments.
- **Every feature row belongs to the graph:** its node or edge must exist in the STEP 13 graph with the same type, and validation checks this.
- **Each run is tied to a snapshot and a reference time:** every row carries `snapshot_id` and `as_of`.

## Temporal rules (no leakage)

`as_of` defaults to the snapshot's extraction time, and can be set **earlier** to build a historical feature set.
- **Comments and videos:** only those published at or before `as_of` are used.
- **Public metrics** (views, likes, subscribers, API comment and video counts) are **observations made at collection time**. They're used only if `collected_at ≤ as_of`; otherwise they're NULL ("not observed as of").
- **Interaction timestamps:** none after `as_of`, which validation checks.
- **Later than the snapshot:** an `as_of` after the snapshot is refused, because nothing after it is known.
- **Descriptive-only features:** features built at the extraction time describe the full snapshot. For prediction or evaluation experiments, build them with `as_of` = the prediction time.

## Feature groups

### A. Structural · B. Interaction · C. Temporal · F. Coverage: `graph_node_features` (one row per node)

| Feature | channel | video | commenter |
|---|---|---|---|
| `stored_video_count` | Stored videos | · | · |
| `unique_commenter_count` | Distinct commenters | Distinct commenters | · |
| `channel_count` / `video_count` | · | · | Channels / videos commented on |
| `comment_count` / `reply_count` | Stored comments on its videos | Stored comments | Comments posted |
| `avg_comments_per_video` | `comment_count / stored_video_count` | · | · |
| `median_comments_per_video` | Median over stored videos (0 counts included) | · | · |
| `active_commenter_count` | Commenters with ≥ 2 comments on the channel | · | · |
| `interaction_density` | · | Comments / unique commenters | · |
| `is_cross_channel` | · | · | `channel_count > 1` |
| `observed_subscriber_count`, `observed_view_count`, `observed_api_video_count` | Public metrics | · | · |
| `observed_view_count`, `observed_like_count`, `observed_api_comment_count` | · | Public metrics | · |
| `comments_per_view`, `likes_per_view` | · | API comments or likes / views | · |
| `published_at`, `age_days` | Created; `as_of − published_at` (days) | Published; age (days) | · |
| `first_interaction_at`, `last_interaction_at`, `active_span_days` | · | · | First and last comment; span (days) |
| `days_since_first_interaction`, `recency_days` | · | · | `as_of − first` / `as_of − last` (days) |
| `active_days`, `comments_per_active_day` | · | · | Distinct UTC days with comments; comments / active days |
| `collection_coverage` | Stored videos / API video count | Stored comments / API comment count | · |
| `interaction_support_count` | Observed comments behind the features | Same | Same |

`collection_coverage` and `interaction_support_count` are **evidence indicators** for a later confidence model. They aren't confidence scores, and coverage isn't bounded at 1 because API counts can lag behind the stored data.

### E. Edge features: `graph_edge_features` (`comments` and `participates_in` edges)

| Column | Meaning |
|---|---|
| `comment_count`, `reply_count`, `video_count` (`participates_in` only) | Interaction support |
| `first_at`, `last_at`, `active_span_days` | First and last comment; span (days) |
| **`interaction_weight`** | **`ln(1 + comment_count)`**: a transparent, deterministic, non-learned weight |
| `channel_share` (`participates_in` only) | Commenter's comments on the channel / commenter's total comments, in [0, 1] |

Video diversity is kept as the separate `video_count`, not hidden inside the weight. `belongs_to` and `has_topic` carry no interaction features. This **isn't** the final Audience Bridge weighting.

### D. Channel-pair overlap: `channel_pair_features` (observed pairs only, `channel_a < channel_b`)

With A and B as the two channels' commenter sets:

| Column | Formula |
|---|---|
| `shared_commenter_count` | \|A ∩ B\| |
| `channel_a_unique_commenter_count`, `channel_b_unique_commenter_count`, `union_commenter_count` | \|A\|, \|B\|, \|A ∪ B\| |
| `jaccard_similarity` | \|A ∩ B\| / \|A ∪ B\| (NULL if the union is empty) |
| `directional_overlap_a_to_b` | \|A ∩ B\| / \|A\| (**directional**: share of A's commenters also on B) |
| `directional_overlap_b_to_a` | \|A ∩ B\| / \|B\| |
| `overlap_ratio` | \|A ∩ B\| / min(\|A\|, \|B\|) (overlap coefficient) |

Only pairs that share at least one commenter are stored, so the table is sparse. These are baseline descriptive measures, **not** Audience Bridge Scores.

### Commenter participation: `commenter_channel_features`

`commenter_id`, `channel_id`, `video_count`, `comment_count`, `reply_count`, `first_interaction_at`, `last_interaction_at`, `active_span_days`, `interaction_weight`. This is one row per observed commenter–channel pair, the same as the `participates_in` edge features in a tabular form for analysis.

## Missing-value policy

| Case | Value |
|---|---|
| Not applicable (column doesn't apply to the node or edge type) | NULL |
| Unavailable from YouTube (hidden likes or subscribers, disabled comments) | NULL |
| Not observed as of `as_of` (public metric collected later) | NULL |
| Undefined ratio (denominator 0 or NULL) | NULL, never 0 or infinity |
| Genuinely counted zero (e.g. a stored video with no stored comments) | 0 |

Missing values are never silently replaced with 0.

## Normalization

There's no learned or dataset-fitted normalization in this step, so no information can leak from evaluation data. Raw counts are always kept. The only transformation is the fixed `ln(1 + x)` weight, and ratios are defined per row. Any later normalization must be fitted on the training or reference period only.

## Validation (never clips or repairs)

Each of these is reported as invalid:
- schema mismatch
- duplicate feature records on each table's key
- a foreign `snapshot_id` or `as_of`
- node IDs or types that aren't in or don't match the graph
- edge features for edges that aren't in the graph, or of the wrong type
- negative counts or measures
- ratios outside [0, 1]: Jaccard, both directional overlaps, overlap ratio, `channel_share`
- timestamps after `as_of`
- `first_at > last_at`
- `interaction_weight ≠ ln(1 + comment_count)`
- unordered pairs, or pairs with shared > min size
- commenter IDs that aren't pseudonyms

## Artifacts

`data/processed/component_3/<snapshot_id>/features/asof-<YYYYMMDDTHHMMSSZ>/` (git-ignored):

| File | Contents |
|---|---|
| `graph_node_features.parquet`, `graph_edge_features.parquet`, `channel_pair_features.parquet`, `commenter_channel_features.parquet` | Fixed schemas (`FEATURE_SCHEMA_VERSION` 1.0), deterministically sorted |
| `feature_manifest.json` | Snapshot, `as_of`, graph fingerprint, row counts, coverage counts, formulas, missing-value policy, content fingerprint |

Feature sets are written once per snapshot and `as_of`. `load_features` checks the fingerprint, and the same input always gives the same fingerprint.

## Privacy

Commenters appear only as pseudonym node IDs (`commenter:anon_…`). Raw IDs, names, demographics and subscription data aren't present, and a non-pseudonym is rejected. Shared commenters are **interaction signals**: they don't show audience migration, influence, identity or causality.
