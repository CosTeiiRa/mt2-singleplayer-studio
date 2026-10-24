"""Activation plans use synthetic installations and never build or run the game."""
import base64
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from metin2_studio.addons import mounts_activation as mounts
from metin2_studio import quest_support


class MountActivationTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / '.test-tmp'
        temporary_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        game = root / 'linux-port/docker/game'
        game.mkdir(parents=True)
        self.studio = SimpleNamespace(root=root, game=game, mount_item_definitions={
            '52001': {'type': 18, 'limittype0': 6, 'limitvalue0': 3600},
            '52006': {'type': 18, 'limittype0': 6, 'limitvalue0': 3600},
        })
        self.put('bin/game', b'synthetic independently verified engine')
        self.base_docker = (b'FROM fixture AS quests\n'
                            b'RUN mkdir -p /tmp/qc-work /out-quest/poland/quest\n'
                            b'FROM fixture AS runtime\n'
                            b'COPY --from=quests /out-quest/ /opt/metin2/share/locale/\n')
        self.put('Dockerfile', self.base_docker)
        self.put('.dockerignore', b'*\n')
        self.capabilities = {'engine_sha256': mounts.sha(b'synthetic independently verified engine'),
                             'point_api': 'pc.get_point', 'point_api_arity': 1,
                             'mount_point': 109, 'mount_bonus_affect': 533,
                             'inventory_slots': 225, 'native_item_ids': list(mounts.NATIVE_ITEM_IDS)}
        rows = [row for row in mounts.mappings() if row['vnum'] in (52001, 52006)]
        self.package = {mounts.TEMPLATE_KEY: (mounts.PAYLOAD / mounts.TEMPLATE_KEY).read_bytes(),
                        mounts.MAPPING_KEY: json.dumps({'schema_version': 1, 'quest_identity': mounts.IDENTITY, 'rows': rows}).encode()}
        self.assets = {row['model']: True for row in rows}

    def put(self, name, raw):
        path = self.studio.game / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def plan(self, action='install', **kw):
        return mounts.plan_activation(self.studio, self.package, action,
                                      asset_availability=kw.pop('asset_availability', self.assets),
                                      capabilities=kw.pop('capabilities', self.capabilities), **kw)

    def save(self, result):
        self.assertEqual(result['conflicts'], [])
        for path, raw in result['changes'].items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def source(self, result):
        return result['changes'].get(self.studio.game / mounts.SOURCE,
                                     (self.studio.game / mounts.SOURCE).read_bytes() if (self.studio.game / mounts.SOURCE).exists() else b'')

    def test_install_is_read_only_and_registers_exact_identity(self):
        result = self.plan()
        self.assertEqual(result['status'], 'ready', result['conflicts'])
        self.assertFalse((self.studio.game / mounts.SOURCE).exists())
        self.assertTrue(result['requires_build'])
        source = self.source(result)
        self.assertIn(b'quest mounts_legacy begin', source)
        self.assertIn(b'pc.get_point(109)', source)
        self.assertNotIn(b'pc.get_point(pc.get_player_id()', source)
        self.assertIn(b'52001.use or 52006.use', source)
        self.assertIn(b'quest/mounts_legacy.quest', result['changes'][self.studio.game / 'custom-quests/studio-source-list.txt'])
        hook = result['changes'][self.studio.game / 'Dockerfile']
        self.assertEqual(hook.count(b'grep -qx'), 1)
        self.assertIn(b'if [ "$quest_name" = "mounts_legacy" ]; then', hook)
        self.assertNotIn(b'pc.get_point', self.base_docker)

    def test_two_argument_profile_keeps_historical_call(self):
        self.capabilities['point_api_arity'] = 2
        result = self.plan()
        self.assertEqual(result['conflicts'], [])
        self.assertIn(b'pc.get_point(pc.get_player_id(), 109)', self.source(result))

    def test_exact_engine_fingerprint_is_required(self):
        result = self.plan(capabilities=None)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('no verified', ' '.join(result['conflicts']))
        self.assertEqual(result['changes'], {})
        self.capabilities['engine_sha256'] = '0' * 64
        self.assertIn('engine changed', ' '.join(self.plan()['conflicts']))

    def test_profile_with_unknown_point_arity_is_refused(self):
        self.capabilities['point_api_arity'] = 3
        self.assertEqual(self.plan()['status'], 'blocked')

    def test_current_assets_override_historical_asset_flag(self):
        model = mounts.mappings(self.package)[0]['model']
        self.assets[model] = False
        result = self.plan()
        self.assertEqual(result['conflicts'], [])
        self.assertGreater(result['component']['refused_missing_assets'], 0)
        source = self.source(result)
        self.assertIn(b'if info[8] == 0 then', source)
        self.assertLess(source.index(b'if info[8] == 0 then'), source.index(b'pc.mount(info[1], left)'))
        self.assertLess(source.index(b'if info[8] == 0 then'), source.index(b'pc.remove_item(vnum, 1)'))
        self.assertIn(b'if info[7] == 1 then until_time = item.get_socket(0) end', source)
        self.assertNotIn(b'item.set_socket', source)

    def test_no_assets_scan_is_not_assumed_available(self):
        result = self.plan(asset_availability=None)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('Verify the current client', ' '.join(result['conflicts']))

    def test_owned_seal_tracking_uses_exact_id_and_vnum(self):
        source = self.source(self.plan())
        self.assertIn(b'item.get_id() == id and item.get_vnum() == vnum', source)
        self.assertIn(b'get_time() >= pc.getqf("active_until")', source)
        self.assertIn(b'if mounts_legacy.mount_vnum() ~= info[1] then return end', source)
        self.assertNotIn(b'horse.set_level', source)
        self.assertNotIn(b'mysql', source)

    def test_known_manual_source_is_adopted_and_retained_in_ownership(self):
        original = b'quest mounts_legacy begin\n state start begin end\nend\n'
        self.put(mounts.SOURCE, original)
        with patch.object(mounts, 'HISTORICAL_SOURCE_SHA256', mounts.sha(original)):
            result = self.plan()
        self.assertEqual(result['status'], 'adopted', result['conflicts'])
        self.assertTrue(result['ownership']['adopted'])
        self.assertEqual(base64.b64decode(result['ownership']['baseline_source_base64']), original)
        self.assertEqual(result['ownership']['baseline_source_sha256'], mounts.sha(original))

    def test_unknown_manual_source_is_never_overwritten(self):
        original = b'quest mounts_legacy begin\n-- my custom changes\nend\n'
        self.put(mounts.SOURCE, original)
        result = self.plan()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['changes'], {})
        self.assertEqual((self.studio.game / mounts.SOURCE).read_bytes(), original)

    def test_reapply_is_idempotent_and_repairs_removed_hook(self):
        initial = self.plan()
        self.save(initial)
        again = self.plan('reapply', owned=initial['ownership'])
        self.assertEqual(again['status'], 'already-integrated', again['conflicts'])
        self.assertEqual(again['changes'], {})
        self.put('Dockerfile', self.base_docker + b'# newer game content\n')
        repaired = self.plan('reapply', owned=initial['ownership'])
        self.assertEqual(repaired['conflicts'], [])
        self.assertIn(b'# newer game content', repaired['changes'][self.studio.game / 'Dockerfile'])
        self.assertIn(b'# SERVER-STUDIO CUSTOM QUESTS', repaired['changes'][self.studio.game / 'Dockerfile'])

    def test_later_owned_source_changes_block_reapply_and_removal(self):
        initial = self.plan()
        self.save(initial)
        path = self.studio.game / mounts.SOURCE
        path.write_bytes(path.read_bytes() + b'-- later unrelated change\n')
        for action in ('reapply', 'remove'):
            result = self.plan(action, owned=initial['ownership'])
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(result['changes'], {})

    def test_existing_native_seal_is_not_intercepted(self):
        self.capabilities['native_item_ids'].append(52006)
        result = self.plan()
        self.assertEqual(result['conflicts'], [])
        self.assertNotIn(b'52006.use', self.source(result))
        self.assertNotIn(b'[52006]', self.source(result))
        self.assertIn(52006, result['component']['native_seals_untouched'])

    def test_registered_upstream_handlers_are_not_duplicated(self):
        self.put('quest/upstream.quest', b'quest upstream begin state start begin when 52001.use or 52006.use begin end end end')
        self.put('custom-quests/studio-source-list.txt', b'quest/upstream.quest\n')
        result = self.plan()
        self.assertEqual(result['status'], 'already-provided', result['conflicts'])
        self.assertEqual(result['component']['provided_by_game'], [52001, 52006])
        self.assertEqual(result['changes'], {})

    def test_explicit_stock_compile_sources_count_but_unused_sources_do_not(self):
        self.put('quest/stock.quest', b'quest stock begin state start begin when 52001.use begin end end end')
        self.put('quest/_unused/unused.quest', b'quest unused begin state start begin when 52006.use begin end end end')
        self.put('Dockerfile', self.base_docker.replace(b'FROM fixture AS runtime', b'RUN for q in stock; do true; done\nFROM fixture AS runtime'))
        result = self.plan()
        self.assertEqual(result['component']['provided_by_game'], [52001])
        self.assertNotIn(b'52001.use', self.source(result))
        self.assertIn(b'52006.use', self.source(result))

    def test_new_compiled_handler_changes_review_context(self):
        before = self.plan()
        self.put('share/locale/poland/quest/object/52001/use/upstream.start', b'handler bytes')
        after = self.plan()
        self.assertNotEqual(before['context_sha256'], after['context_sha256'])
        self.assertEqual(after['component']['provided_by_game'], [52001])
        self.assertNotIn(b'52001.use', self.source(after))

    def test_own_source_registration_does_not_change_foreign_context(self):
        initial = self.plan()
        self.save(initial)
        self.put('share/locale/poland/quest/object/52001/use/mounts_legacy.start', b'own compiled bytes')
        after = self.plan(owned=initial['ownership'])
        self.assertEqual(initial['context_sha256'], after['context_sha256'])

    def test_competing_old_boar_handler_blocks_new_interception(self):
        self.put('share/locale/poland/quest/object/52006/use/boar_mount_52006.start', b'old')
        result = self.plan()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('boar-only', ' '.join(result['conflicts']))
        self.assertEqual(result['changes'], {})

    def test_unidentified_compiled_manual_installation_is_preserved(self):
        self.put('share/locale/poland/quest/object/52006/use/mounts_legacy.start', b'unknown manual compiled code')
        result = self.plan()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('without a known managed/manual source', ' '.join(result['conflicts']))
        self.assertEqual(result['changes'], {})

    def test_duplicate_quest_identity_from_another_source_blocks(self):
        self.put('quest/other.quest', b'quest mounts_legacy begin state start begin end end')
        self.put('custom-quests/studio-source-list.txt', b'quest/other.quest\n')
        self.assertIn('Another registered source', ' '.join(self.plan()['conflicts']))

    def test_other_registered_sources_are_preserved(self):
        self.put('quest/other.quest', b'quest other begin state start begin end end')
        self.put('custom-quests/studio-source-list.txt', b'quest/other.quest\n')
        result = self.plan()
        self.assertEqual(result['conflicts'], [])
        self.assertIn(b'quest/other.quest', result['changes'][self.studio.game / 'custom-quests/studio-source-list.txt'])
        self.assertIn(b'/studio-edited/other.quest', result['changes'][self.studio.game / 'Dockerfile'])

    def test_another_quest_editor_keeps_scoped_mount_compiler_api(self):
        initial = self.plan()
        self.save(initial)
        other = self.put('quest/other.quest', b'quest other begin state start begin end end')
        self.studio.read = lambda path: path.read_bytes() if path.is_file() else None
        self.studio.locale = self.studio.game / 'share/locale/poland'
        changed = quest_support.source_changes(self.studio, other, other.read_bytes() + b'\n-- changed\n')
        hook = changed[self.studio.game / 'Dockerfile']
        allow = hook.index(b'grep -qx')
        compile_quest = hook.index(b'/usr/local/bin/qc "$name"')
        restore = hook.index(b'mv quest_functions.studio-mount-before quest_functions')
        self.assertLess(allow, compile_quest)
        self.assertLess(compile_quest, restore)
        self.assertEqual(hook.count(b'grep -qx'), 1)
        self.assertIn(b'/studio-edited/other.quest', hook)

    def test_current_catalogue_refresh_changes_definition_review_context(self):
        definitions = self.studio.mount_item_definitions
        self.studio.mount_item_definitions = None
        self.studio.catalogue = SimpleNamespace(export=lambda: {'definitions': definitions}, status={})
        calls = []
        self.studio.refresh_catalog = lambda **kw: calls.append(kw)
        first = self.plan()
        definitions['52001']['limitvalue1'] = 80
        definitions['52001']['limittype1'] = 1
        second = self.plan()
        self.assertEqual(calls, [{'force': True}, {'force': True}])
        self.assertNotEqual(first['context_sha256'], second['context_sha256'])
        self.assertIn(b', 80,', self.source(second))

    def test_stale_catalogue_after_update_blocks_activation(self):
        self.studio.mount_item_definitions = None
        self.studio.catalogue = SimpleNamespace(export=lambda: {'definitions': {}},
                                                status={'cacheFromOlderVersion': True})
        self.assertIn('could not be refreshed', ' '.join(self.plan()['conflicts']))

    def test_removed_realtime_limit_is_not_replaced_with_new_lifetime(self):
        self.studio.mount_item_definitions['52001']['limittype0'] = 0
        result = self.plan()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('absolute-expiry', ' '.join(result['conflicts']))

    def test_changed_item_type_blocks_unknown_native_coverage(self):
        self.studio.mount_item_definitions['52001']['type'] = 16
        self.assertIn('changed item type', ' '.join(self.plan()['conflicts']))

    def test_remove_keeps_cleanup_for_offline_owned_riders(self):
        initial = self.plan()
        self.save(initial)
        self.studio.mount_item_definitions = None
        result = self.plan('remove', owned=initial['ownership'])
        self.assertEqual(result['status'], 'cleanup-only', result['conflicts'])
        source = self.source(result)
        self.assertIn(b'when login or logout or legacy_mount_watch.timer', source)
        self.assertIn(b'if mounted == model then pc.unmount()', source)
        self.assertIn(b'pc.getqf("active_model")', source)
        self.assertNotIn(b'.use', source)
        self.assertNotIn(b'pc.mount(', source)
        self.assertEqual(result['ownership']['baseline_source_base64'], initial['ownership']['baseline_source_base64'])
        self.assertIn(b'quest/mounts_legacy.quest', (self.studio.game / 'custom-quests/studio-source-list.txt').read_bytes())

    def test_absent_uninstalled_addon_removal_has_no_changes(self):
        result = self.plan('remove')
        self.assertEqual(result['status'], 'not-installed', result['conflicts'])
        self.assertEqual(result['changes'], {})

    def test_mapping_rejects_duplicate_or_executable_apply_value(self):
        obj = json.loads(self.package[mounts.MAPPING_KEY])
        obj['rows'][1]['vnum'] = obj['rows'][0]['vnum']
        self.package[mounts.MAPPING_KEY] = json.dumps(obj).encode()
        self.assertIn('unique', ' '.join(self.plan()['conflicts']))
        obj['rows'] = obj['rows'][:1]
        obj['rows'][0]['apply'] = 'MAX_HP); os.execute()'
        self.package[mounts.MAPPING_KEY] = json.dumps(obj).encode()
        self.assertIn('Invalid mount bonus', ' '.join(self.plan()['conflicts']))


if __name__ == '__main__':
    unittest.main()
