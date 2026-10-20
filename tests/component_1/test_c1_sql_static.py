"""Text checks only. No SQL execution, repo imports, dotenv, network or DB."""
from pathlib import Path
import re
import unittest

SQL = Path(__file__).resolve().parents[2] / 'research/component_1/sql'
TABLES = {'organizations', 'cohorts', 'channels', 'cohort_channels', 'videos',
          'channel_stats_history', 'video_stats_history', 'collection_runs',
          'collection_work', 'collection_coordination', 'schema_migrations'}


def code(text):
    return re.sub(r'--[^\n]*', '', text)


def view_body(schema, name):
    return schema.split(f'CREATE VIEW c1.{name} ')[1].split(';')[0]


class C1SQLStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read = lambda name: (SQL / name).read_text(encoding='utf-8')
        cls.preflight = read('000_preflight_readonly.sql')
        cls.schema = read('001_schema.sql')
        cls.roles = read('002a_roles.sql')
        cls.membership = read('002a1_owner_membership.sql')
        cls.reader = read('002a2_model_reader_role.sql')
        cls.access = read('002b_access.sql')
        cls.audit = read('003_verify_readonly.sql')
        cls.bootstrap = read('004_bootstrap_v0_3_0.sql')
        cls.revoke = read('005_revoke_owner_membership.sql')

    def test_fresh_schema_and_only_c1_foreign_keys(self):
        self.assertIn('CREATE SCHEMA c1 AUTHORIZATION c1_owner;', self.schema)
        self.assertNotRegex(code(self.schema),
                            r'CREATE\s+(?:SCHEMA|TABLE|INDEX|VIEW)\s+IF NOT EXISTS')
        refs = re.findall(r'REFERENCES\s+([\w.]+)', self.schema)
        self.assertGreater(len(refs), 8)
        self.assertTrue(all(ref.startswith('c1.') for ref in refs))
        tables = set(re.findall(r'CREATE TABLE c1\.(\w+)', self.schema))
        self.assertEqual(tables, TABLES)
        for table in tables:
            self.assertIn(f'ALTER TABLE c1.{table} ENABLE ROW LEVEL SECURITY;', self.access)

    def test_no_non_c1_mutations_or_definer_shortcut(self):
        sources = (self.schema, self.access, self.roles, self.membership, self.reader,
                   self.bootstrap, self.revoke, self.preflight)
        joined = '\n'.join(code(s) for s in sources)
        self.assertNotRegex(joined, r'(?i)\b(?:research|annotation)\s*\.')
        self.assertNotIn('SECURITY DEFINER', joined.upper())
        # Keywords only: channel names such as "5 Million Money Drop" are literals.
        keywords = re.sub(r"'(?:[^']|'')*'", "''", joined)
        self.assertNotRegex(keywords, r'(?i)\b(?:PASSWORD|ALTER ROLE|DROP|DELETE FROM)\b')
        # TRUNCATE may appear only as a trigger event, never as a statement.
        self.assertNotRegex(keywords, r'(?im)(?:^|;)\s*TRUNCATE\b')
        self.assertIn('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA c1 FROM PUBLIC;', joined)
        self.assertEqual(len(re.findall(r'CREATE ROLE ', self.roles)), 2)
        self.assertIn('NOBYPASSRLS', self.roles)

    def test_schema_created_by_actor_before_owner_switch_atomically(self):
        schema = code(self.schema)
        self.assertRegex(schema, r'^\s*BEGIN;\s*CREATE SCHEMA c1 AUTHORIZATION c1_owner;\s*SET LOCAL ROLE c1_owner;')
        self.assertEqual(len(re.findall(r'\bCOMMIT;', schema)), 1)
        self.assertTrue(schema.rstrip().endswith('COMMIT;'))
        self.assertLess(schema.index('SET LOCAL ROLE'), schema.index('CREATE TABLE'))
        for source in (self.schema, self.roles, self.access, self.membership, self.reader):
            self.assertNotRegex(code(source), r'(?i)GRANT\s+CREATE\s+ON\s+DATABASE')

    def test_snapshots_keyed_by_entity_and_time_only(self):
        channel = self.schema.split('CREATE TABLE c1.channel_stats_history (')[1].split('\n);')[0]
        video = self.schema.split('CREATE TABLE c1.video_stats_history (')[1].split('\n);')[0]
        self.assertIn('PRIMARY KEY (channel_id, observed_at)', channel)
        self.assertIn('PRIMARY KEY (video_id, observed_at)', video)
        self.assertIn('UNIQUE (channel_id, run_id)', channel)
        self.assertIn('UNIQUE (video_id, run_id)', video)
        self.assertIn('FOREIGN KEY (video_id, channel_id) REFERENCES c1.videos (video_id, channel_id)', video)
        for body in (channel, video):
            self.assertIn('cohort_id text NOT NULL, version text NOT NULL, run_id uuid NOT NULL', body)
        channels = self.schema.split('CREATE TABLE c1.channels (')[1].split('\n);')[0]
        videos = self.schema.split('CREATE TABLE c1.videos (')[1].split('\n);')[0]
        self.assertRegex(channels, r'channel_id text PRIMARY KEY')
        self.assertRegex(videos, r'video_id text PRIMARY KEY')
        self.assertNotIn('cohort_id', channels + videos)

    def test_organization_role_and_holdout_model(self):
        orgs = self.schema.split('CREATE TABLE c1.organizations (')[1].split('\n);')[0]
        self.assertIn('is_holdout boolean NOT NULL', orgs)
        self.assertNotIn('DEFAULT', orgs)
        channels = self.schema.split('CREATE TABLE c1.channels (')[1].split('\n);')[0]
        self.assertIn('organization_id text NOT NULL REFERENCES c1.organizations', channels)
        members = self.schema.split('CREATE TABLE c1.cohort_channels (')[1].split('\n);')[0]
        self.assertIn("role IN ('owned','competitor','generalization_test')", members)
        self.assertIn('PRIMARY KEY (cohort_id, version, channel_id)', members)
        self.assertIn('C1 cohort membership is immutable', self.schema)
        self.assertIn('C1 organization identity and holdout flag are immutable', self.schema)
        self.assertIn('C1 admission cutoff is set once', self.schema)
        for trigger in ('guard_membership BEFORE INSERT OR UPDATE ON c1.cohort_channels',
                        'guard_organization BEFORE UPDATE ON c1.organizations',
                        'guard_coordination BEFORE UPDATE ON c1.collection_coordination',
                        'guard_channels BEFORE UPDATE ON c1.channels',
                        'guard_videos BEFORE UPDATE ON c1.videos'):
            self.assertIn(f'CREATE TRIGGER {trigger}', self.schema)

    def test_history_append_only_except_retention_purge(self):
        schema = code(self.schema)
        for table in ('channel_stats_history', 'video_stats_history'):
            self.assertRegex(schema, rf'CREATE TRIGGER \w+ BEFORE UPDATE OR DELETE ON c1\.{table}\s+'
                                     r'FOR EACH ROW EXECUTE FUNCTION c1\.guard_history\(\);')
            self.assertRegex(schema, rf'CREATE TRIGGER \w+ BEFORE TRUNCATE ON c1\.{table}\s+'
                                     r'FOR EACH STATEMENT EXECUTE FUNCTION c1\.guard_history\(\);')
        guard = schema.split('CREATE FUNCTION c1.guard_history()')[1].split('END; $$;')[0]
        self.assertIn('SECURITY INVOKER', guard)
        self.assertIn('SET search_path = pg_catalog', guard)
        # DELETE is the only operation with an exit, and only under the purge setting.
        self.assertIn("IF TG_OP = 'DELETE' AND current_setting('c1.retention_purge', true) = 'on' THEN", guard)
        self.assertEqual(re.findall(r'\bRETURN\b[^;]*;', guard), ['RETURN OLD;'])
        self.assertIn('RAISE EXCEPTION', guard)
        self.assertLess(schema.index('c1.guard_history()'),
                        schema.index('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA c1 FROM PUBLIC;'))
        self.assertIn("SET LOCAL c1.retention_purge = 'on'", self.schema)
        # No shipped script turns the purge on.
        sources = (self.schema, self.access, self.roles, self.membership, self.reader,
                   self.bootstrap, self.revoke, self.preflight, self.audit)
        joined = '\n'.join(code(s) for s in sources)
        self.assertNotRegex(joined, r'(?i)\bSET\s+(?:LOCAL\s+|SESSION\s+)?c1\.retention_purge\b')
        self.assertNotRegex(joined, r"(?i)set_config\s*\(\s*'c1\.retention_purge'")

    def test_model_views_are_owner_rights_barriers_with_opposite_holdout_filters(self):
        training = view_body(self.schema, 'training_observations')
        evaluation = view_body(self.schema, 'evaluation_observations')
        for body in (training, evaluation):
            self.assertTrue(body.startswith('WITH (security_barrier = true, security_invoker = false) AS'))
            self.assertEqual(len(re.findall(r'\bis_holdout\b', body)), 1)
            self.assertRegex(body, r'\bWHERE o\.is_holdout = (true|false)\s*$')
        self.assertTrue(training.rstrip().endswith('WHERE o.is_holdout = false'))
        self.assertTrue(evaluation.rstrip().endswith('WHERE o.is_holdout = true'))
        strip = lambda body: re.sub(r'WHERE o\.is_holdout = (true|false)\s*$', '', body)
        self.assertEqual(strip(training), strip(evaluation))

    def test_model_reader_sees_views_only(self):
        self.assertEqual(re.findall(r'CREATE ROLE (\w+)', self.reader), ['c1_model_reader'])
        self.assertIn('NOBYPASSRLS', self.reader)
        self.assertNotRegex(code(self.reader), r'\bGRANT\b')
        grants = re.findall(r'GRANT ([^;]+) TO c1_model_reader;', self.access)
        self.assertEqual(sorted(g.strip() for g in grants), [
            'SELECT ON c1.training_observations, c1.evaluation_observations',
            'USAGE ON SCHEMA c1'])
        self.assertIn('TO c1_collector, c1_model_reader', self.access)

    def test_grants_and_policies_preserve_immutable_fields(self):
        grants = re.findall(r'GRANT UPDATE \((.*?)\)\s+ON c1\.(\w+)', self.access, re.S)
        by_table = {table: set(re.findall(r'\w+', cols)) for cols, table in grants}
        self.assertEqual(set(by_table), {'channels', 'videos', 'collection_runs',
                                        'collection_work', 'collection_coordination'})
        for columns in by_table.values():
            self.assertTrue(columns.isdisjoint({'cohort_id','version','channel_id',
                'video_id','admitted_at','admission_source','organization_id','role',
                'is_holdout','run_id','work_id','work_key','selected_ids',
                'input_cursor','scheduled_for','manifest_hash','started_at','deadline_at'}))
        self.assertNotRegex(self.access, r'GRANT\s+SELECT,\s*INSERT\s+ON\s+c1\.channels')
        self.assertIn('GRANT SELECT ON c1.cohorts, c1.organizations, c1.cohort_channels TO c1_collector;', self.access)
        self.assertIn("IF t NOT IN ('channel_stats_history','video_stats_history')", self.access)
        self.assertIn("IF t NOT IN ('channels','collection_coordination')", self.access)
        self.assertEqual(self.access.count("c.enabled AND c.approval_status = ''approved''"), 3)
        self.assertIn('FROM c1.cohort_channels m JOIN c1.cohorts c', self.access)
        self.assertIn('WITH CHECK (%s)', self.access)
        self.assertNotRegex(self.access, r'GRANT\s+(?:ALL|DELETE|TRUNCATE)\b')

    def test_coordination_and_observation_guards(self):
        coordination = self.schema.split('CREATE TABLE c1.collection_coordination (')[1].split('\n);')[0]
        self.assertIn('PRIMARY KEY (cohort_id, version)', coordination)
        self.assertNotIn('work_key', coordination)
        self.assertIn('active_run_id uuid,', coordination)
        self.assertIn('admission_published_after timestamptz', coordination)
        self.assertIn('C1 channel outside cohort allowlist', self.schema)
        self.assertIn('C1 immutable inventory identity/admission fields', self.schema)
        self.assertIn('C1 immutable run/work definition', self.schema)
        self.assertIn('C1 staged observation is immutable', self.schema)
        self.assertIn("DEFAULT 'pending'", self.schema)
        self.assertIn('DEFAULT false', self.schema)
        self.assertIn('payload_hash IS NOT NULL', self.schema)
        self.assertNotRegex(self.schema, r'INSERT INTO c1\.cohorts')

    def test_preflight_membership_and_revoke_scripts(self):
        statements = [s.strip() for s in code(self.preflight).split(';') if s.strip()]
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0].startswith('SELECT'))
        self.assertIn("server_version_num", self.preflight)
        active = [s.strip() for s in code(self.membership).split(';') if s.strip()]
        self.assertEqual(active, ['GRANT c1_owner TO postgres WITH INHERIT FALSE, SET TRUE'])
        self.assertIn('-- GRANT c1_owner TO postgres;', self.membership)
        active = [s.strip() for s in code(self.revoke).split(';') if s.strip()]
        self.assertEqual(active, ['REVOKE c1_owner FROM postgres'])
        self.assertIn('Re-grant it with 002a1_owner_membership.sql', self.revoke)

    def test_bootstrap_writes_only_seed_tables_and_stays_pending(self):
        boot = code(self.bootstrap)
        self.assertRegex(boot, r'^\s*BEGIN;\s*SET LOCAL ROLE c1_owner;')
        self.assertTrue(boot.rstrip().endswith('COMMIT;'))
        targets = set(re.findall(r'INSERT INTO c1\.(\w+)', boot))
        self.assertEqual(targets, {'organizations', 'cohorts', 'channels',
                                   'cohort_channels', 'collection_coordination'})
        self.assertNotRegex(boot, r'(?i)\bUPDATE\s+c1\.')
        self.assertNotRegex(boot, r"(?i)approval_status\s*=\s*'approved'|enabled\s*=\s*true")
        self.assertNotRegex(boot, r'INSERT INTO c1\.(videos|\w+_history)')
        self.assertIn("RAISE EXCEPTION 'C1 bootstrap verification failed'", boot)

    def test_audit_has_only_read_statements_and_required_catalogs(self):
        audit = code(self.audit)
        for statement in audit.split(';'):
            statement = statement.strip()
            if statement:
                self.assertRegex(statement, r'^(BEGIN READ ONLY|SELECT|WITH RECURSIVE|ROLLBACK)\b')
        for name in ('pg_auth_members','pg_default_acl','pg_policies','pg_trigger',
                     'pg_rewrite','pg_depend','pg_extension','pg_foreign_table',
                     'has_table_privilege','has_column_privilege','has_function_privilege',
                     'reloptions'):
            self.assertIn(name, self.audit)
        self.assertNotIn('vault.decrypted_secrets', audit)
        self.assertNotIn('ftoptions', audit)

    def test_audit_omits_sensitive_values_and_raw_definitions(self):
        audit = code(self.audit)
        for forbidden in ('pg_get_triggerdef', 'pg_get_viewdef', 'pg_get_ruledef',
                          'pg_get_functiondef', 'definition', 'ev_action', 'ev_qual',
                          'tgargs', 'tgqual', 'prosrc', 'probin', 'srvoptions',
                          'ftoptions', 'umoptions'):
            self.assertNotRegex(audit, rf'\b{forbidden}\b')
        self.assertEqual(audit.count('p.proconfig'), 1)
        self.assertIn('(p.proconfig IS NOT NULL) AS has_local_configuration', audit)
        self.assertIn('(qual IS NOT NULL) AS has_using_expression', audit)
        self.assertIn('(with_check IS NOT NULL) AS has_check_expression', audit)
        for identity in ('routine_oid', 'trigger_oid', 'rule_oid', 'relation_oid',
                         'refclassid', 'refobjid', 'deptype'):
            self.assertIn(identity, audit)


if __name__ == '__main__':
    unittest.main()
