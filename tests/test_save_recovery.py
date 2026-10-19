import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch, Mock

from metin2_studio.server import Studio, Handler
from metin2_studio.workspace import Workspace
from metin2_studio.save_recovery import SaveRecovery


def fixture(root, state):
    studio = Studio.__new__(Studio)
    studio.root, studio.state = root, state
    state.mkdir(exist_ok=True)
    studio.game = root / 'linux-port/docker/game'
    studio.compose, studio.locale = studio.game.parent, studio.game / 'share/locale/poland'
    studio.settings_schema, studio.sources, studio.plans = {}, {}, {}
    studio.lock, studio._operation_lock = threading.RLock(), threading.RLock()
    studio._active_mutations, studio._stopping, studio._apply_thread = 0, False, None
    studio._addons = None
    studio.job = {'status': 'idle', 'lines': []}
    studio.updates = SimpleNamespace(job={'status': 'idle'})
    studio.workspace = Workspace(studio)
    studio.save_recovery = SaveRecovery(studio)
    interrupted = studio.workspace.interrupt_deployments()
    if interrupted:
        studio.job = interrupted
    return studio


class SaveRecoveryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.base = Path(self.temp.name)
        self.root, self.state = self.base / 'game', self.base / 'state'
        self.root.mkdir()
        (self.root / 'VERSION').write_text('fixture')
        self.studio = fixture(self.root, self.state)
        self.paths = [self.studio.locale / 'cube.txt', self.studio.game / 'share-add/cube.seon_pyeong.txt']
        self.before = [b'# original first\n', b'# original second\n']
        for path, raw in zip(self.paths, self.before):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def tearDown(self):
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to((Path(__file__).resolve().parents[1] / '.test-tmp').resolve()))
        self.temp.cleanup()

    def plan(self):
        return self.studio.plan('Two file fixture', {path: raw + b'# intended change\n' for path, raw in zip(self.paths, self.before)}, 'Fixture only')

    def interrupt(self, after_all=False):
        plan = self.plan()
        if after_all:
            with patch.object(self.studio.workspace, 'record_commit', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    self.studio.commit(plan['id'])
        else:
            write = self.studio.write
            def stop(path, raw):
                write(path, raw)
                raise KeyboardInterrupt()
            with patch.object(self.studio, 'write', side_effect=stop):
                with self.assertRaises(KeyboardInterrupt):
                    self.studio.commit(plan['id'])
        self.studio = fixture(self.root, self.state)
        return self.studio.save_recovery.pending()[0]['id']

    def test_partial_save_is_visible_blocks_writes_and_recovers_exact_bytes(self):
        ident = self.interrupt()
        self.assertEqual(len(self.studio.workspace.summary()['pending']), 1)
        self.assertEqual(len(self.studio.workspace.summary()['saveRecovery']), 1)
        with self.assertRaisesRegex(ValueError, 'Review recovery'):
            self.plan()
        with self.assertRaisesRegex(ValueError, 'Review recovery'):
            self.studio.apply()
        plan = self.studio.save_recovery.preview(ident)
        self.assertEqual(plan['confirmLabel'], 'Restore interrupted save')
        self.assertTrue(self.studio.commit(plan['id'])['recovered'])
        self.assertEqual([p.read_bytes() for p in self.paths], self.before)
        self.assertFalse(self.studio.workspace.summary()['pending'])
        self.assertFalse(self.studio.save_recovery.pending())
        self.assertTrue((self.state / 'backups' / ident / '0.after').is_file())

    def test_new_game_values_are_retained_and_listed_in_recovery_review(self):
        ident = self.interrupt()
        self.paths[1].write_bytes(b'# new game package value\n')
        plan = self.studio.save_recovery.preview(ident)
        self.assertEqual(plan['keptGameFiles'], [self.paths[1].relative_to(self.root).as_posix()])
        self.studio.commit(plan['id'])
        self.assertEqual(self.paths[0].read_bytes(), self.before[0])
        self.assertEqual(self.paths[1].read_bytes(), b'# new game package value\n')

    def test_external_change_after_review_invalidates_all_recovery_writes(self):
        ident = self.interrupt()
        plan = self.studio.save_recovery.preview(ident)
        self.paths[1].write_bytes(b'# later game change\n')
        first = self.paths[0].read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed since recovery review'):
            self.studio.commit(plan['id'])
        self.assertEqual(self.paths[0].read_bytes(), first)
        self.assertTrue(self.studio.save_recovery.pending())

    def test_corrupt_backup_blocks_recovery_without_touching_game_files(self):
        ident = self.interrupt()
        (self.state / 'backups' / ident / '0.before').write_bytes(b'corrupt')
        before = [p.read_bytes() for p in self.paths]
        self.assertFalse(self.studio.save_recovery.pending()[0]['canRecover'])
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.studio.save_recovery.preview(ident)
        self.assertEqual([p.read_bytes() for p in self.paths], before)

    def test_malformed_receipts_keep_studio_open_and_block_writes_with_a_clear_error(self):
        ident = self.interrupt()
        receipt = self.state / 'backups' / ident / 'manifest.json'
        before = [p.read_bytes() for p in self.paths]
        for value in ('broken JSON', '[]', '{"status":"saving"}',
                      json.dumps({'id': ident, 'title': 'Broken', 'status': 'saving', 'files': [None]})):
            with self.subTest(value=value):
                receipt.write_text(value, 'utf-8')
                self.studio = fixture(self.root, self.state)
                pending = self.studio.save_recovery.pending()
                self.assertFalse(pending[0]['canRecover'])
                self.assertIn('unreadable', pending[0]['error'])
                self.assertFalse(self.studio.history()[0]['canRestore'])
                with self.assertRaisesRegex(ValueError, 'Review recovery'):
                    self.plan()
                self.assertEqual([p.read_bytes() for p in self.paths], before)

    def test_interruption_during_recovery_can_be_reviewed_and_resumed(self):
        ident = self.interrupt(after_all=True)
        plan = self.studio.save_recovery.preview(ident)
        write = self.studio.write
        def stop(path, raw):
            write(path, raw)
            raise KeyboardInterrupt()
        with patch.object(self.studio, 'write', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                self.studio.commit(plan['id'])
        self.studio = fixture(self.root, self.state)
        self.assertTrue(self.studio.save_recovery.pending())
        self.studio.commit(self.studio.save_recovery.preview(ident)['id'])
        self.assertEqual([p.read_bytes() for p in self.paths], self.before)

    def test_committed_save_with_unfinished_receipt_finalizes_without_file_writes(self):
        from metin2_studio.save_recovery import manifest_write
        plan = self.plan()
        def interrupted_receipt(path, receipt):
            if receipt['status'] == 'saved':
                raise KeyboardInterrupt()
            return manifest_write(path, receipt)
        with patch('metin2_studio.save_recovery.manifest_write', side_effect=interrupted_receipt):
            with self.assertRaises(KeyboardInterrupt):
                self.studio.commit(plan['id'])
        self.paths[1].write_bytes(b'# subsequent game update\n')
        current = [p.read_bytes() for p in self.paths]
        self.studio = fixture(self.root, self.state)
        self.assertFalse(self.studio.save_recovery.pending())
        self.assertEqual([p.read_bytes() for p in self.paths], current)
        self.assertEqual(self.studio.history()[0]['status'], 'saved')

    def test_no_file_writes_before_interruption_needs_no_manual_recovery(self):
        plan = self.plan()
        with patch.object(self.studio, 'write', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.studio.commit(plan['id'])
        self.studio = fixture(self.root, self.state)
        self.assertFalse(self.studio.save_recovery.pending())
        self.assertEqual(self.studio.history()[0]['status'], 'rolled-back')

    def test_incomplete_new_quest_creation_is_removed_by_reviewed_recovery(self):
        target = self.studio.game / 'custom-quests/studio_recovery_test.quest'
        plan = self.studio.plan('Create quest fixture', {target: b'quest fixture begin end\n'}, 'Fixture')
        with patch.object(self.studio.workspace, 'record_commit', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.studio.commit(plan['id'])
        self.studio = fixture(self.root, self.state)
        recovery = self.studio.save_recovery.pending()[0]
        self.studio.commit(self.studio.save_recovery.preview(recovery['id'])['id'])
        self.assertFalse(target.exists())

    def test_interrupted_deployment_stays_visible_until_verified_apply(self):
        self.studio.workspace.deployment('unfinished', 'running', {'kind': 'apply', 'files': {}})
        self.studio = fixture(self.root, self.state)
        self.assertEqual(self.studio.job['status'], 'interrupted')
        self.studio.workspace.deployment('only-validated', 'validated', {'kind': 'validation', 'files': {}})
        self.assertEqual(self.studio.workspace.summary()['interruptedDeployment']['id'], 'unfinished')
        self.studio = fixture(self.root, self.state)
        self.assertEqual(self.studio.job['status'], 'interrupted')
        self.studio.workspace.deployment('verified', 'succeeded', {'kind': 'apply', 'files': {}})
        self.studio = fixture(self.root, self.state)
        self.assertEqual(self.studio.job['status'], 'idle')

    def test_interrupted_retry_requires_acknowledgement_and_waits_for_old_process(self):
        self.studio.workspace.deployment('unfinished', 'running', {'kind': 'apply', 'files': {}, 'process': {'pid': 123, 'identity': 'test'}})
        self.studio = fixture(self.root, self.state)
        with patch('metin2_studio.operation_process.previous_build_running', return_value=True):
            with self.assertRaisesRegex(ValueError, 'still running'):
                self.studio.apply(acknowledge_interrupted='unfinished')
        with patch('metin2_studio.operation_process.previous_build_running', return_value=False):
            with self.assertRaisesRegex(ValueError, 'acknowledge'):
                self.studio.apply()
        self.assertEqual(self.studio.workspace.summary()['interruptedDeployment']['id'], 'unfinished')

    def test_shutdown_refuses_active_work_and_prevents_new_work_after_acceptance(self):
        with self.studio.mutation_request():
            with self.assertRaisesRegex(ValueError, 'busy'):
                self.studio.request_shutdown()
        for job in ({'status': 'running', 'kind': 'apply'}, {'status': 'running', 'kind': 'validation'}):
            self.studio.job = job
            with self.assertRaisesRegex(ValueError, 'busy'):
                self.studio.request_shutdown()
        self.studio.job = {'status': 'idle'}
        self.studio.updates.job = {'status': 'running'}
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.studio.request_shutdown()
        self.studio.updates.job = {'status': 'idle'}
        self.studio._addons = SimpleNamespace(jobs=SimpleNamespace(latest=lambda: {'status': 'running'}))
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.studio.request_shutdown()
        self.studio._addons = None
        self.studio.request_shutdown()
        with self.assertRaisesRegex(ValueError, 'stopping'):
            with self.studio.mutation_request():
                self.fail('Stopping Studio admitted a new mutation.')

    def test_worker_stays_busy_during_final_receipt_and_runtime_verification(self):
        self.studio.job = {'status': 'succeeded', 'lines': []}
        self.studio._apply_thread = SimpleNamespace(is_alive=lambda: True)
        self.assertTrue(self.studio.server_busy())
        self.assertEqual(self.studio.public_job()['status'], 'running')
        with self.assertRaisesRegex(ValueError, 'already running'):
            self.studio.apply()
        with self.assertRaisesRegex(ValueError, 'finish'):
            self.plan()
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.studio.request_shutdown()

    def test_post_spawn_tracking_failure_waits_for_the_child_before_finishing(self):
        process = Mock(pid=123, stdout=iter(['build line\n']))
        process.wait.return_value = 0
        self.studio.job = {'status': 'running', 'kind': 'validation', 'id': 'process-failure', 'files': {}, 'lines': []}
        with patch.object(self.studio, 'build_fingerprints', return_value={}), patch('metin2_studio.server.subprocess.Popen', return_value=process), patch('metin2_studio.operation_process.process_identity', side_effect=ValueError('Cannot identify test process')):
            self.studio.run_apply(True)
        process.communicate.assert_called_once()
        process.wait.assert_called_once()
        self.assertEqual(self.studio.job['status'], 'failed')

    def test_http_recovery_and_busy_shutdown_use_review_and_session_guards(self):
        ident = self.interrupt()
        self.studio.token = 'recovery-test-token'
        handler = type('RecoveryHandler', (Handler,), {'studio': self.studio})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:%s' % server.server_port
        def request(route, body=None, token='recovery-test-token'):
            headers = {'Origin': base, 'Content-Type': 'application/json', 'X-Studio-Token': token}
            req = urllib.request.Request(base + '/api/' + route, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)
        try:
            self.assertEqual(len(request('workspace')['saveRecovery']), 1)
            with self.assertRaises(urllib.error.HTTPError):
                request('recovery/preview', {'id': ident}, token='wrong')
            plan = request('recovery/preview', {'id': ident})
            self.assertEqual(plan['confirmLabel'], 'Restore interrupted save')
            self.assertTrue(request('commit', {'id': plan['id']})['recovered'])
            self.assertEqual(request('workspace')['saveRecovery'], [])
            self.studio.job = {'status': 'running', 'kind': 'apply'}
            with self.assertRaises(urllib.error.HTTPError) as failure:
                request('shutdown', {})
            self.assertEqual(failure.exception.code, 400)
            self.assertFalse(self.studio._stopping)
            self.assertEqual(request('workspace')['saveRecovery'], [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)

    def test_error_after_atomic_replacement_does_not_hide_the_changed_file(self):
        plan = self.plan()
        write = self.studio.write
        calls = []
        def after_replace(path, raw):
            write(path, raw)
            calls.append(path)
            if len(calls) == 1:
                raise OSError('Fixture error after replacement')
        with patch.object(self.studio, 'write', side_effect=after_replace):
            with self.assertRaises(OSError):
                self.studio.commit(plan['id'])
        self.assertEqual([p.read_bytes() for p in self.paths], self.before)
        self.assertFalse(self.studio.save_recovery.pending())

    def test_broken_output_pipe_still_waits_for_the_launched_child(self):
        process = Mock(pid=123, stdout=iter([]))
        process.communicate.side_effect = OSError('Fixture broken output pipe')
        process.wait.return_value = 0
        self.studio.job = {'status': 'running', 'kind': 'validation', 'id': 'pipe-failure', 'files': {}, 'lines': []}
        with patch.object(self.studio, 'build_fingerprints', return_value={}), patch('metin2_studio.server.subprocess.Popen', return_value=process), patch('metin2_studio.operation_process.process_identity', side_effect=ValueError('Fixture tracking error')):
            self.studio.run_apply(True)
        process.wait.assert_called_once()
        self.assertEqual(self.studio.job['status'], 'failed')
