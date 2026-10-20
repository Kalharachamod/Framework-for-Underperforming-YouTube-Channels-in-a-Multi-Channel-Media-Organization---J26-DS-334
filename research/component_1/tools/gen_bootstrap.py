"""Generate research/component_1/sql/004_bootstrap_v0_3_0.sql from the cohort manifest.

Standard library only: reads one JSON file and writes one SQL text file. No
database, network, environment files or repository imports. The SQL it writes is
for review; you run it yourself in the Supabase SQL Editor.

Regenerate after any edit to the manifest (any change alters the canonical-JSON
manifest_hash embedded in the SQL), from the repository root:

    .venv/Scripts/python.exe -I -B research/component_1/tools/gen_bootstrap.py config/cohorts/component_1_derana_vs_cm_v0.3.0.proposed.json research/component_1/sql/004_bootstrap_v0_3_0.sql

Then rerun the consistency test, which recomputes the hash and compares every
organization, channel and role against the manifest:

    .venv/Scripts/python.exe -I -B tests/component_1/test_c1_cohort_v030.py
"""
import hashlib
import json
import sys
from pathlib import Path

manifest_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
m = json.loads(manifest_path.read_text(encoding="utf-8"))
canonical = json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
plan = m["collection_plan"]
cid, ver = m["cohort_id"], m["version"]


def lit(s):
    return "'" + s.replace("'", "''") + "'"


ids = sorted(c["channel_id"] for c in m["channels"])
orgs = ",\n".join(
    f"  ({lit(o['organization_id'])}, {lit(o['name'])}, {lit(o['country'])}, {'true' if o['is_holdout'] else 'false'})"
    for o in m["organizations"])
id_lines = []
for i in range(0, len(ids), 3):
    id_lines.append("    " + ", ".join(lit(x) for x in ids[i:i + 3]))
channels = ",\n".join(
    f"  ({lit(c['channel_id'])}, {lit(c['organization_id'])}, {lit(c['channel_name'])})"
    for c in m["channels"])
members = ",\n".join(
    f"  ({lit(cid)}, {lit(ver)}, {lit(c['channel_id'])}, {lit(c['role'])})"
    for c in m["channels"])
roles = {}
for c in m["channels"]:
    roles[c["role"]] = roles.get(c["role"], 0) + 1
holdout = sorted(o["organization_id"] for o in m["organizations"] if o["is_holdout"])
source = f"cohort_manifest:{cid}@{ver}"

sql = f"""-- REVIEW ONLY. Run after 002b_access.sql, as postgres with c1_owner membership
-- (002a1). Seeds C1 from config/cohorts/component_1_derana_vs_cm_v0.3.0.proposed.json
-- only: {len(m['organizations'])} organizations, one pending/disabled cohort, {len(ids)} channels and their roles,
-- and the coordination row. No videos: the first approved discovery run seeds
-- them. Nothing is read from or written to any other schema.
-- manifest_hash is the canonical-JSON SHA-256 described in the manifest's
-- manifest_hash_method; tests/component_1/test_c1_cohort_v030.py recomputes it.
-- Plain INSERTs fail on any existing row; the DO block checks counts and flags
-- before COMMIT, so any mismatch rolls back the whole bootstrap.
BEGIN;
SET LOCAL ROLE c1_owner;

INSERT INTO c1.organizations (organization_id, name, country, is_holdout) VALUES
{orgs};

INSERT INTO c1.cohorts (cohort_id, version, manifest_hash, channel_ids,
  total_attempt_budget, discovery_attempt_budget, candidate_attempt_reserve,
  max_pages_per_channel, admission_lookback_days)
VALUES ({lit(cid)}, {lit(ver)},
  {lit(digest)},
  ARRAY[
{(','+chr(10)).join(id_lines)}
  ],
  {plan['total_attempt_budget']}, {plan['discovery_attempt_budget']}, {plan['candidate_attempt_reserve']}, {plan['max_pages_per_channel']}, {m['admission']['admission_lookback_days']});

-- channel_name is starting metadata; the collector replaces it with API values.
INSERT INTO c1.channels (channel_id, organization_id, channel_name, admitted_at, admission_source)
SELECT channel_id, organization_id, channel_name, now(), {lit(source)}
FROM (VALUES
{channels}
) AS seed (channel_id, organization_id, channel_name);

INSERT INTO c1.cohort_channels (cohort_id, version, channel_id, role, admitted_at)
SELECT cohort_id, version, channel_id, role, now()
FROM (VALUES
{members}
) AS seed (cohort_id, version, channel_id, role);

INSERT INTO c1.collection_coordination (cohort_id, version) VALUES ({lit(cid)}, {lit(ver)});

DO $verify$
BEGIN
  IF (SELECT count(*) FROM c1.organizations) <> {len(m['organizations'])}
    OR (SELECT count(*) FROM c1.organizations WHERE is_holdout) <> {len(holdout)}
    OR NOT EXISTS (SELECT 1 FROM c1.organizations WHERE organization_id = {lit(holdout[0])} AND is_holdout)
    OR (SELECT count(*) FROM c1.channels) <> {len(ids)}
    OR (SELECT count(*) FROM c1.cohort_channels WHERE cohort_id = {lit(cid)} AND version = {lit(ver)}) <> {len(ids)}
    OR (SELECT count(*) FROM c1.cohort_channels WHERE role = 'owned') <> {roles.get('owned', 0)}
    OR (SELECT count(*) FROM c1.cohort_channels WHERE role = 'competitor') <> {roles.get('competitor', 0)}
    OR (SELECT count(*) FROM c1.videos) <> 0
    OR NOT EXISTS (SELECT 1 FROM c1.cohorts WHERE cohort_id = {lit(cid)} AND version = {lit(ver)}
      AND approval_status = 'pending' AND NOT enabled AND cardinality(channel_ids) = {len(ids)})
  THEN
    RAISE EXCEPTION 'C1 bootstrap verification failed';
  END IF;
  RAISE NOTICE 'C1 bootstrap OK: {len(m['organizations'])} organizations, {len(ids)} channels ({roles.get('owned', 0)} owned, {roles.get('competitor', 0)} competitor), cohort pending and disabled';
END; $verify$;
COMMIT;
"""
out_path.write_text(sql, encoding="utf-8", newline="\n")
print("manifest_hash", digest)
print("channels", len(ids), "roles", roles, "holdout", holdout)
