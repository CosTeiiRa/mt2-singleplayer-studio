"""Reference correctness, API-v2 lifecycle and reviewed data refresh."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from addonhub.knowledge import build_index, encoded, sql_rows
from addonhub.hubcore.packages import load_package
from addonhub import client_pack as codec

ROOT = Path(__file__).resolve().parents[1]
(ROOT / '.test-tmp').mkdir(exist_ok=True)
PAYLOAD = ROOT / 'addonhub/catalog/community.pocket-wiki/payload'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def reference():
    return {'schema_version': 1,
            'items': {key: {'id': key, 'name': name, 'category': 'Material', 'description': '', 'aliases': ''}
                      for key, name in [('10', 'Épée +0'), ('11', 'Épée +1'), ('12', 'Épée +2'), ('20', 'Herb')]},
            'recipes': {'native:1': {'id': 'native:1', 'system': 'Native', 'materials': [{'item': '20', 'count': 3}],
                         'outputs': [{'item': '10', 'count': 2}], 'cost': 7, 'chance': 50, 'npcs': ['20001'],
                         'requirements': ['Level 5'], 'provenance': 'database-seed'}},
            'upgrades': {'10': {'id': '10', 'from': '10', 'to': '11', 'materials': [{'item': '20', 'count': 2}], 'cost': 9, 'chance': 60, 'provenance': 'database-seed'},
                         '11': {'id': '11', 'from': '11', 'to': '12', 'materials': [], 'cost': 12, 'chance': 30, 'provenance': 'database-seed'}},
            'npcs': {'20001': {'id': '20001', 'name': 'Herbalist'}},
            'origins': {'shop:1': {'id': 'shop:1', 'name': 'Herbalist', 'kind': 'NPC shop', 'provenance': 'database-seed'}},
            'crafted': {'10': ['native:1']}, 'uses': {'20': [['recipe', 'native:1'], ['upgrade', '10']]},
            'obtained': {'20': ['shop:1']},
            'meta': {'snapshot': 'a' * 64, 'server_version': '2.2.108', 'generated_at': 'fixture',
                     'native_crafting': 'database-seed', 'warnings': ['Fixture coverage'], 'source_hashes': {}}}


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.Model = module('pocket_test_model', PAYLOAD / 'pocket_model.py').Model

    def test_search_matches_localized_names_aliases_ids_npc_and_categories(self):
        model = self.Model(reference(), resolver=lambda ident: 'Espada' if ident == 10 else None)
        self.assertEqual(model.search('espada', 'Items')[1], 1)
        self.assertEqual(model.search('epee', 'Items')[1], 3)
        self.assertEqual(model.search('10', 'Items')[0][0][1], '10')
        self.assertEqual(model.search('Herbalist', 'Crafts')[1], 1)

    def test_recipe_calculator_costs_attempts_and_keeps_successful_output_per_attempt(self):
        model = self.Model(reference())
        _, rows = model.page(['recipe', 'native:1'], attempts=4)
        self.assertTrue(any('28 Yang' in row['text'] for row in rows))
        self.assertTrue(any('Herb x12' == row['text'] for row in rows))
        self.assertTrue(any('Épée +0 x2' == row['text'] for row in rows))

    def test_upgrade_chain_uses_links_and_terminates_cycles(self):
        data = reference()
        data['upgrades']['12'] = dict(data['upgrades']['10'], id='12', to='10')
        model = self.Model(data)
        _, rows = model.page(['item', '11'])
        links = [row['link'] for row in rows if (row.get('link') or [''])[0] == 'upgrade']
        self.assertEqual(len(links), 3)

    def test_history_bookmarks_and_invalid_persisted_pages(self):
        model = self.Model(reference(), {'recent': [['item', 'missing']], 'bookmarks': 'bad'})
        model.navigate('item', '10')
        model.bookmark()
        model.navigate('recipe', 'native:1')
        model.travel(-1)
        self.assertEqual(model.current, ['item', '10'])
        model.travel(1)
        restored = self.Model(reference(), model.persist())
        self.assertEqual(restored.current, ['recipe', 'native:1'])
        self.assertEqual(restored.search('', 'Bookmarks')[1], 1)


class KnowledgeTests(unittest.TestCase):
    def test_sql_parser_handles_multiple_inserts_escaped_quotes_and_commas(self):
        self.assertEqual(sql_rows("INSERT INTO `x` VALUES (1,'a,b'),(2,'it\\'s'); INSERT INTO `x` VALUES (3,'z');", 'x'),
                         [['1', 'a,b'], ['2', "it's"], ['3', 'z']])

    def test_saved_cube_bytes_and_current_native_rows_exclude_pending_overrides(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp') as temporary:
            root = Path(temporary)
            cube = root / 'cube.txt'
            cube.write_bytes(b'saved')
            class Source:
                def recipe_sources(self): return {'cube': cube}
                def recipes(self):
                    assert self.read(cube) == b'saved'
                    return [{'source': 'cube', 'index': 0, 'fields': {'npc': '20001'}, 'materials': [{'item': '20', 'count': '3'}],
                             'rewards': [{'item': '10', 'count': '1'}], 'npcSupported': True}]
                def groups(self, raw): return []
            studio = Source()
            studio.root = root
            studio.items = reference()['items']
            studio.mobs = {'20001': {'name': 'Herbalist'}}
            studio.sources = {}
            studio.read = lambda path: b'pending'
            proto = {'item_vnum': 11, 'count': 2, 'price': 12, 'chance': 80, 'recipe': '20,4',
                     'req_progress': 0, 'req_level': 5, 'recipe_vnum': 0}
            studio.native_crafting = SimpleNamespace(live=lambda fresh: {'rows': {'1': {'proto': proto, 'windows': {'101': 1}}}})
            with patch('crafting_access.discover_native', return_value=[{'id': '20001', 'window': '101'}]):
                data = build_index(studio)
            self.assertEqual(data['recipes']['native:1']['cost'], 12)
            self.assertEqual(data['recipes']['cube:cube:0']['materials'][0]['count'], 3)
            self.assertEqual(data['meta']['native_crafting'], 'current-database')
            self.assertNotIn(str(root), encoded(data).decode())


class RuntimeV2Tests(unittest.TestCase):
    def test_window_lifecycle_shortcuts_keep_original_game_behaviour(self):
        client = module('client_v2_fixture', ROOT / 'addonhub/runtime/m2hub_client.py')
        events = []
        host = SimpleNamespace(_emit=lambda event, game: events.append(event), _log=events.append)
        class Game:
            def Open(self): events.append('original-open'); return 42
            def Close(self): events.append('original-close')
            def OnKeyDown(self, key): events.append(key); return 7
        window = SimpleNamespace(IsShow=lambda: False, Open=lambda: events.append('wiki-open'), Destroy=lambda: events.append('wiki-destroy'))
        handle = client.register_window(SimpleNamespace(id='fixture.wiki'), 'wiki', lambda game: window, 'F12')
        app = SimpleNamespace(DIK_F12=88, DIK_U=22, DIK_LCONTROL=1, DIK_RCONTROL=2, IsPressed=lambda key: False)
        with patch.dict(sys.modules, {'m2hub_runtime': host, 'app': app}):
            client.install({'GameWindow': Game})
            client.install({'GameWindow': Game})
            game = Game()
            self.assertEqual(game.Open(), 42)
            self.assertTrue(game.OnKeyDown(88))
            self.assertEqual(game.OnKeyDown(9), 7)
            game.onPressKeyDict = {88: True}
            self.assertEqual(game.OnKeyDown(88), 7)
            game.Close()
        self.assertLess(events.index('wiki-destroy'), events.index('original-close'))
        self.assertEqual(events.count('game.open'), 1)
        self.assertIsNone(handle.window)

    def test_preferences_recover_previous_generation_and_are_world_scoped(self):
        client = module('client_state_fixture', ROOT / 'addonhub/runtime/m2hub_client.py')
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp') as temporary, patch.dict('os.environ', {'LOCALAPPDATA': temporary}), \
                patch.dict(sys.modules, {'m2hub_config': SimpleNamespace(STATE_NAMESPACE='a' * 32)}):
            client.save_state('fixture.wiki', {'page': 1})
            client.save_state('fixture.wiki', {'page': 2})
            Path(client._state_path('fixture.wiki')).write_text('{broken')
            self.assertEqual(client.load_state('fixture.wiki'), {'page': 1})
            with self.assertRaises(ValueError): client.save_state('../escape', {})
            with self.assertRaises(ValueError): client.save_state('fixture.wiki', {'large': 'x' * 40000})


@unittest.skipIf(codec.lzokay is None, 'Optional pack codec required')
class PocketIntegrationTests(unittest.TestCase):
    def test_playable_copy_is_separate_world_bound_and_blocks_changed_executable(self):
        from test_addon_integration import make_world
        from addonhub.client_adapter import create_playable_copy, ClientAdapter
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp') as temporary:
            studio, source = make_world(Path(temporary))
            (source / 'metin2client.exe').write_bytes(b'original executable fixture')
            state = studio.state / 'addons'
            with patch('addonhub.client_adapter.recorded_profile', return_value={'id': 'fixture-profile'}):
                target = create_playable_copy(source, state)
                backend = ClientAdapter(target, state)
                self.assertEqual(backend.server_root, studio.root)
                self.assertTrue(backend.profile()['writable'])
                backend.check_writable()
                (target / 'metin2client.exe').write_bytes(b'changed')
                self.assertFalse(backend.profile()['writable'])
                with self.assertRaisesRegex(ValueError, 'executable changed'):
                    backend.check_writable()
            self.assertEqual((source / 'metin2client.exe').read_bytes(), b'original executable fixture')

    def test_install_refresh_stale_review_disable_and_exact_remove(self):
        from test_addon_integration import make_world
        with tempfile.TemporaryDirectory(dir=ROOT / '.test-tmp') as temporary:
            studio, source = make_world(Path(temporary))
            pack = codec.EterPack.open(source / 'pack')
            files = pack.files()
            files['game.py'] = b'class GameWindow(object):\n def Open(self): pass\n def Close(self): pass\n def OnKeyDown(self, key): pass\n'
            index, data = pack.build(files)
            (source / 'pack/root.index').write_bytes(index)
            (source / 'pack/root.data').write_bytes(data)
            original = (index, data)
            current = reference()
            current['meta'].pop('generated_at')
            with patch('addonhub.knowledge.build_index', side_effect=lambda studio: copy.deepcopy(current)):
                service = studio.addons
                target = Path(service.post('sandbox', {})['path'])
                def apply(ident, action='install'):
                    plan = service.post('plan', {'addon_id': ident, 'action': action})['plan']
                    self.assertTrue(plan['can_apply'], plan['conflicts'])
                    return service.post('apply', {'plan_id': plan['id']})
                apply('community.map-legend')
                apply('community.pocket-wiki')
                self.assertIn('m2hub_reference.py', codec.EterPack.open(target / 'pack').files())
                self.assertEqual(service.state()['reference']['counts']['recipes'], 1)
                review = service.post('plan', {'addon_id': 'community.pocket-wiki', 'action': 'refresh-data'})['plan']
                current['meta']['snapshot'] = 'b' * 64
                with self.assertRaisesRegex(ValueError, 'changed after review'):
                    service.post('apply', {'plan_id': review['id']})
                apply('community.pocket-wiki', 'refresh-data')
                apply('community.pocket-wiki', 'disable')
                self.assertNotIn('m2hub_reference.py', codec.EterPack.open(target / 'pack').files())
                apply('community.pocket-wiki', 'enable')
                apply('community.pocket-wiki', 'remove')
                apply('community.map-legend', 'remove')
                self.assertEqual(tuple((target / 'pack' / name).read_bytes() for name in ('root.index', 'root.data')), original)
                self.assertEqual(tuple((source / 'pack' / name).read_bytes() for name in ('root.index', 'root.data')), original)
