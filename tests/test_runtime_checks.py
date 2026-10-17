"""Content verification must use the unprivileged game identity."""
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_checks import verify, verify_quest_access


class QuestAccessTests(unittest.TestCase):
    def setUp(self):
        self.studio = SimpleNamespace(compose=Path('.'), sources={}, root=Path('.'),
                                      workspace=SimpleNamespace(tracked=lambda: []))

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
