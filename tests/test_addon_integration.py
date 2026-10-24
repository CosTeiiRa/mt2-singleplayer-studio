"""Merged API boundaries using original synthetic packs, never a live game."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
from urllib.parse import quote
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from metin2_studio.addons import client_pack as codec
from metin2_studio.addons.integration import AddonService
from metin2_studio.local_lock import InstanceLock
from metin2_studio.server import Handler, Studio
from metin2_studio.addons.artifacts import build_artifact
from tools.addon import scaffold


def make_world(base):
    server = base / 'world' / 'Serwer'
    server.mkdir(parents=True)
    (server / 'VERSION').write_text('2.2.108', 'utf-8')
    client = server.parent / 'Klient'
    pack = client / 'pack'
    pack.mkdir(parents=True)
    (client / 'client.version').write_text('2.0.112', 'utf-8')
    config = {'eter_pack_index_key': [1, 2, 3, 4], 'eter_pack_data_key': [8, 7, 6, 5]}
    (pack / 'root.json').write_text(json.dumps(config), 'utf-8')
    empty = codec.EterPack(codec.encode_object(struct.pack('<4sII', b'EPKD', 2, 0), config['eter_pack_index_key']), b'', config)
    index, data = empty.build({'uiminimap.py': b'class AtlasWindow(object):\n def OnUpdate(self): pass\n def SetMapName(self, mapName): pass\n def Destroy(self): pass\n'})
    (pack / 'root.index').write_bytes(index)
    (pack / 'root.data').write_bytes(data)
    maps = server / 'linux-port/docker/game/share/locale/poland/map'
    folder = maps / 'map_n_threeway'
    folder.mkdir(parents=True)
    (maps / 'index').write_text('64 map_n_threeway\n', 'utf-8')
    (folder / 'Setting.txt').write_text('MapSize 4 4\nBasePosition 0 0\n', 'utf-8')
    (folder / 'boss.txt').write_text('m 100 200 10 20 0 0 60m 100 1 691\n', 'utf-8')
    studio = Studio.__new__(Studio)
    studio.root = server
    studio.state = base / 'studio-state'
    studio.state.mkdir()
    studio.lock = threading.RLock()
    studio._operation_lock = threading.RLock()
    studio._active_mutations = 0
    studio._stopping = False
    studio._apply_thread = None
    studio.job = {'status': 'idle'}
    studio.updates = SimpleNamespace(job={'status': 'idle'})
    studio.workspace = SimpleNamespace(summary=lambda: {'recent': [{'kind': 'saved', 'title': 'Server fixture saved', 'at': 1}]})
    studio.token = 'merged-test-token'
    studio._addons = None
    return studio, client


@unittest.skipIf(codec.lzokay is None, 'Install optional add-on dependencies to exercise synthetic pack integration.')
class AddonIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.contexts = ExitStack()
        self.addCleanup(self.contexts.close)
        test_root = Path(__file__).resolve().parents[1] / '.test-tmp'
        test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.base = Path(self.temp.name)
        self.studio, self.client = make_world(self.base)
        self.service = self.studio.addons
        self.original = {name: (self.client / 'pack' / name).read_bytes() for name in ('root.index', 'root.data')}

    def tearDown(self):
        self.temp.cleanup()

    def apply(self, ident, action='install', **extra):
        plan = self.service.post('plan', {'addon_id': ident, 'action': action, **extra})['plan']
        self.assertTrue(plan['can_apply'], plan['conflicts'])
        return self.service.post('apply', {'plan_id': plan['id']})

    def test_world_binding_blocks_another_installation_and_unvalidated_runtime(self):
        state = self.service.state()
        self.assertFalse(state['installation']['writable'])
        other = self.base / 'other'
        other.mkdir()
        _, foreign_client = make_world(other)
        with self.assertRaisesRegex(ValueError, 'another world'):
            self.service.post('connect', {'path': str(foreign_client)})
        plan = self.service.post('plan', {'addon_id': 'community.boss-atlas'})['plan']
        self.assertFalse(plan['can_apply'])

    def supported_client(self):
        (self.client / 'metin2client.exe').write_bytes(b'fixture runtime')
        self.contexts.enter_context(patch('metin2_studio.addons.client_adapter.recorded_profile', return_value={'id': 'fixture-runtime'}))
        running = self.contexts.enter_context(patch('metin2_studio.addons.client_adapter.running_client', return_value=False))
        self.service.post('connect', {'path': str(self.client)})
        return running

    def test_normal_game_client_install_settings_and_removal_need_no_copy(self):
        self.supported_client()
        state = self.service.state()
        self.assertEqual(state['installation']['kind'], 'installation')
        self.assertTrue(state['installation']['writable'])
        self.assertEqual(state['installation']['path'], str(self.client))
        self.assertFalse(state['sandbox_targets'])
        self.apply('community.boss-atlas')
        self.apply('community.boss-atlas', 'configure', settings={'show_metins': True})
        self.apply('community.boss-atlas', 'disable')
        self.apply('community.boss-atlas', 'enable')
        self.apply('community.boss-atlas', 'remove')
        for name, raw in self.original.items():
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)
        self.assertFalse(self.service.state()['sandbox_targets'])
        self.assertTrue(self.service.manager._stored()['baseline_physical'])

    def test_extension_is_catalogued_separately_and_cannot_enter_client_pack_batches(self):
        self.supported_client()
        self.studio.game = self.studio.root / 'linux-port/docker/game'
        catalog = self.service.get('catalog', {})['catalog']['items']
        mount = next(row for row in catalog if row['id'] == 'community.legacy-mount-support')
        self.assertEqual(mount['kind'], 'game-extension')
        self.assertFalse(any(row['kind'] == 'game-extension' for row in self.service.manager.catalog()['items']))
        with self.assertRaisesRegex(ValueError, 'separately'):
            self.service.post('plan/batch', {'addon_ids': ['community.boss-atlas', mount['id']]})
        review = self.service.post('plan', {'addon_id': mount['id']})['plan']
        self.assertEqual(review['kind'], 'game-extension')
        self.assertFalse(review['can_apply'])  # synthetic world has no supported engine/gamedata
        self.assertTrue(review['conflicts'])
        self.assertFalse(self.service.extensions.state_path.exists())

    def test_combined_review_reapplies_real_packs_over_updated_baseline(self):
        self.supported_client()
        self.apply('community.boss-atlas')
        self.apply('community.boss-atlas', 'configure', settings={'show_metins': True})
        # A clean replacement models the launcher overwriting managed packs.
        backend = self.service.manager._require()
        updated = backend.pack().build({'uiminimap.py': b'class AtlasWindow(object):\n def OnUpdate(self): pass\n def SetMapName(self, mapName): pass\n def Destroy(self): pass\n# Updated game baseline\n'})
        for name, raw in zip(('root.index', 'root.data'), updated):
            (self.client / 'pack' / name).write_bytes(raw)
        self.studio.build_fingerprints = lambda: {}
        self.studio.native_pending = lambda: {}
        self.studio.native_crafting = SimpleNamespace(config=lambda: {'recipes': {}}, pending=lambda: False)
        preferences = {}
        self.studio.workspace = SimpleNamespace(summary=lambda: {'pending': [], 'drafts': []}, signature=lambda: 'fixture',
            set_preference=lambda key, value: preferences.update({key: value}))
        self.studio.save_recovery = SimpleNamespace(require_clear=lambda: None)
        workflow = self.studio.apply_workflow
        review = workflow.review()
        self.assertFalse(review['server'])
        self.assertEqual(review['addons']['action'], 'reapply')
        job = workflow.start({'reviewId': review['id']})
        self.studio._apply_thread.join(10)
        self.assertFalse(self.studio._apply_thread.is_alive())
        self.assertEqual(job['status'], 'succeeded', job['lines'])
        state = self.service.state()
        self.assertEqual(state['integrity']['status'], 'healthy')
        self.assertTrue(state['installed'][0]['settings']['show_metins'])
        self.apply('community.boss-atlas', 'remove')
        for name, raw in zip(('root.index', 'root.data'), updated):
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_shared_review_reapplies_selected_real_addons_and_retains_skipped_preferences(self):
        self.supported_client()
        self.apply('community.boss-atlas')
        self.apply('community.map-legend')
        self.apply('community.boss-atlas', 'configure', settings={'show_metins': True})
        backend = self.service.manager._require()
        updated = backend.pack().build({'uiminimap.py': b'class AtlasWindow(object):\n def OnUpdate(self): pass\n def SetMapName(self, mapName): pass\n def Destroy(self): pass\n# New game version\n'})
        for name, raw in zip(('root.index', 'root.data'), updated):
            (self.client / 'pack' / name).write_bytes(raw)
        self.studio.build_fingerprints = lambda: {}
        self.studio.native_pending = lambda: {}
        self.studio.native_crafting = SimpleNamespace(config=lambda: {'recipes': {}}, pending=lambda: False)
        self.studio.workspace = SimpleNamespace(summary=lambda: {'pending': [], 'drafts': []}, signature=lambda: 'fixture',
                                               set_preference=lambda key, value: None)
        self.studio.save_recovery = SimpleNamespace(require_clear=lambda: None)
        workflow = self.studio.apply_workflow
        initial = workflow.review()
        self.assertEqual(len(initial['selectableAddons']), 2)
        selected = workflow.review(addon_ids=['community.boss-atlas'], review_id=initial['id'])
        job = workflow.start({'reviewId': selected['id']})
        self.studio._apply_thread.join(10)
        self.assertFalse(self.studio._apply_thread.is_alive())
        self.assertEqual(job['status'], 'succeeded', job['lines'])
        state = self.service.state()
        records = {row['id']: row for row in state['installed']}
        self.assertEqual(state['integrity']['pending_addon_ids'], ['community.map-legend'])
        self.assertEqual(records['community.boss-atlas']['integrity']['status'], 'healthy')
        self.assertTrue(records['community.boss-atlas']['settings']['show_metins'])
        config = {}
        exec(backend.snapshot()['m2hub_config.py'], config)
        self.assertEqual([row['id'] for row in config['INSTALLED_ADDONS']], ['community.boss-atlas'])
        remaining = workflow.review()
        self.assertEqual(remaining['selectedAddonIds'], ['community.map-legend'])
        job = workflow.start({'reviewId': remaining['id']})
        self.studio._apply_thread.join(10)
        self.assertEqual(job['status'], 'succeeded', job['lines'])
        self.assertEqual(self.service.state()['integrity']['status'], 'healthy')
        self.apply('community.boss-atlas', 'remove')
        self.apply('community.map-legend', 'remove')
        for name, raw in zip(('root.index', 'root.data'), updated):
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_running_normal_client_blocks_review_and_apply_without_writes(self):
        running = self.supported_client()
        running.return_value = True
        plan = self.service.post('plan', {'addon_id': 'community.boss-atlas'})['plan']
        self.assertFalse(plan['can_apply'])
        self.assertTrue(any('Close this Metin2' in conflict for conflict in plan['conflicts']))
        running.return_value = False
        plan = self.service.post('plan', {'addon_id': 'community.boss-atlas'})['plan']
        self.assertTrue(plan['can_apply'])
        running.return_value = True
        with self.assertRaisesRegex(ValueError, 'Close this Metin2'):
            self.service.post('apply', {'plan_id': plan['id']})
        for name, raw in self.original.items():
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_normal_client_executable_change_invalidates_review(self):
        self.supported_client()
        plan = self.service.post('plan', {'addon_id': 'community.boss-atlas'})['plan']
        (self.client / 'metin2client.exe').write_bytes(b'new runtime')
        with self.assertRaisesRegex(ValueError, 'runtime is not validated'):
            self.service.post('apply', {'plan_id': plan['id']})
        for name, raw in self.original.items():
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_normal_client_game_update_reapply_and_exact_new_pack_restoration(self):
        self.supported_client()
        self.apply('community.boss-atlas')
        self.apply('community.boss-atlas', 'configure', settings={'show_metins': True})
        # The game updater supplies a fresh root pair with an upstream UI change.
        from metin2_studio.addons.client_adapter import ClientAdapter
        config = json.loads((self.client / 'pack/root.json').read_text('utf-8'))
        original = codec.EterPack(self.original['root.index'], self.original['root.data'], config)
        fresh = original.files()
        fresh['uiminimap.py'] += b'\n# Updated upstream map implementation\n'
        fresh['upstream.py'] = b'NEW_GAME_FEATURE = True\n'
        index, data = original.build(fresh)
        new_physical = {'root.index': index, 'root.data': data}
        for name, raw in new_physical.items():
            (self.client / 'pack' / name).write_bytes(raw)
        self.assertTrue(ClientAdapter.is_clean_game_baseline(fresh))
        self.assertTrue(self.service.state()['game_update']['detected'])
        self.apply('community.boss-atlas', 'reapply')
        current = codec.EterPack.open(self.client / 'pack').files()
        self.assertEqual(current['upstream.py'], fresh['upstream.py'])
        self.assertIn(b'Updated upstream map implementation', current['uiminimap.py'])
        self.assertTrue(self.service.state()['installed'][0]['settings']['show_metins'])
        self.apply('community.boss-atlas', 'remove')
        for name, raw in new_physical.items():
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_deleted_addon_payload_is_detected_and_repaired_with_running_client_guard(self):
        running = self.supported_client()
        self.apply('community.boss-atlas')
        pack = codec.EterPack.open(self.client / 'pack')
        files = pack.files()
        files.pop('m2hub_addons/boss_atlas.py')
        for name, raw in zip(('root.index', 'root.data'), pack.build(files)):
            (self.client / 'pack' / name).write_bytes(raw)
        state = self.service.state()
        self.assertEqual(state['installed'][0]['integrity']['status'], 'missing')
        self.assertEqual(state['integrity']['repair_action'], 'repair')
        physical = self.service.manager._backend.physical_snapshot()
        running.return_value = True
        plan = self.service.post('plan', {'addon_id': 'community.boss-atlas', 'action': 'repair'})['plan']
        self.assertFalse(plan['can_apply'])
        self.assertTrue(any('Close this Metin2' in conflict for conflict in plan['conflicts']))
        self.assertEqual(self.service.manager._backend.physical_snapshot(), physical)
        running.return_value = False
        self.apply('community.boss-atlas', 'repair')
        self.assertEqual(self.service.state()['integrity']['status'], 'healthy')
        self.apply('community.boss-atlas', 'remove')
        for name, raw in self.original.items():
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_batch_service_reviews_and_applies_two_addons_together_with_client_guard(self):
        running = self.supported_client()
        plan = self.service.post('plan/batch', {'addon_ids': ['community.boss-atlas', 'community.map-legend']})['plan']
        self.assertTrue(plan['can_apply'], plan['conflicts'])
        self.assertEqual(len(plan['batch']), 2)
        running.return_value = True
        with self.assertRaisesRegex(ValueError, 'Close this Metin2'):
            self.service.post('apply', {'plan_id': plan['id']})
        for name, raw in self.original.items():
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)
        running.return_value = False
        self.service.post('apply', {'plan_id': plan['id']})
        state = self.service.state()
        self.assertEqual(len(state['installed']), 2)
        self.assertEqual(state['integrity']['status'], 'healthy')
        self.assertEqual(len(self.service.manager.history()), 1)

    def test_batch_opens_the_supported_client_once_only_after_successful_apply(self):
        self.supported_client()
        plan = self.service.post('plan/batch', {'addon_ids': ['community.boss-atlas', 'community.map-legend']})['plan']
        with patch('metin2_studio.addons.client_adapter.subprocess.Popen', return_value=SimpleNamespace(pid=12345)) as start:
            result = self.service.post('apply', {'plan_id': plan['id'], 'launch_client': True})
        start.assert_called_once_with([str(self.client / 'metin2client.exe')], cwd=str(self.client), close_fds=True)
        self.assertEqual(result['client_launch']['status'], 'launched')
        self.assertEqual(self.service.state()['integrity']['status'], 'healthy')

    def test_failed_batch_does_not_open_client_and_launch_failure_keeps_committed_addons(self):
        running = self.supported_client()
        plan = self.service.post('plan/batch', {'addon_ids': ['community.boss-atlas', 'community.map-legend']})['plan']
        with patch('metin2_studio.addons.client_adapter.subprocess.Popen', side_effect=OSError('Client could not start')) as start:
            running.return_value = True
            with self.assertRaisesRegex(ValueError, 'Close this Metin2'):
                self.service.post('apply', {'plan_id': plan['id'], 'launch_client': True})
            start.assert_not_called()
            running.return_value = False
            result = self.service.post('apply', {'plan_id': plan['id'], 'launch_client': True})
            start.assert_called_once()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['client_launch']['status'], 'failed')
        self.assertEqual(len(self.service.state()['installed']), 2)
        self.assertEqual(self.service.state()['integrity']['status'], 'healthy')

    def test_batch_does_not_open_a_duplicate_client_if_it_was_just_started(self):
        running = self.supported_client()
        plan = self.service.post('plan/batch', {'addon_ids': ['community.boss-atlas', 'community.map-legend']})['plan']
        original_apply = self.service.manager.apply
        def apply_then_external_open(ident):
            result = original_apply(ident)
            running.return_value = True
            return result
        with patch.object(self.service.manager, 'apply', side_effect=apply_then_external_open), patch('metin2_studio.addons.client_adapter.subprocess.Popen') as start:
            result = self.service.post('apply', {'plan_id': plan['id'], 'launch_client': True})
        start.assert_not_called()
        self.assertEqual(result['client_launch']['status'], 'already_running')

    def test_missing_client_pack_is_visible_after_service_restart_and_can_be_rechecked(self):
        self.supported_client()
        self.apply('community.boss-atlas')
        path = self.client / 'pack/root.index'
        installed_index = path.read_bytes()
        path.unlink()
        self.studio._addons = None
        service = self.studio.addons
        state = service.state()
        self.assertFalse(state['installation']['writable'])
        self.assertEqual(state['installed'][0]['id'], 'community.boss-atlas')
        self.assertEqual(state['installed'][0]['integrity']['status'], 'unavailable')
        self.assertFalse(state['integrity']['repair_available'])
        path.write_bytes(installed_index)
        self.assertEqual(service.state()['integrity']['status'], 'healthy')

    def test_running_client_probe_matches_only_the_exact_executable_path(self):
        from metin2_studio.addons.client_adapter import running_client
        from subprocess import CompletedProcess
        expected = self.client / 'metin2client.exe'
        with patch('metin2_studio.addons.client_adapter.os', SimpleNamespace(name='nt')), patch('metin2_studio.addons.client_adapter.subprocess.run') as run:
            run.return_value = CompletedProcess([], 0, json.dumps([{'pid': 10, 'path': str(expected)}]), '')
            self.assertTrue(running_client(expected))
            run.return_value.stdout = json.dumps([{'pid': 10, 'path': str(self.base / 'other/metin2client.exe')}])
            self.assertFalse(running_client(expected))
            run.return_value.stdout = '[]'
            self.assertFalse(running_client(expected))
            run.return_value.stdout = '{}'
            with self.assertRaisesRegex(ValueError, 'Cannot check'):
                running_client(expected)
            run.return_value.stdout = json.dumps([{'pid': 10, 'path': None}])
            with patch('metin2_studio.addons.client_adapter._process_image', return_value=str(expected)):
                self.assertTrue(running_client(expected))
            with patch('metin2_studio.addons.client_adapter._process_image', return_value=str(self.base / 'other/metin2client.exe')):
                self.assertFalse(running_client(expected))
            with patch('metin2_studio.addons.client_adapter._process_image', side_effect=OSError('Access denied')):
                with self.assertRaisesRegex(ValueError, 'Cannot check'):
                    running_client(expected)

    def test_two_addons_and_settings_restore_exact_pair_and_survive_service_reopening(self):
        sandbox = Path(self.service.post('sandbox', {})['path'])
        self.apply('community.boss-atlas')
        self.apply('community.map-legend')
        self.apply('community.boss-atlas', 'configure', settings={'show_metins': True})
        self.service = AddonService(self.studio)
        self.assertEqual(len(self.service.state()['installed']), 2)
        self.assertEqual(self.service.state()['installation']['path'], str(sandbox))
        self.apply('community.boss-atlas', 'remove')
        self.assertEqual(len(self.service.state()['installed']), 1)
        self.apply('community.map-legend', 'remove')
        self.service.post('connect', {'path': str(self.client)})
        self.assertEqual(len(self.service.get('history', {})['history']), 5)
        for name, raw in self.original.items():
            self.assertEqual((sandbox / 'pack' / name).read_bytes(), raw)
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_new_client_version_can_review_and_apply_with_unverified_warning(self):
        (self.client / 'client.version').write_text('2.0.113', 'utf-8')
        sandbox = Path(self.service.post('sandbox', {})['path'])
        item = next(row for row in self.service.get('catalog', {})['catalog']['items'] if row['id'] == 'community.boss-atlas')
        self.assertEqual(item['compatibility_status'], 'unverified')
        self.assertEqual(item['errors'], [])
        self.assertNotEqual(item['status'], 'incompatible')
        plan = self.service.post('plan', {'addon_id': 'community.boss-atlas'})['plan']
        self.assertTrue(plan['can_apply'], plan['conflicts'])
        self.assertTrue(any('2.0.113' in warning and '2.0.112' in warning for warning in plan['warnings']))
        self.service.post('apply', {'plan_id': plan['id']})
        self.assertEqual(self.service.state()['installed'][0]['compatibility_status'], 'unverified')
        self.apply('community.boss-atlas', 'remove')
        for name, raw in self.original.items():
            self.assertEqual((sandbox / 'pack' / name).read_bytes(), raw)
            self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)

    def test_atlas_uses_selected_world_and_resolves_studio_drop_ids_without_pack_dependencies(self):
        with patch.object(codec, 'lzokay', None), patch.object(codec, 'np', None):
            self.assertFalse(self.service.state()['dependencies']['lzokay'])
            world_map = self.service.get('map', {'map': '64'})['map']
            self.assertEqual(world_map['regions'][0]['drop_target_id'], '691')
            self.assertEqual(world_map['regions'][0]['source'], 'linux-port/docker/game/share/locale/poland/map/map_n_threeway/boss.txt')
        self.assertEqual(len(self.service.get('catalog', {})['catalog']['items']), 5)

    def test_addon_mutation_is_blocked_during_server_deployment(self):
        self.studio.job['status'] = 'running'
        with self.assertRaisesRegex(ValueError, 'finish'):
            self.service.post('sandbox', {})

    def test_support_report_omits_paths_tokens_settings_and_repository_urls(self):
        sandbox = self.service.post('sandbox', {})['path']
        self.apply('community.boss-atlas')
        self.service.repositories.fetch = lambda url, limit: b'{"schema_version":1,"name":"Private publisher","publisher":"Personal name","packages":[]}'
        self.service.post('repositories/add', {'url': 'https://catalog.example.test/index.json?private=secret'})
        report = self.service.get('support-report', {})['report']
        text = json.dumps(report)
        self.assertEqual(report['installed'][0]['id'], 'community.boss-atlas')
        self.assertEqual(report['repositories']['count'], 1)
        for private in (str(self.base), sandbox, self.studio.token, 'settings', 'secret', 'Private publisher', 'Personal name', 'example.test'):
            self.assertNotIn(private, text)
        self.assertTrue(report['capabilities']['live_installation_writes'])

    def test_world_data_lock_prevents_a_second_writer(self):
        first = InstanceLock(self.studio.state / 'instance.lock').acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'already in use'):
                InstanceLock(self.studio.state / 'instance.lock').acquire()
        finally:
            first.close()

    def test_local_import_rejects_incomplete_upload_and_server_deployment(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.service.import_archive(io.BytesIO(b'x'), 2, 'addon.zip')
        for length in (0, -1, 66 * 1024 * 1024 + 1):
            with self.assertRaisesRegex(ValueError, '66 MiB'):
                self.service.import_archive(io.BytesIO(b''), length, 'addon.zip')
        self.studio.job['status'] = 'running'
        with self.assertRaisesRegex(ValueError, 'finish'):
            self.service.import_archive(io.BytesIO(b'x'), 1, 'addon.zip')
        self.assertFalse(self.service.repositories._state()['active'])

    def test_http_local_creator_import_install_update_and_exact_removal(self):
        archives = {}
        for version in ('1.0.0', '1.1.0'):
            creator = self.base / ('local-creator-' + version)
            scaffold('fixture.local', 'Local creator fixture', 'Fixture creator', creator, version=version)
            artifact = self.base / ('local-' + version + '.m2addon.zip')
            build_artifact(creator, artifact)
            archives[version] = artifact.read_bytes()
        old = getattr(Handler, 'studio', None)
        Handler.studio = self.studio
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:%s' % server.server_port
        def request(route, body=None, raw=None, headers=None):
            request_headers = {'Content-Type': 'application/zip' if raw is not None else 'application/json',
                               'X-Studio-Token': self.studio.token, 'Origin': base, **(headers or {})}
            req = urllib.request.Request(base + '/api/addons/' + route,
                data=raw if raw is not None else json.dumps(body).encode() if body is not None else None,
                headers=request_headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read())
        def upload(version):
            return request('packages/import', raw=archives[version], headers={'X-Addon-Filename': quote('Pacote-测试-' + version + '.m2addon.zip')})
        def apply(action, **extra):
            plan = request('plan', {'addon_id': 'fixture.local', 'action': action, **extra})['plan']
            self.assertTrue(plan['can_apply'], plan['conflicts'])
            request('apply', {'plan_id': plan['id']})
        try:
            for headers, expected in (({'X-Studio-Token': 'wrong'}, 'Session expired'),
                                      ({'Origin': 'https://foreign.invalid'}, 'Origin is not allowed'),
                                      ({'Content-Type': 'application/json'}, 'Upload an add-on ZIP'),
                                      ({'Content-Length': str(66 * 1024 * 1024 + 1)}, 'no larger than 66 MiB')):
                # These are header-only rejection checks. Sending a full body
                # after an early rejection can reset the TCP socket on Windows.
                with self.subTest(headers=headers), self.assertRaises(urllib.error.HTTPError) as error:
                    request('packages/import', raw=b'', headers=headers)
                self.assertEqual(error.exception.code, 400)
                self.assertIn(expected, json.loads(error.exception.read())['error'])
            self.assertFalse(self.service.repositories._state()['active'])
            imported = upload('1.0.0')
            self.assertEqual(imported['imported'], 'fixture.local')
            self.assertFalse(request('state')['state']['installed'])
            package = next(row for row in request('catalog')['catalog']['items'] if row['id'] == 'fixture.local')
            self.assertEqual(package['distribution']['kind'], 'local')
            self.assertIn('测试', package['distribution']['filename'])
            self.assertFalse(request('repositories')['repositories'])
            sandbox = Path(request('sandbox', {})['path'])
            plan = request('plan', {'addon_id': 'fixture.local'})['plan']
            upload('1.0.0')
            with self.assertRaises(urllib.error.HTTPError):
                request('apply', {'plan_id': plan['id']})
            self.assertEqual((sandbox / 'pack/root.index').read_bytes(), self.original['root.index'])
            apply('install')
            apply('configure', settings={'log_map_changes': False})
            upload('1.1.0')
            self.assertEqual(request('state')['state']['installed'][0]['version'], '1.0.0')
            apply('update')
            state = request('state')['state']
            self.assertEqual(state['installed'][0]['version'], '1.1.0')
            self.assertFalse(state['installed'][0]['settings']['log_map_changes'])
            self.studio._addons = AddonService(self.studio)
            self.assertEqual(request('state')['state']['installed'][0]['version'], '1.1.0')
            apply('disable')
            apply('enable')
            request('packages/forget', {'addon_id': 'fixture.local'})
            self.assertEqual(request('state')['state']['installed'][0]['version'], '1.1.0')
            self.assertFalse(any(row['id'] == 'fixture.local' for row in request('catalog')['catalog']['items']))
            apply('remove')
            self.assertFalse(request('state')['state']['installed'])
            for name, raw in self.original.items():
                self.assertEqual((sandbox / 'pack' / name).read_bytes(), raw)
                self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            Handler.studio = old

    def test_github_http_install_update_restart_and_exact_removal(self):
        from tests.github_fixture import GitHubFixture
        from tools.check_github_workflow import A, rehearse
        fixture = GitHubFixture(self.base / 'github-creator')
        fixture.add('1.0.0', A)
        result = rehearse(self.studio, fixture)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(result['steps']), 8)
        self.assertTrue(result['exact_pack_restoration'])

    def test_collection_http_independent_lifecycle_and_exact_removal(self):
        from tests.collection_fixture import CollectionFixture, FIRST, SECOND, specs
        from tools.check_collection_workflow import A, rehearse
        fixture = CollectionFixture(self.base / 'collection-creator')
        fixture.snapshot(A, specs())
        fixture.publish(FIRST, '1.0.0', A)
        fixture.publish(SECOND, '2.0.0', A)
        result = rehearse(self.studio, fixture)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(result['steps']), 8)
        self.assertTrue(result['exact_pack_restoration'])

    def test_fresh_upstream_baseline_preserves_game_fixes_and_previous_target(self):
        old_sandbox = Path(self.service.post('sandbox', {})['path'])
        self.apply('community.boss-atlas')
        old_pair = {name: (old_sandbox / 'pack' / name).read_bytes() for name in self.original}
        updated_studio, updated_client = make_world(self.base / 'upstream-copy')
        pack = codec.EterPack.open(updated_client / 'pack')
        files = pack.files()
        files['uiminimap.py'] += b'# Original synthetic upstream atlas fix\n'
        files['upstream_fix.py'] = b'FIXED = True\n'
        index, data = pack.build(files)
        (updated_client / 'pack/root.index').write_bytes(index)
        (updated_client / 'pack/root.data').write_bytes(data)
        updated_pair = {name: (updated_client / 'pack' / name).read_bytes() for name in self.original}
        service = updated_studio.addons
        sandbox = Path(service.post('sandbox', {})['path'])
        for ident, action in [('community.boss-atlas', 'install'), ('community.map-legend', 'install'),
                              ('community.boss-atlas', 'remove'), ('community.map-legend', 'remove')]:
            plan = service.post('plan', {'addon_id': ident, 'action': action})['plan']
            self.assertTrue(plan['can_apply'], plan['conflicts'])
            service.post('apply', {'plan_id': plan['id']})
            self.assertEqual(codec.EterPack.open(sandbox / 'pack').read('upstream_fix.py'), b'FIXED = True\n')
        for name in self.original:
            self.assertEqual((sandbox / 'pack' / name).read_bytes(), updated_pair[name])
            self.assertEqual((updated_client / 'pack' / name).read_bytes(), updated_pair[name])
            self.assertEqual((old_sandbox / 'pack' / name).read_bytes(), old_pair[name])
            self.assertEqual((self.client / 'pack' / name).read_bytes(), self.original[name])
        self.assertEqual(len(self.service.state()['installed']), 1)

    def test_repository_workflow_downloads_separately_and_invalidates_install_review(self):
        package_dir = self.base / 'remote-creator'
        scaffold('fixture.download', 'Downloaded fixture', 'Fixture creator', package_dir, version='1.0.0')
        artifact = self.base / 'download.zip'
        info = build_artifact(package_dir, artifact)
        url, asset = 'https://catalog.example.test/index.json', 'https://downloads.example.test/download.zip'
        index = {'schema_version': 1, 'name': 'Fixture catalog', 'publisher': 'Fixture creator', 'packages': [{
            'id': 'fixture.download', 'name': 'Downloaded fixture', 'description': 'Original test package', 'releases': [{
                'version': '1.0.0', 'url': asset, 'sha256': info['sha256'], 'bytes': info['bytes']}]}]}
        content = {url: json.dumps(index).encode(), asset: artifact.read_bytes()}
        self.service.repositories.fetch = lambda address, limit: content[address]
        self.service.post('repositories/add', {'url': url})
        repository_id = self.service.get('repositories', {})['repositories'][0]['id']
        review = self.service.post('releases/review', {'repository_id': repository_id, 'addon_id': 'fixture.download', 'version': '1.0.0'})['review']
        self.service.post('releases/download', {'review_id': review['id']})
        self.assertEqual(self.service.state()['installed'], [])
        sandbox = Path(self.service.post('sandbox', {})['path'])
        before = {name: (sandbox / 'pack' / name).read_bytes() for name in ('root.index', 'root.data')}
        plan = self.service.post('plan', {'addon_id': 'fixture.download'})['plan']
        self.service.post('repositories/configure', {'repository_id': repository_id, 'enabled': False})
        with self.assertRaisesRegex(ValueError, 'review expired'):
            self.service.post('apply', {'plan_id': plan['id']})
        for name, raw in before.items():
            self.assertEqual((sandbox / 'pack' / name).read_bytes(), raw)
        self.service.post('repositories/configure', {'repository_id': repository_id, 'enabled': True})
        plan = self.service.post('plan', {'addon_id': 'fixture.download'})['plan']
        self.service.post('apply', {'plan_id': plan['id']})
        self.assertEqual(len(self.service.state()['installed']), 1)
        self.service.post('repositories/remove', {'repository_id': repository_id})
        plan = self.service.post('plan', {'addon_id': 'fixture.download', 'action': 'remove'})['plan']
        self.service.post('apply', {'plan_id': plan['id']})
        for name, raw in before.items():
            self.assertEqual((sandbox / 'pack' / name).read_bytes(), raw)

    def test_one_origin_api_accepts_only_studio_token_and_preserves_server_routes(self):
        old = getattr(Handler, 'studio', None)
        Handler.studio = self.studio
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:%s' % server.server_port
        def request(path, body=None, headers=None):
            request_headers = {'Content-Type': 'application/json', **(headers or {})}
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=request_headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read())
        try:
            for script in ('addons.mjs', 'addon_helpers.mjs', 'addon_jobs.mjs'):
                with urllib.request.urlopen(base + '/' + script, timeout=10) as response:
                    self.assertIn('javascript', response.headers['Content-Type'])
                    self.assertTrue(response.read())
                self.assertEqual(request('/api/addons/catalog')['catalog']['count'], 5)
            with self.assertRaises(urllib.error.HTTPError):
                request('/api/addons/sandbox', {}, {'X-Hub-Token': self.studio.token})
            result = request('/api/addons/sandbox', {}, {'X-Studio-Token': self.studio.token})
            self.assertTrue(result['state']['installation']['writable'])
            self.assertEqual(request('/api/activity')['items'][0]['title'], 'Server fixture saved')
            with self.assertRaises(urllib.error.HTTPError):
                request('/api/addons/state', headers={'Origin': 'https://untrusted.invalid'})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            Handler.studio = old

    def test_http_repository_install_update_withdrawal_and_exact_uninstall(self):
        url = 'https://catalog.example.test/index.json'
        content, releases = {}, []
        for version in ('1.0.0', '1.1.0'):
            creator = self.base / ('creator-' + version)
            scaffold('fixture.http', 'HTTP fixture', 'Fixture creator', creator, version=version)
            artifact = self.base / ('http-' + version + '.zip')
            info = build_artifact(creator, artifact)
            asset = 'https://downloads.example.test/' + artifact.name
            content[asset] = artifact.read_bytes()
            releases.append({'version': version, 'url': asset, 'sha256': info['sha256'], 'bytes': info['bytes']})
        index = {'schema_version': 1, 'name': 'HTTP fixture catalog', 'publisher': 'Fixture creator', 'packages': [{
            'id': 'fixture.http', 'name': 'HTTP fixture', 'description': 'Original end-to-end test package',
            'releases': [releases[0]]}]}
        content[url] = json.dumps(index).encode()
        self.service.repositories.fetch = lambda address, limit: content[address]
        old = getattr(Handler, 'studio', None)
        Handler.studio = self.studio
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:%s' % server.server_port
        def request(route, body=None):
            req = urllib.request.Request(base + '/api/' + route,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type': 'application/json', 'X-Studio-Token': self.studio.token, 'Origin': base})
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read())
        def apply(action, **extra):
            plan = request('addons/plan', {'addon_id': 'fixture.http', 'action': action, **extra})['plan']
            self.assertTrue(plan['can_apply'], plan['conflicts'])
            request('addons/apply', {'plan_id': plan['id']})
        def download(version):
            review = request('addons/releases/review', {'repository_id': repo, 'addon_id': 'fixture.http', 'version': version})['review']
            request('addons/releases/download', {'review_id': review['id']})
        try:
            activity = request('activity')
            repo = request('addons/repositories/add', {'url': url})['repositories'][0]['id']
            download('1.0.0')
            self.assertFalse(request('addons/state')['state']['installed'])
            sandbox = Path(request('addons/sandbox', {})['path'])
            apply('install')
            apply('configure', settings={'log_map_changes': False})
            index['packages'][0]['releases'].append(releases[1])
            content[url] = json.dumps(index).encode()
            request('addons/repositories/refresh', {'repository_id': repo})
            self.assertTrue(request('addons/releases')['releases'][0]['update_available'])
            download('1.1.0')
            self.assertEqual(request('addons/state')['state']['installed'][0]['version'], '1.0.0')
            apply('update')
            installed = request('addons/state')['state']['installed'][0]
            self.assertEqual(installed['version'], '1.1.0')
            self.assertFalse(installed['settings']['log_map_changes'])
            index['packages'][0]['releases'][1].update(withdrawn=True, reason='Fixture withdrawal')
            content[url] = json.dumps(index).encode()
            request('addons/repositories/refresh', {'repository_id': repo})
            with self.assertRaises(urllib.error.HTTPError) as error:
                request('addons/plan', {'addon_id': 'fixture.http', 'action': 'enable'})
            self.assertEqual(error.exception.code, 400)
            self.assertIn('withdrawn', error.exception.read().decode())
            request('addons/repositories/remove', {'repository_id': repo})
            apply('remove')
            self.assertFalse(request('addons/state')['state']['installed'])
            self.assertEqual([row for row in request('activity')['items'] if row['kind'] == 'server'], activity['items'])
            for name, raw in self.original.items():
                self.assertEqual((sandbox / 'pack' / name).read_bytes(), raw)
                self.assertEqual((self.client / 'pack' / name).read_bytes(), raw)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            Handler.studio = old
