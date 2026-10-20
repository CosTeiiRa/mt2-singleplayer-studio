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

    def test_mining_targets_and_build_additions_are_separate_from_npcs_and_metins(self):
        quest = self.locale / 'quest/quest/systems/mining.quest'
        quest.parent.mkdir(parents=True)
        quest.write_text('when 9001.click begin npc.open_shop() end\n'
                         '-- when 9999.click begin pc.mining() end\n'
                         'when 20047.click or 30301.click begin pc.mining() end\n')
        folder = self.locale / 'map/test_map'
        line = 'm 60 70 4 5 0 0 5m-10m 100 1 20047\n'
        (folder / 'stone.txt').write_text(line)
        (folder / 'npc.txt').write_text('m 10 20 1 1 0 0 1m 100 1 9001\n')
        additions = self.root / 'linux-port/docker/game/ore_veins'
        additions.mkdir()
        (additions / 'test_map.txt').write_text(line + 'm 80 90 4 5 0 0 5m 100 1 30301\n')
        mobs = {str(i): {'name': n, 'category': 'npc', 'level': 1}
                for i, n in [(20047, 'Diamond vein'), (30301, 'Soul crystal vein'), (9001, 'Shopkeeper')]}
        world = WorldData(self.root, mobs, include_monsters=True)
        self.assertEqual(world.mining_ids, {20047, 30301})
        rows = world.map(64)['regions']
        ore = [r for r in rows if r['type'] == 'ore']
        self.assertEqual([r['mob_id'] for r in ore], [20047, 30301])
        self.assertEqual(ore[0]['respawn'], '5m-10m')
        self.assertTrue(ore[1]['source'].endswith('/ore_veins/test_map.txt'))
        self.assertEqual([r['mob_id'] for r in rows if r['type'] == 'npc'], [9001])
        runtime = world.runtime_data()['test_map']['regions']
        self.assertFalse(any('/ore_veins/' in r['source'] for r in runtime))

    def test_mining_build_additions_work_without_optional_mining_quest(self):
        additions = self.root / 'linux-port/docker/game/ore_veins'
        additions.mkdir()
        (additions / 'test_map.txt').write_text('m 10 20 1 2 0 0 5m 100 1 20047\n')
        world = WorldData(self.root, include_monsters=True)
        ore = [r for r in world.map(64)['regions'] if r['type'] == 'ore']
        self.assertEqual(len(ore), 1)
        self.assertEqual(ore[0]['mob_id'], 20047)

    def test_english_labels_and_navigation_copies_are_read_without_executing_or_changing_game_source(self):
        import base64
        from metin2_studio.catalogue_client import png_pixels
        image = png_pixels(bytes([0,0,2])+bytes(9)+__import__('struct').pack('<HHBB',1,1,32,32)+bytes([0,0,255,255]))
        admin = self.root / 'files/admin_panel.py'; admin.parent.mkdir()
        admin.write_text("EVENT_MAPS=((64,'Polish name','English valley'),)\nPLAYERBOT_MAP_TILES={64:" + repr(base64.b64encode(image).decode()) + "}\nraise RuntimeError('must not execute')\n")
        modules = admin.parent / 'editsql/modules.py'; modules.parent.mkdir()
        modules.write_text("MAP_NAMES={64:P('Polish','English map')}\n")
        folder = self.locale / 'map/test_map'
        (folder / 'server_attr').write_bytes(b'exact same map geometry')
        copy = self.locale / 'map/monkey_dungeon'
        copy.mkdir(); (copy / 'server_attr').write_bytes((folder / 'server_attr').read_bytes())
        (copy / 'Setting.txt').write_text('MapSize 3 4\n')
        (self.locale / 'map/index').write_text('64 test_map\n65 monkey_dungeon\n')
        before = admin.read_bytes()
        world = WorldData(self.root, include_monsters=True)
        self.assertEqual(world.map(64)['name'], 'English map')
        self.assertEqual(world.map(64)['original_name'], 'Test map')
        self.assertEqual(world.map(65)['image_source'], 'game-navigation')
        self.assertEqual(world.image_data(65), (image, 'image/png'))
        self.assertEqual(admin.read_bytes(), before)
        self.assertEqual(WorldData(self.root).map(64)['name'], 'Test map')
        (copy / 'server_attr').write_bytes(b'different geometry')
        self.assertIsNone(WorldData(self.root, include_monsters=True).map(65)['image_url'])
        modules.write_text("MAP_NAMES={64:P('Polish','New English map label')}\n")
        self.assertEqual(WorldData(self.root, include_monsters=True).map(64)['name'], 'New English map label')

    def test_cached_client_atlas_and_english_name_take_priority_over_dashboard_data(self):
        image = self.root / 'studio-cache.png'; image.write_bytes(b'cached client image')
        world = WorldData(self.root, include_monsters=True, map_names={'test_map':'Client English map'},
                          map_images={'test_map':'cached-image'}, image_resolver=lambda name:image if name=='cached-image' else None)
        result = world.map(64)
        self.assertEqual((result['name'],result['name_source']), ('Client English map','client-en'))
        self.assertEqual(result['image_source'], 'client-atlas')
        self.assertEqual(world.image_data(64), (b'cached client image','image/png'))
        self.assertEqual(world.image_path(64), image)
