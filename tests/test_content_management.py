import copy
from pathlib import Path
import sys
import unittest

import tests.test_studio as test_studio
from metin2_studio.crafting_access import opens_cube, npc_routes
from metin2_studio.quest_templates import library
from metin2_studio.server import ACTIVE_CHANGESET, digest


class ManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_studio.StudioTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_studio.StudioTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_studio.StudioTests.setUp(self)
        self.context = ACTIVE_CHANGESET.set(None)

    def tearDown(self):
        ACTIVE_CHANGESET.reset(self.context)

    def test_access_distinguishes_cube_from_other_crafting_and_comments(self):
        self.assertFalse(opens_cube('-- command("cube open")\ncrafting.open(CRAFTING_BAEKGO)'))
        self.assertFalse(opens_cube('say("command cube open")'))
        self.assertTrue(opens_cube('command ( "cube open" )'))
        self.assertEqual(list(npc_routes(b'quest route begin state start begin when 20091.chat."Craft" begin command("cube open") end end end')), ['20091'])
        ids = {row['id'] for row in self.s.crafting_access()['npcs']}
        self.assertIn('20091', ids)
        self.assertNotIn('9003', ids)

    def test_general_shop_rejected_and_move_uses_seon_table_with_stale_guard(self):
        recipe = copy.deepcopy(self.s.recipes()[0])
        recipe['fields']['npc'] = '9003'
        with self.assertRaisesRegex(ValueError, 'Cube'):
            self.s.recipe_plan(recipe)
        recipe['fields']['npc'] = '20091'
        original = {source: path.read_bytes() for source, path in self.s.recipe_sources().items()}
        count = len(self.s.recipes())
        plan = self.s.recipe_plan(recipe)
        self.assertEqual(len(plan['files']), 2)
        saved = self.s.commit(plan['id'])
        self.assertEqual(len(self.s.recipes()), count)
        self.assertNotIn(b'npc\t20091', self.s.recipe_sources()['base'].read_bytes())
        self.assertTrue(any(row['fields']['npc'] == '20091' and row['materials'] == recipe['materials'] for row in self.s.recipes() if row['source'] == 'seon'))
        self.s.commit(self.s.restore_plan(saved['id'])['id'])
        for source, path in self.s.recipe_sources().items():
            self.assertEqual(path.read_bytes(), original[source])
        self.s.recipe_sources()['seon'].write_bytes(original['seon'] + b'\n# newer\n')
        with self.assertRaisesRegex(ValueError, 'destination'):
            self.s.recipe_plan(recipe)

    def test_custom_recipe_provenance_survives_saving_and_ignores_unrelated_entries(self):
        rows = self.s.recipes()
        self.assertFalse(any(r['custom'] for r in rows))
        recipe = copy.deepcopy(rows[0]); recipe['fields']['gold'] = str(int(recipe['fields'].get('gold', '0')) + 1)
        self.s.commit(self.s.recipe_plan(recipe)['id'])
        changed = self.s.recipes()
        self.assertEqual(sum(r['custom'] for r in changed), 1)
        self.assertTrue(changed[0]['custom'])
        clone = copy.deepcopy(changed[0]); clone['new'] = True; clone.pop('index', None)
        clone['fields']['gold'] = str(int(clone['fields']['gold']) + 10)
        self.s.commit(self.s.recipe_plan(clone)['id'])
        self.assertEqual(sum(r['custom'] for r in self.s.recipes()), 2)

    def test_recipe_removal_preserves_every_other_byte_and_is_undoable(self):
        recipe = self.s.recipes()[0]
        count = len(self.s.recipes())
        path = self.s.recipe_sources()[recipe['source']]
        before = path.read_bytes()
        plan = self.s.recipe_delete_plan(recipe)
        self.assertEqual(path.read_bytes(), before)
        saved = self.s.commit(plan['id'])
        self.assertEqual(path.read_bytes(), before[:recipe['start']] + before[recipe['end']:])
        self.s.commit(self.s.restore_plan(saved['id'])['id'])
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.s.recipe_delete_plan({**recipe, 'hash':'old'})

    def test_custom_quest_removal_restores_exact_source_and_rejects_package_paths(self):
        body = dict(id='studio_removal_test', title='Removal test', intro='Hello.', npc='9001', target='101', reward='71084', kills=1, level=1, quantity=1, yang=0, exp=0)
        self.s.commit(self.s.quest_plan(body)['id'])
        row = next(row for row in library(self.s) if row['questName'] == body['id'])
        path = self.s.root / row['id']
        before = path.read_bytes()
        saved = self.s.commit(self.s.quest_delete_plan(row)['id'])
        self.assertFalse(path.exists())
        self.assertFalse(any(r['questName'] == body['id'] for r in library(self.s)))
        self.s.commit(self.s.restore_plan(saved['id'])['id'])
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'only for Studio'):
            self.s.quest_delete_plan({'id':'linux-port/docker/game/quest/seon_pyeong.quest','hash':'old'})
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.s.quest_delete_plan({**row, 'hash':'stale'})

    def test_removed_new_quest_stays_pending_until_a_successful_apply(self):
        body = dict(id='studio_pending_test',title='Pending test',intro='Hello.',npc='9001',target='101',reward='71084',kills=1,level=1,quantity=1,yang=0,exp=0)
        self.s.commit(self.s.quest_plan(body)['id'])
        self.s.workspace.deployment('before-removal', 'succeeded', {'files':self.s.build_fingerprints()})
        row = next(row for row in library(self.s) if row['questName'] == body['id'])
        self.s.commit(self.s.quest_delete_plan(row)['id'])
        self.assertIn(row['id'], [pending['path'] for pending in self.s.workspace.summary()['pending']])
        self.assertIsNone(self.s.build_fingerprints()[row['id']])
        self.s.workspace.deployment('after-removal', 'succeeded', {'files':self.s.build_fingerprints()})
        self.assertFalse(self.s.workspace.summary()['pending'])

    def test_history_explains_newer_edits_and_latest_undo_is_available(self):
        first = self.s.recipes()[0]
        first['fields']['gold'] = '123'
        a = self.s.commit(self.s.recipe_plan(first)['id'])
        latest = self.s.recipes()[0]
        latest['fields']['gold'] = '124'
        b = self.s.commit(self.s.recipe_plan(latest)['id'])
        rows = {row['id']: row for row in self.s.history()}
        self.assertFalse(rows[a['id']]['canRestore'])
        self.assertIn('Newer edits', rows[a['id']]['restoreReason'])
        self.assertTrue(rows[b['id']]['canRestore'])
        self.s.commit(self.s.restore_plan(b['id'])['id'])
        self.assertTrue(next(row for row in self.s.history() if row['id'] == a['id'])['canRestore'])

    def test_history_groups_keep_backups_and_cross_category_rollback_guards(self):
        recipe = self.s.recipes()[0]
        recipe['fields']['gold'] = '123'
        first = self.s.commit(self.s.recipe_plan(recipe)['id'])
        latest = self.s.recipes()[0]
        latest['fields']['gold'] = '124'
        plan = self.s.recipe_plan(latest)
        self.s.plans[plan['id']]['metadata']['historyCategory'] = 'reconciliation'
        second = self.s.commit(plan['id'])
        rows = {row['id']: row for row in self.s.history()}
        self.assertEqual(rows[first['id']]['category'], 'gameplay')
        self.assertEqual(rows[second['id']]['category'], 'reconciliation')
        self.assertEqual(rows[first['id']]['areas'], ['crafting'])
        self.assertEqual(rows[second['id']]['areas'], ['crafting'])
        self.assertFalse(rows[first['id']]['canRestore'])
        restored = self.s.commit(self.s.restore_plan(second['id'])['id'])
        rows = {row['id']: row for row in self.s.history()}
        self.assertEqual(rows[restored['id']]['category'], 'reconciliation')
        self.assertEqual(rows[restored['id']]['areas'], ['crafting'])
        self.assertTrue(rows[first['id']]['canRestore'])

    def test_recipe_removal_can_be_staged_without_writing_game_files(self):
        recipe = self.s.recipes()[0]
        count = len(self.s.recipes())
        path = self.s.recipe_sources()[recipe['source']]
        before = path.read_bytes()
        ident = self.s.workspace.create_set({'name':'Remove recipe'})['id']
        ACTIVE_CHANGESET.set(ident)
        self.s.commit(self.s.recipe_delete_plan(recipe)['id'])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.s.recipes()), count - 1)
