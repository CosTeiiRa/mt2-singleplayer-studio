"""Brief Windows sharing conflicts must not discard an add-on state update."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from metin2_studio.addons.hubcore.manager import _atomic_bytes


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.target = self.directory / 'state.json'
        self.target.write_bytes(b'original')

    def sharing_error(self, code):
        error = PermissionError('File is temporarily locked')
        error.winerror = code
        return error

    def test_transient_windows_reader_keeps_original_until_replacement_succeeds(self):
        replace = os.replace
        attempts = []

        def temporarily_locked(source, destination):
            self.assertEqual(self.target.read_bytes(), b'original')
            self.assertEqual(Path(source).read_bytes(), b'revised')
            attempts.append(source)
            if len(attempts) < 3:
                raise self.sharing_error(32)
            replace(source, destination)

        with patch('metin2_studio.addons.hubcore.manager.os.replace', side_effect=temporarily_locked), \
                patch('metin2_studio.filesystem.time.sleep'):
            _atomic_bytes(self.target, b'revised')
        self.assertEqual(self.target.read_bytes(), b'revised')
        self.assertEqual(list(self.directory.iterdir()), [self.target])

    def test_persistent_windows_lock_preserves_original_and_cleans_staging(self):
        with patch('metin2_studio.addons.hubcore.manager.os.replace', side_effect=self.sharing_error(5)), \
                patch('metin2_studio.filesystem.time.sleep'), self.assertRaises(PermissionError):
            _atomic_bytes(self.target, b'revised')
        self.assertEqual(self.target.read_bytes(), b'original')
        self.assertEqual(list(self.directory.iterdir()), [self.target])

    def test_unrelated_permission_failure_is_reported_without_retry(self):
        with patch('metin2_studio.addons.hubcore.manager.os.replace', side_effect=PermissionError(13, 'Denied')) as replace, \
                patch('metin2_studio.filesystem.time.sleep') as sleep, self.assertRaises(PermissionError):
            _atomic_bytes(self.target, b'revised')
        replace.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b'original')
