import csv
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from economy import Economy, options
from economy_export import csv_bytes, download, spreadsheet_tables
from test_economy import CATALOG, NOW, observations


def read_csv(raw):
    return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))


class EconomyExportTests(unittest.TestCase):
    def setUp(self):
        self.test_runs = Path(__file__).resolve().parents[1] / 'data' / 'test-runs'
        self.test_runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_runs)
        self.economy = Economy(SimpleNamespace(state=Path(self.temp.name), items=CATALOG))
        self.collect = patch.object(self.economy, 'collect', return_value=observations())
        self.sources = patch('economy.configured_sources', return_value=[])
        self.collect.start()
        self.sources.start()
        self.addCleanup(self.sources.stop)
        self.addCleanup(self.collect.stop)

    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to(self.test_runs.resolve())
        self.temp.cleanup()

    def test_zip_carries_units_scope_definitions_and_all_item_rows(self):
        report = self.economy.export({'population': 'bot', 'stage': 'late'})
        raw, mime, name = download(report, 'zip')
        self.assertEqual(mime, 'application/zip')
        self.assertRegex(name, r'^metin2-economy-\d{8}T\d{6}Z-bot-late-7d\.zip$')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertIsNone(archive.testzip())
            summary = {row['metric']: row for row in read_csv(archive.read('summary.csv'))}
            self.assertEqual(summary['wallet']['value'], '9000')
            self.assertEqual(summary['wallet']['unit'], 'Yang')
            self.assertIn('mixed global', summary['recordedIn']['scope'])
            self.assertEqual(summary['recordedIn']['value'], '10000')
            self.assertEqual(summary['wallet']['population'], 'bot')
            items = read_csv(archive.read('items.csv'))
            self.assertEqual({row['item_id'] for row in items}, {row['id'] for row in report['items']})
            self.assertEqual(next(row for row in items if row['item_id'] == '30001')['median_unit_price_yang'], '200.0')
            self.assertEqual(len(read_csv(archive.read('progression.csv'))), 3)
            self.assertIn('No raw player/account IDs', archive.read('README.txt').decode())
            exported = json.loads(archive.read('report.json'))
            self.assertNotIn('players', exported)
            self.assertNotIn('sales', exported)

    def test_all_matching_history_and_notes_export_without_capturing_or_mixing_scopes(self):
        scope = options({})
        legacy = {key: value for key, value in options({'population': 'all'}).items() if key != 'classification'}
        payload = json.dumps({'metrics': {'wallet': 123, 'stock': 4}, 'items': [{'id': '30001', 'stock': 4}]})
        with self.economy.connect() as conn:
            conn.executemany('INSERT INTO snapshots(at,scope,payload) VALUES (?,?,?)',
                [(NOW - 7200 + i, json.dumps(scope, sort_keys=True), payload) for i in range(95)])
            conn.execute('INSERT INTO snapshots(at,scope,payload) VALUES (?,?,?)', (NOW, json.dumps(legacy, sort_keys=True), payload))
            conn.execute('INSERT INTO snapshots(at,scope,payload) VALUES (?,?,?)', (NOW, json.dumps(options({'population': 'gm'}), sort_keys=True), payload))
            conn.executemany('INSERT INTO notes(at,title,body) VALUES (?,?,?)', [(NOW + i, 'note', 'text') for i in range(55)])
        report = self.economy.export({})
        self.assertEqual(len(report['history']), 90)
        self.assertEqual(len(report['snapshots']), 95)
        self.assertEqual(len(report['notes']), 55)
        self.assertEqual(len(report['legacySnapshots']), 1)
        self.assertEqual(report['legacySnapshots'][0]['filters']['population'], 'all')
        tables = spreadsheet_tables(report)
        self.assertEqual(len(read_csv(tables['snapshots.csv'])), 95)
        self.assertEqual(len(read_csv(tables['snapshot_items.csv'])), 95)
        self.assertEqual(len(read_csv(tables['journal.csv'])), 55)
        self.assertEqual(read_csv(tables['legacy_snapshots.csv'])[0]['classification'], '')
        with self.economy.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0], 97)
        self.assertEqual(len(self.economy.export({'population': 'gm'})['legacySnapshots']), 0)

    def test_offline_export_keeps_history_and_nulls_unavailable_sources(self):
        self.economy.capture({})
        with patch.object(self.economy, 'collect', side_effect=ValueError('World stopped')):
            report = self.economy.export({})
        raw, mime, name = download(report, 'json')
        data = json.loads(raw)
        self.assertFalse(data['connected'])
        self.assertIsNone(data['metrics']['successes'])
        self.assertIsNone(data['gm']['wallet'])
        self.assertIsNone(data['prices']['matched'])
        self.assertIsNone(data['bands'][0]['wallet'])
        self.assertEqual(data['snapshots'][0]['metrics']['wallet'], 10500)
        tables = spreadsheet_tables(data)
        summary = {row['metric']: row for row in read_csv(tables['summary.csv'])}
        self.assertEqual(summary['successes']['value'], '')
        self.assertEqual(summary['successes']['availability'], 'unavailable')
        self.assertEqual(summary['priceMovement']['availability'], 'unavailable')
        self.assertEqual(next(row for row in read_csv(tables['coverage.csv']) if row['measurement'] == 'Collection')['explanation'], 'World stopped')
        self.assertIn('application/json', mime)

    def test_partial_item_sources_and_decimal_prices_preserve_meaning(self):
        raw = observations()
        raw['available'].remove('actions')
        raw['actions'] = []
        raw['sales'][0][2] = 3
        with patch.object(self.economy, 'collect', return_value=raw):
            report = self.economy.export({})
        encoded, _, _ = download(report, 'json')
        exported = json.loads(encoded)
        item = next(row for row in exported['items'] if row['id'] == '30001')
        self.assertIsNone(item['uses'])
        self.assertIsNone(item['burns'])
        self.assertAlmostEqual(item['unitPrice'], 1000 / 3)
        self.assertEqual(next(row for row in report['items'] if row['id'] == '30001')['uses'], 0)

    def test_csv_round_trips_unicode_quotes_newlines_and_escapes_formulas(self):
        raw = csv_bytes(('text', 'number'), [('Épée, "rare"\nline', -12.5), ('=1+1', 0), ('  @SUM(A1)', 1), ('\tcommand', 2), ('-name', 3)])
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        rows = read_csv(raw)
        self.assertEqual(rows[0], {'text': 'Épée, "rare"\nline', 'number': '-12.5'})
        self.assertEqual(rows[1]['text'], "'=1+1")
        self.assertTrue(all(row['text'].startswith("'") for row in rows[1:]))
        self.economy.note({'title': '=1+1', 'body': 'Épée, "rare"\nline'})
        report = self.economy.export({})
        self.assertEqual(read_csv(spreadsheet_tables(report)['journal.csv'])[0]['title'], "'=1+1")
        data = json.loads(download(report, 'json')[0])
        self.assertEqual(data['notes'][0]['title'], '=1+1')

    def test_invalid_formats_and_filters_are_rejected(self):
        with self.assertRaises(ValueError):
            download({}, 'xlsx')
        with patch.object(self.economy, 'collect') as collect:
            with self.assertRaises(ValueError):
                self.economy.export({'population': '../../'})
            collect.assert_not_called()
