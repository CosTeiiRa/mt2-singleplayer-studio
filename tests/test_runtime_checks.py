"""Content verification must use the unprivileged game identity."""
from pathlib import Path
import subprocess
import sys
import tempfile
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_checks import verify, verify_quest_access


class QuestAccessTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parents[1] / '.test-tmp'
        self.test_root.mkdir(exist_ok=True)
        self.studio = SimpleNamespace(compose=Path('.'), sources={}, root=Path('.'),
                                      workspace=SimpleNamespace(tracked=lambda **kwargs: [], deferred_paths=lambda: set()))

    def test_permission_failure_prevents_success_even_without_custom_drops(self):
        run = SimpleNamespace(returncode=1, stdout='', stderr='Permission denied')
        with patch('runtime_checks.subprocess.run', return_value=run) as command:
            result = verify(self.studio)
        self.assertFalse(result['questAccess']['readable'])
        self.assertIn('not readable', result['issues'][0])
        args = command.call_args.args[0]
        self.assertEqual(args[:9], ['docker', 'compose', 'exec', '-T', '--user', 'metin2', 'game', 'sh', '-c'])

    def test_success_reports_the_number_actually_read(self):
        run = SimpleNamespace(returncode=0, stdout='Quest state files readable: 230\n')
        with patch('runtime_checks.subprocess.run', return_value=run):
            result = verify(self.studio)
        self.assertEqual(result['issues'], [])
        self.assertTrue(result['questAccess']['readable'])
        self.assertIn('230', result['questAccess']['detail'])

    def test_unavailable_probe_is_not_reported_as_verified(self):
        with patch('runtime_checks.subprocess.run', side_effect=subprocess.TimeoutExpired('docker', 30)):
            result = verify_quest_access(self.studio)
        self.assertFalse(result['readable'])
        self.assertIn('could not be verified', result['issue'])

    def custom_quest(self, directory):
        self.studio.root = Path(directory)
        game = self.studio.root / 'linux-port/docker/game'
        sources = game / 'custom-quests'
        sources.mkdir(parents=True)
        (game / 'Dockerfile').write_bytes(b'# SERVER-STUDIO CUSTOM QUESTS\n')
        raw = b'quest studio_fixture begin\r\n state start begin\r\n end\r\nend\r\n'
        (sources / 'studio_fixture.quest').write_bytes(raw)
        return game, hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()

    def test_custom_quest_requires_its_saved_source_and_compiled_state(self):
        test_root = self.test_root
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            assert Path(directory).resolve().is_relative_to(test_root.resolve())
            _, expected = self.custom_quest(directory)
            with patch('runtime_checks.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='')) as command:
                result = verify_quest_access(self.studio)
            self.assertFalse(result['readable'])
            self.assertIn('custom quest', result['issue'])
            script = command.call_args.args[0][-1]
            self.assertIn('studio_fixture.quest', script)
            self.assertIn('object/state/studio_fixture', script)
            self.assertIn(expected, script)

    def test_custom_quest_success_reports_the_verified_count(self):
        test_root = self.test_root
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            assert Path(directory).resolve().is_relative_to(test_root.resolve())
            self.custom_quest(directory)
            with patch('runtime_checks.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='Quest files verified')):
                result = verify_quest_access(self.studio)
            self.assertTrue(result['readable'])
            self.assertEqual(result['customQuests'], 1)

    def test_deferred_build_integration_does_not_require_custom_quests_in_game_update(self):
        test_root = self.test_root
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            assert Path(directory).resolve().is_relative_to(test_root.resolve())
            self.custom_quest(directory)
            self.studio.workspace.deferred_paths = lambda: {'linux-port/docker/game/Dockerfile'}
            with patch('runtime_checks.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='Quest files readable')) as command:
                result = verify_quest_access(self.studio)
            self.assertTrue(result['readable'])
            self.assertEqual(result['customQuests'], 0)
            self.assertNotIn('studio_fixture', command.call_args.args[0][-1])
