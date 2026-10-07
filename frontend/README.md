# Frontend (React)

Decision Support Dashboard. Not initialised yet; create the app in this folder (e.g. Vite + React) when implementation starts.

```
frontend/
├── public/
├── src/
│   ├── assets/        images, icons
│   ├── components/
│   │   ├── common/    buttons, cards, tables
│   │   ├── layout/    navbar, sidebar, page shell
│   │   └── charts/    shared chart wrappers
│   ├── features/
│   │   ├── component_1/   opportunity scores, SHAP views
│   │   ├── component_2/   demand-gap visualisation
│   │   ├── component_3/   audience bridge ranking
│   │   └── component_4/   emerging topic alerts
│   ├── pages/         one file per screen (created during UI design)
│   ├── hooks/         reusable React hooks
│   ├── services/      API client calling the backend
│   ├── routes/        route definitions
│   ├── store/         shared state
│   ├── utils/
│   └── styles/
└── tests/
```

Rule: each member builds only inside their own `features/component_N/`; shared pieces go in `components/`.
Backend URL is read from `VITE_API_URL` (see `.env.example`).
