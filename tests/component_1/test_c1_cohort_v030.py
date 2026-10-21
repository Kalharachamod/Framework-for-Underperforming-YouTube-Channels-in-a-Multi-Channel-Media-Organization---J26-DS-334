"""v0.3.0 manifest and 004 bootstrap consistency. Stdlib only: no repo imports,
dotenv, network, SQL execution or DB."""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'config/cohorts/component_1_derana_vs_cm_v0.3.0.proposed.json'
V020 = ROOT / 'config/cohorts/component_1_audited43_v0.2.0.proposed.json'
BOOTSTRAP = ROOT / 'research/component_1/sql/004_bootstrap_v0_3_0.sql'
LITERAL = r"'((?:[^']|'')*)'"


def canonical_hash(manifest):
    """The method documented in the manifest's manifest_hash_method."""
    text = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def unquote(value):
    return value.replace("''", "'")


class CohortV030Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
        cls.v020 = json.loads(V020.read_text(encoding='utf-8'))
        cls.sql = BOOTSTRAP.read_text(encoding='utf-8')
        cls.channels = cls.manifest['channels']

    def test_manifest_scope_roles_and_holdout(self):
        ids = [c['channel_id'] for c in self.channels]
        self.assertEqual(len(ids), 41)
        self.assertEqual(len(set(ids)), 41)
        self.assertTrue(set(ids) <= {c['channel_id'] for c in self.v020['channels']})
        roles = [c['role'] for c in self.channels]
        self.assertEqual((roles.count('owned'), roles.count('competitor')), (18, 23))
        orgs = {o['organization_id']: o for o in self.manifest['organizations']}
        self.assertEqual({k: v['is_holdout'] for k, v in orgs.items()},
                         {'derana': False, 'capital_maharaja': True})
        for c in self.channels:
            self.assertEqual(c['role'] == 'owned', c['organization_id'] == 'derana')
        self.assertNotIn('organization', self.manifest)
        self.assertFalse(self.manifest['enabled'])
        self.assertEqual(self.manifest['status'], 'proposed')

    def test_plan_matches_collector_caps(self):
        plan = self.manifest['collection_plan']
        self.assertEqual((plan['total_attempt_budget'], plan['discovery_attempt_budget'],
                          plan['candidate_attempt_reserve'], plan['max_pages_per_channel'],
                          plan['dispatches_per_invocation']), (200, 70, 20, 10, 6))
        self.assertLessEqual(plan['discovery_attempt_budget'] + plan['candidate_attempt_reserve'],
                             plan['total_attempt_budget'])
        self.assertEqual(self.manifest['admission']['admission_lookback_days'], 30)
        refresh = self.manifest['refresh_policy']
        self.assertEqual((refresh['daily_until_age_days'], refresh['weekly_until_age_days']), (30, 365))

    def test_bootstrap_hash_is_canonical_json_sha256(self):
        hashes = re.findall(r"'([0-9a-f]{64})'", self.sql)
        self.assertEqual(hashes, [canonical_hash(self.manifest)])
        self.assertIn("ensure_ascii=False", self.manifest['manifest_hash_method'])
        # Line endings and indentation do not change the canonical hash.
        reformatted = json.loads(json.dumps(self.manifest, indent=4).replace('\n', '\r\n'))
        self.assertEqual(canonical_hash(reformatted), hashes[0])

    def test_bootstrap_cohort_row_matches_manifest(self):
        plan = self.manifest['collection_plan']
        cohort = self.sql.split('INSERT INTO c1.cohorts')[1].split(';')[0]
        self.assertIn(f"'{self.manifest['cohort_id']}', '{self.manifest['version']}'", cohort)
        array = cohort.split('ARRAY[')[1].split(']')[0]
        self.assertEqual(re.findall(LITERAL, array), sorted(c['channel_id'] for c in self.channels))
        numbers = [int(n) for n in re.findall(r'(\d+)', cohort.split(']')[-1])]
        self.assertEqual(numbers, [plan['total_attempt_budget'], plan['discovery_attempt_budget'],
                                   plan['candidate_attempt_reserve'], plan['max_pages_per_channel'],
                                   self.manifest['admission']['admission_lookback_days']])
        self.assertNotIn('approval_status', cohort)
        self.assertNotIn('enabled', cohort)

    def test_bootstrap_organizations_channels_and_roles_match_manifest(self):
        orgs = re.findall(rf"\({LITERAL}, {LITERAL}, {LITERAL}, (true|false)\)",
                          self.sql.split('INSERT INTO c1.organizations')[1].split(';')[0])
        self.assertEqual({(i, unquote(n), c, h == 'true') for i, n, c, h in orgs},
                         {(o['organization_id'], o['name'], o['country'], o['is_holdout'])
                          for o in self.manifest['organizations']})
        rows = re.findall(rf"\({LITERAL}, {LITERAL}, {LITERAL}\)",
                          self.sql.split('INSERT INTO c1.channels')[1].split(';')[0])
        self.assertEqual([(i, o, unquote(n)) for i, o, n in rows],
                         [(c['channel_id'], c['organization_id'], c['channel_name'])
                          for c in self.channels])
        members = re.findall(rf"\({LITERAL}, {LITERAL}, {LITERAL}, {LITERAL}\)",
                             self.sql.split('INSERT INTO c1.cohort_channels')[1].split(';')[0])
        self.assertEqual(members, [(self.manifest['cohort_id'], self.manifest['version'],
                                    c['channel_id'], c['role']) for c in self.channels])
        self.assertIn('සිරස ධම්ම', self.sql)
        self.assertIn("Sri Lanka''s Got Talent", self.sql)


if __name__ == '__main__':
    unittest.main()
