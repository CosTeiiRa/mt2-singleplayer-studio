import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from economy import Economy, analyse, options, price_change, configured_sources


NOW = 2000000000
CATALOG = {'20': {'name': 'Long Sword+0', 'catalogGroups': ['equipment']},
           '29': {'name': 'Long Sword+9', 'catalogGroups': ['equipment']},
           '30001': {'name': 'Material', 'catalogGroups': ['materials']}}


def observations():
    return {'at': NOW, 'days': 7, 'gmSeparated': True,
            'available': ['players', 'stock', 'sales', 'refines', 'money', 'actions', 'active'],
            'players': [[1, 100, 20, 'human', 1000, 2, 60, NOW],
                        [2, 100, 60, 'human', 500, 0, 60, NOW],
                        [3, 200, 90, 'bot', 9000, 0, 300, NOW]],
            'active': [[100, 20, 'human'], [100, 60, 'human']],
            'stock': [[30001, 20, 'human', 30, 2, 0, 5], [30001, 90, 'bot', 70, 1, 0, 0],
                      [29, 90, 'bot', 1, 1, 1, 0], [30001, 0, 'unknown', 40, 1, 0, 0]],
            'sales': [[NOW-20, 30001, 5, 1000, 0, 1, 3, 90, 'bot'],
                      [NOW-20, 20, 1, 700, 0, 3, 1, 20, 'human'],
                      [NOW-20, 30001, 1, 100, 2, 1, 3, 90, 'bot']],
            'refines': [['2033-05-18', 20, 'human', 1, 'POWER', 2],
                        ['2033-05-18', 90, 'bot', 0, 'SCROLL', 1]],
            'money': [['2033-05-18', 'MONSTER', 10000, 0, 1], ['2033-05-18', 'REFINE', 0, 4000, 1]],
            'actions': [['GET', 30001, 20, 'human', 6], ['USE_ITEM', 30001, 20, 'human', 2],
                        ['REMOVE (REFINE SUCCESS)', 20, 20, 'human', 2],
                        ['REMOVE (REFINE FAIL)', 20, 90, 'bot', 1], ['STONE_KILL', 8001, 20, 'human', 4]]}


class EconomyMathTests(unittest.TestCase):
    def test_accounts_are_deduplicated_and_activity_is_not_seed_last_play(self):
        report = analyse(observations(), options({}), CATALOG)
        self.assertEqual(report['metrics']['accounts'], 2)
        self.assertEqual(report['metrics']['activeAccounts'], 1)
        self.assertEqual(report['metrics']['medianWallet'], 5250)
        self.assertEqual(report['metrics']['wallet'], 10500)
        self.assertEqual(report['metrics']['won'], 2)

    def test_stage_population_and_seller_filters_do_not_filter_global_money(self):
        report = analyse(observations(), options({'population': 'bot', 'stage': 'late'}), CATALOG)
        self.assertEqual(report['metrics']['wallet'], 9000)
        self.assertEqual(report['metrics']['stock'], 71)
        self.assertEqual(report['metrics']['turnover'], 1000)
        self.assertEqual(report['metrics']['trades'], 1)
        self.assertEqual(report['metrics']['recordedNet'], 6000)
        self.assertEqual(report['metrics']['scrollAttempts'], 1)
        self.assertTrue(any('Won' in message for message in report['alerts']))

    def test_successful_refine_conversion_is_not_counted_as_destruction(self):
        report = analyse(observations(), options({}), CATALOG)
        self.assertEqual(report['metrics']['burns'], 1)
        herb = next(row for row in report['items'] if row['id'] == '30001')
        self.assertEqual(herb['stock'], 100)
        self.assertEqual(herb['acquisitions'], 6)
        self.assertEqual(herb['uses'], 2)
        self.assertNotIn('consumedUnits', herb)
        self.assertEqual(next(row for row in report['items'] if row['id'] == '29')['grade'], 9)

    def test_missing_sources_are_unavailable_not_measured_zero(self):
        report = analyse({'at': NOW, 'available': []}, options({}), CATALOG)
        for key in ('wallet', 'stock', 'turnover', 'attempts', 'recordedNet', 'activeAccounts'):
            self.assertIsNone(report['metrics'][key], key)

    def test_prices_need_matched_commodities_and_ignore_equipment_quality(self):
        catalog = {str(i): {'catalogGroups': ['materials']} for i in (1, 2, 3)}
        catalog['20'] = CATALOG['20']
        old = {str(i): [100] * 5 for i in (1, 2, 3, 20)}
        new = {str(i): [120] * 5 for i in (1, 2, 3)}
        new['20'] = [99999] * 5
        result = price_change(new, old, catalog)
        self.assertAlmostEqual(result['percent'], 20)
        self.assertEqual(result['matched'], 3)
        new['3'] = [120] * 4
        self.assertIsNone(price_change(new, old, catalog)['percent'])

    def test_invalid_filters_are_rejected(self):
        for values in ({'days': '7;DROP TABLE player'}, {'population': 'admin'}, {'stage': '../'},
                       {'early': 80, 'mid': 50}, {'days': 0}, {'early': 0}, {'mid': 121}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                options(values)

    def test_regular_economy_excludes_gm_assets_actions_and_either_trade_party(self):
        raw = observations()
        raw['players'] += [[9, 999, 90, 'gm', 1000000000, 0, 100, NOW], [10, 999, 20, 'gm', 50000, 0, 100, NOW]]
        raw['active'] += [[999, 90, 'gm'], [999, 20, 'gm']]
        raw['stock'] += [[30001, 90, 'gm', 1000, 1, 0, 0], [30001, 0, 'gm', 200, 1, 0, 0]]
        raw['refines'] += [['2033-05-18', 20, 'gm', 1, 'POWER', 100]]
        raw['actions'] += [['STONE_KILL', 8001, 90, 'gm', 100]]
        raw['sales'] += [[NOW-20, 30001, 1, 10000, 0, 9, 3, 90, 'bot', 1, 90],
                         [NOW-20, 30001, 1, 20000, 0, 1, 10, 20, 'gm', 0, 20],
                         [NOW-20, 30001, 1, 50000, 0, 10, 9, 90, 'gm', 1, 20]]
        raw['banks'] = [['Account safebox Yang', 25, 0, 'human'], ['Account safebox Yang', 900000, 0, 'gm']]
        raw['shopbanks'] = [['Shop safebox Yang', 40, 2, 'bot'], ['Shop safebox Yang', 50000, 1, 'gm']]
        regular = analyse(raw, options({}), CATALOG)
        self.assertEqual(regular['metrics']['wallet'], 10500)
        self.assertEqual(regular['metrics']['stock'], 101)
        self.assertEqual(regular['metrics']['turnover'], 1700)
        self.assertEqual(regular['metrics']['trades'], 2)
        self.assertEqual(regular['metrics']['attempts'], 3)
        self.assertEqual(regular['activity']['8001'], 4)
        self.assertEqual(regular['banks'], [['Account safebox Yang', 25, 0], ['Shop safebox Yang', 40, 2]])
        self.assertEqual(regular['gm']['accounts'], 1)
        self.assertEqual(regular['gm']['involvedTrades'], 3)
        self.assertEqual(sum(row['turnover'] for row in regular['bands']), 1700)
        gm = analyse(raw, options({'population': 'gm'}), CATALOG)
        self.assertEqual(gm['metrics']['wallet'], 1000050000)
        self.assertEqual(gm['metrics']['stock'], 1200)
        self.assertEqual(gm['metrics']['accounts'], 1)
        self.assertEqual(gm['metrics']['turnover'], 80000)
        self.assertEqual(gm['metrics']['trades'], 3)
        self.assertEqual(gm['banks'], [['Account safebox Yang', 900000, 0], ['Shop safebox Yang', 50000, 1]])
        self.assertEqual(next(row for row in gm['bands'] if row['key'] == 'early')['turnover'], 20000)
        self.assertEqual(analyse(raw, options({'population': 'gm', 'stage': 'late'}), CATALOG)['metrics']['turnover'], 60000)
        self.assertEqual(analyse(raw, options({'population': 'bot'}), CATALOG)['metrics']['turnover'], 1000)
        self.assertEqual(analyse(raw, options({'population': 'all'}), CATALOG)['metrics']['turnover'], 81700)

    def test_missing_registry_cannot_silently_claim_gm_free_data(self):
        raw = observations()
        raw['gmSeparated'] = False
        for population in ('regular', 'human', 'bot', 'gm', 'unknown'):
            with self.subTest(population=population), self.assertRaisesRegex(ValueError, 'GM classification'):
                analyse(raw, options({'population': population}), CATALOG)
        report = analyse(raw, options({'population': 'all'}), CATALOG)
        self.assertFalse(report['gm']['identified'])


class EconomyStorageTests(unittest.TestCase):
    def test_offline_report_keeps_saved_figures_separate_and_scope_matched(self):
        with patch.object(self.economy, 'collect', return_value=observations()), patch('economy.configured_sources', return_value=[]):
            self.economy.capture({})
        with patch.object(self.economy, 'collect', side_effect=ValueError('World stopped')), patch('economy.configured_sources', return_value=[]):
            offline=self.economy.report({})
            self.assertFalse(offline['connected'])
            self.assertIsNone(offline['metrics']['wallet'])
            self.assertEqual(offline['lastSaved']['metrics']['wallet'],10500)
            self.assertEqual(offline['lastSaved']['at'],NOW)
            self.assertEqual(next(r for r in offline['lastSaved']['items'] if r['id']=='30001')['name'],'Material')
            self.assertIsNone(self.economy.report({'population':'gm'})['lastSaved'])
            self.assertIsNone(self.economy.report({'stage':'early'})['lastSaved'])
            self.assertFalse(any('Fewer than' in a for a in offline['alerts']))

    def test_stopped_docker_has_actionable_sanitized_error(self):
        failed=SimpleNamespace(returncode=1,stdout='',stderr='secret failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine')
        with patch('economy.subprocess.run',return_value=failed):
            with self.assertRaisesRegex(ValueError,'Open Docker Desktop') as error:self.economy.query(['SELECT 1;'])
        self.assertNotIn('secret',str(error.exception))

    def setUp(self):
        self.test_runs = Path(__file__).resolve().parents[1] / 'data' / 'test-runs'
        self.test_runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_runs)
        self.studio = SimpleNamespace(state=Path(self.temp.name), compose=Path(self.temp.name), items=CATALOG)
        self.economy = Economy(self.studio)

    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to(self.test_runs.resolve())
        self.temp.cleanup()

    def test_capture_persists_aggregates_and_stock_loss_without_player_ids(self):
        raw = observations()
        with patch.object(self.economy, 'collect', return_value=raw), patch('economy.configured_sources', return_value=[]):
            self.economy.capture({})
            with self.economy.connect() as conn:
                payload = json.loads(conn.execute('SELECT payload FROM snapshots').fetchone()[0])
            self.assertNotIn('players', payload)
            self.assertNotIn('sales', payload)
            self.assertTrue({'at', 'metrics', 'items', 'available', 'bands', 'rarity'} <= set(payload))
            self.assertTrue(all('owner_id' not in row and 'account' not in row for row in payload['items']))
            raw['at'] += 3600
            raw['stock'] = []
            raw['sales'] = []
            raw['actions'] = []
            report = self.economy.report({})
            herb = next(row for row in report['items'] if row['id'] == '30001')
            self.assertEqual(herb['stockChange'], -100)
            self.assertEqual(report['baseline']['at'], NOW)
            self.assertEqual(report['history'][0]['wallet'], 10500)
            self.assertIsNone(self.economy.report({'stage': 'early'})['baseline'])

    def test_notes_are_local_and_validated(self):
        self.economy.note({'title': 'Exchange event', 'body': 'Consume excess herbs; watch scroll and weapon stock.'})
        with self.economy.connect() as conn:
            self.assertEqual(conn.execute('SELECT title FROM notes').fetchone()[0], 'Exchange event')
        for values in ({'title': ''}, {'title': 'x' * 121}, {'title': 'x', 'body': 'x' * 1501}):
            with self.assertRaises(ValueError):
                self.economy.note(values)

    def test_database_command_uses_read_only_transaction_and_hides_errors(self):
        good = SimpleNamespace(returncode=0, stdout='{"set":"test","row":[1]}\n')
        with patch('economy.subprocess.run', return_value=good) as run:
            self.assertEqual(self.economy.query(['SELECT 1;']), {'test': [[1]]})
            sql = run.call_args.kwargs['input']
            self.assertIn('SET TRANSACTION READ ONLY', sql)
            self.assertIn('WITH CONSISTENT SNAPSHOT', sql)
            self.assertTrue(sql.endswith('ROLLBACK;'))
            self.assertNotIn('password', sql.lower())
        with patch('economy.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='secret credentials')):
            with self.assertRaisesRegex(ValueError, 'read-only database') as error:
                self.economy.query(['SELECT 1;'])
            self.assertNotIn('secret', str(error.exception))

    def test_collection_skips_unsupported_schema(self):
        with patch.object(self.economy, 'query', return_value={'schema': []}) as query:
            raw = self.economy.collect(7)
            self.assertEqual(raw['available'], [])
            self.assertIn('stock', raw['missing'])
            self.assertEqual(query.call_count, 1)

    def test_offline_report_keeps_saved_history_and_never_replaces_live_gaps_with_zero(self):
        with patch.object(self.economy, 'collect', return_value=observations()), patch('economy.configured_sources', return_value=[]):
            self.economy.capture({})
        with patch.object(self.economy, 'collect', side_effect=ValueError('World stopped')), patch('economy.configured_sources', return_value=[]):
            report = self.economy.report({})
        self.assertFalse(report['connected'])
        self.assertEqual(report['error'], 'World stopped')
        self.assertEqual(len(report['history']), 1)
        self.assertIsNone(report['metrics']['wallet'])
        self.assertIsNone(report['metrics']['recordedNet'])

    def test_invalid_filter_is_rejected_before_database_access(self):
        with patch.object(self.economy, 'collect') as collect, self.assertRaises(ValueError):
            self.economy.report({'days': '7 OR 1=1'})
        collect.assert_not_called()

    def test_older_mixed_snapshots_are_preserved_and_never_used_as_clean_baseline(self):
        old_scope = {key: value for key, value in options({'population': 'all'}).items() if key != 'classification'}
        payload = {'metrics': {'wallet': 999999999, 'stock': 100}, 'items': []}
        with self.economy.connect() as conn:
            conn.execute('INSERT INTO snapshots(at,scope,payload) VALUES (?,?,?)', (NOW-3600, json.dumps(old_scope, sort_keys=True), json.dumps(payload)))
        with patch.object(self.economy, 'collect', return_value=observations()), patch('economy.configured_sources', return_value=[]):
            clean = self.economy.report({})
            self.assertEqual(clean['history'], [])
            self.assertIsNone(clean['baseline'])
            self.assertEqual(clean['legacyHistory'][0]['wallet'], 999999999)
            self.economy.capture({})
            clean = self.economy.report({})
            self.assertEqual(len(clean['history']), 1)
            self.assertEqual(len(clean['legacyHistory']), 1)
        with self.economy.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0], 2)


class EconomySourceTests(unittest.TestCase):
    def test_configured_sources_deduplicate_targets_and_cycle_safe_pool_items(self):
        def entry(ident):
            return SimpleNamespace(item=ident)
        tables = {'mob': [SimpleNamespace(key='one', entries=[entry('s1'), entry('20')]),
                          SimpleNamespace(key='two', entries=[entry('s1')])],
                  'chest': [SimpleNamespace(key='pool', entries=[entry('s1'), entry('20'), entry('29')])]}
        metadata = [{'source': 'mob-base', 'key': key, 'id': '8001', 'name': 'Metin', 'level': 5, 'category': 'metin'} for key in ('one', 'two')]
        metadata.append({'source': 'chest-base', 'key': 'pool', 'id': '1', 'name': 'Pool', 'level': None, 'category': 'pool'})
        studio = SimpleNamespace(sources={'mob-base': (None, 'mob', ''), 'chest-base': (None, 'chest', '')},
                                 source_raw=lambda _: b'constant', groups=lambda _: metadata,
                                 dt=SimpleNamespace(logical_groups=lambda filename, _: tables[filename]))
        result = configured_sources(studio)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['items'], 2)
        self.assertEqual(result[0]['pools'], 1)
        self.assertEqual(len(result[0]['groups']), 2)
