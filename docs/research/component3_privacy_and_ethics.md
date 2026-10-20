# Component 3: Privacy and Ethics

*STEP 33, §15.* See also [../architecture/privacy.md](../architecture/privacy.md) and [component3_scope_boundary.md](component3_scope_boundary.md).

## Data used

- Only **public** YouTube data from the Data API v3: channel metadata, video titles and descriptions, and public comments.
- No private activity, watch history, subscriptions per user, likes per user or demographics.

## Protection measures (verified)

| Measure | Implementation |
|---|---|
| Pseudonymisation at parse time | commenter ID → `anon_` + HMAC-SHA256(`COMMENTER_HASH_SALT`, id). Raw IDs are not stored in research snapshots |
| Fail closed | the pipeline refuses to run without the salt |
| Secret handling | salt, API key and Supabase credentials live only in `.env`; never in code, docs or logs |
| Aggregate-only outputs | every model output is channel-level or a count / similarity. No per-commenter result leaves the pipeline |
| API boundary | the API never returns commenter IDs (raw or hashed) |
| Frontend guard | the API client rejects payloads containing `anon_` / `commenter:` identifiers |
| Comment text | loaded into the STEP 12 research dataset, but no Component 3 model uses it (topic similarity uses video titles and descriptions only); never returned by the API |
| Read-only dashboard | no write or delete operations on research data |

## Ethical boundaries

- **No profiling of individuals.** The unit of analysis is the channel pair.
- **No migration, causality or growth claims.** Scores are evidence of shared public commenters and similar content, not of people moving.
- **Representativeness.** Commenters are a small, self-selected subset of viewers, so results describe commenter behaviour only.
- **Popularity bias.** Absolute shared-commenter counts favour larger channels; results should not be read as a judgement of channel quality.
- **Dual use.** Rankings could be used for cross-promotion targeting. They are presented as research signals with confidence and explanations, not as guaranteed recommendations.
- **Data sharing.** Raw data is not redistributed; only code, configuration and snapshot identifiers are.

**Status:** compliant with the project privacy rules. No issue found.
