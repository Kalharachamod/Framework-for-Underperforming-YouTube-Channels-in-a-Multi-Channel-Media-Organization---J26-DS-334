# Config

Shared, non-secret settings (channel list, snapshot schedule, paths). Secrets such as the API key go in `.env`, never here.

- `organizations/<org>.json` – reviewer-confirmed YouTube channel list of a media organization, created with `python -m shared.data_collection.discover` (see [docs/architecture/org_discovery.md](../docs/architecture/org_discovery.md)).
