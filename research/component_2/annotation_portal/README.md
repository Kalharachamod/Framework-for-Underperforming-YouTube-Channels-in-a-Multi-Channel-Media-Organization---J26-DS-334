# Component 2 Annotation Portal

This Streamlit portal supports human demand and spam annotation for the reviewed 300-comment Component 2 snapshot. It preserves the deterministic Section A-E assignments and the primary researcher mode without changing the original research tables or CSV labels.

## Local Testing

From the repository root:

```bash
.venv/bin/python -m streamlit run research/component_2/annotation_portal/app.py
```

Local mode is the default and uses:

```text
data/processed/component_2/annotation/component2_demand_annotation_sample.csv
data/processed/component_2/annotation/annotation_portal_local.sqlite3
```

The local SQLite file is ignored by Git and is only a development/test store. It must not be used as the deployed response store.

The local participant flow is:

1. Enter a display name or nickname.
2. Choose Section A, B, C, D, or E, or choose Primary researcher mode.
3. Save the private return code shown after starting.
4. Use the return code to resume the same session later.

Display names are not verified authentication. Each session receives a unique participant ID and responses are isolated by participant ID plus comment ID. Multiple people can annotate the same section independently.

## Guidance Shown In The Portal

Demand and spam are separate decisions:

- `DEMAND`: the commenter requests or suggests content, an explanation, another topic, or an improvement.
- `NON_DEMAND`: general feedback, reactions, or discussion without an identifiable content request.
- `UNCLEAR`: insufficient information.
- `SPAM`: advertisements, suspicious promotions, scams, or unrelated self-promotion.
- `NOT_SPAM`: genuine comments, feedback, opinions, or requests.
- `UNCLEAR`: insufficient information.

Praise such as `Good video` is not automatically unmet demand. Topic-specific interest or a clear request can be demand. The full operational guide remains in `research/component_2/annotation_guidelines.md`.

## Architecture

- `app.py`: public annotator interface. It contains no export panel or database credential.
- `assignments.py`: deterministic primary and Section A-E assignment generation.
- `auth.py`: cryptographically secure return codes, hashes, and rate limiting.
- `local_store.py`: SQLite development store only.
- `supabase_store.py`: server-side PostgreSQL adapter for the existing Supabase project.
- `snapshot_import.py`: validated, idempotent snapshot import and validation CLI.
- `admin_cli.py`: researcher-only export CLI, outside the public app.
- `validation.py`: demand/spam response validation.
- `sql/`: prepared Supabase migrations; they are not executed automatically.

## Deterministic Assignments

- Primary researcher mode receives all 300 comments.
- Sections A-E each receive 30 comments.
- Each section receives six comments from each of the five channels.
- Section comments are disjoint and are a subset of the primary 300 comments.
- Assignment generation uses seed `20261014`.

## Production Supabase Configuration

Production mode must be explicit:

```text
COMPONENT2_ANNOTATION_MODE=supabase
COMPONENT2_ANNOTATION_RUN_ID=component2_phase2a_20261014
COMPONENT2_PORTAL_SECRET=<long-random-server-secret>
SUPABASE_DB_URL=<server-side-postgres-connection-string>
```

`SUPABASE_DB_URL` is the participant-only PostgreSQL connection string from the existing J26-DS-334 Supabase project. Do not put it in browser code, Git, or a public Streamlit value. The portal does not use `SUPABASE_ANON_KEY` for writes. When Supabase mode is selected, a missing database URL or weak portal secret is an error; the app does not fall back to SQLite.

The adapter stores only a hash of each return code. It verifies the return code server-side, checks the participant's active session and assigned section on every read/write, and uses `(run_id, participant_id, comment_id)` as the response key. Updating a response cannot create a duplicate or overwrite another participant's response.

The prepared RLS migration creates separate least-privilege `annotation_app`, `annotation_admin`, and `annotation_importer` roles. The public app receives only `SUPABASE_DB_URL`; admin export and snapshot import use separate protected connections. All roles are created without `BYPASSRLS` or ownership. Configure their private passwords out of band.

The admin and importer connections are intentionally not Streamlit app secrets:

```text
SUPABASE_ADMIN_DB_URL=<protected-admin-postgres-connection-string>
SUPABASE_IMPORT_DB_URL=<protected-import-postgres-connection-string>
```

The application checks ownership first, while RLS adds a database boundary. Never give the public app process the admin or importer connection strings.

The existing `research` schema remains untouched and must remain unexposed through the public REST API.

## Prepared Migrations

Review these files before applying them:

```text
sql/0001_annotation_schema.sql
sql/0002_annotation_rls.sql
```

They create isolated `annotation` tables for runs, sections, comments, section assignments, participants, responses, researcher admins, and adjudications. They do not alter `research.channels`, `research.videos`, `research.comments`, or statistics tables. Do not execute them from the browser or before approval.

After approval, apply them with a database owner/admin connection, then configure separate LOGIN passwords for `annotation_app`, `annotation_admin`, and `annotation_importer` out of band. Do not expose the `annotation` schema through REST merely to make this server-side portal work.

## Snapshot Validation And Import

The import CLI validates the existing CSV before any database connection:

```bash
.venv/bin/python -m research.component_2.annotation_portal.snapshot_import \
  --csv data/processed/component_2/annotation/component2_demand_annotation_sample.csv \
  --validate-only
```

It checks exactly 300 unique comment IDs, five channels, deterministic section assignments, six comments per channel per section, Unicode-preserving fields, and the 300-comment primary assignment. The command reports counts without printing comment text.

After migrations and database credentials are approved:

```bash
COMPONENT2_ANNOTATION_MODE=supabase \
COMPONENT2_ANNOTATION_RUN_ID=component2_phase2a_20261014 \
SUPABASE_IMPORT_DB_URL=<protected-import-postgres-connection-string> \
.venv/bin/python -m research.component_2.annotation_portal.snapshot_import \
  --csv data/processed/component_2/annotation/component2_demand_annotation_sample.csv
```

The import is idempotent. It inserts new snapshot rows, updates changed read-only context fields, skips unchanged rows, reports invalid rows, upserts section assignments, and never writes or overwrites `annotation.responses`. The CSV remains Git-ignored.

## Researcher Export

Exports are not available in the public Streamlit interface. Use the separate admin CLI after the database/admin setup is approved.

Local development export:

```bash
COMPONENT2_ADMIN_TOKEN=dev-admin-token \
.venv/bin/python -m research.component_2.annotation_portal.admin_cli \
  --mode local --output /tmp/component2_annotation_export.csv
```

Supabase export:

```bash
COMPONENT2_ANNOTATION_MODE=supabase \
SUPABASE_ADMIN_DB_URL=<protected-admin-postgres-connection-string> \
.venv/bin/python -m research.component_2.annotation_portal.admin_cli \
  --mode supabase --admin-id <approved-admin-id> \
  --output /secure/researcher/path/component2_annotation_export.csv
```

The Supabase export requires `SUPABASE_ADMIN_DB_URL` and an active row in `annotation.researcher_admins`. Choosing Primary researcher mode never grants export access.

To revoke a Supabase participant session from the protected admin environment:

```bash
COMPONENT2_ANNOTATION_MODE=supabase \
SUPABASE_ADMIN_DB_URL=<protected-admin-postgres-connection-string> \
.venv/bin/python -m research.component_2.annotation_portal.admin_cli \
  --mode supabase --admin-id <approved-admin-id> \
  --revoke-participant-id <participant-id>
```

## Streamlit Community Cloud Preparation

The application entry point is:

```text
research/component_2/annotation_portal/app.py
```

The root `requirements.txt` contains the Streamlit and PostgreSQL adapter dependencies. The cloud app must run in Supabase mode and must not depend on the Git-ignored CSV. Therefore the approved sequence is:

1. Review and apply the two SQL migrations to the existing Supabase project.
2. Configure separate participant, admin, and importer database roles and permissions.
3. Run the validation-only import check.
4. Import the snapshot once using the server-side database URL.
5. Create and verify at least one researcher-admin row.
6. Configure Streamlit secrets only for `COMPONENT2_ANNOTATION_MODE`, `COMPONENT2_ANNOTATION_RUN_ID`, `COMPONENT2_PORTAL_SECRET`, and participant-only `SUPABASE_DB_URL`.
7. Deploy the existing `component-2` branch with the entry point above.
8. Start one volunteer session, save its return code, submit a test response, restart the app, and resume it.
9. Confirm the response is present in `annotation.responses` and cannot be read by another participant session.
10. Run the admin CLI from a protected environment using `SUPABASE_ADMIN_DB_URL` to export annotations.

Do not put a service-role key, database password, return code, or `.env` file in the repository. Do not place admin/import connection strings in Streamlit Cloud. Do not expose the existing `research` schema.

## Current Limitations

- Live migrations, snapshot import, Supabase security tests, and deployment have not been performed.
- The production adapter is implemented but requires the approved schema, separated roles, and server-side connection strings.
- Name-only participant identification is intentionally lightweight and is not verified authentication.
- Streamlit Community Cloud deployment should be treated as private/restricted until the return-code threat model and admin operations are approved.
- The portal does not train classifiers, filter comments automatically, adjudicate labels, or calculate agreement metrics.
