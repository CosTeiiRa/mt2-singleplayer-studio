from types import SimpleNamespace
import unittest

from metin2_studio.item_usage import drop_route, drop_summary, item_usage, item_drop_summary


def node(ident, entries, source='chest-base'):
    return {'meta': {'source': source, 'key': ident},
            'group': SimpleNamespace(entries=[SimpleNamespace(item=item, count='1', prob='5') for item in entries])}


class DropRouteTests(unittest.TestCase):
    def test_pool_namespace_does_not_confuse_an_item_with_a_pool(self):
        loot = node('8001', ['71084'])
        self.assertIsNone(drop_route(node('mob', ['8001'], 'mob-base'), '71084', {'8001': [loot]}))
        route = drop_route(node('mob', ['s8001'], 'mob-base'), '71084', {'8001': [loot]})
        self.assertEqual([step['item'] for step in route], ['s8001', '71084'])

    def test_cycles_terminate_and_shortest_matching_path_wins(self):
        first, second = node('1', ['s2']), node('2', ['s1', '71084'])
        route = drop_route(first, '71084', {'1': [first], '2': [second]})
        self.assertEqual(len(route), 2)
        self.assertIsNone(drop_route(first, '99999', {'1': [first], '2': [second]}))
        self.assertEqual(len(drop_route(node('3', ['s1', '71084']), '71084', {'1': [first], '2': [second]})), 1)

    def test_invalid_item_ids_are_rejected_before_reading_any_source(self):
        for ident in ('s8001', '../71084', '0', '-1', '71084.0', '4294967296'):
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                item_usage(None, ident, None)
        for ident in ('ss8001', '../71084', '0', '-1', '71084.0', '4294967296'):
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                item_drop_summary(None, ident)

    def test_summary_counts_distinct_targets_through_nested_and_cyclic_pools(self):
        first, second = node('1', ['s2']), node('2', ['s1', '71084'])
        pools = {'1': [first], '2': [second]}
        nodes = []
        for ident, key, source, entries in (
            ('8001', 'drop', 'mob-base', ['s1', 's1']),
            ('8001', 'kill', 'mob-base', ['71084']),
            ('8001', 'drop', 'mob-m3', ['71084']),
            ('8002', 'drop', 'mob-base', ['s2']),
            ('8003', 'drop', 'mob-base', ['1']),
        ):
            row = node(key, entries, source)
            row['meta'].update(id=ident, name='Metin ' + ident, level=10, category='metin')
            nodes.append(row)
        result = drop_summary('71084', nodes, pools, {})
        self.assertEqual(result['counts']['metins'], 2)
        self.assertEqual([row['id'] for row in result['metins']], ['8001', '8002'])
        self.assertFalse(result['zeroParameter'])

    def test_summary_keeps_zero_references_and_separates_chests_from_other_tables(self):
        rows = []
        for ident, category in (('50011', 'lottery'), ('29999', 'chest'), ('8001', 'pool')):
            row = node(ident, ['71084'])
            row['meta'].update(id=ident, name=ident, level=None, category=category)
            rows.append(row)
        rows[0]['group'].entries[0].prob = '0'
        result = drop_summary('71084', rows, {}, {'50011': {'catalogGroups': ['chests']}})
        self.assertEqual(result['counts']['chests'], 1)
        self.assertEqual(result['counts']['pools'], 2)
        self.assertEqual(result['counts']['metins'], 0)
        self.assertTrue(result['zeroParameter'])
