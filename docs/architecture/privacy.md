# Privacy: Commenter Pseudonymization

Code: [`shared/utils/privacy.py`](../../shared/utils/privacy.py) · Tests: [`tests/shared/test_privacy.py`](../../tests/shared/test_privacy.py)

## What is protected

A YouTube comment carries the commenter's channel ID (`author_channel_id`). It's public on YouTube, but storing it would let our dataset be linked back to individual people. The project therefore stores a **pseudonym** instead:

```
author_channel_id  "UC…"  →  "anon_" + HMAC-SHA256(COMMENTER_HASH_SALT, "UC…")   (64 hex characters)
```

| Property | Why it matters |
|---|---|
| Same commenter → same pseudonym | Component 3 can still see that one person comments on several channels (audience bridges) |
| Different commenters → different pseudonyms | Audiences stay distinguishable |
| Can't be reversed without the secret salt | The stored data alone doesn't identify anyone |
| Keyed with a salt (HMAC), not a plain hash | Nobody can hash a known channel ID and look it up in our data |

## Where it happens

```
API response → collector → Comment schema (raw id, in memory only) → store_records → pseudonymize → Parquet
```

- `store_records("comments", ...)` pseudonymizes every `author_channel_id` before writing. **Raw commenter IDs never reach Parquet, snapshots or DuckDB**, whichever code calls it.
- The schema stays a plain data definition; privacy processing is a separate module.
- Already-pseudonymized values are left unchanged, so re-runs are safe and never double-hashed.
- A missing `author_channel_id` stays missing; nothing is invented.
- **Fails closed:** without a valid salt, storing comments that have commenter IDs raises `PrivacyConfigError`, and nothing is written.
- The quality check (`unhashed_commenter_ids`, see [data_quality.md](data_quality.md)) warns about any stored commenter ID that isn't a pseudonym.

## The salt (`COMMENTER_HASH_SALT`)

- Generate it **once for the whole team**:
  `python -c "import secrets; print(secrets.token_hex(32))"`
- Keep it in `.env` only. It must be at least 32 characters, and placeholders are rejected.
- **All members must use the same salt.** Otherwise the same commenter gets different pseudonyms on different machines.
- **Never change it.** Pseudonyms made with a new salt don't match the old ones.
- Share it privately and keep a private backup. If it leaks, someone could test guessed channel IDs against the data.
- The salt never appears in logs, errors, reports, manifests or stored data.

## Interpretation limits

A pseudonym is a stable *account* token. Its presence does **not** prove subscription, audience migration, demographic identity or causality (see [schemas.md](schemas.md)).
