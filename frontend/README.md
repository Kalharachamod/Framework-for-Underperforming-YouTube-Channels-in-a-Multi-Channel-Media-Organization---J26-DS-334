# Frontend (React)

The Decision Support Dashboard: Vite + React + TypeScript. Component 3 (Audience Bridge Scoring) is implemented; Components 1, 2 and 4 have placeholder feature folders.

```
frontend/
├── public/
├── src/
│   ├── assets/        images, icons
│   ├── components/
│   │   ├── common/    cards, badges, selects, pager, loading / empty / error states
│   │   ├── layout/    AppShell: sidebar navigation, skip link, page shell
│   │   └── charts/    dependency-free bar charts (fixed axes, text alternatives)
│   ├── features/
│   │   ├── component_1/   opportunity scores, SHAP views
│   │   ├── component_2/   demand-gap visualisation
│   │   ├── component_3/   audience bridge dashboard (api, types, context, pages/)
│   │   └── component_4/   emerging topic alerts
│   ├── pages/         one file per screen (created during UI design)
│   ├── hooks/         useApi: loading / success / error with stale-response protection
│   ├── services/      apiClient: central HTTP client calling the backend
│   ├── routes/        AppRoutes: navigation and route definitions
│   ├── store/         shared state
│   ├── utils/         formatting (NULL shown as "—", never as 0)
│   └── styles/        global.css (neutral theme, responsive rules)
└── tests/             Vitest + Testing Library, mocked API responses
```

Rule: each member builds only inside their own `features/component_N/`; shared pieces go in `components/`.

## Setup

Use Node 20 or newer.

```powershell
cd frontend
npm install
copy .env.example .env.local      # optional; the default is http://localhost:8000
```

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Backend base URL. Vite exposes `VITE_*` values to the browser, so **never put secrets here** |

## Run

Start the backend from the repository root, then start the dashboard:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
cd frontend; npm run dev                      # http://localhost:5173
```

You don't need a proxy. The backend allows `http://localhost:5173` by default through `API_CORS_ORIGINS` in the root `.env`. If you serve the dashboard from another origin, add it there; `*` is refused.

| Command | Purpose |
|---|---|
| `npm run dev` | Development server on port 5173 |
| `npm test` | Unit and component tests (mocked API, no backend needed) |
| `npm run build` | Type-check and production build into `dist/` |

## Component 3 screens

| Route | Screen | API endpoints (`/api/v1/component-3/...`) |
|---|---|---|
| `/` | Overview: snapshot, current experiment, artifact availability | `status`, `bridge/experiments`, `channels` |
| `/bridges` | Audience Bridges: ranked destinations for a source, score chart, components | `bridge/{source}/destinations` |
| `/channels` | Channel Explorer: metadata, aggregate features, shared-commenter overlap | `channels/{id}`, `channels/{id}/pairs` |
| `/explainability` | Score decomposition, evidence with states, reasons, uncertainty, ranking context | `bridge/{source}/destinations/{destination}` |
| `/evaluation` | Method status, relevance metrics (only with labels), agreement, top-k, temporal, sparse robustness, performance | `evaluation/runs`, `evaluation/{id}/metadata`, `evaluation/{id}/{table}` |
| `/status` | API health and pipeline artifacts, reported separately | `/health`, `status` |

How the dashboard handles context and data:
- **Context:** the snapshot and experiment selectors in the top bar default to the latest, the same as the API. Every result shows the snapshot and experiment IDs it came from.
- **Display only:** every number comes from the API. Missing values show as "—", and a failed request shows an error, never fallback data. The dashboard never generates explanations.
- **Privacy:** only aggregate evidence is shown. As a second safeguard after the backend's own check, the API client refuses any response containing commenter identifiers.

## Known limitations

- **Evidence lives on the pair endpoint:** the ranking endpoint returns scores and components only, so per-destination evidence is shown on the Explainability screen (each row links there). This is a documented backend contract choice, not a missing feature.
- **Top-k lists show the first 100 rows** of the selected method.
- **Charts are simple bar charts** with fixed axes. The tables beside them are the primary accessible view.
