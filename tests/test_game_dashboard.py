from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import zipfile

from metin2_studio.game_dashboard import dashboard_info, retire_collection, history_archive
from metin2_studio.server import Handler


class DashboardTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / '.test-tmp'
        folder.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.studio = SimpleNamespace(compose=self.root, state=self.root)

    def test_configured_port_quotes_comments_and_credentials_are_not_exposed(self):
        (self.root / '.env').write_text('M2_SEBAN_PANEL_PORT="8890" # public port\nM2_PANEL_BIND_ADDRESS=0.0.0.0\nM2_DB_PASSWORD=private-test-secret\n')
        info = dashboard_info(self.studio)
        self.assertEqual(info['economyUrl'], 'http://127.0.0.1:8890/economy')
        self.assertNotIn('secret', json.dumps(info))
        self.assertFalse(info['archiveAvailable'])

    def test_default_and_configured_bind_addresses(self):
        self.assertEqual(dashboard_info(self.studio)['economyUrl'], 'http://127.0.0.1:7790/economy')
        for setting, host in [('M2_HOST_BIND_ADDRESS=192.168.56.1', '192.168.56.1'), ('M2_PANEL_BIND_ADDRESS=::', '[::1]'), ('M2_PANEL_BIND_ADDRESS=::1', '[::1]')]:
            (self.root / '.env').write_text(setting)
            self.assertEqual(dashboard_info(self.studio)['economyUrl'], 'http://' + host + ':7790/economy')

    def test_invalid_ports_and_addresses_do_not_become_links(self):
        for value in ['M2_SEBAN_PANEL_PORT=0', 'M2_SEBAN_PANEL_PORT=65536', 'M2_SEBAN_PANEL_PORT=7790/evil', 'M2_PANEL_BIND_ADDRESS=javascript:alert(1)']:
            (self.root / '.env').write_text(value)
            info = dashboard_info(self.studio)
            self.assertIsNone(info['economyUrl'])
            self.assertIn('error', info)

    def test_schedule_migration_is_idempotent_and_preserves_all_other_preferences(self):
        schedule = {'enabled': True, 'minutes': 60, 'retention': 180, 'filters': {'days': 7}}
        workspace = Mock()
        workspace.preference.return_value = schedule
        retire_collection(workspace)
        workspace.set_preference.assert_called_once_with('economySchedule', {**schedule, 'enabled': False})
        self.assertTrue(schedule['enabled'])
        for value in [None, {**schedule, 'enabled': False}]:
            workspace.reset_mock(); workspace.preference.return_value = value
            retire_collection(workspace)
            workspace.set_preference.assert_not_called()

    def test_archive_preserves_notes_and_committed_wal_records_without_modifying_history(self):
        path = self.root / 'economy.sqlite'
        with closing(sqlite3.connect(path)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('CREATE TABLE snapshots (payload TEXT)')
            writer.execute('CREATE TABLE notes (body TEXT)')
            writer.execute('INSERT INTO snapshots VALUES (?)', ('{"wallet":123}',))
            writer.execute('INSERT INTO notes VALUES (?)', ('My balancing note',))
            writer.commit()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            raw = history_archive(self.root)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            self.assertEqual(writer.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0], 1)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(set(archive.namelist()), {'economy.sqlite', 'README.txt'})
            self.assertIn('separate from the game dashboard', archive.read('README.txt').decode())
            extracted = self.root / 'download.sqlite'
            extracted.write_bytes(archive.read('economy.sqlite'))
        with closing(sqlite3.connect(extracted)) as downloaded:
            self.assertEqual(downloaded.execute('SELECT body FROM notes').fetchone()[0], 'My balancing note')
            self.assertEqual(downloaded.execute('SELECT payload FROM snapshots').fetchone()[0], '{"wallet":123}')
        self.assertFalse(list(self.root.glob('economy-archive-*')))

    def test_missing_and_invalid_archives_preserve_the_original_state(self):
        with self.assertRaisesRegex(ValueError, 'No previous'):
            history_archive(self.root)
        self.assertEqual(list(self.root.iterdir()), [])
        path = self.root / 'economy.sqlite'; path.write_bytes(b'original damaged database')
        with self.assertRaisesRegex(ValueError, 'preserved'):
            history_archive(self.root)
        self.assertEqual(path.read_bytes(), b'original damaged database')

    def request(self, path, post=False):
        handler = Handler.__new__(Handler)
        handler.studio = self.studio  # No analytics object or database query exists.
        handler.path = path; handler.headers = {'Content-Length':'2', 'Content-Type':'application/json'}; handler.guard = Mock()
        handler.connection = Mock(); handler.rfile = io.BytesIO(b'{}')
        handler.send = Mock()
        (handler._post if post else handler.do_GET)()
        return handler.send.call_args

    def test_shortcut_metadata_never_needs_a_running_game_database(self):
        response = self.request('/api/game-dashboard')
        self.assertEqual(response.args[0]['economyUrl'], 'http://127.0.0.1:7790/economy')

    def test_old_analytics_endpoints_cannot_collect_or_enable_a_schedule(self):
        for path, post in [('/api/economy?fresh=1', False), ('/api/economy/export', False), ('/api/economy/capture', True), ('/api/economy/schedule', True), ('/api/economy/experiment', True)]:
            with self.subTest(path=path):
                response = self.request(path, post)
                self.assertEqual(response.args[1], 410)
                self.assertIn('retired', response.args[0]['error'])
