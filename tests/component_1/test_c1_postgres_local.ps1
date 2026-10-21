# NOT RE-VALIDATED: updated on 2026-10-20 for the entity-keyed schema
# (organizations, cohort_channels, holdout views, c1_model_reader) but never
# executed against PostgreSQL since. Run only in an isolated disposable container.
# Focused synthetic tests; requires the reviewed SQL already applied
# (000 is read-only; apply 002a, 002a2, 001, 002b; 002a1 is unnecessary for a
# superuser fixture login). No environment files, external database URLs, or
# repository imports.
$ErrorActionPreference = 'Stop'
$container = 'c1-sql-test-f337cd70fa9d4922866dce767c607f66'
$endpoint = 'npipe:////./pipe/docker_engine'
function Invoke-LocalSql([string]$login, [string]$sql) {
    $sql | docker --host $endpoint exec -i $container psql -X -U $login -d postgres -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw "Unexpected SQL failure as ${login}: $sql" }
}
function Assert-Rejected([string]$label, [string]$state, [string]$statement, [string]$login = 'c1_collector', [string]$prefix = '') {
    $literal = $statement.Replace("'", "''")
    Invoke-LocalSql $login @"
$prefix
DO `$test`$ BEGIN
  BEGIN
    EXECUTE '$literal';
  EXCEPTION WHEN SQLSTATE '$state' THEN
    RAISE NOTICE 'PASS: $label'; RETURN;
  END;
  RAISE EXCEPTION 'FAIL: expected rejection: $label';
END `$test`$;
"@
}
$isolationJson = docker --host $endpoint inspect $container
if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed' }
$isolated = ($isolationJson | ConvertFrom-Json)[0]
if ($isolated.HostConfig.NetworkMode -ne 'none' -or
    @($isolated.Mounts).Count -ne 0 -or
    @($isolated.HostConfig.PortBindings.PSObject.Properties).Count -ne 0 -or
    $isolated.HostConfig.Tmpfs.'/var/lib/postgresql/data' -ne 'rw') {
    throw 'Container isolation differs; stopped'
}
Invoke-LocalSql 'postgres' @'
CREATE SCHEMA research;
CREATE SCHEMA annotation;
CREATE TABLE research.c1_synthetic_probe (id integer);
CREATE TABLE research.schema_migrations (version text);
CREATE TABLE annotation.c1_synthetic_probe (id integer);
SET ROLE c1_owner;
INSERT INTO c1.organizations VALUES
 ('synthetic_org','Synthetic Org','LK',false),
 ('synthetic_holdout','Synthetic Holdout','LK',true);
INSERT INTO c1.cohorts (cohort_id,version,manifest_hash,channel_ids)
VALUES ('synthetic_c1_local_pending','test',repeat('a',64),ARRAY['synthetic_channel_c']);
INSERT INTO c1.cohorts (cohort_id,version,manifest_hash,channel_ids,approval_status,
 approved_by,approved_at,approval_reference,enabled,total_attempt_budget,
 discovery_attempt_budget,candidate_attempt_reserve,max_pages_per_channel,retention_decision_reference)
VALUES ('synthetic_c1_local_enabled','test',repeat('b',64),ARRAY['synthetic_channel_a','synthetic_channel_b'],
 'approved','synthetic-test',now(),'synthetic-only',true,200,70,20,10,'synthetic-only');
INSERT INTO c1.channels (channel_id,organization_id,admitted_at,admission_source) VALUES
 ('synthetic_channel_a','synthetic_org',now(),'synthetic'),
 ('synthetic_channel_b','synthetic_holdout',now(),'synthetic'),
 ('synthetic_channel_c','synthetic_org',now(),'synthetic');
INSERT INTO c1.cohort_channels (cohort_id,version,channel_id,role,admitted_at) VALUES
 ('synthetic_c1_local_pending','test','synthetic_channel_c','owned',now()),
 ('synthetic_c1_local_enabled','test','synthetic_channel_a','owned',now()),
 ('synthetic_c1_local_enabled','test','synthetic_channel_b','competitor',now());
INSERT INTO c1.collection_coordination (cohort_id,version)
VALUES ('synthetic_c1_local_enabled','test');
'@
Invoke-LocalSql 'c1_collector' @'
SELECT session_user,current_user;
DO $$ BEGIN
 IF session_user <> 'c1_collector' OR current_user <> 'c1_collector' THEN
 RAISE EXCEPTION 'Wrong login'; END IF;
END $$;
'@
Assert-Rejected 'pending-cohort video insert' '42501' "INSERT INTO c1.videos (video_id,channel_id,admitted_at,admission_source,inventory_revision) VALUES ('synthetic_video_c','synthetic_channel_c',now(),'synthetic',1)"
Invoke-LocalSql 'c1_collector' @'
DO $$ DECLARE n integer; BEGIN
 UPDATE c1.channels SET channel_name='forbidden' WHERE channel_id='synthetic_channel_c';
 GET DIAGNOSTICS n = ROW_COUNT;
 IF n <> 0 THEN RAISE EXCEPTION 'Disabled update succeeded'; END IF;
 RAISE NOTICE 'PASS: disabled update affects zero rows';
END $$;
INSERT INTO c1.videos (video_id,channel_id,admitted_at,admission_source,inventory_revision) VALUES
 ('synthetic_video_a','synthetic_channel_a',now(),'synthetic',1),
 ('synthetic_video_b','synthetic_channel_b',now(),'synthetic',1);
UPDATE c1.channels SET channel_name='Synthetic',country='LK',default_language='si',
 topic_categories=ARRAY['https://en.wikipedia.org/wiki/Entertainment'],
 metadata_observed_at='2026-10-18T00:00:00Z' WHERE channel_id IN ('synthetic_channel_a','synthetic_channel_b');
UPDATE c1.videos SET title='Synthetic',duration_seconds=60,category_id='22',metadata_observed_at='2026-10-18T00:00:00Z';
INSERT INTO c1.collection_runs (run_id,cohort_id,version,manifest_hash,scheduled_for,collection_date,inventory_revision,inventory_cutoff,started_at,deadline_at,phase)
VALUES ('00000000-0000-4000-8000-000000000001','synthetic_c1_local_enabled','test',repeat('b',64),now(),current_date,1,now(),now(),now()+interval '1 hour','refresh');
INSERT INTO c1.collection_work (work_id,run_id,cohort_id,version,work_key,phase,selected_ids,dispatch_order)
VALUES ('00000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','synthetic_c1_local_enabled','test','synthetic','refresh',ARRAY['synthetic_video_a','synthetic_video_b'],0);
UPDATE c1.collection_coordination SET active_run_id='00000000-0000-4000-8000-000000000001',fence=1,
 admission_published_after='2026-09-18T00:00:00Z';
UPDATE c1.collection_runs SET heartbeat_at=now(),status='running';
UPDATE c1.collection_work SET staged_response='{"synthetic":true}',observed_at='2026-10-18T00:01:00Z',payload_hash=repeat('c',64),status='staged';
INSERT INTO c1.video_stats_history (video_id,channel_id,observed_at,cohort_id,version,run_id,work_id,view_count,like_count,comment_count,payload_hash) VALUES
 ('synthetic_video_a','synthetic_channel_a','2026-10-18T00:01:00Z','synthetic_c1_local_enabled','test','00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002',NULL,0,9223372036854775807,repeat('c',64)),
 ('synthetic_video_b','synthetic_channel_b','2026-10-18T00:01:00Z','synthetic_c1_local_enabled','test','00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002',5,0,0,repeat('c',64));
INSERT INTO c1.channel_stats_history (channel_id,observed_at,cohort_id,version,run_id,work_id,subscriber_count,view_count,video_count,payload_hash) VALUES
 ('synthetic_channel_a','2026-10-18T00:01:00Z','synthetic_c1_local_enabled','test','00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002',NULL,0,NULL,repeat('c',64));
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM c1.video_stats_history WHERE view_count IS NULL AND like_count=0 AND comment_count=9223372036854775807) OR
 NOT EXISTS (SELECT 1 FROM c1.channel_stats_history WHERE subscriber_count IS NULL AND view_count=0 AND video_count IS NULL) THEN
 RAISE EXCEPTION 'NULL/zero/bigint assertion failed'; END IF;
 RAISE NOTICE 'PASS: enabled inserts/updates and NULL/zero/bigint';
END $$;
'@
Assert-Rejected 'collector channel insert' '42501' "INSERT INTO c1.channels (channel_id,organization_id,admitted_at,admission_source) VALUES ('new_channel','synthetic_org',now(),'synthetic')"
Assert-Rejected 'collector membership insert' '42501' "INSERT INTO c1.cohort_channels VALUES ('synthetic_c1_local_enabled','test','synthetic_channel_c','owned',now())"
Assert-Rejected 'collector holdout change' '42501' "UPDATE c1.organizations SET is_holdout=false"
Assert-Rejected 'channel organization change' '42501' "UPDATE c1.channels SET organization_id='synthetic_holdout'"
Assert-Rejected 'video ownership' '42501' "UPDATE c1.videos SET channel_id='synthetic_channel_b'"
Assert-Rejected 'approval mutation' '42501' "UPDATE c1.cohorts SET enabled=false"
Assert-Rejected 'inventory immutable admission' '42501' "UPDATE c1.videos SET admission_source='changed'"
Assert-Rejected 'admission cutoff set once' 'P0001' "UPDATE c1.collection_coordination SET admission_published_after=now()"
Assert-Rejected 'run immutable schedule' '42501' "UPDATE c1.collection_runs SET scheduled_for=now()"
Assert-Rejected 'work immutable selection' '42501' "UPDATE c1.collection_work SET selected_ids=ARRAY['other']"
Assert-Rejected 'migration insert' '42501' "INSERT INTO c1.schema_migrations VALUES ('synthetic',repeat('a',64),now())"
Assert-Rejected 'migration read' '42501' 'SELECT * FROM c1.schema_migrations'
Assert-Rejected 'collector training view' '42501' 'SELECT * FROM c1.training_observations'
foreach ($table in @('channel_stats_history','video_stats_history')) {
 $key = if ($table -eq 'video_stats_history') {'video_id'} else {'channel_id'}
 Assert-Rejected "$table update" '42501' "UPDATE c1.$table SET view_count=1"
 Assert-Rejected "$table delete" '42501' "DELETE FROM c1.$table"
 Assert-Rejected "$table duplicate" '23505' "INSERT INTO c1.$table SELECT * FROM c1.$table"
 Assert-Rejected "$table upsert overwrite" '42501' "INSERT INTO c1.$table SELECT * FROM c1.$table ON CONFLICT ($key,observed_at) DO UPDATE SET view_count=99"
}
Assert-Rejected 'channel history negative count' '23514' "INSERT INTO c1.channel_stats_history (channel_id,observed_at,cohort_id,version,run_id,work_id,view_count,payload_hash) VALUES ('synthetic_channel_b','2026-10-18T00:02:00Z','synthetic_c1_local_enabled','test','00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002',-1,repeat('c',64))"
Assert-Rejected 'video history negative count' '23514' "INSERT INTO c1.video_stats_history (video_id,channel_id,observed_at,cohort_id,version,run_id,work_id,view_count,payload_hash) VALUES ('synthetic_video_a','synthetic_channel_a','2026-10-18T00:02:00Z','synthetic_c1_local_enabled','test','00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002',-1,repeat('c',64))"
Assert-Rejected 'staged payload' 'P0001' "UPDATE c1.collection_work SET staged_response='{}'"
Assert-Rejected 'staged timestamp' 'P0001' "UPDATE c1.collection_work SET observed_at=now()"
Assert-Rejected 'staged hash' 'P0001' "UPDATE c1.collection_work SET payload_hash=repeat('d',64)"
Assert-Rejected 'assume owner' '42501' 'SET ROLE c1_owner'
foreach ($table in @('research.c1_synthetic_probe','annotation.c1_synthetic_probe','research.schema_migrations')) {
 Assert-Rejected "$table insert" '42501' "INSERT INTO $table VALUES (NULL)"
 Assert-Rejected "$table update" '42501' "UPDATE $table SET $(if ($table.EndsWith('schema_migrations')) {'version'} else {'id'})=NULL"
 Assert-Rejected "$table delete" '42501' "DELETE FROM $table"
}
# Owner-path integrity triggers (owner trusted, but locked fields still protected).
$owner = 'SET ROLE c1_owner;'
Assert-Rejected 'owner membership update' 'P0001' "UPDATE c1.cohort_channels SET role='competitor'" 'postgres' $owner
Assert-Rejected 'owner holdout flag update' 'P0001' "UPDATE c1.organizations SET is_holdout=false WHERE organization_id='synthetic_holdout'" 'postgres' $owner
Assert-Rejected 'owner off-allowlist membership' 'P0001' "INSERT INTO c1.cohort_channels VALUES ('synthetic_c1_local_pending','test','synthetic_channel_a','owned',now())" 'postgres' $owner
Assert-Rejected 'owner channel organization change' 'P0001' "UPDATE c1.channels SET organization_id='synthetic_holdout' WHERE channel_id='synthetic_channel_a'" 'postgres' $owner
# Model reader: views only; holdout rows only in the evaluation view.
Invoke-LocalSql 'c1_model_reader' @'
DO $$ BEGIN
 IF (SELECT count(*) FROM c1.training_observations) <> 1 OR
    EXISTS (SELECT 1 FROM c1.training_observations WHERE organization_id <> 'synthetic_org') OR
    (SELECT count(*) FROM c1.evaluation_observations) <> 1 OR
    EXISTS (SELECT 1 FROM c1.evaluation_observations WHERE organization_id <> 'synthetic_holdout') THEN
  RAISE EXCEPTION 'Holdout view split failed'; END IF;
 RAISE NOTICE 'PASS: training excludes holdout, evaluation holds only holdout';
END $$;
'@
foreach ($table in @('video_stats_history','channels','organizations')) {
 Assert-Rejected "model reader base table $table" '42501' "SELECT * FROM c1.$table" 'c1_model_reader'
}
Invoke-LocalSql 'c1_collector' @'
DO $$ BEGIN
 IF (SELECT count(*) FROM c1.video_stats_history) <> 2 OR
 (SELECT count(*) FROM c1.channel_stats_history) <> 1 OR
 NOT EXISTS (SELECT 1 FROM c1.video_stats_history WHERE view_count IS NULL AND like_count=0) THEN
 RAISE EXCEPTION 'History changed'; END IF;
 RAISE NOTICE 'PASS: history preserved';
END $$;
'@
Write-Output 'PASS: all focused synthetic checks completed'
