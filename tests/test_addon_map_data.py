import json
import tempfile
import unittest
from pathlib import Path

from metin2_studio.addons.map_data import WorldData

PROJECT = Path(__file__).resolve().parents[1]


class MapDataTests(unittest.TestCase):
    def setUp(self):
        (PROJECT / '.test-tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PROJECT / '.test-tmp')
        self.root = Path(self.temp.name)
        self.locale = self.root / 'linux-port/docker/game/share/locale/poland'
        folder = self.locale / 'map/test_map'
        folder.mkdir(parents=True)
        (self.locale / 'map/index').write_text('64 test_map\n999 ../../outside\n')
        (folder / 'Setting.txt').write_text('MapSize 3 4\nBasePosition 100000 200000\n')
        (folder / 'boss.txt').write_text('ga 100 200 30 40 0 0 48m-52m 100 1 2316\nr 1 2 3 4 0 0 1m 100 1 999\n')
        (folder / 'stone.txt').write_text('m 200 300 20 10 0 0 15m 100 1 8001\n')
        (self.locale / 'group.txt').write_text('Group example\n{\nLeader boss 2382\nVnum 2316\n}\n')
        panel = self.root / 'linux-port/docker/seban-panel'
        (panel / 'static').mkdir(parents=True)
        (panel / 'app.py').write_text("MAP_NAMES={64:'Test map'}\nMAP_IMAGE_FILES={}\nraise RuntimeError('must not execute')\n")
        (panel / 'static/mob_names_en.json').write_text(json.dumps({'2382': ['Local name', 'Dae-Ho'], '8001': ['Local stone', 'Metin stone']}))

    def tearDown(self):
        self.temp.cleanup()

    def test_groups_extents_names_and_base_intervals(self):
        world = WorldData(self.root)
        m = world.map(64)
        self.assertEqual((m['width'], m['height']), (768, 1024))
        boss = m['regions'][0]
        self.assertEqual((boss['mob_id'], boss['group_id'], boss['name']), (2382, 2316, 'Dae-Ho'))
        self.assertEqual((boss['width'], boss['height']), (60, 80))
        self.assertEqual(boss['respawn'], '48m-52m')
        self.assertFalse(m['coverage']['live'])
        self.assertEqual(len(m['coverage']['omitted']), 1)
        self.assertEqual(world.catalog()['maps'][0]['stone_count'], 1)

    def test_unsafe_index_directory_is_ignored(self):
        world = WorldData(self.root)
        with self.assertRaises(ValueError):
            world.map(999)

    def test_studio_atlas_expands_regular_group_members_without_changing_runtime_export(self):
        folder = self.locale / 'map/test_map'
        (self.locale / 'group.txt').write_text('Group wolves\n{\nVnum 10\nLeader wolf 101\n1 blue_wolf 102\n2 wolf 101\n}\n')
        (folder / 'regen.txt').write_text('g 20 30 4 5 0 0 30s 100 2 10\n')
        mobs = {'101': {'name': 'Wolf', 'category': 'monster', 'level': 1}, '102': {'name': 'Blue Wolf', 'category': 'monster', 'level': 2}}
        world = WorldData(self.root, mobs, include_monsters=True)
        regular = [r for r in world.map(64)['regions'] if r['source'].endswith('/regen.txt')]
        self.assertEqual([(r['mob_id'], r['level'], r['name']) for r in regular], [(101, 1, 'Wolf'), (102, 2, 'Blue Wolf')])
        self.assertTrue(all(r['group_spawn'] and r['count'] == 2 and r['width'] == 8 for r in regular))
        self.assertFalse(any(r['source'].endswith('/regen.txt') for r in world.runtime_data()['test_map']['regions']))

    def test_random_groups_show_possible_members_and_omit_unresolved_alternatives(self):
        (self.locale / 'group_group.txt').write_text('Group random\n{\nVnum 50\n1 2316 10\n}\nGroup incomplete\n{\nVnum 51\n1 9999 1\n}\n')
        (self.locale / 'map/test_map/regen.txt').write_text('r 10 20 3 4 0 0 30s 100 1 50\nr 20 30 3 4 0 0 30s 100 1 51\n')
        world = WorldData(self.root, {'2382': {'name': 'Boss', 'category': 'boss', 'level': 50}}, include_monsters=True)
        result = world.map(64)
        rows = [r for r in result['regions'] if r['source'].endswith('/regen.txt')]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['random_group'])
        self.assertEqual(rows[0]['mob_id'], 2382)
        self.assertTrue(any('unresolved random group 51' in warning for warning in result['coverage']['omitted']))
