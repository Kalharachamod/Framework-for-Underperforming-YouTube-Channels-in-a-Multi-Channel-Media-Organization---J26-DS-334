# Component 3: Reproduction Guide

This guide is for a new researcher reproducing Component 3. The commands are the ones that exist in the repository.

- **Windows PowerShell** (as used for the reported runs): `.venv\Scripts\python.exe -m …`
- **macOS / Linux:** activate the virtual environment, then use `python -m …`

## 1. Environment setup

Prerequisites: Python 3.10 or later (the reported runs used 3.13.2), Node.js 18 or later, Git, and about 2 GB of free disk space.

```powershell
git clone <repository-url>
cd J26-DS-334-Growth-Intelligence
python -m venv .venv
.venv\Scripts\activate                    # macOS/Linux: source .venv/bin/activate
```

## 2. Dependency installation

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU PyTorch first
pip install -r requirements.txt
pip install -e .
cd frontend; npm install; cd ..
```

`requirements.txt` gives lower bounds only. To match the reported runs, install the versions recorded in [component3_experimental_setup.md](component3_experimental_setup.md) (each experiment manifest also lists them). The first topic run downloads `intfloat/multilingual-e5-small` (~470 MB) at the pinned revision.

## 3. Configuration

```powershell
Copy-Item .env.example .env               # macOS/Linux: cp .env.example .env
```

Fill in `.env`, which must never be committed:
- `YOUTUBE_API_KEY`
- `COMMENTER_HASH_SALT`: use the team's salt to reproduce the same pseudonyms
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_DB_URL`
- optionally `VITE_API_URL`

## 4. API configuration

- **YouTube key:** see [../architecture/youtube_api.md](../architecture/youtube_api.md).
- **Database:** see [../architecture/supabase.md](../architecture/supabase.md). Create the tables once with:

  ```powershell
  .venv\Scripts\python.exe -m shared.database.migrate
  ```

## 5–6. Data collection and snapshot creation

```powershell
.venv\Scripts\python.exe -m shared.data_collection.run_collection --max-videos 50 --snapshot
```

This creates a new `rs-<time>` research snapshot.
- **Exit code 1 means some items failed.** Read the run log in `data/raw/collection_runs/` and do not treat that snapshot as complete.
- **Without API access:** use an existing snapshot instead.
- **Pipeline only, no API calls:** `.venv\Scripts\python.exe -m research.component_3.pilot --config config/experiments/component_3_full.json --snapshot rs-…` runs every stage with timings on a snapshot created by the runner.

## 7. Processing

```powershell
.venv\Scripts\python.exe -m research.component_3.preprocessing.research_dataset
.venv\Scripts\python.exe -m research.component_3.model.topic_similarity --topics 10
```

## 8. Graph construction

```powershell
.venv\Scripts\python.exe -m research.component_3.preprocessing.hetero_graph --topic-run latest
.venv\Scripts\python.exe -m research.component_3.preprocessing.graph_features
```

Check that the graph output reports `topic 10` and `has_topic` > 0. Without `--topic-run`, the graph has no topic nodes and the VTV metapath is unused.

## 9. Model execution

```powershell
.venv\Scripts\python.exe -m research.component_3.model.metapath2vec
.venv\Scripts\python.exe -m research.component_3.model.hgt
.venv\Scripts\python.exe -m research.component_3.model.ppr_diffusion
```

## 10. Scoring

```powershell
.venv\Scripts\python.exe -m research.component_3.model.audience_bridge
# ablations (documented variants, not replacements):
.venv\Scripts\python.exe -m research.component_3.model.audience_bridge --embedding-source hgt
.venv\Scripts\python.exe -m research.component_3.model.audience_bridge --weights 0.5 0 0.5 --embedding-source none
```

## 11. Baselines

```powershell
.venv\Scripts\python.exe -m research.component_3.model.baselines louvain
.venv\Scripts\python.exe -m research.component_3.model.baselines node2vec
```

## 12. Evaluation and explanations

```powershell
.venv\Scripts\python.exe -m research.component_3.evaluation.evaluate                 # full: can take hours
.venv\Scripts\python.exe -m research.component_3.evaluation.evaluate --skip-sparse   # quick, no robustness
.venv\Scripts\python.exe -m research.component_3.explainability.explain
.venv\Scripts\python.exe -m research.component_3.findings --snapshot rs-20261010T081534Z   # report from stored artifacts
```

- Every stage takes `--snapshot rs-…`; the default is the latest snapshot.
- Results are write-once: re-running with identical inputs reproduces the same experiment ID.
- Keep the machine awake during a full evaluation (Finding 1).

## 13. Backend

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000    # docs: http://localhost:8000/docs
```

## 14. Dashboard

Run this in a second terminal:

```powershell
cd frontend; npm run dev                                                     # http://localhost:5173
```

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/backend tests/component_3 tests/integration -q
cd frontend; npx tsc -b; npx vitest run
```

Tests use synthetic data and never call the YouTube API or production Supabase. One pilot preflight test requires at least 1 GB of free disk space.
