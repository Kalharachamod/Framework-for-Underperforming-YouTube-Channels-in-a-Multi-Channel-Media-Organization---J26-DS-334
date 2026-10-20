# Component 3: Ethics and Privacy

This document supersedes and extends the STEP 33 audit in [component3_privacy_and_ethics.md](component3_privacy_and_ethics.md). Technical detail is in [../architecture/privacy.md](../architecture/privacy.md).

## Public-data scope

- Only **public** YouTube resources are used: channel metadata and public statistics, video titles and descriptions, and public comments and replies.
- No private account information, YouTube Studio analytics, watch history, per-user subscriptions or per-user likes are accessed.

## YouTube API usage

- **Access:** the official YouTube Data API v3 only, with a project API key kept in `.env`.
- **Quota:** collection is quota-bounded and logged per run.
- **Terms of Service:** the project intends to follow the YouTube API Services Terms of Service. Formal legal compliance has **not** been independently verified. That review belongs to the supervisor or institution, and this document does not claim it.

## Commenter pseudonymisation

- **How:** at parse time, the public author channel ID is replaced by `anon_` + HMAC-SHA256(`COMMENTER_HASH_SALT`, ID). Raw IDs are not written to research snapshots.
- **Salt:** it lives only in `.env`. It is never committed, printed or logged. The pipeline refuses to run without it (fails closed).
- **Stability:** the same salt gives stable pseudonyms, so overlap can be computed. A different salt makes datasets unlinkable.
- **Limit:** a pseudonym is still a stable account token. It is treated as personal data and never displayed.

## Data minimisation and identity protection

- Every model output is **aggregate**: channel-pair counts, similarities, scores and channel-level statistics.
- The API **never returns commenter identifiers**, raw or hashed. The frontend API client rejects payloads that contain `anon_` or `commenter:` identifiers.
- Comment text is loaded into the research dataset, but **no Component 3 model uses it**, and the dashboard never shows it. Topic similarity uses video titles and descriptions.
- **No personal information appears in the dashboard.** It shows channels, counts, scores and explanations only.
- **No demographic inference** of any kind is made.
- `data/`, `.env` and model outputs are git-ignored.

## Research-use limitations

- Results are research signals about channels, not judgements of individuals or of channel quality.
- They must not be used to profile, target or contact individual commenters.
- They do not show audience migration, subscriber transfer, causality or growth. See [component3_claims_and_boundaries.md](component3_claims_and_boundaries.md).
- **Dual use:** rankings could inform cross-promotion. They are presented with confidence and explanations, not as guaranteed recommendations.
- Raw data is not redistributed. Code, configuration and snapshot IDs are.
- **Retention:** the project README states a 30-day raw-data retention rule. Its enforcement for Component 3 research snapshots has **not** been verified in this audit and should be confirmed with the supervisor.
