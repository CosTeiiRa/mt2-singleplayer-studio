import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from metin2_studio.installation import REQUIRED, bind_state, default_root, load_settings, port_number, resolve_settings, save_settings, server_root, world_state


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.test_runs = Path(__file__).resolve().parents[1] / 'data/test-runs'
        self.test_runs.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_runs)
        self.base = Path(self.temp.name)
        self.game = self.base / 'My existing game' / 'Serwer'
        for rel in REQUIRED + ('linux-port/docker/docker-compose.yml',):
            target = self.game / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('2.2.106' if rel == 'VERSION' else 'fixture', 'utf-8')
        self.settings = self.base / 'studio/data/studio-settings.json'
        self.data = self.base / 'studio/data'

    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to(self.test_runs.resolve())
        self.temp.cleanup()

    def resolve(self, **kwargs):
        return resolve_settings(saved={}, environ={}, base=self.data, **kwargs)

    def test_no_personal_default_or_drive_scan(self):
        self.assertIsNone(default_root({}, {}))
        with self.assertRaisesRegex(ValueError, 'Install Studio.bat'):
            self.resolve()
        self.assertFalse(self.data.exists())

    def test_choose_serwer_or_existing_installation_parent(self):
        self.assertEqual(server_root(self.game), self.game.resolve())
        self.assertEqual(server_root(self.game.parent), self.game.resolve())
        self.assertEqual(server_root('"' + str(self.game) + '"'), self.game.resolve())

    def test_environment_is_supported_without_local_settings(self):
        self.assertEqual(default_root({}, {'METIN2_STUDIO_SERVER_ROOT': str(self.game)}), self.game.resolve())

    def test_missing_package_file_is_reported_without_creating_anything(self):
        (self.game / 'files/drop_tables.py').unlink()
        with self.assertRaisesRegex(ValueError, 'files/drop_tables.py'):
            self.resolve(root=self.game)
        self.assertFalse(self.data.exists())

    def test_port_validation(self):
        for value in (-1, 0, 1023, 65536, True, '8765;command', '8.5', '\u0668\u0667\u0666\u0665'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                port_number(value)
        self.assertEqual(port_number('8766'), 8766)

    def test_worlds_have_separate_data_and_selected_override_is_scoped(self):
        other = self.base / 'another-world'
        self.assertNotEqual(world_state(self.game, self.data), world_state(other, self.data))
        saved = {'schema': 1, 'serverRoot': str(other), 'stateDir': str(self.base / 'old-history'), 'port': 8766}
        result = resolve_settings(root=self.game, saved=saved, environ={}, base=self.data)
        self.assertNotEqual(result['stateDir'], saved['stateDir'])
        self.assertEqual(result['port'], 8766)

    def test_check_does_not_write_game_or_studio_files(self):
        before = {str(p): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        result = self.resolve(root=self.game)
        self.assertEqual(result['serverVersion'], '2.2.106')
        self.assertFalse(self.data.exists())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.game.rglob('*') if p.is_file()})

    def test_roundtrip_writes_only_local_settings_and_world_binding(self):
        result = self.resolve(root=self.game, port=8766)
        save_settings(result, self.settings)
        saved = load_settings(self.settings)
        again = resolve_settings(saved=saved, environ={}, base=self.data)
        self.assertEqual(again, result)
        self.assertEqual(set(saved), {'schema', 'serverRoot', 'stateDir', 'port'})
        self.assertTrue((Path(result['stateDir']) / 'studio-world.json').exists())

    def test_other_world_cannot_reuse_history(self):
        result = self.resolve(root=self.game)
        bind_state(result)
        with self.assertRaisesRegex(ValueError, 'another server'):
            bind_state({**result, 'serverRoot': str(self.base / 'another-world')})
        binding = json.loads((Path(result['stateDir']) / 'studio-world.json').read_text('utf-8'))
        self.assertEqual(binding['serverRoot'], str(self.game.resolve()))

    def test_game_directory_cannot_be_used_as_studio_data(self):
        for selected in (self.game, self.game / 'studio-data', self.game.parent):
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError, 'outside'):
                self.resolve(root=self.game, state=selected)

    def test_corrupt_or_wrong_schema_settings_have_actionable_error(self):
        self.settings.parent.mkdir(parents=True)
        for raw in ('broken', '[]', '{"schema":2,"serverRoot":"game"}', '{"schema":1,"serverRoot":"game","port":0}'):
            self.settings.write_text(raw, 'utf-8')
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'Install Studio.bat'):
                load_settings(self.settings)

    def test_utf8_bom_settings_are_supported(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({'schema':1,'serverRoot':str(self.game),'port':8765}), 'utf-8-sig')
        self.assertEqual(load_settings(self.settings)['port'], 8765)
