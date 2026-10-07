# J26-DS-334 – Growth Intelligence

A Public-Data-Driven Growth Intelligence Framework for Underperforming YouTube Channels in a Multi-Channel Media Organization (SLIIT, IT4010 Research Project, CoEAI / Data Science).

## Team and components

| Component | Topic | Owner | Folder |
|---|---|---|---|
| 1 | Channel-Specific Growth Opportunity Prediction with Pooled Learning | Samarasinghe S I (IT23333802) | `research/component_1/` |
| 2 | Quantified Audience Demand Mining and Content-Gap Divergence | Kahandawa K A N N (IT23307094) | `research/component_2/` |
| 3 | Diffusion-Based Cross-Channel Audience Bridge Scoring | Koonara K M K C (IT23200760) | `research/component_3/` |
| 4 | Hierarchically Pooled Dynamic Topic Modelling with Bayesian Changepoint Flagging | Sankalpa H D T P (IT23323452) | `research/component_4/` |

## Repository layout

```
├── research/component_1..4/   each: preprocessing, model, evaluation, notebooks, results
├── shared/                    common code: data_collection (YouTube API + snapshots), schemas, utils
├── backend/                   api, database, services (incl. growth_engine result fusion)
├── frontend/                  React decision-support dashboard
├── data/                      raw, processed, snapshots  (git-ignored)
├── models/                    trained models, embeddings (git-ignored)
├── config/                    shared non-secret settings
├── docs/                      architecture, methodology, contracts (component output formats)
├── tests/component_1..4/
└── .env.example               copy to .env (never commit .env)
```

## Lifecycle
Research: Data → Preprocessing → Model/Method → Evaluation → Results
System: Results → Backend (Growth Intelligence Engine) → Frontend (Dashboard)

## Rules
- Work inside your own component folders; shared code goes in `shared/`, agreed through a pull request.
- Output formats between components are defined in `docs/contracts/`.
- Public YouTube Data API v3 data only. Commenter IDs are hashed. Never commit data, models or `.env`.
- See `CONTRIBUTING.md` for branches and commits.
