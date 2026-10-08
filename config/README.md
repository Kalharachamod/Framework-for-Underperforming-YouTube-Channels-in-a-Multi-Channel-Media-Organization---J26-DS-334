# Config

Shared, non-secret settings (channel list, snapshot schedule, paths). Secrets such as the API key go in `.env`, never here.

- `research_channels.json` – channel groups collected for the research (`owned`, `competitor`, …): organizations and/or channel IDs; used by the channel collector (see [docs/architecture/supabase.md](../docs/architecture/supabase.md#channel-collector)).
- `organizations/<org>.json` – reviewer-confirmed YouTube channel list of a media organization, created with `python -m shared.data_collection.discover` (see [docs/architecture/org_discovery.md](../docs/architecture/org_discovery.md)).
