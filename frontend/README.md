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
│   │   └── charts/    dependency-free SVG/HTML charts: bridge flow, ego network, score breakdown, heatmap, histograms, lines, bars
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
│   └── styles/        global.css (research theme: navy/indigo, responsive rules)
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

The dashboard presents the Component 3 method in order: heterogeneous graph → metapath2vec / HGT → Personalized PageRank → topic similarity → confidence weighting → Audience Bridge Score → baseline comparison → evaluation → explainability.

| Route | Screen | API endpoints (`/api/v1/component-3/...`) |
|---|---|---|
| `/` | Overview: research status (snapshot, channels, videos, comments, graph nodes and edges, experiment), the method steps with their stored-run status, a bridge explorer (source, destination, ranking depth) and the strongest bridges | `dashboard/summary`, `graph/summary`, `bridge/pairs`, `status` |
| `/bridges` | Audience Bridges: source list, ego network of the selected source (directed edges, width and colour by score, adjustable depth), selected-bridge analysis (score decomposition and aggregate evidence), and the sortable, filterable table of all scored pairs | `bridge/pairs`, `bridge/{source}/destinations/{destination}` |
| `/channels` | Channel Explorer: metadata, aggregate features, graph connectivity, mean of the stored outgoing scores, top potential destinations, topic profile, publishing activity, shared-commenter overlap | `channels/{id}`, `channels/{id}/pairs`, `bridge/pairs`, `topics/similarity`, `graph/summary`, `dashboard/views-timeline` |
| `/pipeline` | Pipeline Graph: the method as connected run cards in lanes (data, signals, scoring, baselines, validation); each card shows its stored status, run id and recorded settings; click a card for its configuration | `status`, `graph/summary`, `experiments/runs` |
| `/graph` | Graph Intelligence: node and edge counts, relations, degree histograms, channel connectivity and components, metapath2vec / HGT runs, Personalized PageRank settings and convergence | `graph/summary` |
| `/topics` | Topic Intelligence: topic-similarity heatmap (select a channel to highlight it), most similar channels, topic clusters, profile coverage | `topics/similarity`, `dashboard/topics` |
| `/evaluation` | Baselines & Evaluation: method status, relevance metrics (only with labels), agreement, top-k, temporal stability, sparse robustness, runtime | `evaluation/runs`, `evaluation/{id}/metadata`, `evaluation/{id}/{table}` |
| `/explainability` | Score decomposition with the formula, ranking context, a descriptive interpretation, reasons, evidence with states, uncertainty | `bridge/{source}/destinations/{destination}` |
| `/experiments` | Experiments: every stored run with its recorded configuration and validation result, plus the snapshot list | `experiments/runs`, `dashboard/summary`, `status` |
| `/status` | API health and pipeline artifacts, reported separately | `/health`, `status` |
| `/overview` | Research Overview (artifact list; kept for direct links, not in the menu) | `status`, `bridge/experiments`, `channels` |

Visualisations (all drawn from API values; geometry is the only thing computed in the browser):
- **Card graphs** (`FlowCanvas`): HTML cards on a scalable canvas with SVG connectors, used by the Pipeline Graph and the bridge tree. Fit, zoom buttons and Ctrl + wheel / pinch zoom; cards are keyboard-accessible buttons.
- **Bridge tree** (Overview, Audience Bridges): a source card connected to its top-k destination cards; connector width, colour and label follow the stored score.
- **Radial network** (Audience Bridges, "Radial" view): the selected source in the centre and every scored destination around it; directed edges for the chosen depth, width and colour by score.
- **Score decomposition**: diffusion, embedding and topic components, base score, confidence and final score, with the formula `AudienceBridgeScore = BaseScore × Confidence` in a tooltip.
- **Topic heatmap**: an HTML table of the stored similarities; shading spans the observed value range, which the legend states.
- **Degree histograms**: node counts per degree bin (linear axis, counts printed on each bar).

How the dashboard handles context and data:
- **Context:** the snapshot and experiment selectors in the top bar default to the latest, the same as the API. Every result shows the snapshot and experiment IDs it came from. Snapshots are compared only inside the evaluation (temporal stability), where the backend pairs comparable snapshots; the dashboard never compares snapshots itself.
- **Display only:** every research value comes from the API. Scores are never recalculated; sorting and filtering only reorder what the backend returned. The channel page's mean outgoing score is the average of stored scores and is labelled as such. Missing values show as "—", a failed request shows an error, and an empty snapshot says "No research data available for this snapshot."
- **Privacy:** only aggregate evidence and channel-level values are shown. As a second safeguard after the backend's own check, the API client refuses any response containing commenter identifiers.
- **Terminology:** scores are described as potential audience bridges or observed audience affinity. The shared limitations note states that they do not show audience migration, subscriber transfer, causal influence or future growth. The explainability interpretation is generated from stored values with descriptive wording only.

Design system: light neutral background, navy as the primary colour (scores, active navigation), indigo for the selected element in charts, muted green / amber / red for status only, Inter throughout.

## Known limitations

- **Evidence lives on the pair endpoint:** the ranking endpoint returns scores and components only, so per-destination evidence is shown on the Explainability screen (each row links there). This is a documented backend contract choice, not a missing feature.
- **Top-k lists show the first 100 rows** of the selected method.
- **No graph library:** charts are dependency-free SVG and HTML. The ego network and bridge flow show channel-level data only (at most one node per channel), so they stay small; the raw commenter graph is never sent to the browser.
- **Snapshot comparison** is limited to the evaluation's temporal stability results; there is no free side-by-side snapshot comparison.
