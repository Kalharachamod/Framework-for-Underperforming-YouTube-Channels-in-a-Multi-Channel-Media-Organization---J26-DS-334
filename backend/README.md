# Backend

Read-only FastAPI service over the research results. Component 3 (Diffusion-Based Cross-Channel Audience Bridge Scoring) is implemented; Components 1, 2 and 4 have placeholder folders.

The API **reads stored research artifacts**. It never collects data, trains a model or reruns the pipeline during a request.

## Layout

| Path | Responsibility |
|---|---|
| `main.py` | App factory: CORS, request timeout, error handlers, `/health`, routers |
| `config.py` | Environment-based settings |
| `errors.py` | One consistent error format; no stack traces or paths |
| `api/component_3/routes.py` | Endpoints, parameters and OpenAPI documentation |
| `api/component_3/schemas.py` | Pydantic response contracts |
| `services/component_3/service.py` | Snapshot and experiment selection, validation, response shaping, identifier guard |
| `database/component_3_artifacts.py` | Bounded DuckDB queries over Parquet research snapshots and artifacts |

## Configuration

Copy `.env.example` to `.env`. The API needs **no secrets**.

| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `data` | Research data root, shared with the pipeline |
| `API_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated frontend origins. `*` is refused |
| `API_MAX_PAGE_SIZE` | `100` | Upper bound for `?limit=` |
| `API_REQUEST_TIMEOUT_SECONDS` | `30` | Longer requests get `504 timeout` |

## Run locally

```powershell
pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs (OpenAPI JSON at `/openapi.json`)
- Liveness: http://localhost:8000/health

### Artifact prerequisites

The API serves whatever exists. `GET /api/v1/component-3/status` shows each artifact's status separately. To produce everything for the latest snapshot:

```powershell
python -m shared.data_collection.run_collection --snapshot             # research snapshot (STEP 12)
python -m research.component_3.preprocessing.hetero_graph              # graph (STEP 13)
python -m research.component_3.preprocessing.graph_features            # features (STEP 14)
python -m research.component_3.model.audience_bridge                   # scores (STEP 19)
python -m research.component_3.explainability.explain                  # explanations (STEP 22)
python -m research.component_3.evaluation.evaluate --skip-sparse       # evaluation (STEP 21)
```

## Endpoints

All Component 3 paths start with `/api/v1/component-3`. Channel IDs are YouTube channel IDs (`UC…`).

How selection works:
- `snapshot_id` defaults to the latest research snapshot.
- `experiment_id` defaults to the latest Audience Bridge Score run of that snapshot.
- Responses always echo the IDs actually used.

| Method and path | Purpose |
|---|---|
| `GET /health` | The API process is up. Says nothing about artifacts |
| `GET /status` | Snapshots, plus per-artifact availability (graph, features, diffusion, topics, baselines, scores, explanations, evaluations) |
| `GET /channels` | Channels with aggregate features |
| `GET /channels/{channel_id}` | One channel's metadata and STEP 14 features |
| `GET /channels/{channel_id}/pairs` | Channels sharing commenters (aggregate counts, Jaccard), paged |
| `GET /bridge/experiments` | STEP 19 runs, their weights, and linked explanations and evaluations |
| `GET /bridge/{source}/destinations` | Ranked destinations (`limit`, `offset`, `include_unscored`, `experiment_id`) |
| `GET /bridge/{source}/destinations/{destination}` | Score, decomposition, evidence, reasons, uncertainty, ranking context |
| `GET /evaluation/runs` | STEP 21 runs of a snapshot |
| `GET /evaluation/{evaluation_id}/metadata` | Run settings, method statuses, labels and temporal status (no local paths) |
| `GET /evaluation/{evaluation_id}/{table}` | Rows of `ranking`, `top_k`, `temporal_stability`, `sparse_robustness` or `performance`, filtered by `method` and `metric`, paged |
| `GET /bridge/pairs` | Every stored scored pair of a scoring run with its components and raw topic similarity, ordered by score (bounded by the number of channel pairs; nothing recalculated) |
| `GET /dashboard/channel-icons` | Public YouTube profile-image URLs of the research channels (presentation only; not used by any score). Filled by `python -m research.component_3.preprocessing.channel_icons` (one `channels.list` call, about 1 quota unit per 50 channels) into `data/processed/component_3/channel_icons.json`; only https URLs on YouTube image hosts and valid channel ids are served, an absent file gives an empty list |
| `GET /bridge/compare?base_snapshot_id=…&snapshot_id=…` | Pair-level change between the latest scoring runs of an older snapshot and the selected one (score, rank, confidence, diffusion contribution, topic similarity: previous, current, difference). Returns `compatible: false` with a reason unless the base is older, both have a scoring run and both cover the same channel set; `same_configuration` says whether method version and weights match. Differences of stored values only |
| `GET /graph/summary` | Node and edge counts by type, degree histograms (node counts per degree bin, observed edges only), channel connectivity, connected components, stored metapath2vec / HGT / Personalized PageRank run settings |
| `GET /topics/similarity` | Channel × channel topic-similarity matrix of the latest STEP 18 run, with profile coverage |
| `GET /models/neural` | Stored HGT configuration, per-epoch training and validation records (loss, ROC-AUC, average precision), input feature names per node type, split sizes, and metapath2vec walk statistics per metapath; a model that was not run is `missing` |
| `GET /experiments/runs` | Every stored run of a snapshot (graph, features, diffusion, topics, embeddings, baselines, scoring, explanations, evaluations) with id, time, validation result and recorded configuration |
| `GET /dashboard/summary`, `/dashboard/channels`, `/dashboard/top-videos`, `/dashboard/views-timeline`, `/dashboard/overlap`, `/dashboard/topics`, `/dashboard/top-bridges` | Snapshot totals and channel-level aggregates for the dashboard (public counts of collected videos; aggregate commenter counts only) |

The research-view endpoints (`/bridge/pairs`, `/bridge/compare`, `/graph/summary`, `/topics/similarity`, `/experiments/runs`, `/models/neural`) read stored run metadata and Parquet results only. They return counts, channel-level values and run settings, never a commenter or video node identifier; a missing run is reported (`artifact_unavailable`, or `status: missing` inside the graph summary), never filled in.

### Example

`GET /api/v1/component-3/bridge/UCJr5vlnK6HEBVISUtxnq_sg/destinations?limit=1`:

```json
{
  "total": 17, "limit": 1, "offset": 0,
  "snapshot_id": "rs-20261008T191612Z", "experiment_id": "abs-84bac08439a8",
  "source_channel_id": "UCJr5vlnK6HEBVISUtxnq_sg", "source_channel_name": "Derana Little Star",
  "include_unscored": false,
  "items": [{"rank": 1, "destination_channel_id": "UCs8gVM6lPhRZk3L_zZmedpw", "destination_channel_name": "Dream Star",
             "audience_bridge_score": 0.8853, "diffusion_component": 0.5, "embedding_component": 0.0, "topic_component": 0.4591,
             "confidence_component": 0.9231, "base_score": 0.9591, "score_status": "ok"}],
  "note": "Audience Bridge Scores are potential audience bridge signals ..."
}
```

The pair endpoint adds:
- `score_breakdown`: raw and normalized diffusion, embedding and topic components, the three weights, `embedding_source`, `shared_commenters`, the confidence parts, and the formula
- `explanation_status`: `available`, or `unavailable` with `explanation_detail` when no STEP 22 artifact exists for the experiment
- `evidence_summary`, `explanation_reasons`, `uncertainty_notes` and `ranking_context`

## Errors

Every error has the same shape: `{"error": {"code", "message", "details"?}}`.

| HTTP | `code` | When |
|---|---|---|
| 404 | `not_found` | Unknown snapshot, channel, experiment, evaluation or pair |
| 404 | `artifact_unavailable` | The artifact hasn't been produced yet (e.g. no STEP 19 run, no evaluation yet) |
| 422 | `invalid_parameter` | Malformed ID, `limit` out of range, unknown method, a filter the table doesn't support, a self pair |
| 503 | `storage_unavailable` | Artifacts couldn't be read (missing or corrupt file) |
| 504 | `timeout` | The request exceeded `API_REQUEST_TIMEOUT_SECONDS` |
| 500 | `internal_error` | Anything unexpected. The message is generic, and the log records the exception type only |

A filter that matches nothing returns `200` with an empty `items` list. That's distinct from "not run yet" (`artifact_unavailable`) and from "invalid filter" (`invalid_parameter`).

## Security and privacy

- **CORS:** only the configured origins are allowed, for `GET` only and without credentials. A wildcard is rejected at startup.
- **Validated input:** IDs are checked against strict patterns, and filters against the run's own methods. SQL values are bound parameters, and column names come only from code.
- **Bounded reads:** every list is paged (`limit` ≤ `API_MAX_PAGE_SIZE`), and queries read single Parquet files with projection and `WHERE`/`LIMIT`. No full comment or embedding tables are loaded.
- **No commenter identifiers:** the schemas have no field for them, and a final guard blocks any response containing a pseudonym (`anon_…`) or commenter node ID, answering with a generic 500.
- **No sensitive values in responses:** responses and OpenAPI contain no credentials, file paths or stack traces. Evaluation metadata drops local paths and platform details.
- **Access control:** there's no authentication. The project has none, and the API is read-only over aggregate research results. It's meant for local or trusted-network use. Put it behind an authenticating proxy before exposing it publicly.
- **Supabase:** the API doesn't connect to Supabase. Supabase is the collection store, while the API serves the immutable research snapshots and artifacts derived from it.

## Testing

```powershell
.venv\Scripts\python.exe -m pytest tests/backend -q
```

The tests build a synthetic snapshot and run the real STEP 13, 14, 19, 21 and 22 pipeline into a temporary folder. They make no network calls and don't use Supabase.

## Known limitations

- **Artifact checksums are verified when artifacts are written,** not on every API read, to keep requests cheap. A corrupted file surfaces as `storage_unavailable`.
- **The request timeout returns 504,** but a thread already running a query finishes in the background.
- **Baseline status:** baselines appear as `missing` unless they were saved by their own CLI (`python -m research.component_3.model.baselines …`). The evaluation runs them without persisting them.
- **The STEP 19 formula is provisional** (see `docs/architecture/audience_bridge.md`).
