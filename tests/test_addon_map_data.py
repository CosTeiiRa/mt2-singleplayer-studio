import json
import tempfile
import unittest
from pathlib import Path

from addonhub.map_data import WorldData

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
