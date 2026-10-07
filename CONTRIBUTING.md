# Contributing

## Branches
- `main`: stable, always working. No direct pushes; merge through pull requests.
- Work branches: `component-<n>/<short-description>` (e.g. `component-3/ppr-diffusion`), or `shared/<description>`, `frontend/<description>`.

## Commits
Short, imperative messages with a prefix: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

## Pull requests
- At least one teammate reviews before merging.
- Changes to `shared/`, `docs/contracts/` or `backend/services/growth_engine/` need review from all component owners.

## Do not commit
Data (`data/`), trained models (`models/`), notebook outputs with comment text, `.env`, API keys.
