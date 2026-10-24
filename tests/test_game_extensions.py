"""Cross-component mount lifecycle and transaction crash boundaries.

Only synthetic packs and an isolated server directory are written.
"""
import copy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import tests.test_mounts_client as client_fixture
from metin2_studio.addons import game_extensions as extensions, mounts_activation, mounts_client
from metin2_studio.addons.hubcore.manager import _atomic_bytes
from metin2_studio.addons.repositories import RepositoryStore


@unittest.skipUnless(client_fixture.client_pack.lzokay is not None, 'lzokay is required')
class GameExtensionTests(unittest.TestCase):
    def setUp(self):
        fixture = self.fixture = client_fixture.MountClientTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        server = fixture.root / 'Serwer'
        game = server / 'linux-port/docker/game'
        game.mkdir(parents=True)
        self.pending_files = []
        self.saved_plans = {}
        self.studio = SimpleNamespace(root=server, game=game,
            mount_item_definitions={'52006': {'type': 18, 'limittype0': 6, 'limitvalue0': 3600}},
            workspace=SimpleNamespace(summary=lambda: {'pending': self.pending_files}),
            safe=lambda path: path, plan=self.save_plan, commit=self.commit)
        self.put('bin/game', b'synthetic engine')
        self.put('Dockerfile', b'FROM fixture AS quests\nRUN mkdir -p /tmp/qc-work /out-quest/poland/quest\n'
                 b'FROM fixture AS runtime\nCOPY --from=quests /out-quest/ /opt/metin2/share/locale/\n')
        self.put('.dockerignore', b'*\n')
        profile = {'point_api': 'pc.get_point', 'point_api_arity': 1, 'mount_point': 109,
                   'inventory_slots': 225, 'mount_bonus_affect': 533,
                   'native_item_ids': list(mounts_activation.NATIVE_ITEM_IDS)}
        profile_patch = patch.dict(mounts_activation.ENGINE_PROFILES, {extensions.sha256(b'synthetic engine'): profile})
        profile_patch.start()
        self.addCleanup(profile_patch.stop)
        real_client_plan = mounts_client.plan_client_fixes
        client_patch = patch.object(mounts_client, 'plan_client_fixes',
            side_effect=lambda *args, **kw: real_client_plan(*args, codec=fixture.codec, **kw))
        client_patch.start()
        self.addCleanup(client_patch.stop)
        backend = SimpleNamespace(target_root=fixture.client, check_writable=Mock(),
            profile=lambda: {'path': str(fixture.client), 'kind': 'installation', 'writable': True})
        bundled = Path(extensions.__file__).parent / 'catalog'
        self.service = SimpleNamespace(studio=self.studio, source=fixture.client.resolve(),
            state_dir=fixture.root / 'state', manager=SimpleNamespace(_require=lambda: backend),
            repositories=RepositoryStore(fixture.root / 'state', bundled))
        self.extension = extensions.GameExtensions(self.service)
        self.service.state = lambda: self.extension.state()
        self.initial_client = fixture.snapshot()

    def put(self, name, data):
        path = self.studio.game / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def save_plan(self, title, changes, hint, **kwargs):
        self.saved_plans['save'] = (changes, kwargs['metadata']['guards'])
        return {'id': 'save'}

    def commit(self, key):
        changes, guards = self.saved_plans[key]
        for path, old in guards:
            self.assertEqual(path.read_bytes() if path.is_file() else None, old)
        for path, raw in changes.items():
            _atomic_bytes(path, raw)
            self.pending_files.append({'path': path.relative_to(self.studio.root).as_posix()})
        return {'id': 'server-save'}

    def plan(self, action='install'):
        result = self.extension.plan(extensions.IDENT, action)
        self.assertTrue(result['can_apply'], result['conflicts'])
        return result

    def server_success(self, plan):
        self.extension.stage_server(plan['id'])
        self.pending_files.clear()
        self.extension.server_applied(plan['id'])

    def install(self):
        plan = self.plan()
        self.server_success(plan)
        self.extension.apply(plan['id'])
        return plan

    def test_plan_is_read_only_and_client_waits_for_verified_server(self):
        plan = self.plan()
        self.assertTrue(plan['server_required'])
        self.assertEqual(self.initial_client, self.fixture.snapshot())
        self.assertFalse(self.extension.state_path.exists())
        self.extension.stage_server(plan['id'])
        self.assertEqual(self.initial_client, self.fixture.snapshot())
        with self.assertRaisesRegex(ValueError, 'verified server build'):
            self.extension.apply(plan['id'])
        self.pending_files.clear()
        self.extension.server_applied(plan['id'])
        self.extension.apply(plan['id'])
        self.assertEqual(self.extension.state()['installed'][0]['integrity']['status'], 'healthy')
        self.assertNotEqual(self.initial_client, self.fixture.snapshot())
        for name in ('metin2client.exe', 'pack/root.index', 'pack/root.data'):
            self.assertEqual(self.initial_client[name], self.fixture.snapshot()[name])

    def test_open_client_allows_review_and_explains_why_apply_is_blocked(self):
        backend = self.service.manager._require()
        backend.check_writable.side_effect = ValueError('Close this Metin2 game client before applying add-ons.')
        backend.mutation_blockers = lambda: ['Close this Metin2 game client before applying add-ons.']
        plan = self.extension.plan(extensions.IDENT)
        self.assertFalse(plan['can_apply'])
        self.assertTrue(plan['components'])
        self.assertTrue(plan['server_files'])
        self.assertIn('Close this Metin2', plan['conflicts'][0])
        backend.check_writable.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'Resolve the mount add-on conflicts'):
            self.extension.apply(plan['id'])
        self.assertEqual(self.initial_client, self.fixture.snapshot())

    def test_failed_server_save_keeps_old_source_ownership_for_update_retry(self):
        self.install()
        packages, errors = self.service.repositories.packages()
        old = packages[extensions.IDENT]
        files = dict(old.files)
        files[mounts_activation.TEMPLATE_KEY] += b'\n-- reviewed new quest revision\n'
        updated = replace(old, files=files, digest=extensions.sha256(b'updated revision'))
        self.service.repositories.packages = lambda: ({extensions.IDENT: updated}, errors)
        update = self.plan('update')
        with patch.object(self.studio, 'commit', side_effect=OSError('server save failed')):
            with self.assertRaisesRegex(OSError, 'server save failed'):
                self.extension.stage_server(update['id'])
        self.assertTrue(self.extension.stored()['pending'])
        retry = self.plan('update')
        self.assertTrue(retry['can_apply'])
        self.server_success(retry)
        self.extension.apply(retry['id'])
        self.assertIn(b'reviewed new quest revision', (self.studio.game / mounts_activation.SOURCE).read_bytes())

    def test_disable_retry_preserves_committed_client_ownership_and_remove_restores_baseline(self):
        self.install()
        disable = self.plan('disable')
        self.assertTrue(disable['server_required'])
        self.extension.stage_server(disable['id'])
        # Restart/review after a failed server build, before any client writes.
        self.extension = extensions.GameExtensions(self.service)
        retry = self.plan('disable')
        self.assertTrue(retry['server_required'])
        self.assertTrue(self.extension.pending['client']['changes'])
        self.server_success(retry)
        self.extension.apply(retry['id'])
        self.assertEqual(self.initial_client, self.fixture.snapshot())
        self.assertFalse(self.extension.state()['installed'][0]['enabled'])
        enable = self.plan('enable')
        self.server_success(enable)
        self.extension.apply(enable['id'])
        remove = self.plan('remove')
        self.server_success(remove)
        self.extension.apply(remove['id'])
        self.assertEqual(self.initial_client, self.fixture.snapshot())
        self.assertFalse(self.extension.state()['installed'])
        self.assertIn(b'cleanup-only retirement', (self.studio.game / mounts_activation.SOURCE).read_bytes())

    def test_competing_handler_or_client_update_invalidates_review_without_writes(self):
        plan = self.plan()
        self.put('share/locale/poland/quest/object/52006/use/new_mount.start', b'pc.mount(20110, 60)\n')
        with self.assertRaisesRegex(ValueError, 'handlers changed'):
            self.extension.stage_server(plan['id'])
        self.assertEqual(self.initial_client, self.fixture.snapshot())
        self.assertFalse(self.extension.state_path.exists())

    def test_failed_second_pack_write_rolls_back_and_retains_verified_server_receipt(self):
        plan = self.plan()
        self.server_success(plan)
        def fail(path, raw):
            if path == self.fixture.client / mounts_client.PACK_FILES[1]:
                raise OSError('simulated write failure')
            return _atomic_bytes(path, raw)
        with patch.object(extensions, '_atomic_bytes', side_effect=fail), self.assertRaisesRegex(OSError, 'simulated'):
            self.extension.apply(plan['id'])
        self.assertEqual(self.initial_client, self.fixture.snapshot())
        self.assertFalse(self.extension.journal_path.exists())
        self.assertTrue(self.extension.stored()['pending']['server_verified'])
        retry = self.plan()
        self.assertFalse(retry['server_required'])
        self.extension.apply(retry['id'])
        self.assertTrue(self.extension.stored()['record'])

    def test_crash_mid_pair_is_recoverable_and_foreign_update_is_retained(self):
        plan = self.plan()
        self.server_success(plan)
        def crash(path, raw):
            if path == self.fixture.client / mounts_client.PACK_FILES[1]:
                raise KeyboardInterrupt('process ended')
            return _atomic_bytes(path, raw)
        with patch.object(extensions, '_atomic_bytes', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.extension.apply(plan['id'])
        self.assertTrue(self.extension.journal_path.exists())
        changed = self.fixture.client / mounts_client.PACK_FILES[1]
        changed.write_bytes(b'later game update')
        with self.assertRaisesRegex(ValueError, 'later client-data change'):
            self.extension.recover()
        self.assertEqual(changed.read_bytes(), b'later game update')
        changed.write_bytes(self.initial_client[mounts_client.PACK_FILES[1]])
        self.extension.recover()
        self.assertEqual(self.initial_client, self.fixture.snapshot())

    def test_state_save_failure_after_commit_finishes_without_rolling_back_outputs(self):
        plan = self.plan()
        self.server_success(plan)
        real_json = extensions._atomic_json
        def fail(path, value):
            if path == self.extension.state_path and value.get('record'):
                raise OSError('receipt save failure')
            return real_json(path, value)
        with patch.object(extensions, '_atomic_json', side_effect=fail), self.assertRaisesRegex(OSError, 'receipt save failure'):
            self.extension.apply(plan['id'])
        after = self.fixture.snapshot()
        self.assertNotEqual(after, self.initial_client)
        self.extension.recover()
        self.assertEqual(after, self.fixture.snapshot())
        self.assertEqual(self.extension.state()['installed'][0]['integrity']['status'], 'healthy')

    def test_newer_pack_reapply_then_remove_keeps_unrelated_updated_data(self):
        self.install()
        changed = copy.deepcopy(self.fixture.logical)
        changed['gamedata/unrelated.txt'] = b'new game version'
        self.fixture.write_pack('gamedata', changed)
        update_baseline = self.fixture.snapshot()
        self.assertTrue(self.extension.state()['installed'][0]['reapply_pending'])
        reapply = self.plan('reapply')
        self.assertFalse(reapply['server_required'])
        self.extension.apply(reapply['id'])
        remove = self.plan('remove')
        self.server_success(remove)
        self.extension.apply(remove['id'])
        self.assertEqual(self.fixture.snapshot(), update_baseline)

    def test_reapply_preserves_disabled_preference_after_game_update(self):
        self.install()
        disable = self.plan('disable')
        self.server_success(disable)
        self.extension.apply(disable['id'])
        changed = dict(self.fixture.logical, **{'gamedata/unrelated.txt': b'new game baseline'})
        self.fixture.write_pack('gamedata', changed)
        before = self.fixture.snapshot()
        reapply = self.plan('reapply')
        self.assertFalse(reapply['desired_state'][0]['enabled'])
        self.extension.apply(reapply['id'])
        self.assertEqual(before, self.fixture.snapshot())
        self.assertFalse(self.extension.stored()['record']['enabled'])
        self.assertTrue(self.extension.stored()['record']['activation_ownership']['cleanup_only'])
