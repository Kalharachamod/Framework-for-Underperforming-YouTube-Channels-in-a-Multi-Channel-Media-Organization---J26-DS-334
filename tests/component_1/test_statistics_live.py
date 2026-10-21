"""All live boundaries mocked; no real credentials or connections."""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('c1_live_tests_runner', ROOT / 'research/component_1/statistics_runner.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
FIX = Path(__file__).with_name('fixtures')
RETENTION = {'payload_retention_days': 1, 'policy_reference': 'synthetic-test-only'}


class LiveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.manifest = r.load_manifest(FIX / 'c1_cohort.json')
        self.fixture = json.loads((FIX / 'c1_statistics.json').read_text())
        self.env = patch.dict(os.environ, {'YOUTUBE_API_KEY': 'test-key-secret', 'COMPONENT1_DB_URL': 'postgresql://test:secret@invalid/db'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.network = patch('socket.create_connection', side_effect=AssertionError('real network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = r.main(['--manifest', str(FIX / 'c1_cohort.json'), '--dry-run', *args])
        return code, output.getvalue()

    def client(self, budget=20, transport=None, retries=2):
        return r.LiveClient(budget, authorized=True, transport=transport or r.fixture_client(self.fixture)._transport,
                            retries=retries, sleep=lambda _: None)

    def execute(self, client, **kwargs):
        with patch('shared.database.repository.upsert_channels') as channels, patch('shared.database.repository.upsert_videos') as videos, patch('psycopg.connect') as db:
            report = r.run(self.manifest, client, self.state, self.fixture['seed'], retention=RETENTION, **kwargs)
            db.assert_not_called()
            channels.assert_not_called()
            videos.assert_not_called()
        return report

    def test_opt_in_and_configuration_before_connections(self):
        with self.assertRaises(r.PrerequisiteError):
            r.LiveClient(10)
        with patch('psycopg.connect') as db, patch.object(r.yc, 'urllib_transport') as api:
            self.assertEqual(self.cli('--live')[0], 1)
            code, message = self.cli('--live', '--api-budget', '10')
            self.assertEqual(code, 1)
            self.assertIn('retention', message)
            db.assert_not_called()
            api.assert_not_called()

    def test_offline_preflight_has_no_connections_or_approval_changes(self):
        before = r.digest(self.manifest)
        with patch('psycopg.connect') as db, patch.object(r.yc, 'urllib_transport') as api:
            code, message = self.cli('--offline-preflight', '--api-budget', '10')
            self.assertEqual(code, 0)
            for expected in ('pending', 'offline; no connections', 'disabled', 'do not guarantee'):
                self.assertIn(expected, message)
            db.assert_not_called()
            api.assert_not_called()
        self.assertEqual(before, r.digest(self.manifest))

    def connection(self, access=('component1_readonly', 'on'), rows=None):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = access
        cur.fetchall.return_value = rows if rows is not None else [(self.fixture['seed'][0]['video_id'], self.manifest['channels'][0]['channel_id'])]
        return conn, cur

    def test_bootstrap_guards_filter_parameters_timeouts_and_rollback(self):
        conn, cur = self.connection()
        connect = MagicMock(return_value=conn)
        rows = r.bootstrap_inventory(self.manifest, connect=connect)
        self.assertEqual(len(rows), 1)
        calls = cur.execute.call_args_list
        self.assertIn('READ ONLY', calls[0].args[0])
        self.assertIn('transaction_read_only', calls[1].args[0])
        self.assertIn('WHERE channel_id = ANY(%s)', calls[2].args[0])
        self.assertEqual(calls[2].args[1], ([self.manifest['channels'][0]['channel_id']],))
        self.assertEqual(connect.call_args.kwargs['connect_timeout'], 10)
        self.assertIn('statement_timeout=30000', connect.call_args.kwargs['options'])
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()
        conn.commit.assert_not_called()

    def test_bad_role_or_writable_transaction_never_queries_inventory(self):
        for access in [('owner', 'on'), ('component1_readonly', 'off')]:
            conn, cur = self.connection(access)
            with self.assertRaises(r.PrerequisiteError):
                r.bootstrap_inventory(self.manifest, connect=lambda *a, **k: conn)
            self.assertEqual(cur.execute.call_count, 2)
            cur.fetchall.assert_not_called()
            conn.rollback.assert_called_once()

    def test_bootstrap_rejects_foreign_channel_even_if_driver_returns_it(self):
        conn, _ = self.connection(rows=[('old00000001', 'UCbbbbbbbbbbbbbbbbbbbbbb')])
        with self.assertRaises(r.PrerequisiteError):
            r.bootstrap_inventory(self.manifest, connect=lambda *a, **k: conn)

    def test_no_url_fallback_and_raw_database_exception_suppressed(self):
        with patch.dict(os.environ, {'COMPONENT1_DB_URL': ''}), patch('psycopg.connect') as db:
            with self.assertRaises(r.PrerequisiteError):
                r.bootstrap_inventory(self.manifest)
            db.assert_not_called()
        with self.assertRaises(r.PrerequisiteError) as error:
            r.bootstrap_inventory(self.manifest, connect=MagicMock(side_effect=RuntimeError('password-secret postgresql://private')))
        self.assertNotIn('password-secret', str(error.exception))
        self.assertNotIn('postgresql://', str(error.exception))

    def test_budget_counts_retries_and_stops_before_next_attempt(self):
        transport = MagicMock(return_value=r.HttpResult(503, {}, b'{}'))
        client = self.client(2, transport, retries=5)
        result = self.execute(client)
        self.assertEqual(client.attempted_requests, 2)
        self.assertEqual(transport.call_count, 2)
        self.assertFalse(result['complete'])
        self.assertTrue(result['stopped'])
        self.assertEqual(result['inventory_size'], 1)

    def test_budget_spans_pages_and_retains_unavailable_inventory(self):
        client = self.client(2)
        result = self.execute(client)
        self.assertEqual(client.attempted_requests, 2)  # inventory refresh + channels
        self.assertFalse(result['complete'])
        self.assertEqual(result['inventory_size'], 1)

    def test_retry_bound_and_transient_recovery(self):
        underlying = r.fixture_client(self.fixture)._transport
        attempts = []
        def transient(url, params, timeout):
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutError('secret')
            return underlying(url, params, timeout)
        client = self.client(10, transient)
        self.assertTrue(self.execute(client)['complete'])
        self.assertEqual(client.attempted_requests, 6)
        bad = MagicMock(return_value=r.HttpResult(503, {}, b'{}'))
        # Direct request verifies per-request retry cap independently of later stages.
        with self.assertRaises(r.yc.ServerError):
            self.client(10, bad, retries=1).channels_list(part='snippet', id=['test'])
        self.assertEqual(bad.call_count, 2)

    def test_fatal_auth_quota_and_nontransient_errors_do_not_retry(self):
        for status, reason in [(400, 'keyInvalid'), (403, 'quotaExceeded'), (401, 'unauthorized')]:
            body = json.dumps({'error': {'message': 'test-key-secret postgresql://private password-secret', 'errors': [{'reason': reason}]}}).encode()
            transport = MagicMock(return_value=r.HttpResult(status, {}, body))
            result = self.execute(self.client(20, transport))
            self.assertEqual(transport.call_count, 1)
            self.assertFalse(result['complete'])
            self.assertNotIn('secret', json.dumps(result))
        transport = MagicMock(return_value=r.HttpResult(400, {}, b'{}'))
        with self.assertRaises(r.yc.BadRequestError):
            self.client(10, transport).channels_list(part='snippet', id=['test'])
        self.assertEqual(transport.call_count, 1)

    def test_live_retention_state_separation_payload_replay_and_no_writes(self):
        client = self.client()
        with self.assertRaises(r.PrerequisiteError):
            r.run(self.manifest, client, self.state)
        result = self.execute(client)
        self.assertTrue(result['complete'])
        payload = next(self.state.glob('run_*/payload_*.json'))
        original = payload.read_bytes()
        stored = r.replay_batch(payload, self.manifest)
        self.assertIn('observed_at', stored)
        self.assertEqual(payload.read_bytes(), original)
        with self.assertRaises(ValueError):
            r.run(self.manifest, r.fixture_client(self.fixture), self.state)
        self.assertEqual(payload.read_bytes(), original)
        with self.assertRaises(ValueError):
            r.run(self.manifest, client, self.state, dry_run=False, retention=RETENTION)

    def test_page_limit_incomplete_and_cli_failure_redaction(self):
        result = self.execute(self.client(), max_pages=1)
        self.assertFalse(result['complete'])
        self.assertTrue(any(x['stage'] == 'discovery_incomplete' for x in result['failures']))
        with patch.object(r, 'bootstrap_inventory', side_effect=RuntimeError('test-key-secret password-secret postgresql://private')):
            code, message = self.cli('--live', '--api-budget', '10', '--payload-retention-days', '1', '--retention-policy-ref', 'synthetic-only')
        self.assertEqual(code, 1)
        self.assertNotIn('secret', message)
        self.assertNotIn('postgresql://', message)

    def test_connected_preflight_only_never_constructs_api_client(self):
        with patch.object(r, 'bootstrap_inventory', return_value=self.fixture['seed']) as bootstrap, patch.object(r, 'LiveClient') as client:
            code, message = self.cli('--live', '--preflight-only', '--api-budget', '10', '--payload-retention-days', '1', '--retention-policy-ref', 'synthetic-only')
            self.assertEqual(code, 0)
            self.assertIn('read-only database bootstrap', message)
            bootstrap.assert_called_once()
            client.assert_not_called()

    def test_preflight_without_retention_reads_only_inventory_and_never_persists(self):
        conn, cur = self.connection()
        with patch('psycopg.connect', return_value=conn) as connect, \
             patch.object(r, 'LiveClient') as client, \
             patch.object(r, 'save_new') as save, \
             patch.object(r, 'run') as collect, \
             patch.object(r.yc, 'urllib_transport') as api, \
             patch('pathlib.Path.unlink') as unlink, \
             patch('pathlib.Path.mkdir') as mkdir, \
             patch('shared.database.repository.upsert_channels') as write_channels, \
             patch('shared.database.repository.upsert_videos') as write_videos:
            code, message = self.cli('--live', '--preflight-only', '--api-budget', '100')
            self.assertEqual(code, 0)
            self.assertIn('read-only database bootstrap', message)
            self.assertEqual(cur.execute.call_count, 3)
            self.assertIn('WHERE channel_id = ANY(%s)', cur.execute.call_args.args[0])
            connect.assert_called_once()
            conn.rollback.assert_called_once()
            conn.close.assert_called_once()
            conn.commit.assert_not_called()
            for mock in (client, save, collect, api, unlink, mkdir, write_channels, write_videos):
                mock.assert_not_called()


    def memory_run(self, client, **kwargs):
        with patch.object(r, 'save_new') as save, \
             patch('pathlib.Path.mkdir') as mkdir, \
             patch('pathlib.Path.unlink') as unlink, \
             patch('pathlib.Path.open', side_effect=AssertionError('State access forbidden')), \
             patch('pathlib.Path.glob', side_effect=AssertionError('State access forbidden')), \
             patch('psycopg.connect') as db, \
             patch('shared.database.repository.upsert_channels') as channels, \
             patch('shared.database.repository.upsert_videos') as videos:
            result = r.run(self.manifest, client, self.state, self.fixture['seed'], no_persist=True, **kwargs)
            for mock in (save, mkdir, unlink, db, channels, videos):
                mock.assert_not_called()
        return result

    def test_memory_only_success_has_counts_and_never_accesses_state(self):
        result = self.memory_run(self.client())
        self.assertTrue(result['complete'])
        self.assertFalse(result['persistence'])
        self.assertEqual(result['counts']['channels'], {
            'requested': 1, 'returned': 1, 'unavailable': 0, 'validation_failures': 0,
            'unconfirmed_due_to_request_failure': 0})
        self.assertEqual(result['counts']['videos']['requested'], 2)
        self.assertEqual(result['counts']['videos']['returned'], 2)
        self.assertEqual(result['attempted_requests'], 5)
        self.assertEqual(result['batches'], [])
        self.assertIsNone(result['inventory_revision'])

    def test_memory_only_reports_unavailable_and_invalid_separately(self):
        self.fixture['videos'] = self.fixture['videos'][1:]
        self.fixture['videos'][0]['snippet']['channelId'] = 'UCbbbbbbbbbbbbbbbbbbbbbb'
        result = self.memory_run(self.client())
        self.assertFalse(result['complete'])
        self.assertEqual(result['inventory_size'], 1)
        self.assertEqual(result['counts']['videos']['requested'], 2)
        self.assertEqual(result['counts']['videos']['returned'], 1)
        self.assertEqual(result['counts']['videos']['unavailable'], 1)
        self.assertEqual(result['counts']['videos']['validation_failures'], 1)

    def test_memory_only_budget_and_fatal_stop_are_safe(self):
        transport = MagicMock(return_value=r.HttpResult(503, {}, b'{}'))
        result = self.memory_run(self.client(2, transport, retries=5))
        self.assertFalse(result['complete'])
        self.assertEqual(result['attempted_requests'], 2)
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(result['counts']['videos']['unconfirmed_due_to_request_failure'], 1)
        self.assertEqual(result['counts']['channels']['unavailable'], 0)
        self.assertEqual(result['counts']['channels']['requested'], 0)
        fatal = MagicMock(return_value=r.HttpResult(401, {}, b'{}'))
        result = self.memory_run(self.client(100, fatal))
        self.assertEqual(fatal.call_count, 1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['stop_reason'], 'UnauthorizedError')

    def test_memory_cli_skips_retention_and_files_and_keeps_bootstrap(self):
        conn, cur = self.connection()
        with patch('psycopg.connect', return_value=conn), \
             patch.object(r.yc, 'urllib_transport', side_effect=r.fixture_client(self.fixture)._transport), \
             patch.object(r, 'save_new') as save, \
             patch('pathlib.Path.mkdir') as mkdir, \
             patch('pathlib.Path.unlink') as unlink, \
             patch('pathlib.Path.glob', side_effect=AssertionError('Disk inventory forbidden')), \
             patch('shared.database.repository.upsert_channels') as channels, \
             patch('shared.database.repository.upsert_videos') as videos:
            code, message = self.cli('--live', '--no-persist', '--api-budget', '100')
            self.assertEqual(code, 0)
            self.assertIn('"attempted_requests": 5', message)
            self.assertIn('"persistence": false', message)
            self.assertNotIn('test-key-secret', message)
            self.assertNotIn('postgresql://', message)
            self.assertEqual(cur.execute.call_count, 3)
            conn.rollback.assert_called_once()
            conn.commit.assert_not_called()
            for mock in (save, mkdir, unlink, channels, videos):
                mock.assert_not_called()

    def test_memory_cli_incomplete_exits_nonzero_and_still_requires_opt_in(self):
        with patch('psycopg.connect') as db:
            code, _ = self.cli('--offline-preflight', '--no-persist')
            self.assertEqual(code, 1)
            db.assert_not_called()
        with patch.object(r, 'bootstrap_inventory', return_value=self.fixture['seed']), \
             patch.object(r.yc, 'urllib_transport', return_value=r.HttpResult(401, {}, b'{}')):
            code, message = self.cli('--live', '--no-persist', '--api-budget', '100')
            self.assertEqual(code, 1)
            self.assertIn('"attempted_requests": 1', message)
        with self.assertRaises(ValueError):
            r.run(self.manifest, self.client(), None, no_persist=True, dry_run=False)


    def test_extensive_discovery_cannot_starve_1186_inventory_refresh(self):
        import copy
        cid = self.manifest['channels'][0]['channel_id']
        self.fixture['seed'] = [{'video_id': f'v{i:010d}', 'channel_id': cid} for i in range(1186)]
        base = self.fixture['videos'][0]
        self.fixture['videos'] = [dict(copy.deepcopy(base), id=row['video_id']) for row in self.fixture['seed']]
        for playlist in self.fixture['playlists']:
            self.fixture['playlists'][playlist] = [[] for _ in range(150)]
        underlying = r.fixture_client(self.fixture)._transport
        order = []
        def transport(url, params, timeout):
            order.append(url.rsplit('/', 1)[-1])
            return underlying(url, params, timeout)
        result = self.memory_run(self.client(100, transport), max_pages=200, discovery_budget=20)
        self.assertEqual(order[:24], ['videos'] * 24)
        self.assertEqual(result['counts']['videos']['returned'], 1186)
        self.assertTrue(result['inventory_refresh']['complete'])
        self.assertEqual(result['inventory_refresh']['reserved_initial_attempts'], 24)
        self.assertFalse(result['discovery']['complete'])
        self.assertEqual(result['endpoint_requests']['playlistItems']['attempts'], 20)
        self.assertEqual(result['attempted_requests'], 45)
        self.assertFalse(result['complete'])
        self.assertFalse(result['stopped'])

    def test_refresh_retry_reserve_protects_later_batches(self):
        import copy
        cid = self.manifest['channels'][0]['channel_id']
        self.fixture['seed'] = [{'video_id': f'v{i:010d}', 'channel_id': cid} for i in range(61)]
        base = self.fixture['videos'][0]
        self.fixture['videos'] = [dict(copy.deepcopy(base), id=row['video_id']) for row in self.fixture['seed']]
        underlying = r.fixture_client(self.fixture)._transport
        calls = []
        def transport(url, params, timeout):
            calls.append(params['id'])
            if len(calls) == 1:
                return r.HttpResult(503, {}, b'{}')
            return underlying(url, params, timeout)
        result = self.memory_run(self.client(2, transport), discovery_budget=0)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0], calls[1])  # retry could not spend later batch's reserve
        self.assertEqual(result['counts']['videos']['requested'], 61)
        self.assertEqual(result['counts']['videos']['returned'], 11)
        self.assertEqual(result['attempted_requests'], 2)
        self.assertFalse(result['inventory_refresh']['complete'])

    def test_discovery_retries_count_toward_separate_cap_and_endpoint_totals(self):
        underlying = r.fixture_client(self.fixture)._transport
        def transport(url, params, timeout):
            if url.endswith('/playlistItems'):
                return r.HttpResult(503, {}, b'{}')
            return underlying(url, params, timeout)
        result = self.memory_run(self.client(100, transport, retries=5), discovery_budget=2)
        stats = result['endpoint_requests']['playlistItems']
        self.assertEqual(stats, {'attempts': 2, 'initial_attempts': 1,
                                 'retry_attempts': 1, 'successful_requests': 0})
        self.assertTrue(result['inventory_refresh']['complete'])
        self.assertFalse(result['discovery']['complete'])
        self.assertFalse(result['stopped'])
        self.assertEqual(sum(v['attempts'] for v in result['endpoint_requests'].values()), result['attempted_requests'])
        self.assertEqual(result['endpoint_requests']['videos']['successful_requests'], 1)

    def test_per_channel_page_guard_and_discovery_membership_still_enforced(self):
        self.fixture['videos'][1]['snippet']['channelId'] = 'UCbbbbbbbbbbbbbbbbbbbbbb'
        result = self.memory_run(self.client(100), max_pages=1, discovery_budget=20)
        self.assertFalse(result['discovery']['complete'])
        self.assertEqual(result['endpoint_requests']['playlistItems']['attempts'], 1)
        # First page contains the new candidate; membership guard must reject it.
        self.assertEqual(result['counts']['videos']['validation_failures'], 1)
        self.assertEqual(result['inventory_size'], 1)


    def test_discovery_cap_is_global_across_channels_and_candidate_phase_continues(self):
        import copy
        channel = copy.deepcopy(self.fixture['channels'][0])
        channel['id'] = 'UCbbbbbbbbbbbbbbbbbbbbbb'
        channel['contentDetails']['relatedPlaylists']['uploads'] = 'UUbbbbbbbbbbbbbbbbbbbbbb'
        self.fixture['channels'].append(channel)
        self.manifest['channels'].append({'channel_id': channel['id']})
        self.fixture['playlists']['UUbbbbbbbbbbbbbbbbbbbbbb'] = [[]]
        result = self.memory_run(self.client(100), discovery_budget=1)
        self.assertEqual(result['endpoint_requests']['playlistItems']['attempts'], 1)
        self.assertEqual(len(result['discovery']['incomplete_channels']), 2)
        self.assertTrue(result['inventory_refresh']['complete'])
        self.assertEqual(result['inventory_size'], 2)  # verified first-page candidate still admitted
        self.assertFalse(result['stopped'])


    def add_discovery_channels(self, count, pages=10):
        import copy
        base = self.fixture['channels'][0]
        self.manifest['channels'] = []
        self.fixture['channels'] = []
        self.fixture['playlists'] = {}
        for i in range(count):
            cid, playlist = f'UC{i:022d}', f'UU{i:022d}'
            self.manifest['channels'].append({'channel_id': cid})
            channel = copy.deepcopy(base)
            channel['id'] = cid
            channel['contentDetails']['relatedPlaylists']['uploads'] = playlist
            self.fixture['channels'].append(channel)
            self.fixture['playlists'][playlist] = [[] for _ in range(pages)]
        self.fixture['seed'] = []
        self.fixture['videos'] = []

    def test_round_robin_18_channels_before_second_pages(self):
        self.add_discovery_channels(18)
        underlying = r.fixture_client(self.fixture)._transport
        pages = []
        def transport(url, params, timeout):
            if url.endswith('/playlistItems'):
                pages.append((params['playlistId'], params.get('pageToken')))
            return underlying(url, params, timeout)
        result = self.memory_run(self.client(100, transport), max_pages=10, discovery_budget=20)
        playlists = sorted(self.fixture['playlists'])
        self.assertEqual(pages[:18], [(pid, None) for pid in playlists])
        self.assertEqual(pages[18:], [(pid, '1') for pid in playlists[:2]])
        self.assertEqual(result['endpoint_requests']['playlistItems']['attempts'], 20)
        self.assertEqual(len(result['discovery']['incomplete_channels']), 18)
        self.assertFalse(result['discovery']['complete'])
        self.assertEqual(sorted(x['pages_returned'] for x in result['discovery']['channels'].values()), [1] * 16 + [2] * 2)

    def test_round_robin_retries_exhausted_channels_and_page_limits(self):
        self.add_discovery_channels(3, pages=3)
        playlists = sorted(self.fixture['playlists'])
        self.fixture['playlists'][playlists[1]] = [[]]  # exhausted after its first page
        underlying = r.fixture_client(self.fixture)._transport
        calls = []
        def transport(url, params, timeout):
            if url.endswith('/playlistItems'):
                calls.append((params['playlistId'], params.get('pageToken')))
                if len(calls) == 1:
                    return r.HttpResult(503, {}, b'{}')
            return underlying(url, params, timeout)
        result = self.memory_run(self.client(100, transport), max_pages=2, discovery_budget=20)
        self.assertEqual(calls, [(playlists[0], None), (playlists[0], None),
                                 (playlists[1], None), (playlists[2], None),
                                 (playlists[0], '1'), (playlists[2], '1')])
        self.assertEqual(result['endpoint_requests']['playlistItems']['retry_attempts'], 1)
        self.assertEqual(result['endpoint_requests']['playlistItems']['successful_requests'], 5)
        self.assertTrue(result['discovery']['channels'][self.manifest['channels'][1]['channel_id']]['complete'])
        self.assertEqual({row['reason'] for row in result['discovery']['incomplete_channels']}, {'per_channel_page_limit_reached'})

    def test_omitted_inventory_is_unavailable_not_request_failure_or_deletion(self):
        self.fixture['videos'] = self.fixture['videos'][1:]  # original ID omitted, candidate returned
        result = self.memory_run(self.client())
        inventory, candidate = result['inventory_refresh'], result['new_candidates']
        self.assertEqual({key: inventory[key] for key in ('requested', 'returned', 'unavailable', 'invalid', 'failed_requests')},
                         {'requested': 1, 'returned': 0, 'unavailable': 1, 'invalid': 0, 'failed_requests': 0})
        self.assertTrue(inventory['all_requests_completed'])
        self.assertFalse(inventory['all_videos_returned'])
        self.assertFalse(inventory['complete'])
        self.assertEqual(candidate['returned'], 1)
        self.assertTrue(candidate['complete'])
        self.assertEqual(result['inventory_size'], 2)  # original omitted ID retained alongside candidate

    def test_invalid_candidate_cannot_change_inventory_completion(self):
        self.fixture['videos'][1]['snippet']['channelId'] = 'UCbbbbbbbbbbbbbbbbbbbbbb'
        result = self.memory_run(self.client())
        self.assertTrue(result['inventory_refresh']['complete'])
        self.assertEqual(result['inventory_refresh']['invalid'], 0)
        self.assertEqual(result['new_candidates']['invalid'], 1)
        self.assertTrue(result['new_candidates']['all_requests_completed'])
        self.assertTrue(result['new_candidates']['all_videos_returned'])
        self.assertFalse(result['new_candidates']['complete'])
        self.assertEqual(result['inventory_size'], 1)

    def test_group_request_failure_is_not_unavailable_and_skipped_batches_not_failed(self):
        import copy
        cid = self.manifest['channels'][0]['channel_id']
        self.fixture['seed'] = [{'video_id': f'v{i:010d}', 'channel_id': cid} for i in range(61)]
        self.fixture['videos'] = [dict(copy.deepcopy(self.fixture['videos'][0]), id=row['video_id']) for row in self.fixture['seed']]
        transport = MagicMock(return_value=r.HttpResult(401, {}, b'{}'))
        result = self.memory_run(self.client(100, transport))
        group = result['inventory_refresh']
        self.assertEqual(group['requested'], 50)
        self.assertEqual(group['failed_requests'], 1)
        self.assertEqual(group['unattempted_requests'], 1)
        self.assertEqual(group['unconfirmed'], 50)
        self.assertEqual(group['unavailable'], 0)
        self.assertFalse(group['all_requests_completed'])
        self.assertEqual(result['new_candidates']['failed_requests'], 0)



if __name__ == '__main__':
    unittest.main()
