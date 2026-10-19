import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

import tests.test_studio as test_studio
from metin2_studio.server import ACTIVE_CHANGESET
from metin2_studio.crafting_access import native_calls, discover_native
from metin2_studio.native_crafting import EMPTY, COLS, NativeCrafting, snapshot, operations, transition, fingerprint, transaction_sql


def row(ident=1, chance=80, windows=None):
    return {'proto': dict(zip(COLS, [ident, 25044, 1, 400000, chance, '25040,1,70035,1', 0, 0, 0, None])),
            'windows': windows if windows is not None else {'101': 1}}


def config(before, after, ident='1'):
    return {'version': 1, 'recipes': {ident: {'before': copy.deepcopy(before), 'after': copy.deepcopy(after)}}, 'accepted': {}}


class MergeTests(unittest.TestCase):
    def test_native_routes_resolve_constants_multiple_npcs_and_ignore_comments(self):
        text = '-- crafting.open(999)\nsay("crafting.open(888)")\ncrafting . open ( CRAFTING_BAEKGO )\ncrafting.open(npc.get_vnum())'
        self.assertEqual(list(native_calls(text, {'CRAFTING_BAEKGO': '102'}, '20018')), ['102', '20018'])

    def test_only_customised_fields_conflict(self):
        before, after = row(), row(chance=100)
        wanted = config(before, after)
        live = row()
        live['proto']['price'] = 900000
        target, conflicts = transition(EMPTY, wanted, {'1': live})
        self.assertEqual(conflicts, [])
        self.assertEqual(target['1']['proto']['price'], 900000)
        self.assertEqual(target['1']['proto']['chance'], 100)
        live['proto']['chance'] = 90
        _, conflicts = transition(EMPTY, wanted, {'1': live})
        self.assertEqual([c['field'] for c in conflicts], ['proto.chance'])

    def test_reapply_and_undo_preserve_unrelated_server_fields(self):
        before, after = row(), row(chance=100)
        previous = config(before, after)
        live = copy.deepcopy(after)
        live['proto']['comment'] = 'New package comment'
        targets, conflicts = transition(previous, previous, {'1': live})
        self.assertEqual((targets, conflicts), ({}, []))
        targets, conflicts = transition(previous, EMPTY, {'1': live})
        self.assertFalse(conflicts)
        self.assertEqual(targets['1']['proto']['chance'], 80)
        self.assertEqual(targets['1']['proto']['comment'], 'New package comment')

    def test_updates_after_apply_require_review_only_for_our_columns(self):
        previous = config(row(), row(chance=100))
        live = row(chance=90)
        _, conflicts = transition(previous, previous, {'1': live})
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['server'], 90)
        self.assertEqual(conflicts[0]['studio'], 100)

    def test_new_recipe_rollback_protects_new_external_references(self):
        before = {'proto': None, 'windows': {}}
        after = row(100000)
        previous = config(before, after, '100000')
        target, conflicts = transition(previous, EMPTY, {'100000': after})
        self.assertFalse(conflicts)
        self.assertEqual(target['100000'], before)
        external = copy.deepcopy(after)
        external['windows']['103'] = 99
        _, conflicts = transition(previous, EMPTY, {'100000': external})
        self.assertTrue(any(c.get('reason') for c in conflicts))

    def test_sql_guards_entire_observed_rows_but_updates_only_selected_columns(self):
        before, after = row(), row(chance=100)
        sql = transaction_sql({'1': before}, {'1': after})
        self.assertIn('START TRANSACTION', sql)
        self.assertIn('FOR UPDATE', sql)
        self.assertIn('CHECK(ok=1)', sql)
        self.assertIn('UPDATE world.crafting_proto SET `chance`=100 WHERE vnum=1;', sql)
        self.assertNotIn('DELETE FROM world.crafting_window', sql)
        self.assertLess(sql.index('studio_crafting_guard VALUES (IF(EXISTS'), sql.index('UPDATE world.crafting_proto'))
        self.assertIn('COMMIT;', sql)


class NativeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_studio.StudioTests.setUpClass.__func__(cls)
        for npc, window in [('20016', '101'), ('11001', '106'), ('11003', '106'), ('11005', '106')]:
            opener = cls.s.locale / f'quest/object/{npc}/chat/native_fixture.start.0.script'
            opener.parent.mkdir(parents=True, exist_ok=True)
            opener.write_text(f'crafting.open({window})', 'ascii')
        cls.initial = {p: p.read_bytes() for p in cls.root.rglob('*') if p.is_file()}

    @classmethod
    def tearDownClass(cls):
        test_studio.StudioTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_studio.StudioTests.setUp(self)
        self.context = ACTIVE_CHANGESET.set(None)
        self.s.native_crafting.path.unlink(missing_ok=True)
        self.s.workspace.set_preference('nativeCraftingApplied', copy.deepcopy(EMPTY))
        self.s.workspace.set_preference('nativeUpdatePending', {})
        self.live = {'rows': {'1': row(), '2': row(2, windows={'101': 2, '106': 2})}, 'names': {'101': 'Blacksmith', '106': 'Arrows'}}
        self.mock = patch.object(self.s.native_crafting, 'live', side_effect=lambda fresh=False: copy.deepcopy(self.live))
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        ACTIVE_CHANGESET.reset(self.context)

    def recipe(self, ident=1, window='101'):
        return next(r for r in self.s.native_crafting.catalog()['recipes'] if r['index'] == ident and r['window'] == window)

    def test_catalog_lists_shared_npcs_and_excludes_general_store(self):
        access = discover_native(self.s)
        self.assertEqual({r['id'] for r in access}, {'20016', '11001', '11003', '11005'})
        recipe = self.recipe(2, '106')
        self.assertEqual(recipe['npcIds'], ['11001', '11003', '11005'])
        self.assertIn('Blacksmith', recipe['sharedWith'])

    def test_item_explorer_uses_current_native_recipes_and_saved_overrides(self):
        from metin2_studio.item_usage import item_usage
        from metin2_studio.server import sql_rows
        recipe = self.recipe()
        recipe['rewards'][0]['item'] = '71084'
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        usage = item_usage(self.s, '71084', sql_rows, native=True)
        rows = [r for r in usage['sections']['crafted'] if r.get('nativeCraft')]
        self.assertEqual(len(rows), 1)
        self.assertIn('Native crafting #1', rows[0]['summary'])
        self.assertFalse(rows[0].get('seed'))

    def test_save_is_file_only_and_rollback_removes_configuration(self):
        recipe = self.recipe()
        recipe['fields']['percent'] = '100'
        with patch.object(self.s.native_crafting, 'execute') as execute:
            plan = self.s.recipe_plan(recipe)
            saved = self.s.commit(plan['id'])
            execute.assert_not_called()
        self.assertEqual(self.live['rows']['1']['proto']['chance'], 80)
        self.assertEqual(self.recipe()['fields']['percent'], '100')
        self.assertTrue(self.s.workspace.summary()['pending'])
        self.s.commit(self.s.restore_plan(saved['id'])['id'])
        self.assertFalse(self.s.native_crafting.path.exists())
        self.assertEqual(self.recipe()['fields']['percent'], '80')

    def test_move_recipe_preserves_other_shared_windows(self):
        recipe = self.recipe(2)
        recipe['originalWindow'] = '101'
        recipe['window'] = '106'
        recipe['fields']['npc'] = '11001'
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        after = self.s.native_crafting.config()['recipes']['2']['after']
        self.assertEqual(after['windows'], {'106': 2})

    def test_edit_does_not_adopt_unrelated_package_changes_as_custom_fields(self):
        recipe = self.recipe()
        recipe['fields']['percent'] = '100'
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        self.live['rows']['1']['proto']['price'] = 999999
        recipe = self.recipe()
        recipe['fields']['percent'] = '95'
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        record = self.s.native_crafting.config()['recipes']['1']
        self.assertEqual(set(operations(record)), {'proto.chance'})
        self.assertEqual(record['after']['proto']['price'], 999999)

    def test_create_and_remove_from_one_window_only(self):
        recipe = self.recipe(2)
        self.s.commit(self.s.recipe_delete_plan(recipe)['id'])
        self.assertEqual(self.s.native_crafting.config()['recipes']['2']['after']['windows'], {'106': 2})
        new = self.recipe(1)
        new.update(new=True, index=-1)
        self.s.commit(self.s.recipe_plan(new)['id'])
        new_row = self.s.native_crafting.config()['recipes']['100000']
        self.assertIsNone(new_row['before']['proto'])
        self.assertEqual(new_row['after']['windows'], {'101': 2})

    def test_native_validation_rejects_unsafe_engine_values_and_stale_sources(self):
        for change in ('duplicate', 'reward', 'level', 'quantity', 'npc', 'hash'):
            recipe = self.recipe()
            if change == 'duplicate': recipe['materials'].append(copy.deepcopy(recipe['materials'][0]))
            if change == 'reward': recipe['rewards'].append(copy.deepcopy(recipe['rewards'][0]))
            if change == 'level': recipe['requirements']['req_level'] = 300
            if change == 'quantity': recipe['materials'][0]['count'] = '1,0'
            if change == 'npc': recipe['fields']['npc'] = '9003'
            if change == 'hash': recipe['hash'] = 'old'
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.s.recipe_plan(recipe)

    def test_create_then_remove_before_apply_leaves_nothing_pending(self):
        recipe = self.recipe()
        recipe.update(new=True, index=-1)
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        created = self.recipe(100000)
        self.s.commit(self.s.recipe_delete_plan(created)['id'])
        self.assertFalse(self.s.native_crafting.path.exists())
        self.assertFalse(self.s.native_crafting.pending())
        self.assertFalse(self.s.workspace.summary()['pending'])

    def test_apply_guards_conflicts_and_records_database_state_after_verification(self):
        recipe = self.recipe()
        recipe['fields']['percent'] = '100'
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        def execute(sql):
            self.assertIn('`chance`=100', sql)
            self.live['rows']['1']['proto']['chance'] = 100
        with patch.object(self.s.native_crafting, 'execute', side_effect=execute):
            self.assertEqual(self.s.native_crafting.apply(), 1)
        self.assertFalse(self.s.native_crafting.pending())
        self.live['rows']['1']['proto']['chance'] = 90
        with patch.object(self.s.native_crafting, 'execute') as execute, self.assertRaisesRegex(ValueError, 'review'):
            self.s.native_crafting.apply()
        execute.assert_not_called()

    def test_resolve_keep_studio_or_accept_server_then_undo_safely(self):
        for choice in ('studio', 'server'):
            with self.subTest(choice=choice):
                self.s.native_crafting.path.unlink(missing_ok=True)
                with self.s.workspace.connect() as conn:
                    conn.execute('DELETE FROM tracked')
                self.s.workspace.set_preference('nativeCraftingApplied', copy.deepcopy(EMPTY))
                self.live['rows']['1'] = row()
                recipe = self.recipe()
                recipe['fields']['percent'] = '100'
                self.s.commit(self.s.recipe_plan(recipe)['id'])
                self.s.workspace.set_preference('nativeCraftingApplied', self.s.native_crafting.config())
                self.live['rows']['1']['proto']['chance'] = 90
                report = self.s.native_crafting.review()
                plan = self.s.native_crafting.resolve({'signature': report['signature'], 'choices': {'1:proto.chance': choice}})
                self.s.commit(plan['id'])
                _, _, desired, conflicts = self.s.native_crafting.view(True)
                self.assertFalse(conflicts)
                self.assertEqual(desired['1']['proto']['chance'], 100 if choice == 'studio' else 90)
                self.s.workspace.set_preference('nativeCraftingApplied', self.s.native_crafting.config())
                self.live['rows']['1'] = desired['1']
                _, later = transition(self.s.native_crafting.applied(), self.s.native_crafting.config(), self.live['rows'])
                self.assertFalse(later)

    def test_no_saved_changes_cannot_restart_and_drafts_do_not_count(self):
        with self.assertRaisesRegex(ValueError, 'no saved changes'):
            self.s.apply()
        ident = self.s.workspace.create_set({'name': 'Draft crafts'})['id']
        context = ACTIVE_CHANGESET.set(ident)
        try:
            recipe = self.recipe()
            recipe['fields']['percent'] = '100'
            self.s.commit(self.s.recipe_plan(recipe)['id'])
            with self.assertRaisesRegex(ValueError, 'no saved changes'):
                self.s.apply()
        finally:
            ACTIVE_CHANGESET.reset(context)
        self.assertFalse(self.s.native_crafting.path.exists())
        self.assertFalse(self.s.workspace.summary()['pending'])

    def test_native_apply_runs_after_migration_before_restart_and_failure_leaves_game_stopped(self):
        recipe = self.recipe()
        recipe['fields']['percent'] = '100'
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        commands = []
        def process(cmd, **kwargs):
            commands.append(cmd)
            run = Mock(stdout=iter([]))
            run.wait.return_value = 0
            return run
        def rejected():
            commands.append(['native-transaction'])
            raise ValueError('A customised recipe changed externally.')
        migration = Mock(returncode=0, stdout='{"ExitCode":0,"State":"exited"}')
        self.s.job = {'status':'running','lines':[],'files':self.s.build_fingerprints(),'id':'native-order-test'}
        with patch('metin2_studio.server.subprocess.Popen',side_effect=process), patch('metin2_studio.server.subprocess.run',return_value=migration), patch.object(self.s.native_crafting,'apply',side_effect=rejected):
            self.s.run_apply()
        self.assertEqual(self.s.job['status'],'failed')
        self.assertEqual(commands[-1],['native-transaction'])
        self.assertEqual(commands[-2],['docker','compose','wait','playerbot-migrate'])
        self.assertNotIn(['docker','compose','up','-d','--no-deps','--force-recreate','game'],commands)

    def test_invalid_native_configuration_does_not_leave_background_apply_running(self):
        self.s.job = {'status':'running','lines':[],'files':self.s.build_fingerprints(),'id':'bad-config-test'}
        with patch.object(self.s.native_crafting,'config',side_effect=ValueError('Configuration changed externally.')), patch('metin2_studio.server.subprocess.Popen') as run:
            self.s.run_apply()
        self.assertEqual(self.s.job['status'],'failed')
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
