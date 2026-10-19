import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from installation import REQUIRED
from tools.import_existing import import_existing


class HistoryImportTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / '.test-tmp'
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.base = Path(self.temp.name)
        self.server = self.base / 'game' / 'Serwer'
        for name in REQUIRED + ('linux-port/docker/docker-compose.yml',):
            path = self.server / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('2.2.108' if name == 'VERSION' else 'fixture', 'utf-8')
        self.source = self.base / 'old-state'
        self.source.mkdir()
        (self.source / 'studio-world.json').write_text(json.dumps({'serverRoot': str(self.server)}), 'utf-8')
        with closing(sqlite3.connect(self.source / 'workspace.sqlite')) as conn:
            conn.execute('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)')
            conn.execute('INSERT INTO meta VALUES (?,?)', ('installation', str(self.server)))
            conn.execute('CREATE TABLE history(value TEXT)')
            conn.execute('INSERT INTO history VALUES (?)', ('preserved draft',))
            conn.commit()
        backup = self.source / 'backups' / 'example'
        backup.mkdir(parents=True)
        (backup / '0.before').write_bytes(b'original bytes\x00\xff')
        self.destination = self.base / 'new-app/data/world'
        self.settings = self.base / 'new-app/data/studio-settings.json'

    def tearDown(self):
        self.temp.cleanup()

    def run_import(self, hub=None):
        return import_existing(self.server, self.source, hub, destination=self.destination, settings_path=self.settings)

    def test_sqlite_snapshot_and_backups_are_copied_without_rewriting_source(self):
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        self.run_import()
        self.assertEqual(before, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()})
        with closing(sqlite3.connect(self.destination / 'workspace.sqlite')) as conn:
            self.assertEqual(conn.execute('SELECT value FROM history').fetchone()[0], 'preserved draft')
        self.assertEqual((self.destination / 'backups/example/0.before').read_bytes(), b'original bytes\x00\xff')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_import()

    def test_another_world_is_rejected_before_creating_destination(self):
        (self.source / 'studio-world.json').write_text(json.dumps({'serverRoot': str(self.base / 'other')}), 'utf-8')
        with self.assertRaisesRegex(ValueError, 'another world'):
            self.run_import()
        self.assertFalse(self.destination.exists())

    def test_only_matching_world_hub_history_is_imported_without_adopting_payloads(self):
        hub = self.base / 'old-hub'
        client = self.server.parent / 'Klient'
        key = hashlib.sha256(os.path.normcase(str(client.resolve())).encode('utf-8')).hexdigest()[:24]
        for ident in (key, 'foreign-target'):
            target = hub / 'targets' / ident
            target.mkdir(parents=True)
            (target / 'state.json').write_text('{}', 'utf-8')
            (target / 'history.jsonl').write_text(json.dumps({'time': '2026-10-18T10:00:00+00:00', 'action': 'install', 'addon_id': ident, 'backup_directory': str(target / 'backups')})+'\n', 'utf-8')
        report = self.run_import(hub)
        self.assertEqual(report['legacy_addon_events'], 1)
        rows = json.loads((self.destination / 'legacy-addon-history.json').read_text('utf-8'))['items']
        self.assertTrue(rows[0]['legacy'])
        self.assertFalse((self.destination / 'addons').exists())
