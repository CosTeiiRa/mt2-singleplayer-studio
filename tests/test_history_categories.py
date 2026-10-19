import unittest
from workspace import history_category, history_areas


class HistoryCategoryTests(unittest.TestCase):
    def test_known_old_reconciliations_and_their_rollbacks_keep_their_group(self):
        for title in ('Reconcile custom changes after update', 'Merge custom changes onto the updated game',
                      'Resolve customised native crafting changes'):
            self.assertEqual(history_category(title), 'reconciliation')
            self.assertEqual(history_category('Revert: Revert: ' + title), 'reconciliation')

    def test_gameplay_updates_are_not_mistaken_for_game_update_reconciliation(self):
        for title in ('Update world settings', 'Update crafting recipe: Red Potion', 'Remove recipe: Potion',
                      'Create quest', 'Change EXP to 150%', 'Update a recipe after testing'):
            self.assertEqual(history_category(title), 'gameplay')

    def test_explicit_categories_and_merge_metadata_outweigh_title_heuristics(self):
        self.assertEqual(history_category('A chosen merge', {'reconciled': {}}), 'reconciliation')
        self.assertEqual(history_category('Keep the game baseline', {'deferred': {}}), 'reconciliation')
        self.assertEqual(history_category('Custom title', {'historyCategory': 'reconciliation'}), 'reconciliation')
        self.assertEqual(history_category('Reconcile custom changes after update', {'category': 'gameplay'}), 'gameplay')


class HistoryAreaTests(unittest.TestCase):
    def test_files_use_their_content_area_instead_of_the_save_title(self):
        examples = {
            'quests': ['linux-port/docker/game/custom-quests/studio_test.quest', 'locale/quest/npc.lua', 'locale/quest/studio-source-list.txt'],
            'crafting': ['share-add/studio-crafting.json', 'locale/cube.txt', 'share-add/cube.seon_pyeong.txt', 'locale/quest/libs/crafting/crafting_data.lua'],
            'drops': ['locale/mob_drop_item.txt', 'share-add/mob_drop_item.m3.append.txt', 'locale/special_item_group.txt', 'locale/etc_drop_item.txt', 'locale/common_drop_item.txt'],
            'settings': ['.env', 'locale/quest/settings.lua'],
            'maps': ['locale/map/map_a/Setting.txt', 'locale/map/map_a/regen', 'locale/special_spawns.txt', 'locale/group.txt', 'locale/group_group.txt'],
            'shops': ['locale/shop_table_ex.txt'], 'fishing': ['locale/fishing.txt'],
            'alchemy': ['locale/dragon_soul_table.txt'], 'items': ['locale/blend.txt'],
            'skills': ['locale/skill_power.txt'], 'events': ['locale/quest/oxquiz.lua'],
            'files': ['Dockerfile', '.dockerignore', 'share-add/unrecognised.lua'],
        }
        for area, paths in examples.items():
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(history_areas([{'path': path}]), [area])

    def test_mixed_saves_keep_every_type_once_with_normalised_paths(self):
        files = [{'path': path} for path in ('LOCALE\\CUBE.TXT', 'custom-quests/test.quest',
                                           'locale/cube.txt', '.env', 'Dockerfile')]
        self.assertEqual(history_areas(files), ['crafting', 'files', 'quests', 'settings'])
        self.assertEqual(history_areas([]), ['files'])
