# Collection Runbook (setup, repeated collection, scheduling)

How to set up a machine, collect YouTube data repeatedly, and keep the research dataset growing over time. Repeated collection is what makes temporal evaluation possible: HGT's temporal split, historical features and snapshot comparisons all depend on it.

## 1. One-time setup per team member

```powershell
git clone <repo> ; cd <repo>
python -m venv .venv ; .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU PyTorch (~200 MB), before the rest
pip install -r requirements.txt
pip install -e .
Copy-Item .env.example .env       # then fill in the values (never in .env.example)
```

| `.env` value | Source | Notes |
|---|---|---|
| `YOUTUBE_API_KEY` | Google Cloud Console | Each member can use their own key, or the team shares one; mind the quota |
| `COMMENTER_HASH_SALT` | Shared privately by the team | **Must be identical for everyone and never change** ([privacy.md](architecture/privacy.md)) |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_DB_URL` | Supabase project → Connect (Session pooler) | The database password is secret ([supabase.md](architecture/supabase.md)) |

- **First topic run:** the multilingual model `intfloat/multilingual-e5-small` (~470 MB) downloads once and is then cached.
- **Database tests:** `python -m pytest` runs everything. The database tests need a local **PostgreSQL** installation (for `initdb` / `pg_ctl`); without it they're skipped with a message. The suite takes about 2–3 minutes.

## 2. One collection run

```powershell
python -m shared.data_collection.run_collection --max-videos 50 --snapshot
```

The run goes through these stages in order:

| Stage | What it does | Approximate quota (18 channels) |
|---|---|---|
| channels | Refreshes channel statistics | 1 |
| videos | Newest 50 videos per channel (new ones inserted, known ones updated) | ~37 |
| comments | `--incremental`: new threads per video, stopping at already-stored threads | ~1 per video with comments + reply pages |
| research snapshot (`--snapshot`) | Supabase → immutable Parquet snapshot → validation → research-ready datasets | 0 (database read) |

- **Daily quota:** 10,000 units. A routine run costs a few hundred.
- **Run logs** are written to `data/raw/collection_runs/<time>.json`.
- **Exit codes:** `0` means OK; `1` means some items failed (see the stage output); a stage that can't run at all (configuration or connection) stops the run.

**Unstable network:** a dropped connection fails only the affected videos; everything else is stored. Run `python -m shared.data_collection.comment_collector --new-only` afterwards to fill in videos that are still missing comments.

## 3. Repeat automatically (Windows Task Scheduler)

1. **Task Scheduler → Create Basic Task →** name `J26 YouTube collection` → **Daily**, at a fixed time (e.g. 02:00).
2. **Action: Start a program**
   - Program: `C:\SLIIT\Research\J26-DS-334-Growth-Intelligence\.venv\Scripts\python.exe`
   - Arguments: `-m shared.data_collection.run_collection --max-videos 50 --snapshot`
   - Start in: `C:\SLIIT\Research\J26-DS-334-Growth-Intelligence`
3. **Properties:**
   - "Run whether user is logged on or not"
   - "Do not start a new instance" if one is still running (single writer)

Only **one** team member should schedule collection, to avoid duplicate quota use. Everyone else reads the shared Supabase data.

On Linux or macOS, the cron equivalent is:
`0 2 * * * cd /path/to/repo && .venv/bin/python -m shared.data_collection.run_collection --max-videos 50 --snapshot`.

## 4. After each run (analysis pipeline, local)

```powershell
python -m research.component_3.model.topic_similarity --topics 10   # topic clusters (choose and report N)
python -m research.component_3.preprocessing.hetero_graph --topic-run latest   # graph with topic nodes
python -m research.component_3.preprocessing.graph_features      # features
python -m research.component_3.model.metapath2vec                # primary embeddings
python -m research.component_3.model.hgt                         # alternative embeddings
python -m research.component_3.model.ppr_diffusion               # diffusion
python -m research.component_3.model.audience_bridge             # Audience Bridge Score (diffusion + embedding + topic)
python -m research.component_3.model.audience_bridge --embedding-source hgt    # same with the HGT embeddings
python -m research.component_3.model.baselines louvain           # Louvain baseline
python -m research.component_3.model.baselines node2vec          # node2vec baseline
python -m research.component_3.explainability.explain            # explanations of the latest bridge run
python -m research.component_3.evaluation.evaluate               # evaluation (add --skip-sparse for a quick run)
```

The API and dashboard then serve these results (see [backend/README.md](../backend/README.md)).

## Scope and open items

- **Channel set:** the 18 confirmed **Derana** channels (`config/research_channels.json`, group `owned`). The `competitor` group is intentionally empty, because the research studies bridges between the organization's own channels.
- **Data retention:** the 30-day YouTube API retention policy is **still to be decided** with the supervisor. Until then, keep the data private (no exports outside the team).
