#!/bin/sh
# Runs inside c1-pgtest only. Phase: pending | enabled.
set -eu
cd /opt/c1
export DENO_DIR=/opt/c1/deno_dir
export C1_IT_DB_URL='postgres://c1_collector:collector_throwaway_local@localhost:5432/postgres?sslmode=verify-full'
export C1_IT_PHASE="$1"
exec deno test --cached-only --deny-import --no-lock --no-prompt \
  --config supabase/functions/c1-collect/deno.json --cert /opt/c1/tls/ca.pem \
  --allow-net=localhost:5432 --allow-read=/opt/c1 \
  --allow-env=C1_IT_DB_URL,C1_IT_PHASE,C1_IT_COHORT,C1_IT_VERSION,C1_IT_MANIFEST_HASH,C1_IT_RETENTION,PGMAX_PIPELINE,PGBACKOFF,PGKEEP_ALIVE,PGFETCH_TYPES,PGPUBLICATIONS,PGTARGET_SESSION_ATTRS,PGTARGETSESSIONATTRS,PGAPPNAME \
  --deny-write --deny-run --deny-ffi \
  tests/component_1/edge_collection/postgres.integration.test.mjs
