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
| `/` | Overview: four visual figure cards (channels with their icons, public comments with the share of commenters on 2+ channels, graph nodes by type, bridge pairs with a histogram of stored scores), a spotlight of the strongest stored bridge (channel icons, score ring, confidence, shared commenters, topic similarity, component breakdown), the research pipeline as a stepper (Ready / Incomplete / Unavailable from stored artifacts; "Running" is never inferred), the top bridges, channels by audience and the research models | `dashboard/summary`, `dashboard/channels`, `dashboard/channel-icons`, `graph/summary`, `bridge/pairs`, `status` |
| `/bridges` | Audience Bridges: the bridge card graph (inbound channels → selected source → outbound destinations, top 3 or 5 per side, optional hiding of confidence below 0.5), the inspection panel of the selected card, and the ranking table (search, source / destination filters, score and confidence thresholds, sortable columns, rows that expand to aggregate evidence) | `bridge/pairs`, `dashboard/channels`, `bridge/{source}/destinations/{destination}` |
| `/channels` | Channel Explorer: metadata, aggregate features, graph connectivity, mean of the stored outgoing scores, outbound (this channel → other) and inbound (other → this channel) potential bridges, research coverage, topic profile, publishing activity, shared-commenter overlap | `channels/{id}`, `channels/{id}/pairs`, `bridge/pairs`, `topics/similarity`, `graph/summary`, `dashboard/views-timeline` |
| `/pipeline` | Pipeline Graph: the method as connected run cards in lanes (data, signals, scoring, baselines, validation); each card shows its stored status, run id and recorded settings; click a card for its configuration | `status`, `graph/summary`, `experiments/runs` |
| `/neural` | Neural Models: HGT architecture diagram from the run configuration (input neurons = recorded input features per node type), training and validation loss and validation ROC-AUC / average precision per epoch, metapath2vec walks per metapath, input features and training setup | `models/neural` |
| `/graph` | Graph Intelligence: node and edge counts, relations, degree histograms, channel connectivity and components, metapath2vec / HGT runs, Personalized PageRank settings and convergence | `graph/summary` |
| `/topics` | Topic Intelligence: a note that topics are continuous embeddings without human-readable labels and that similarity is symmetric, the topic-similarity heatmap (select a channel to highlight it), most similar channels, topic clusters, profile coverage | `topics/similarity`, `dashboard/topics` |
| `/evaluation` | Baselines & Evaluation: the three compared methods (proposed framework, Louvain structural baseline, node2vec representation baseline), a key-results table (metric, value, interpretation band), "Ground-truth relevance labels unavailable", relevance metrics (only with labels), agreement, top-k, temporal stability, sparse robustness, runtime | `evaluation/runs`, `evaluation/{id}/metadata`, `evaluation/{id}/{table}` |
| `/explainability` | A decomposition flow (components → base score → × confidence → final stored score), score decomposition with the formula, ranking context, a descriptive interpretation, reasons, evidence with states, uncertainty | `bridge/{source}/destinations/{destination}` |
| `/experiments` | Experiments: scoring experiments (experiment, snapshot, created, observation period, channels, method weights, status); selecting one shows its configuration, artifacts, evaluation and strongest results. Snapshot comparison (previous → current) when the backend reports the pair compatible, otherwise "Snapshot comparison unavailable for this selection." with the reason. Every stored run with its recorded configuration, and the snapshot list | `bridge/experiments`, `bridge/compare`, `bridge/pairs`, `experiments/runs`, `dashboard/summary`, `status` |
| `/status` | API health and pipeline artifacts, reported separately | `/health`, `status` |
| `/overview` | Research Overview (artifact list; kept for direct links, not in the menu) | `status`, `bridge/experiments`, `channels` |

Visualisations (all drawn from API values; geometry is the only thing computed in the browser):
- **Bridge card graph** (Audience Bridges): one card per stored directed bridge, in three fixed rows: inbound bridges (other channel → source), the selected source, outbound bridges (source → destination). Connector width and colour follow the stored score (bands ≥ 0.6, 0.3–0.6, < 0.3, stated in the legend), dashed connectors mark confidence below 0.5, and each connector carries its score. The layout is fixed, so the same data always gives the same picture; cards are keyboard-accessible buttons that open the inspection panel.
- **Inspection panel**: the selected directed pair with its stored score, confidence, rank, decomposition and aggregate evidence, and a link to the full explanation.
- **Card graphs** (`FlowCanvas`): HTML cards on a scalable canvas with SVG connectors, used by the Pipeline Graph and the bridge card graph. The Pipeline Graph draws only edges between neighbouring lanes; inputs that skip a lane are stated in its caption.
- **Score decomposition**: diffusion, embedding and topic components, base score, confidence and final score, with the formula `AudienceBridgeScore = BaseScore × Confidence`.
- **Topic heatmap**: an HTML table of the stored similarities on a blue sequential scale whose range the legend states.
- **Degree histograms**: node counts per degree bin (linear axis, counts printed on each bar).

Channel icons: channel badges show the channel's public YouTube profile image (from `dashboard/channel-icons`) and fall back to coloured initials when no icon is stored or an image fails to load. Images load directly from YouTube's image hosts (`yt3.ggpht.com`), so the viewer's browser contacts them; no commenter or account image is ever shown.

How the dashboard handles context and data:
- **Context:** the snapshot and experiment selectors in the top bar default to the latest, the same as the API. Every result shows the snapshot and experiment IDs it came from. Snapshot comparison is computed by the backend (`bridge/compare`), which accepts it only for an older snapshot with the same channel set and a stored scoring run; the dashboard shows the reason when it refuses.
- **Display only:** every research value comes from the API. Scores are never recalculated; sorting and filtering only reorder what the backend returned. The channel page's mean outgoing score is the average of stored scores and is labelled as such. Missing values show as "—", loading shows a skeleton shaped like the content, a failed request names what failed and offers "Retry" only when retrying can help (rate limit: "Research API rate limit reached. Please retry later."; timeouts after 20 s), and an empty snapshot says "No research data available for this snapshot."
- **Privacy:** only aggregate evidence and channel-level values are shown. As a second safeguard after the backend's own check, the API client refuses any response containing commenter identifiers.
- **Terminology:** scores are described as potential audience bridges or observed audience affinity. The shared limitations note states that they do not show audience migration, subscriber transfer, causal influence or future growth. The explainability interpretation is generated from stored values with descriptive wording only.

Layout and design (AURA template style): a white left sidebar (Growth Intelligence mark from `public/brand/`, navigation grouped into Core workspace, Research models, Validation and System, the active page marked with a red bar; a drawer behind the menu button below 1024 px) and a white top bar with the page title, snapshot and experiment selectors, channel search and live status. Light grey canvas with flat white panels and thin borders; blue is the data colour, red only marks the active page and the logo, green / amber / red show states. Inter throughout. Secondary pages are lazy-loaded. Checked at 1366, 1440, 1600 and 1920 px wide and at tablet width.

## Known limitations

- **Evidence lives on the pair endpoint:** the ranking endpoint returns scores and components only, so per-destination evidence is shown on the Explainability screen (each row links there). This is a documented backend contract choice, not a missing feature.
- **Top-k lists show the first 100 rows** of the selected method.
- **Comparison table** shows the 25 pairs with the largest absolute score change; the total count is stated.
- **No graph library:** charts are dependency-free SVG and HTML. The bridge network shows channel-level data only (at most one node per channel), so they stay small; the raw commenter graph is never sent to the browser.
- **Snapshot comparison** needs two snapshots with the same channel set; the 3-channel pilot snapshot is therefore not comparable with the 18-channel snapshots.
