import copy
import json
import re
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Studio, DEFAULT_ROOT, digest, sql_rows
from catalog import item_metadata
from item_help import item_description
from item_usage import item_usage, item_drop_summary


class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DEFAULT_ROOT is None or not (DEFAULT_ROOT / 'files/items.json').is_file():
            raise unittest.SkipTest('Game integration tests require METIN2_STUDIO_SERVER_ROOT pointing to your existing supported Serwer folder. Game assets are not bundled.')
        cls.test_runs = Path(__file__).resolve().parents[1] / 'data' / 'test-runs'
        cls.test_runs.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=cls.test_runs)
        cls.root = Path(cls.temp.name) / 'server'
        files = ['files/items.json', 'files/playerbot_names_en.tsv', 'files/drop_tables.py', 'files/static/item_icons.json',
                 'linux-port/docker/.env.example', 'linux-port/docker/mariadb/initdb.d/dumps/world.sql',
                 'linux-port/docker/game/Dockerfile', 'linux-port/docker/game/.dockerignore',
                 'linux-port/docker/game/share/locale/poland/mob_drop_item.txt',
                 'linux-port/docker/game/share/locale/poland/special_item_group.txt',
                 'linux-port/docker/game/share/locale/poland/cube.txt',
                 'linux-port/docker/game/share-add/mob_drop_item.m3.append.txt',
                 'linux-port/docker/game/share-add/cube.seon_pyeong.txt',
                 'linux-port/docker/game/share-add/special_item_group.moonlight.txt',
                 'linux-port/docker/game/share-add/special_item_group.starter.txt',
                 'linux-port/docker/game/share-add/special_item_group.hexagonal.txt']
        files += ['linux-port/docker/mariadb/playerbot/crafting_windows.sql',
                  'linux-port/docker/game/share/locale/poland/quest/libs/crafting/crafting_data.lua',
                  'linux-port/docker/game/share/locale/poland/quest/quest/systems/crafting.lua']
        for name in files:
            target = cls.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DEFAULT_ROOT / name, target)
        # The user's installation may already contain saved Studio quests. The
        # disposable fixture starts before that integration so first-install,
        # restore and update-recovery checks stay independent of their work.
        dockerfile = cls.root / 'linux-port/docker/game/Dockerfile'
        raw = dockerfile.read_bytes()
        raw = re.sub(rb'(?ms)^# SERVER-STUDIO CUSTOM QUESTS\r?\n.*?(?=^FROM )', b'', raw)
        raw = re.sub(rb'(?ms)^# SERVER-STUDIO EDITED QUEST CLEANUP\r?\n.*?^# END SERVER-STUDIO EDITED QUEST CLEANUP\r?\n', b'', raw)
        dockerfile.write_bytes(raw)
        ignore = cls.root / 'linux-port/docker/game/.dockerignore'
        ignore.write_bytes(b'\n'.join(line for line in ignore.read_bytes().splitlines()
                                    if line not in (b'# Server Studio quests', b'!custom-quests', b'!custom-quests/**')) + b'\n')
        # Synthetic, known Cube route for recipe write tests. This does not
        # assert that the installed package exposes this NPC's old Cube window.
        opener = cls.root / 'linux-port/docker/game/share/locale/poland/quest/object/20018/chat/fixture_cube.start.0.script'
        opener.parent.mkdir(parents=True, exist_ok=True)
        opener.write_bytes(b'command ( "cube open" )\n')
        source = cls.root / 'linux-port/docker/game/quest/seon_pyeong.quest'
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_ROOT / 'linux-port/docker/game/quest/seon_pyeong.quest', source)
        cls.initial = {p: p.read_bytes() for p in cls.root.rglob('*') if p.is_file()}
        cls.s = Studio(cls.root, Path(cls.temp.name) / 'state')

    @classmethod
    def tearDownClass(cls):
        assert Path(cls.temp.name).resolve().is_relative_to(cls.test_runs.resolve())
        cls.temp.cleanup()

    def setUp(self):
        for p, raw in self.initial.items():
            p.write_bytes(raw)
        (self.root / 'linux-port/docker/.env').write_bytes(b'M2_DB_PASSWORD=test-private-value\r\nM2_DIFFICULTY=easy\r\nM2_MAX_LEVEL=120\r\n')
        self.s.plans.clear()
        self.s.job = {'status': 'idle', 'lines': []}
        with self.s.workspace.connect() as conn:
            for table in ('tracked', 'deferred_merges', 'drafts', 'staged', 'changesets', 'deployments', 'activity'):
                conn.execute('DELETE FROM ' + table)
        for p in (self.s.game / 'custom-quests').glob('*'):
            p.unlink()
        (self.s.game / 'special_item_group.moonlight.custom.txt').unlink(missing_ok=True)

    def drop(self):
        return self.s.group('mob-base', '8001 drop')

    def test_catalog_has_real_targets(self):
        self.assertEqual(self.s.mobs['8001']['name'], 'Metin of Sorrow')
        self.assertEqual(self.s.mobs['8001']['category'], 'metin')
        self.assertGreater(len(self.s.items), 9000)

    def test_catalog_filters_follow_installed_item_types(self):
        cases = {
            '71084': ('bonus', 'bonus-changer'),
            '71085': ('bonus', 'bonus-adder'),
            '70024': ('bonus', 'fifth-bonus'),
            '25040': ('scrolls', 'upgrade-scroll'),
            '27002': ('potions', 'recovery-potion'),
            '27101': ('potions', 'speed-potion'),
            '50300': ('books', 'skill-book'),
            '50821': ('potions', 'blend'),
            '30010': ('materials', 'upgrade-material'),
            '11200': ('equipment', 'armour-0'),
            '28000': ('stones', 'spirit-stone'),
            '110000': ('stones', 'dragon-stone'),
        }
        for ident, (group, function) in cases.items():
            with self.subTest(ident=ident):
                item = self.s.items[ident]
                self.assertIn(group, item['catalogGroups'])
                self.assertEqual(item['catalogKind'], function)
        self.assertEqual(self.s.items['50821']['requiredLevel'], 55)
        self.assertEqual(self.s.items['50300']['category'], 'lottery')
        self.assertEqual(self.s.items['71084']['name'], 'Enchant Item')

    def test_catalog_missing_definitions_use_conservative_fallbacks(self):
        self.assertEqual(item_metadata({'name': 'Unknown', 'category': 'pickaxe'})['catalogGroups'], ['other'])
        self.assertEqual(item_metadata({'name': 'A book', 'category': 'lottery'})['catalogGroups'], ['books'])
        self.assertEqual(item_metadata({'name': 'Pink Potion', 'category': 'special'})['catalogGroups'], ['potions'])
        self.assertEqual(item_metadata({'name': 'Bonus Sword', 'category': 'weapon'})['catalogGroups'], ['equipment'])

    def test_item_help_distinguishes_bonus_actions(self):
        changer = self.s.items['71084']['description']['text']
        adder = self.s.items['71085']['description']['text']
        fifth = self.s.items['70024']['description']['text']
        self.assertIn('Rerolls existing', changer)
        self.assertIn('does not add', changer)
        self.assertIn('up to four', adder)
        self.assertIn('fifth normal bonus', fifth)
        self.assertIn('40 or below', self.s.items['71151']['description']['note'])

    def test_item_help_uses_seed_values_and_flags_misleading_names(self):
        self.assertIn('800 HP', self.s.items['27002']['description']['text'])
        self.assertIn('250 MP', self.s.items['27005']['description']['text'])
        self.assertEqual(self.s.items['27002']['description']['source'], 'definition')
        scroll = self.s.items['25041']['description']
        self.assertIn('Name mismatch', scroll['note'])
        self.assertIn('Blessing Scroll', scroll['text'])
        self.assertIn('Magic Stone', self.s.items['25042']['description']['text'])
        self.assertTrue(all(item['description']['text'] for item in self.s.items.values()))

    def test_unknown_item_help_does_not_invent_an_effect(self):
        unknown = item_description({'id':'999999', 'name':'Magic Stone', 'catalogKind':'unclassified'})
        self.assertEqual(unknown['source'], 'unknown')
        self.assertIn('No reliable effect', unknown['text'])
        fallback = item_description({'id':'25041', 'catalogKind':'upgrade-scroll'})
        self.assertEqual(fallback['source'], 'catalog')
        self.assertNotIn('Name mismatch', fallback['note'])

    def test_item_usage_reads_cube_and_native_crafting_without_writing(self):
        before = {p: digest(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        herb = item_usage(self.s, '50721', sql_rows)
        self.assertTrue(any(row['actions'] and row['actions'][0]['kind'] == 'recipe' for row in herb['sections']['ingredients']))
        native = item_usage(self.s, '71284', sql_rows)
        self.assertTrue(any(row.get('seed') and 'Native crafting #100' in row['summary'] for row in native['sections']['crafted']))
        self.assertTrue(any('Heuk-Young' in row['summary'] for row in native['sections']['crafted']))
        after = {p: digest(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_item_usage_tracks_saved_changes_and_matches_exact_ids(self):
        path = self.s.locale / 'cube.txt'
        path.write_bytes(path.read_bytes() + b'\nsection\nnpc 20018\nitem 71084 2\nreward 27002 1\npercent 100\ngold 50\nend\n')
        usage = item_usage(self.s, '71084', sql_rows)
        self.assertTrue(any('Enchant Item' in detail and '#71084' in detail for row in usage['sections']['ingredients'] for detail in row['details']))
        source = self.s.game / 'custom-quests' / 'studio_usage_test.quest'
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('-- 71084 comment\npc.give_item2(71084, 1)\npc.give_item2(710840, 1)\n', 'utf-8')
        usage = item_usage(self.s, '71084', sql_rows)
        matches = [row for row in usage['sections']['files'] if row['name'] == source.name]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['line'], 2)
        self.assertEqual(len(matches[0]['details']), 1)

    def test_item_usage_respects_replaced_chest_definitions(self):
        path = self.s.game / 'special_item_group.moonlight.custom.txt'
        path.write_bytes(b'Group studio_moon\n{\nVnum 50011\n1 71084 1 25\n}\n')
        usage = item_usage(self.s, '71084', sql_rows)
        moon = [row for row in usage['sections']['chests'] if row['actions'][0]['key'] == '50011']
        self.assertEqual(len(moon), 1)
        self.assertEqual(moon[0]['actions'][0]['source'], 'chest-moonlight')

    def test_item_usage_finds_shared_metin_routes(self):
        usage = item_usage(self.s, '20', sql_rows)
        sorrow = [row for row in usage['sections']['drops'] if row['actions'][0]['key'] == '8001 drop']
        self.assertTrue(sorrow)
        self.assertIn('Via pool #8001', sorrow[0]['summary'])
        self.assertEqual(sorrow[0]['actions'][1]['label'], 'Open reward pool')

    def test_hover_summary_reuses_index_and_refreshes_after_pool_file_changes(self):
        # Only disposable fixture files are changed, never the installed server.
        self.s.sources['mob-base'][0].write_bytes(b'Group one\n{\nMob 8001\nType drop\n1 s8001 1 5\n}\nGroup two\n{\nMob 8002\nType drop\n1 s8001 1 5\n}\n')
        self.s.sources['mob-m3'][0].write_bytes(b'Group extra\n{\nMob 8001\nType drop\n1 999999999 1 5\n}\n')
        pool = self.s.sources['chest-base'][0]
        pool.write_bytes(b'Group shared\n{\nVnum 8001\n1 999999998 1 5\n}\n')
        with patch.object(self.s, 'groups', wraps=self.s.groups) as groups, patch.object(self.s, 'recipes', side_effect=AssertionError('Hover must not scan recipes')):
            first = item_drop_summary(self.s, '999999999')
            self.assertEqual(first['counts']['metins'], 1)
            self.assertEqual(item_drop_summary(self.s, 's8001')['counts']['metins'], 2)
            self.assertEqual(item_drop_summary(self.s, '999999999'), first)
            self.assertEqual(groups.call_count, 1)
            pool.write_bytes(pool.read_bytes().replace(b'999999998', b'999999999'))
            updated = item_drop_summary(self.s, '999999999')
            self.assertEqual(updated['counts']['metins'], 2)
            self.assertEqual(groups.call_count, 2)
            pool.write_bytes(pool.read_bytes().replace(b'999999999', b'999999998'))
            self.assertEqual(item_drop_summary(self.s, '999999999')['counts']['metins'], 1)

    def test_item_usage_does_not_label_unknown_reward_tables_as_physical_chests(self):
        path = self.s.sources['chest-base'][0]
        path.write_bytes(path.read_bytes() + b'\nGroup studio_orphan\n{\nVnum 29999\n1 71084 1 10\n}\n')
        usage = item_usage(self.s, '71084', sql_rows)
        self.assertTrue(any(row['actions'][0]['key'] == '29999' for row in usage['sections']['pools']))
        self.assertFalse(any(row['actions'][0]['key'] == '29999' for row in usage['sections']['chests']))

    def test_drop_save_and_restore_exact_original(self):
        original = self.s.sources['mob-base'][0].read_bytes()
        g = self.drop()
        g['entries'][0]['prob'] = '8.5'
        p = self.s.drop_plan(g)
        self.assertEqual(self.s.sources['mob-base'][0].read_bytes(), original)
        result = self.s.commit(p['id'])
        self.assertEqual(self.drop()['entries'][0]['prob'], '8.5')
        self.assertEqual(self.s.group('mob-base', '8002 drop')['entries'][0]['prob'],
                         self.s.dt.logical_groups('mob_drop_item.txt', original)[next(i for i, x in enumerate(self.s.dt.logical_groups('mob_drop_item.txt', original)) if x.key == '8002 drop')].entries[0].prob)
        self.s.commit(self.s.restore_plan(result['id'])['id'])
        self.assertEqual(self.s.sources['mob-base'][0].read_bytes(), original)

    def test_invalid_reward_is_refused(self):
        g = self.drop(); g['entries'][0]['item'] = '999999999'
        with self.assertRaises(ValueError): self.s.drop_plan(g)

    def test_reward_pools_cannot_reference_themselves(self):
        g = self.s.group('chest-base', '8001')
        g['entries'] = [{'item':'s8001','count':'1','prob':'1','rare':''}]
        with self.assertRaisesRegex(ValueError, 'loop'): self.s.drop_plan(g)

    def test_recipe_change_preserves_other_recipes_and_restores(self):
        before = self.s.recipe_sources()['base'].read_bytes()
        recipes = self.s.recipes()
        self.assertGreater(len(recipes), 100)
        r = copy.deepcopy(recipes[0])
        r['fields']['percent']='75'
        result = self.s.commit(self.s.recipe_plan(r)['id'])
        after = self.s.recipes()
        self.assertEqual(after[0]['fields']['percent'],'75')
        self.assertEqual(after[1]['materials'],recipes[1]['materials'])
        self.s.commit(self.s.restore_plan(result['id'])['id'])
        self.assertEqual(self.s.recipe_sources()['base'].read_bytes(),before)

    def test_new_recipe_uses_names_and_validates_npc(self):
        r=copy.deepcopy(self.s.recipes()[0]);r.update(index=-1,new=True)
        count=len(self.s.recipes())
        self.s.commit(self.s.recipe_plan(r)['id'])
        self.assertEqual(len(self.s.recipes()),count+1)
        r['hash']=digest(self.s.recipe_sources()['base'].read_bytes())
        r['fields']['npc']='8001'
        with self.assertRaisesRegex(ValueError,'NPC'):self.s.recipe_plan(r)
        g = self.drop(); g['entries'][0]['count'] = '-1'
        with self.assertRaises(ValueError): self.s.drop_plan(g)

    def test_stale_preview_is_refused(self):
        g = self.drop(); g['entries'][0]['prob'] = '3'
        p = self.s.drop_plan(g)
        target = self.s.sources['mob-base'][0]
        target.write_bytes(target.read_bytes() + b'\n# external edit\n')
        with self.assertRaisesRegex(ValueError, 'changed since review'): self.s.commit(p['id'])

    def test_moonlight_edits_use_persistent_custom_file(self):
        g = self.s.group('chest-moonlight', '50011')
        base = (self.s.game / 'share-add/special_item_group.moonlight.txt').read_bytes()
        g['entries'][0]['prob'] = str(int(g['entries'][0]['prob'])+1)
        self.s.commit(self.s.drop_plan(g)['id'])
        self.assertTrue((self.s.game / 'special_item_group.moonlight.custom.txt').exists())
        self.assertEqual((self.s.game / 'share-add/special_item_group.moonlight.txt').read_bytes(), base)

    def test_settings_redact_credentials_and_keep_unrelated_bytes(self):
        data = self.s.settings()
        self.assertNotIn('test-private-value', json.dumps(data))
        p = self.s.settings_plan({'hash': data['hash'], 'values': {'M2_DIFFICULTY': 'medium'}})
        self.assertNotIn('test-private-value', json.dumps(p))
        self.s.commit(p['id'])
        raw = (self.s.compose / '.env').read_bytes()
        self.assertIn(b'M2_DB_PASSWORD=test-private-value\r\n', raw)
        self.assertIn(b'M2_DIFFICULTY=medium\r\n', raw)

    def test_settings_reject_injection_fresh_rates_and_invalid_bounds(self):
        for values in [{'M2_DB_PASSWORD':'bad'}, {'M2_RATE_EXP':'200'}, {'M2_MAX_LEVEL':'500'}, {'M2_DIFFICULTY':'easy\nM2_LOCAL_ONLY=0'}]:
            with self.assertRaises(ValueError): self.s.settings_plan({'hash':self.s.settings()['hash'], 'values':values})

    def test_legacy_editor_preserves_every_byte_when_unchanged(self):
        f = self.s.file('linux-port/docker/game/share/locale/poland/cube.txt')
        with self.assertRaisesRegex(ValueError, 'no changes'):
            self.s.file_plan(f)

    def test_path_traversal_is_refused(self):
        with self.assertRaises(ValueError): self.s.file('../outside.txt')
        with self.assertRaises(ValueError): self.s.plan('bad', {self.root / '../outside.txt':b'bad'}, '')

    def quest(self):
        return {'id':'studio_test_hunt','title':'The Stone Hunter','intro':'Help the village.', 'npc':'9001','target':'8001','reward':'71084','kills':3,'level':5,'quantity':1,'yang':1000,'exp':100}

    def test_quest_hook_is_reviewable_and_undoable(self):
        q = self.quest()
        code = self.s.quest_code(q)[1]
        self.assertIn('state complete begin', code)
        self.assertIn('state reward begin', code)
        self.assertIn('The Stone Hunter', code)
        plan = self.s.quest_plan(q)
        self.assertEqual(len(plan['files']), 3)
        original = (self.s.game / 'Dockerfile').read_bytes()
        result = self.s.commit(plan['id'])
        raw = (self.s.game / 'Dockerfile').read_bytes()
        self.assertLess(raw.index(b'# SERVER-STUDIO CUSTOM QUESTS'), raw.index(b' AS runtime'))
        self.assertIn(b'!custom-quests/**', (self.s.game / '.dockerignore').read_bytes())
        self.s.commit(self.s.restore_plan(result['id'])['id'])
        self.assertFalse((self.s.game / 'custom-quests/studio_test_hunt.quest').exists())
        self.assertEqual((self.s.game / 'Dockerfile').read_bytes(), original)

    def test_quest_target_and_id_validation(self):
        for k,v in [('id','../../escape'),('npc','8001'),('target','9001'),('reward','1'),('quantity',999),('intro','bad\nline'),('title','The "Stone" Hunter')]:
            q = self.quest(); q[k] = v
            with self.assertRaises(ValueError): self.s.quest_code(q)

    def test_restore_refuses_overwriting_newer_changes(self):
        g = self.drop(); g['entries'][0]['prob']='2'
        result=self.s.commit(self.s.drop_plan(g)['id'])
        g = self.drop(); g['entries'][0]['prob']='3'
        self.s.commit(self.s.drop_plan(g)['id'])
        with self.assertRaisesRegex(ValueError, 'newer edits'): self.s.restore_plan(result['id'])

    def test_running_apply_locks_edits(self):
        self.s.job['status']='running'
        with self.assertRaisesRegex(ValueError, 'apply'): self.s.plan('test', {self.s.game/'x.txt':b'x'}, '')

    def test_sql_is_parsed_as_data(self):
        rows=sql_rows("INSERT INTO `mob_proto` VALUES (1,'a\\'b','c,d'),(2,'x','z'); DROP TABLE x;",'mob_proto')
        self.assertEqual(rows, [['1', "a'b", 'c,d'], ['2','x','z']])


if __name__ == '__main__':
    unittest.main()
